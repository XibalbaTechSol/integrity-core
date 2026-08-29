// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title IntegrityGovernance
/// @notice Token-weighted, timelocked governance for the Integrity Protocol. Implements the
/// exact lifecycle the dashboard's GovernancePanel documents as the roadmap: a proposal is
/// created by locking ITK, ITK holders lock tokens to vote FOR/AGAINST during a fixed window,
/// a passing proposal is queued behind a timelock, then executed as a single on-chain call.
///
/// @dev Vote weight is deliberately **lock-to-vote**, not `ERC20Votes`/checkpoint-based:
/// `IntegrityToken` is a plain ERC20 with no `getPastVotes` surface, and — critically — it
/// removed fee-on-transfer specifically so `transferFrom(voter, address(this), amount)` credits
/// exactly `amount` (see IntegrityToken NatSpec). Locking real ITK for the duration of a vote
/// is therefore both accurate and flash-loan/sybil resistant: a flash-borrowed balance can't
/// vote because it can't stay locked across the voting window. Voters reclaim their locked ITK
/// via {withdraw} once a proposal reaches a terminal state.
///
/// The execute leg — the single highest-risk surface in any governance contract — is hand-rolled
/// but constrained hard: the target/value/calldata are fixed at proposal time and executed
/// verbatim (there is no accept-actions-at-execute path, so a proposal's actions cannot be
/// mutated between vote and execution), execution is `nonReentrant`, and it is gated on both a
/// timelock ETA and a bounded grace window.
contract IntegrityGovernance is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    /// @notice The state a proposal is in, derived purely from stored data + block.timestamp.
    enum ProposalState {
        Active, // voting window open
        Defeated, // window closed, quorum unmet or againstVotes >= forVotes
        Succeeded, // window closed, passed, not yet queued
        Queued, // queued behind the timelock, awaiting ETA
        Executed, // action executed
        Expired, // queued but not executed within the grace period
        Canceled // canceled by proposer or guardian before execution
    }

    struct Proposal {
        address proposer;
        address target;
        uint256 value;
        bytes callData;
        uint64 startTime;
        uint64 endTime;
        uint64 eta; // 0 until queued
        uint256 forVotes;
        uint256 againstVotes;
        bool executed;
        bool canceled;
        string description;
    }

    struct Receipt {
        bool hasVoted;
        bool support;
        uint256 votes; // ITK locked by this voter on this proposal
    }

    /// @notice Grace window after the ETA during which a queued proposal may still execute.
    /// Past this it becomes {Expired} and its locked ITK is reclaimable — a stuck proposal
    /// can never permanently trap voter funds.
    uint256 public constant GRACE_PERIOD = 14 days;

    IERC20 public immutable itk;
    /// @notice Duration of the voting window, in seconds.
    uint256 public immutable votingPeriod;
    /// @notice Delay between a proposal succeeding-and-queued and being executable, in seconds.
    uint256 public immutable timelockDelay;
    /// @notice ITK a proposer must lock to open a proposal (counted as their initial FOR vote).
    uint256 public immutable proposalThreshold;
    /// @notice Minimum total participating votes (for + against) for a result to be valid.
    uint256 public immutable quorumVotes;

    uint256 public proposalCount;
    mapping(uint256 => Proposal) private _proposals;
    mapping(uint256 => mapping(address => Receipt)) public receipts;

    event ProposalCreated(
        uint256 indexed id, address indexed proposer, address target, uint256 value, string description
    );
    event VoteCast(uint256 indexed id, address indexed voter, bool support, uint256 amount);
    event ProposalQueued(uint256 indexed id, uint64 eta);
    event ProposalExecuted(uint256 indexed id, bytes returnData);
    event ProposalCanceled(uint256 indexed id);
    event Withdrawn(uint256 indexed id, address indexed voter, uint256 amount);

    error InvalidProposal();
    error NotActive();
    error AlreadyVoted();
    error VoteSideMismatch();
    error ZeroAmount();
    error NotSucceeded();
    error NotQueued();
    error TimelockNotElapsed();
    error ProposalStale();
    error NotWithdrawable();
    error NothingToWithdraw();
    error Unauthorized();
    error ExecutionFailed();
    error BadConfig();

    /// @param admin Guardian address (Ownable owner) able to cancel a malicious proposal.
    /// @param itk_ The ITK token locked for proposing/voting.
    /// @param votingPeriod_ Voting window in seconds (must be > 0).
    /// @param timelockDelay_ Timelock delay in seconds (may be 0 for local/test configs).
    /// @param proposalThreshold_ ITK locked to propose, also the proposer's initial FOR vote.
    /// @param quorumVotes_ Minimum total participating votes for validity.
    constructor(
        address admin,
        IERC20 itk_,
        uint256 votingPeriod_,
        uint256 timelockDelay_,
        uint256 proposalThreshold_,
        uint256 quorumVotes_
    ) Ownable(admin) {
        if (address(itk_) == address(0) || votingPeriod_ == 0 || proposalThreshold_ == 0) revert BadConfig();
        itk = itk_;
        votingPeriod = votingPeriod_;
        timelockDelay = timelockDelay_;
        proposalThreshold = proposalThreshold_;
        quorumVotes = quorumVotes_;
    }

    /// @notice Opens a proposal to run `target.call{value}(callData)` if it passes. The caller
    /// locks `proposalThreshold` ITK, recorded as their initial FOR vote (so proposing is itself
    /// flash-loan resistant and the proposer has skin in the game). Reclaimable via {withdraw}
    /// once the proposal is terminal.
    function propose(address target, uint256 value, bytes calldata callData, string calldata description)
        external
        nonReentrant
        returns (uint256 id)
    {
        if (target == address(0)) revert InvalidProposal();

        id = ++proposalCount;
        Proposal storage p = _proposals[id];
        p.proposer = msg.sender;
        p.target = target;
        p.value = value;
        p.callData = callData;
        p.startTime = uint64(block.timestamp);
        p.endTime = uint64(block.timestamp + votingPeriod);
        p.description = description;

        // Proposer's locked threshold is their initial FOR vote.
        itk.safeTransferFrom(msg.sender, address(this), proposalThreshold);
        p.forVotes = proposalThreshold;
        receipts[id][msg.sender] = Receipt({hasVoted: true, support: true, votes: proposalThreshold});

        emit ProposalCreated(id, msg.sender, target, value, description);
        emit VoteCast(id, msg.sender, true, proposalThreshold);
    }

    /// @notice Locks `amount` ITK as a vote on proposal `id`. A voter may add to their position
    /// but cannot vote on both sides. Locked ITK is reclaimable via {withdraw} once terminal.
    function castVote(uint256 id, bool support, uint256 amount) external nonReentrant {
        if (state(id) != ProposalState.Active) revert NotActive();
        if (amount == 0) revert ZeroAmount();

        Receipt storage r = receipts[id][msg.sender];
        if (r.hasVoted && r.support != support) revert VoteSideMismatch();

        itk.safeTransferFrom(msg.sender, address(this), amount);

        Proposal storage p = _proposals[id];
        if (support) {
            p.forVotes += amount;
        } else {
            p.againstVotes += amount;
        }
        r.hasVoted = true;
        r.support = support;
        r.votes += amount;

        emit VoteCast(id, msg.sender, support, amount);
    }

    /// @notice Queues a succeeded proposal behind the timelock, setting its ETA.
    function queue(uint256 id) external {
        if (state(id) != ProposalState.Succeeded) revert NotSucceeded();
        Proposal storage p = _proposals[id];
        uint64 eta = uint64(block.timestamp + timelockDelay);
        p.eta = eta;
        emit ProposalQueued(id, eta);
    }

    /// @notice Executes a queued proposal after its ETA and within the grace period. The stored
    /// action is executed verbatim; `nonReentrant` guards the external call.
    function execute(uint256 id) external payable nonReentrant returns (bytes memory returnData) {
        if (state(id) != ProposalState.Queued) revert NotQueued();
        Proposal storage p = _proposals[id];
        if (block.timestamp < p.eta) revert TimelockNotElapsed();

        p.executed = true;
        bool ok;
        (ok, returnData) = p.target.call{value: p.value}(p.callData);
        if (!ok) revert ExecutionFailed();

        emit ProposalExecuted(id, returnData);
    }

    /// @notice Cancels a proposal before it executes. Callable by the proposer or the guardian
    /// (owner). Voters can then {withdraw} their locked ITK.
    function cancel(uint256 id) external {
        Proposal storage p = _proposals[id];
        if (p.proposer == address(0)) revert InvalidProposal();
        if (p.executed || p.canceled) revert InvalidProposal();
        if (msg.sender != p.proposer && msg.sender != owner()) revert Unauthorized();
        p.canceled = true;
        emit ProposalCanceled(id);
    }

    /// @notice Reclaims the caller's ITK locked on proposal `id`, once the proposal can no
    /// longer be executed (Defeated / Executed / Expired / Canceled). While a proposal is
    /// Active, Succeeded, or Queued its stake stays locked.
    function withdraw(uint256 id) external nonReentrant {
        ProposalState s = state(id);
        if (
            s != ProposalState.Defeated && s != ProposalState.Executed && s != ProposalState.Expired
                && s != ProposalState.Canceled
        ) revert NotWithdrawable();

        Receipt storage r = receipts[id][msg.sender];
        uint256 amount = r.votes;
        if (amount == 0) revert NothingToWithdraw();
        r.votes = 0;

        itk.safeTransfer(msg.sender, amount);
        emit Withdrawn(id, msg.sender, amount);
    }

    /// @notice Derives a proposal's current state from stored data + `block.timestamp`.
    function state(uint256 id) public view returns (ProposalState) {
        Proposal storage p = _proposals[id];
        if (p.proposer == address(0)) revert InvalidProposal();
        if (p.canceled) return ProposalState.Canceled;
        if (p.executed) return ProposalState.Executed;
        if (block.timestamp <= p.endTime) return ProposalState.Active;

        // Voting window closed — decide the outcome.
        uint256 total = p.forVotes + p.againstVotes;
        if (total < quorumVotes || p.forVotes <= p.againstVotes) {
            return ProposalState.Defeated;
        }
        if (p.eta == 0) return ProposalState.Succeeded;
        if (block.timestamp > uint256(p.eta) + GRACE_PERIOD) return ProposalState.Expired;
        return ProposalState.Queued;
    }

    /// @notice Full proposal record (calldata included) for a given id. Reverts on unknown id.
    function getProposal(uint256 id) external view returns (Proposal memory) {
        Proposal storage p = _proposals[id];
        if (p.proposer == address(0)) revert InvalidProposal();
        return p;
    }

    /// @notice The caller-agnostic receipt for a specific voter on a proposal.
    function getReceipt(uint256 id, address voter) external view returns (Receipt memory) {
        return receipts[id][voter];
    }
}
