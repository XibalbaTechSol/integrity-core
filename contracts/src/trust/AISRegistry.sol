// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {StakeVault} from "./StakeVault.sol";
import {RewardRegistry} from "./RewardRegistry.sol";
import {XibalbaAgentRegistry} from "../framework/XibalbaAgentRegistry.sol";

/// @title AISRegistry
/// @notice Singleton Agent Integrity Score (AIS) checkpoint registry for the Integrity Protocol
/// v2 trust layer. A `SCORER_ROLE` holder posts a score checkpoint per agent; the latest
/// checkpoint overwrites the prior one.
/// @dev Score is basis points in 0..10000 (uint32, never a float). `evidenceRoot` is an opaque
/// bytes32 commitment; no PHI or off-chain evidence handling happens here.
contract AISRegistry is AccessControl {
    /// @notice Role allowed to post score checkpoints.
    bytes32 public constant SCORER_ROLE = keccak256("SCORER_ROLE");

    /// @notice Maximum valid score, in basis points.
    uint32 public constant MAX_SCORE = 10000;

    struct Checkpoint {
        uint32 score;
        uint64 windowEnd;
        bytes32 evidenceRoot;
    }

    /// @notice The most recent checkpoint posted for each agent.
    mapping(address agent => Checkpoint) public latest;

    event CheckpointPosted(address indexed agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot);

    error ScoreOutOfRange();

    /// @param admin Receives `DEFAULT_ADMIN_ROLE`, which may grant `SCORER_ROLE`.
    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    /// @notice Stake vault that receives freeze + release calls. Must be set before checkpoints.
    StakeVault public stakeVault;
    /// @notice Optional positive-reward path; skipped when unset.
    RewardRegistry public rewardRegistry;
    /// @notice Resolves an agent's domain for reward routing; reward skipped when unset.
    XibalbaAgentRegistry public agentRegistry;

    event StakeVaultSet(address indexed stakeVault);
    event RewardRegistrySet(address indexed rewardRegistry);
    event AgentRegistrySet(address indexed agentRegistry);
    /// @notice Reward notification failed; the checkpoint and freeze were still applied (R5).
    event RewardNotifyFailed(address indexed agent, bytes reason);

    error StakeVaultNotSet();

    function setStakeVault(address v) external onlyRole(DEFAULT_ADMIN_ROLE) {
        stakeVault = StakeVault(v);
        emit StakeVaultSet(v);
    }

    function setRewardRegistry(address r) external onlyRole(DEFAULT_ADMIN_ROLE) {
        rewardRegistry = RewardRegistry(r);
        emit RewardRegistrySet(r);
    }

    function setAgentRegistry(address r) external onlyRole(DEFAULT_ADMIN_ROLE) {
        agentRegistry = XibalbaAgentRegistry(r);
        emit AgentRegistrySet(r);
    }

    /// @notice Stores a checkpoint for `agent`, replacing its prior `latest` checkpoint, then
    /// applies the latching freeze and lock release on the stake vault in the same tx.
    /// @param score Agent Integrity Score in basis points, 0..10000.
    /// @param releasable Amount of the agent's action lock to release for the compliant window.
    /// @dev The vault calls are NOT wrapped: they must succeed. The reward notification (positive
    /// delta only) IS wrapped in try/catch so a faulty reward module can never block a
    /// checkpoint or freeze.
    function postCheckpoint(address agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot, uint256 releasable)
        external
        onlyRole(SCORER_ROLE)
    {
        if (score > MAX_SCORE) revert ScoreOutOfRange();
        StakeVault vault = stakeVault;
        if (address(vault) == address(0)) revert StakeVaultNotSet();

        uint32 oldScore = latest[agent].score;
        latest[agent] = Checkpoint({score: score, windowEnd: windowEnd, evidenceRoot: evidenceRoot});
        emit CheckpointPosted(agent, score, windowEnd, evidenceRoot);

        vault.onCheckpoint(agent, score);
        vault.releaseLock(agent, releasable);

        if (score > oldScore) _notifyReward(agent, oldScore, score);
    }

    function _notifyReward(address agent, uint32 oldScore, uint32 score) internal {
        RewardRegistry rr = rewardRegistry;
        XibalbaAgentRegistry ar = agentRegistry;
        if (address(rr) == address(0) || address(ar) == address(0)) return;

        try ar.resolveAgent(agent) returns (XibalbaAgentRegistry.AgentRecord memory rec) {
            try rr.notifyPositiveCheckpoint(agent, oldScore, score, rec.domainId) {}
            catch (bytes memory reason) {
                emit RewardNotifyFailed(agent, reason);
            }
        } catch (bytes memory reason) {
            emit RewardNotifyFailed(agent, reason);
        }
    }
}
