// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title XibalbaAgentRegistry
/// @notice Canonical mapping from agent identity (DID) to deployed primitive contracts.
/// @dev Holds the mapping for both sovereign-profile agents (full 7-primitive set)
/// and enterprise-profile agents (StateAnchor-only accounts with direct oracle scoring).
contract XibalbaAgentRegistry is AccessControl {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    // Optional capability bits. Identity and memory are the core registration;
    // these modules are provisioned only when an agent needs them.
    uint256 public constant CAP_REPUTATION = 1 << 0;
    uint256 public constant CAP_SLASHER = 1 << 1;
    uint256 public constant CAP_VERIFIER = 1 << 2;
    uint256 public constant CAP_COMPLIANCE = 1 << 3;
    uint256 public constant CAP_PROFILE = 1 << 4;

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
    event CoreRegistered(bytes32 indexed didHash, address indexed sovereignAgent, address indexed controller, address stateAnchor, bytes32 domainId);
    event PrimitivesProvisioned(bytes32 indexed didHash, PrimitiveSet primitives, uint256 capabilityMask);
    event EnterpriseAgentRegistered(address indexed agent, address indexed stateAnchor, address controller, bytes32 domainId);

    error AlreadyRegistered();
    error UnknownDID();
    error UnknownAgent();
    error ZeroController();
    error ZeroCoreAddress();
    error CapabilityAlreadyProvisioned();
    error CapabilityAddressMissing();

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
        if (controller == address(0)) revert ZeroController();

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

    /// @notice Registers the minimum identity and memory surface. Optional
    /// assurance, staking, verification, compliance, and profile modules may be
    /// attached later by the registrar factory.
    function registerCore(
        bytes32 didHash_,
        address sovereignAgent,
        address stateAnchor,
        address controller,
        bytes32 domainId
    ) external onlyRole(REGISTRAR_ROLE) {
        if (_byDID[didHash_].exists) revert AlreadyRegistered();
        if (didHashOf[sovereignAgent] != bytes32(0)) revert AlreadyRegistered();
        if (sovereignAgent == address(0) || stateAnchor == address(0)) revert ZeroCoreAddress();
        if (controller == address(0)) revert ZeroController();

        _byDID[didHash_] = AgentRecord({
            primitives: PrimitiveSet({
                sovereignAgent: sovereignAgent,
                stateAnchor: stateAnchor,
                reputationRegistry: address(0),
                slasher: address(0),
                verifierRegistry: address(0),
                complianceGate: address(0),
                agentProfile: address(0)
            }),
            controller: controller,
            domainId: domainId,
            registeredAt: block.timestamp,
            exists: true
        });
        didHashOf[sovereignAgent] = didHash_;
        totalAgents += 1;
        emit CoreRegistered(didHash_, sovereignAgent, controller, stateAnchor, domainId);
    }

    /// @notice Attaches one or more optional module addresses to an existing
    /// core registration. Existing module addresses can never be replaced.
    function provisionPrimitives(bytes32 didHash_, PrimitiveSet calldata additions, uint256 requestedCapabilities)
        external
        onlyRole(REGISTRAR_ROLE)
    {
        AgentRecord storage record = _byDID[didHash_];
        if (!record.exists) revert UnknownDID();
        if (additions.sovereignAgent != address(0) && additions.sovereignAgent != record.primitives.sovereignAgent) {
            revert CapabilityAddressMissing();
        }
        if (additions.stateAnchor != address(0) && additions.stateAnchor != record.primitives.stateAnchor) {
            revert CapabilityAddressMissing();
        }

        _provision(record.primitives.reputationRegistry, additions.reputationRegistry);
        _provision(record.primitives.slasher, additions.slasher);
        _provision(record.primitives.verifierRegistry, additions.verifierRegistry);
        _provision(record.primitives.complianceGate, additions.complianceGate);
        _provision(record.primitives.agentProfile, additions.agentProfile);

        if (additions.reputationRegistry != address(0)) record.primitives.reputationRegistry = additions.reputationRegistry;
        if (additions.slasher != address(0)) record.primitives.slasher = additions.slasher;
        if (additions.verifierRegistry != address(0)) record.primitives.verifierRegistry = additions.verifierRegistry;
        if (additions.complianceGate != address(0)) record.primitives.complianceGate = additions.complianceGate;
        if (additions.agentProfile != address(0)) record.primitives.agentProfile = additions.agentProfile;

        emit PrimitivesProvisioned(didHash_, record.primitives, requestedCapabilities);
    }

    function _provision(address existing, address addition) private pure {
        if (addition != address(0) && existing != address(0)) revert CapabilityAlreadyProvisioned();
        if (addition == address(0) && existing == address(0)) return;
    }

    function capabilityMask(address sovereignAgent) external view returns (uint256 mask) {
        bytes32 didHash_ = didHashOf[sovereignAgent];
        if (didHash_ == bytes32(0) || !_byDID[didHash_].exists) revert UnknownAgent();
        AgentRecord memory record = _byDID[didHash_];
        if (record.primitives.reputationRegistry != address(0)) mask |= CAP_REPUTATION;
        if (record.primitives.slasher != address(0)) mask |= CAP_SLASHER;
        if (record.primitives.verifierRegistry != address(0)) mask |= CAP_VERIFIER;
        if (record.primitives.complianceGate != address(0)) mask |= CAP_COMPLIANCE;
        if (record.primitives.agentProfile != address(0)) mask |= CAP_PROFILE;
    }

    /// @notice Registers an enterprise agent (StateAnchor-backed account, no full clone-set required).
    function registerEnterpriseAgent(address agent, address stateAnchor, address controller, bytes32 domainId)
        external
        onlyRole(REGISTRAR_ROLE)
    {
        if (didHashOf[agent] != bytes32(0) || enterpriseRecordOf[agent].exists) revert AlreadyRegistered();
        require(agent != address(0), "zero agent");
        require(stateAnchor != address(0), "zero stateAnchor");
        if (controller == address(0)) revert ZeroController();

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
