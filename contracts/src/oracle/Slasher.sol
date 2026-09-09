// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {AccessControlUpgradeable} from "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IntegrityToken} from "./IntegrityToken.sol";

/// @title Slasher
/// @notice Holds agents' $ITK collateral and executes programmatic, dispute-gated
/// slashing when an agent is found to have violated protocol rules.
/// @dev Self-contained: unlike the old prototype's Slasher (which read "deals" from a
/// separate marketplace contract not in this rewrite's scope), staking and dispute
/// state both live here, so this contract's guarantees don't depend on an external
/// contract this package doesn't control.
///
/// Why a dispute window exists at all: DISPUTER_ROLE is meant to be held by the
/// integrity-oracle backend, which raises a dispute automatically off the back of an
/// automated signal (e.g. a BCC commitment that didn't match the agent's actual
/// on-chain action). Automated signals can be wrong — a bug in the oracle, a
/// mis-parsed payload, a compromised oracle signing key. If `raiseDispute` could
/// immediately move funds, a single bad oracle report (or a briefly compromised oracle
/// key) could destroy an agent's entire stake before any human ever looked at it.
/// Instead, raising a dispute only *locks* the disputed amount (the agent can't
/// withdraw it, so it can't be front-run away), and actual fund movement
/// (`resolveDispute`) requires both (a) the challenge window to have fully elapsed,
/// giving the agent/operator time to present counter-evidence off-chain, and (b) a
/// separate arbiter role (DEFAULT_ADMIN_ROLE, expected to be a multisig/governance
/// address, not the same key as DISPUTER_ROLE) to make the actual call.
/// @dev Per-agent EIP-1167 clone (see AgentPrimitivesFactory). `itk` stays a real
/// Solidity `immutable` rather than an `initialize()` parameter: it is baked into the
/// implementation contract's own runtime bytecode at that implementation's one-time
/// deployment, and since every clone delegatecalls into that same bytecode, every
/// agent's Slasher clone reads the identical, correct $ITK address for free — no need to
/// spend a storage write repeating a value that never varies per agent. `admin`
/// (arbiter) and `disputer` DO vary in spirit (they're protocol-governance/oracle
/// signers, not the agent) but are passed as `initialize()` params rather than
/// implementation-immutables so a future re-key of governance doesn't require
/// redeploying the implementation and every dependent clone.
contract Slasher is Initializable, AccessControlUpgradeable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant DISPUTER_ROLE = keccak256("DISPUTER_ROLE");

    IntegrityToken public immutable itk;

    // Slashed collateral is burned via IntegrityToken.burn (see resolveDispute) rather
    // than routed to an arbitrary treasury address — that removes any incentive for
    // whoever controls DEFAULT_ADMIN_ROLE to raise/resolve disputes for personal gain,
    // since there is no address that profits from a slash.

    /// @dev Deliberately NOT given an inline initializer (`= 3 days`) — inline field
    /// initializers compile into the *constructor*, which never runs for an EIP-1167
    /// clone (clones only ever delegatecall into `initialize`). Left as a bare
    /// declaration (defaults to 0) and set explicitly in `initialize` instead; a
    /// previous version of this contract kept the inline initializer after the
    /// Initializable conversion and every clone silently got a 0-length dispute window,
    /// meaning `resolveDispute` never actually enforced the challenge period.
    uint256 public disputeWindow;

    struct Dispute {
        address agent;
        uint256 amount;
        uint256 raisedAt;
        bool resolved;
        bool slashed;
        string reason;
    }

    mapping(address => uint256) public stakeOf;
    mapping(address => uint256) public lockedStakeOf;
    mapping(uint256 => Dispute) public disputes;
    uint256 public nextDisputeId;

    event Staked(address indexed agent, uint256 amount);
    event Unstaked(address indexed agent, uint256 amount);
    event DisputeRaised(uint256 indexed disputeId, address indexed agent, uint256 amount, string reason);
    event DisputeResolved(uint256 indexed disputeId, address indexed agent, bool slashed, uint256 amount);
    event DisputeWindowUpdated(uint256 newWindow);

    error ZeroAmount();
    error InsufficientAvailableStake();
    error DisputeNotFound();
    error DisputeAlreadyResolved();
    error ChallengeWindowNotElapsed();

    constructor(address _itk) {
        itk = IntegrityToken(_itk);
        _disableInitializers();
    }

    /// @param admin Arbiter role (DEFAULT_ADMIN_ROLE) — protocol governance, deliberately
    /// never the agent itself (see contract-level NatSpec: an agent cannot be trusted to
    /// arbitrate its own slashing dispute).
    /// @param disputer DISPUTER_ROLE — the protocol's oracle/dispute signer.
    /// @dev Uses the plain (non-upgradeable) `ReentrancyGuard`, not
    /// `ReentrancyGuardUpgradeable` — OZ 5.6.x's upgradeable package no longer ships that
    /// variant. This is safe under EIP-1167 clones without an explicit init step because
    /// `ReentrancyGuard`'s modifier only ever checks `slot == ENTERED (2)`, never
    /// `== NOT_ENTERED (1)`; a freshly-cloned contract's guard slot is zero-initialized,
    /// which is neither value, so the very first call behaves identically to a properly
    /// initialized guard. OZ's own NatSpec on that contract flags it as safe to reuse
    /// this way for exactly this reason.
    function initialize(address admin, address disputer) external initializer {
        __AccessControl_init();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        if (disputer != address(0)) {
            _grantRole(DISPUTER_ROLE, disputer);
        }
        disputeWindow = 3 days;
    }

    function setDisputeWindow(uint256 newWindow) external onlyRole(DEFAULT_ADMIN_ROLE) {
        disputeWindow = newWindow;
        emit DisputeWindowUpdated(newWindow);
    }

    function stake(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        IERC20(address(itk)).safeTransferFrom(msg.sender, address(this), amount);
        stakeOf[msg.sender] += amount;
        emit Staked(msg.sender, amount);
    }

    /// @notice Stakes on behalf of another account (e.g. pulled by AgentPrimitivesFactory during registration)
    function stakeFor(address account, uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        IERC20(address(itk)).safeTransferFrom(msg.sender, address(this), amount);
        stakeOf[account] += amount;
        emit Staked(account, amount);
    }

    /// @notice Withdraws stake. Only the *unlocked* portion (total minus whatever is
    /// currently tied up in open disputes) can be withdrawn — this is what makes
    /// `raiseDispute` meaningful; without it, an agent could see a dispute coming (or
    /// simply front-run the oracle's report in the mempool) and withdraw before the
    /// lock ever applies.
    function unstake(uint256 amount) external nonReentrant {
        if (amount == 0) revert ZeroAmount();
        uint256 available = stakeOf[msg.sender] - lockedStakeOf[msg.sender];
        if (available < amount) revert InsufficientAvailableStake();
        stakeOf[msg.sender] -= amount;
        IERC20(address(itk)).safeTransfer(msg.sender, amount);
        emit Unstaked(msg.sender, amount);
    }

    /// @notice Opens a dispute against `agent` for `amount` of their staked collateral,
    /// locking it immediately. Does not move funds — only `resolveDispute`, after the
    /// challenge window, can do that.
    function raiseDispute(address agent, uint256 amount, string calldata reason)
        external
        onlyRole(DISPUTER_ROLE)
        returns (uint256 disputeId)
    {
        if (amount == 0) revert ZeroAmount();
        uint256 available = stakeOf[agent] - lockedStakeOf[agent];
        if (available < amount) revert InsufficientAvailableStake();

        lockedStakeOf[agent] += amount;
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

    /// @notice Arbiter resolves a dispute once the challenge window has elapsed, either
    /// slashing (burning) the locked amount or releasing the lock back to the agent.
    function resolveDispute(uint256 disputeId, bool slash) external onlyRole(DEFAULT_ADMIN_ROLE) nonReentrant {
        Dispute storage d = disputes[disputeId];
        if (d.raisedAt == 0) revert DisputeNotFound();
        if (d.resolved) revert DisputeAlreadyResolved();
        if (block.timestamp < d.raisedAt + disputeWindow) revert ChallengeWindowNotElapsed();

        d.resolved = true;
        d.slashed = slash;
        lockedStakeOf[d.agent] -= d.amount;

        if (slash) {
            stakeOf[d.agent] -= d.amount;
            itk.burn(d.amount);
        }

        emit DisputeResolved(disputeId, d.agent, slash, d.amount);
    }
}
