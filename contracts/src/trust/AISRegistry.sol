// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

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

    /// @notice Stores a checkpoint for `agent`, replacing its prior `latest` checkpoint.
    /// @param score Agent Integrity Score in basis points, 0..10000.
    function postCheckpoint(address agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot)
        external
        onlyRole(SCORER_ROLE)
    {
        if (score > MAX_SCORE) revert ScoreOutOfRange();
        latest[agent] = Checkpoint({score: score, windowEnd: windowEnd, evidenceRoot: evidenceRoot});
        emit CheckpointPosted(agent, score, windowEnd, evidenceRoot);
    }
}
