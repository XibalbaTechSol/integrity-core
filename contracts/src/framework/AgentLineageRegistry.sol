// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {XibalbaAgentRegistry} from "./XibalbaAgentRegistry.sol";

interface ILineageControllerBoundAgent {
    function DEFAULT_ADMIN_ROLE() external view returns (bytes32);
    function hasRole(bytes32 role, address account) external view returns (bool);
}

/// @title AgentLineageRegistry
/// @notice Append-only provenance attestations between already-registered agents.
/// @dev This records lineage only; it does not migrate balances, stake, markets, or identity.
contract AgentLineageRegistry {
    bytes32 public constant FORKED_FROM = keccak256("forked_from");
    bytes32 public constant MIGRATED_FROM = keccak256("migrated_from");
    bytes32 public constant RECOVERED_FROM = keccak256("recovered_from");

    struct Lineage {
        address predecessor;
        bytes32 relation;
        address attestor;
        uint256 recordedAt;
    }

    XibalbaAgentRegistry public immutable agentRegistry;
    mapping(address => Lineage) public lineageOf;

    event LineageRecorded(
        address indexed successor,
        address indexed predecessor,
        bytes32 indexed relation,
        address attestor,
        uint256 recordedAt
    );

    error UnknownSuccessor();
    error UnknownPredecessor();
    error ZeroAddress();
    error SelfLineage();
    error AlreadyRecorded();
    error InvalidRelation();
    error NotCurrentController();

    constructor(address registry_) {
        require(registry_ != address(0), "zero registry");
        agentRegistry = XibalbaAgentRegistry(registry_);
    }

    /// @notice Records one immutable predecessor edge for `successor`.
    /// @dev The successor's current controller may call directly, or the successor
    /// SovereignAgent may call this through execute().
    function recordLineage(address successor, address predecessor, bytes32 relation) external {
        if (successor == address(0) || predecessor == address(0)) revert ZeroAddress();
        if (successor == predecessor) revert SelfLineage();
        if (!agentRegistry.isRegisteredAgent(successor)) revert UnknownSuccessor();
        if (!agentRegistry.isRegisteredAgent(predecessor)) revert UnknownPredecessor();
        if (relation != FORKED_FROM && relation != MIGRATED_FROM && relation != RECOVERED_FROM) {
            revert InvalidRelation();
        }
        if (lineageOf[successor].predecessor != address(0)) revert AlreadyRecorded();

        bool agentCall = msg.sender == successor;
        bool controllerCall = false;
        if (!agentCall) {
            bytes32 adminRole = ILineageControllerBoundAgent(successor).DEFAULT_ADMIN_ROLE();
            controllerCall = ILineageControllerBoundAgent(successor).hasRole(adminRole, msg.sender);
        }
        if (!agentCall && !controllerCall) revert NotCurrentController();

        lineageOf[successor] = Lineage(predecessor, relation, msg.sender, block.timestamp);
        emit LineageRecorded(successor, predecessor, relation, msg.sender, block.timestamp);
    }
}
