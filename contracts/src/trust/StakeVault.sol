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
/// Three claims on an agent's stake are tracked separately so none can erase another:
///  - `Stake.locked`: per-action locks, taken by the agent (`lockForAction`) and
///    released by the AIS registry (`releaseLock`).
///  - `disputeLockedOf`: amounts held by open disputes, released only by `resolveDispute`.
///  - `unbondingOf`: stake queued for withdrawal, waiting out `unbondingDelay`.
/// Invariant: `locked + disputeLockedOf + unbonding <= amount`.
///
/// Withdrawal is request -> wait -> withdraw (`requestUnstake` / `withdraw`). Without the
/// delay an agent could front-run its own freezing checkpoint in the mempool and pull its
/// free stake before the freeze lands. Queued stake stays inside `amount`: it is still
/// frozen by `onCheckpoint`, and `raiseDispute` can take it back out of the queue.
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

    /// @dev Hard bounds on `unbondingDelay`. The floor keeps governance from disabling the
    /// delay; the ceiling keeps it from trapping honest stake indefinitely.
    uint256 public constant MIN_UNBONDING_DELAY = 1 days;
    uint256 public constant MAX_UNBONDING_DELAY = 30 days;

    struct Unbonding {
        uint256 amount;
        uint256 releaseAt;
    }

    uint256 public disputeWindow = 3 days;
    /// @notice Wait between `requestUnstake` and `withdraw`. Default exceeds `disputeWindow`
    /// so a dispute raised at request time can resolve before the funds leave.
    uint256 public unbondingDelay = 7 days;
    uint32 public freezeThreshold;

    mapping(address agent => Stake) internal _stakes;
    mapping(address agent => uint256) public disputeLockedOf;
    mapping(address agent => Unbonding) public unbondingOf;
    mapping(uint256 => Dispute) public disputes;
    uint256 public nextDisputeId;

    event Staked(address indexed agent, uint256 amount);
    event UnstakeRequested(address indexed agent, uint256 amount, uint256 totalQueued, uint256 releaseAt);
    event UnstakeCancelled(address indexed agent, uint256 amount);
    event Unstaked(address indexed agent, uint256 amount);
    event UnbondingDelayUpdated(uint256 newDelay);
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
    error UnbondingNotElapsed();
    error NothingUnbonding();
    error UnbondingDelayOutOfBounds();

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

    /// @notice True free stake: amount - locked - open-dispute holds - queued withdrawals.
    /// @dev Consumers must use this, never `stakeOf().amount - stakeOf().locked`, which
    /// overstates free stake whenever a dispute is open or a withdrawal is queued.
    function availableOf(address agent) external view returns (uint256) {
        return _available(agent);
    }

    /// @notice Stake a dispute may hold: free stake PLUS queued withdrawals. Queuing a
    /// withdrawal must not shrink what is slashable.
    function disputableOf(address agent) external view returns (uint256) {
        return _disputable(agent);
    }

    function _disputable(address agent) internal view returns (uint256) {
        Stake storage s = _stakes[agent];
        return s.amount - s.locked - disputeLockedOf[agent];
    }

    function _available(address agent) internal view returns (uint256) {
        return _disputable(agent) - unbondingOf[agent].amount;
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

    /// @notice Sets the unbonding delay within the hard bounds. Applies to requests made
    /// afterwards only: an in-flight request keeps the `releaseAt` it was given.
    function setUnbondingDelay(uint256 newDelay) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (newDelay < MIN_UNBONDING_DELAY || newDelay > MAX_UNBONDING_DELAY) revert UnbondingDelayOutOfBounds();
        unbondingDelay = newDelay;
        emit UnbondingDelayUpdated(newDelay);
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

    /// @notice Queues `amount` of free stake for withdrawal after `unbondingDelay`.
    /// @dev Moves no tokens. Adding to an existing queue restarts the clock for the whole
    /// queue, so repeated small requests cannot be used to pre-age a large exit.
    function requestUnstake(uint256 amount) external {
        if (amount == 0) revert ZeroAmount();
        if (_stakes[msg.sender].frozen) revert StakeFrozen();
        if (_available(msg.sender) < amount) revert InsufficientAvailableStake();
        Unbonding storage u = unbondingOf[msg.sender];
        u.amount += amount;
        u.releaseAt = block.timestamp + unbondingDelay;
        emit UnstakeRequested(msg.sender, amount, u.amount, u.releaseAt);
    }

    /// @notice Returns the whole queue to free stake. Allowed while frozen: it only makes
    /// the stake more available to the protocol, never less.
    function cancelUnstake() external {
        uint256 amount = unbondingOf[msg.sender].amount;
        if (amount == 0) revert NothingUnbonding();
        delete unbondingOf[msg.sender];
        emit UnstakeCancelled(msg.sender, amount);
    }

    /// @notice Pays out the queue once its delay has elapsed.
    /// @dev Slashing backstop: a frozen agent may not withdraw ANY stake, independent of the
    /// execute-time gate. The frozen check runs here, at payout, so a freeze that lands at
    /// any point during the delay still holds the collateral in place.
    function withdraw() external nonReentrant {
        Unbonding memory u = unbondingOf[msg.sender];
        if (u.amount == 0) revert NothingUnbonding();
        if (_stakes[msg.sender].frozen) revert StakeFrozen();
        if (block.timestamp < u.releaseAt) revert UnbondingNotElapsed();
        delete unbondingOf[msg.sender];
        _stakes[msg.sender].amount -= u.amount;
        itk.safeTransfer(msg.sender, u.amount);
        emit Unstaked(msg.sender, u.amount);
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

    /// @notice Opens a dispute, holding `amount` of `agent`'s stake, drawing on queued
    /// withdrawals if free stake is short. Moves no funds.
    function raiseDispute(address agent, uint256 amount, string calldata reason)
        external
        onlyRole(DISPUTER_ROLE)
        returns (uint256 disputeId)
    {
        if (amount == 0) revert ZeroAmount();
        if (_disputable(agent) < amount) revert InsufficientAvailableStake();

        // Take any shortfall out of the withdrawal queue, so queued stake stays slashable.
        uint256 free = _available(agent);
        if (free < amount) {
            unbondingOf[agent].amount -= amount - free;
        }
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
