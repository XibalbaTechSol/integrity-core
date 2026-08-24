// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title XibalbaAgentRegistry
/// @notice Canonical mapping from agent identity (DID) to deployed primitive contracts.
/// @dev Holds the mapping for both sovereign-profile agents (full 7-primitive set)
/// and enterprise-profile agents (StateAnchor-only accounts with direct oracle scoring).
contract XibalbaAgentRegistry is AccessControl {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    /// @notice The 7 primitive contract addresses that make up one sovereign agent's identity.
    struct PrimitiveSet {
        address sovereignAgent;
        address stateAnchor;
        address reputationRegistry;
        address slasher;
        address verifierRegistry;
        address complianceGate;
        address agentProfile;
    }

    struct AgentRecord {
        PrimitiveSet primitives;
        address controller;
        bytes32 domainId;
        uint256 registeredAt;
        bool exists;
    }

    struct EnterpriseRecord {
        address stateAnchor;
        address controller;
        bytes32 domainId;
        bool exists;
    }

    uint256 public totalAgents;
    mapping(bytes32 => AgentRecord) private _byDID;
    mapping(address => bytes32) public didHashOf;
    mapping(address => EnterpriseRecord) public enterpriseRecordOf;

    event PrimitivesRegistered(bytes32 indexed didHash, PrimitiveSet primitives);
    event EnterpriseAgentRegistered(address indexed agent, address indexed stateAnchor, address controller, bytes32 domainId);

    error AlreadyRegistered();
    error UnknownDID();
    error UnknownAgent();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    /// @notice Registers a sovereign agent with the full 7-primitive set.
    function registerPrimitives(bytes32 didHash_, PrimitiveSet calldata primitives, address controller, bytes32 domainId)
        external
        onlyRole(REGISTRAR_ROLE)
    {
        if (_byDID[didHash_].exists) revert AlreadyRegistered();
        if (didHashOf[primitives.sovereignAgent] != bytes32(0)) revert AlreadyRegistered();

        _byDID[didHash_] = AgentRecord({
            primitives: primitives,
            controller: controller,
            domainId: domainId,
            registeredAt: block.timestamp,
            exists: true
        });
        didHashOf[primitives.sovereignAgent] = didHash_;
        totalAgents += 1;
        emit PrimitivesRegistered(didHash_, primitives);
    }

    /// @notice Registers an enterprise agent (StateAnchor-backed account, no full clone-set required).
    function registerEnterpriseAgent(address agent, address stateAnchor, address controller, bytes32 domainId)
        external
        onlyRole(REGISTRAR_ROLE)
    {
        if (didHashOf[agent] != bytes32(0) || enterpriseRecordOf[agent].exists) revert AlreadyRegistered();
        require(agent != address(0), "zero agent");
        require(stateAnchor != address(0), "zero stateAnchor");

        enterpriseRecordOf[agent] = EnterpriseRecord({
            stateAnchor: stateAnchor,
            controller: controller,
            domainId: domainId,
            exists: true
        });
        totalAgents += 1;
        emit EnterpriseAgentRegistered(agent, stateAnchor, controller, domainId);
    }

    function resolveDID(string calldata did) external view returns (AgentRecord memory record) {
        bytes32 h = didHash(did);
        record = _byDID[h];
        if (!record.exists) revert UnknownDID();
    }

    function resolveDIDHash(bytes32 didHash_) external view returns (AgentRecord memory record) {
        record = _byDID[didHash_];
        if (!record.exists) revert UnknownDID();
    }

    function resolveAgent(address sovereignAgent) external view returns (AgentRecord memory record) {
        bytes32 h = didHashOf[sovereignAgent];
        if (h == bytes32(0)) revert UnknownAgent();
        record = _byDID[h];
        if (!record.exists) revert UnknownAgent();
    }

    function isRegisteredAgent(address sovereignAgent) external view returns (bool) {
        return _byDID[didHashOf[sovereignAgent]].exists;
    }

    function isEnterpriseAgent(address agent) external view returns (bool) {
        return enterpriseRecordOf[agent].exists;
    }

    function didHash(string memory did) public pure returns (bytes32) {
        return keccak256(bytes(did));
    }
}
