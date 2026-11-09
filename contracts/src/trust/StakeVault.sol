// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ERC20Burnable} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Burnable.sol";

/// @title StakeVault
/// @notice Holds agents' ITK stake for the Integrity Protocol v2 trust layer: per-action
/// locks, a LATCHING score-driven freeze, and a dispute-gated burn.
/// @dev Plain singleton with a constructor (not an EIP-1167 clone like `Slasher`).
/// Stake/dispute shapes are ported from `src/oracle/Slasher.sol`, including
/// burn-not-treasury: slashed ITK is burned, so no address profits from a slash.
///
/// Locks come in two kinds, tracked separately so neither can erase the other:
///  - `Stake.locked`: per-action locks, taken by the agent (`lockForAction`) and
///    released by the AIS registry (`releaseLock`).
///  - `disputeLockedOf`: amounts held by open disputes, released only by `resolveDispute`.
/// Invariant: `locked + disputeLockedOf <= amount` (hence `locked <= amount`).
///
/// Freeze is a latch: `onCheckpoint` can set `frozen` but never clear it. Only admin
/// `unfreeze` clears it. `resolveDispute` deliberately does not touch `frozen`.
contract StakeVault is AccessControl, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant DISPUTER_ROLE = keccak256("DISPUTER_ROLE");
    bytes32 public constant AIS_REGISTRY_ROLE = keccak256("AIS_REGISTRY_ROLE");

    struct Stake {
        uint256 amount;
        uint256 locked;
        bool frozen;
    }

    struct Dispute {
        address agent;
        uint256 amount;
        uint256 raisedAt;
        bool resolved;
        bool slashed;
        string reason;
    }

    IERC20 public immutable itk;

    uint256 public disputeWindow = 3 days;
    uint32 public freezeThreshold;

    mapping(address agent => Stake) internal _stakes;
    mapping(address agent => uint256) public disputeLockedOf;
    mapping(uint256 => Dispute) public disputes;
    uint256 public nextDisputeId;

    event Staked(address indexed agent, uint256 amount);
    event Unstaked(address indexed agent, uint256 amount);
    event Locked(address indexed agent, uint256 amount);
    event LockReleased(address indexed agent, uint256 amount);
    event Frozen(address indexed agent, uint32 score);
    event Unfrozen(address indexed agent);
    event FreezeThresholdUpdated(uint32 newThreshold);
    event DisputeWindowUpdated(uint256 newWindow);
    event DisputeRaised(uint256 indexed disputeId, address indexed agent, uint256 amount, string reason);
    event DisputeResolved(uint256 indexed disputeId, address indexed agent, bool slashed, uint256 amount);

    error ZeroAmount();
    error InsufficientAvailableStake();
    error StakeFrozen();
    error NotAgent();
    error DisputeNotFound();
    error DisputeAlreadyResolved();
    error ChallengeWindowNotElapsed();

    constructor(address _itk, address admin) {
        itk = IERC20(_itk);
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    // ---------------------------------------------------------------- views

    /// @notice Stake record for `agent`; the gate reads `frozen` from here.
    /// @dev `locked` covers per-action locks only, NOT open-dispute holds. Consumers must
    /// use `availableOf`, never `amount - locked`, to learn free stake.
    function stakeOf(address agent) external view returns (Stake memory) {
        return _stakes[agent];
    }

    /// @notice True free stake: amount - locked - open-dispute holds.
    /// @dev Consumers must use this, never `stakeOf().amount - stakeOf().locked`, which
    /// overstates free stake whenever a dispute is open.
    function availableOf(address agent) external view returns (uint256) {
        return _available(agent);
    }

    function _available(address agent) internal view returns (uint256) {
        Stake storage s = _stakes[agent];
        return s.amount - s.locked - disputeLockedOf[agent];
    }

    // ---------------------------------------------------------------- admin

    function setFreezeThreshold(uint32 newThreshold) external onlyRole(DEFAULT_ADMIN_ROLE) {
        freezeThreshold = newThreshold;
        emit FreezeThresholdUpdated(newThreshold);
    }

    function setDisputeWindow(uint256 newWindow) external onlyRole(DEFAULT_ADMIN_ROLE) {
        disputeWindow = newWindow;
        emit DisputeWindowUpdated(newWindow);
    }

    /// @notice The only way (besides redeploy) to clear the freeze latch.
    function unfreeze(address agent) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _stakes[agent].frozen = false;
        emit Unfrozen(agent);
    }

    // ---------------------------------------------------------------- stake

    function stake(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        _stakes[msg.sender].amount += amount;
        itk.safeTransferFrom(msg.sender, address(this), amount);
        emit Staked(msg.sender, amount);
    }

    /// @notice Withdraws only the unlocked portion (amount - locked - dispute holds).
    /// @dev Slashing backstop: a frozen agent may not withdraw ANY stake, independent of the
    /// execute-time gate. Freeze latches collateral in place so it stays slashable until governance
    /// `unfreeze`s; without this check a frozen agent could drain its available stake before a
    /// `DISPUTER` holds it, defeating the freeze's purpose.
    function unstake(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        if (_stakes[msg.sender].frozen) revert StakeFrozen();
        if (_available(msg.sender) < amount) revert InsufficientAvailableStake();
        _stakes[msg.sender].amount -= amount;
        itk.safeTransfer(msg.sender, amount);
        emit Unstaked(msg.sender, amount);
    }

    // ---------------------------------------------------------------- action locks

    /// @notice Locks `req` of the caller's own stake for an action. Only the agent may
    /// lock its own stake, so no third party can grief it by locking it up.
    function lockForAction(address agent, uint256 req) external {
        if (msg.sender != agent) revert NotAgent();
        if (_available(agent) < req) revert InsufficientAvailableStake();
        _stakes[agent].locked += req;
        emit Locked(agent, req);
    }

    /// @notice Releases up to `amount` of action lock; clamps to `locked`, never underflows.
    /// Cannot release dispute holds.
    function releaseLock(address agent, uint256 amount) external onlyRole(AIS_REGISTRY_ROLE) {
        Stake storage s = _stakes[agent];
        uint256 rel = amount < s.locked ? amount : s.locked;
        s.locked -= rel;
        emit LockReleased(agent, rel);
    }

    // ---------------------------------------------------------------- freeze latch

    /// @notice Latching freeze: a score below the threshold freezes; nothing here clears it.
    function onCheckpoint(address agent, uint32 score) external onlyRole(AIS_REGISTRY_ROLE) {
        if (score < freezeThreshold) {
            _stakes[agent].frozen = true;
            emit Frozen(agent, score);
        }
    }

    // ---------------------------------------------------------------- disputes

    /// @notice Opens a dispute, holding `amount` of `agent`'s stake. Moves no funds.
    function raiseDispute(address agent, uint256 amount, string calldata reason)
        external
        onlyRole(DISPUTER_ROLE)
        returns (uint256 disputeId)
    {
        if (amount == 0) revert ZeroAmount();
        if (_available(agent) < amount) revert InsufficientAvailableStake();

        disputeLockedOf[agent] += amount;
        disputeId = nextDisputeId++;
        disputes[disputeId] = Dispute({
            agent: agent,
            amount: amount,
            raisedAt: block.timestamp,
            resolved: false,
            slashed: false,
            reason: reason
        });

        emit DisputeRaised(disputeId, agent, amount, reason);
    }

    /// @notice Arbiter resolves after the window: burn the held amount, or release it.
    /// @dev Deliberately does NOT clear `frozen` — the freeze latch is governance-durable and only
    /// admin `unfreeze` lifts it (R4). Resolving a dispute, even in the agent's favour, leaves any
    /// score-driven freeze in place; the two controls are orthogonal by design (see commit
    /// `f3403434` "pin freeze latch across resolveDispute").
    function resolveDispute(uint256 disputeId, bool slash) external onlyRole(DEFAULT_ADMIN_ROLE) nonReentrant {
        Dispute storage d = disputes[disputeId];
        if (d.raisedAt == 0) revert DisputeNotFound();
        if (d.resolved) revert DisputeAlreadyResolved();
        if (block.timestamp < d.raisedAt + disputeWindow) revert ChallengeWindowNotElapsed();

        d.resolved = true;
        d.slashed = slash;
        disputeLockedOf[d.agent] -= d.amount;

        if (slash) {
            _stakes[d.agent].amount -= d.amount;
            ERC20Burnable(address(itk)).burn(d.amount);
        }

        emit DisputeResolved(disputeId, d.agent, slash, d.amount);
    }
}
