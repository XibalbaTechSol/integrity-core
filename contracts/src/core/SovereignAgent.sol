// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IAccount} from "./IAccount.sol";

/// @title SovereignAgent
/// @notice The per-agent on-chain account for a single AI ("Sovereign") agent.
/// @dev One instance is deployed per agent by `AgentFactory`. It is intentionally a thin
/// account: identity + a cached reputation score + a generic `execute`. Everything
/// heavier (staking, slashing, cross-chain sync, HIPAA gating) lives in the shared
/// oracle/framework/health contracts and simply *reads* this contract's controller/DID,
/// rather than being folded into it — that keeps a compromise of one agent's logic from
/// being able to reach into protocol-wide state it has no business touching.
contract SovereignAgent is AccessControl, IAccount {
    /// @dev Granted to the integrity-oracle backend's signer so it can push AIS cache
    /// updates. Deliberately *not* the same key as DEFAULT_ADMIN_ROLE (the controller):
    /// the oracle should never be able to rotate control of the agent or execute calls
    /// on its behalf, only report a score.
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    /// @dev Off-chain DID string this account is bound to, e.g.
    /// `did:integrity:9f1c...`. Set once at construction; the AgentFactory is
    /// responsible for ensuring DID uniqueness registry-wide (see AgentFactory.sol).
    string private _agentDID;

    /// @notice Cached Agent Integrity Score last reported by the oracle. This is a cache
    /// of `ReputationRegistry`'s value for cheap on-chain reads (e.g. by other
    /// contracts gating access on "this agent's score"); ReputationRegistry remains the
    /// canonical, cross-agent source of truth.
    uint256 public ais;

    /// @notice Monotonic nonce, bumped on every `execute`. Lets off-chain indexers
    /// (integrity-oracle, integrity-dashboard) correlate on-chain actions with the
    /// BCC commitments (`nonce` field, §4.2) an agent submitted off-chain.
    uint256 public executionNonce;

    /// @notice The factory that deployed this agent (informational / for indexers).
    address public immutable factory;

    event AISUpdated(uint256 oldScore, uint256 newScore);
    event ControllerRotated(address indexed oldController, address indexed newController);
    event AgentExecuted(address indexed target, uint256 value, bytes data, uint256 nonce);

    error NotController();

    modifier onlyController() {
        if (!hasRole(DEFAULT_ADMIN_ROLE, msg.sender)) revert NotController();
        _;
    }

    constructor(string memory did_, address controller_, address oracle_, address factory_) {
        require(controller_ != address(0), "SovereignAgent: zero controller");
        _agentDID = did_;
        factory = factory_;

        _grantRole(DEFAULT_ADMIN_ROLE, controller_);
        if (oracle_ != address(0)) {
            _grantRole(ORACLE_ROLE, oracle_);
        }
        // Baseline score before the oracle has ever reported one. 0 rather than an
        // arbitrary "starting reputation" — a nonzero default would let a freshly
        // created, never-scored agent masquerade as one with an established track
        // record in any downstream threshold check (e.g. health/EHRGate.sol).
        ais = 0;
    }

    /// @inheritdoc IAccount
    function agentDID() external view returns (string memory) {
        return _agentDID;
    }

    /// @inheritdoc IAccount
    /// @dev Arbitrary external call gated to the controller only. Bubbles up the revert
    /// reason from the callee verbatim (via the assembly block) so failures are
    /// debuggable from the controller's perspective instead of collapsing to a generic
    /// "call failed".
    function execute(address target, uint256 value, bytes calldata data)
        external
        onlyController
        returns (bytes memory)
    {
        uint256 nonce = ++executionNonce;
        (bool success, bytes memory result) = target.call{value: value}(data);
        if (!success) {
            assembly {
                revert(add(result, 32), mload(result))
            }
        }
        emit AgentExecuted(target, value, data, nonce);
        return result;
    }

    /// @inheritdoc IAccount
    function updateAIS(uint256 newScore) external onlyRole(ORACLE_ROLE) {
        uint256 old = ais;
        ais = newScore;
        emit AISUpdated(old, newScore);
    }

    /// @notice Rotates control of the agent to a new address.
    /// @dev Only the *current* controller may do this (a single AccessControl role,
    /// not an NFT-ownership check as older prototypes used) — collapsing "who can act
    /// as this agent" into one role avoids the two-sources-of-truth bug where an NFT
    /// transfer and a role grant could disagree about who is actually in control.
    function rotateController(address newController) external onlyController {
        require(newController != address(0), "SovereignAgent: zero controller");
        _revokeRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(DEFAULT_ADMIN_ROLE, newController);
        emit ControllerRotated(msg.sender, newController);
    }

    /// @notice Lets the account receive native value (e.g. refunds from `execute` calls).
    receive() external payable {}
}
