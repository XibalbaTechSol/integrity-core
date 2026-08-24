// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {SmartBAAFactory} from "./SmartBAAFactory.sol";
import {XibalbaAgentRegistry} from "../framework/XibalbaAgentRegistry.sol";
import {IAgentAuthorityResolver} from "../framework/IAgentAuthorityResolver.sol";

/// @title EHRGate
/// @notice Patient-controlled access gate for AI agents requesting PHI (Protected Health
/// Information). A patient grants a specific agent access to a specific record hash; the
/// agent may only actually read it if three independent checks all pass: the patient's
/// grant is still unlocked, the covered entity has an active BAA with that agent, and the
/// agent's current AIS clears the configured floor.
/// @dev AIS is resolved through IAgentAuthorityResolver (Stream 2 / SPEC.md §3.4) rather
/// than reading registry.resolveAgent(...).primitives.reputationRegistry directly, so this
/// gate serves both sovereign clone-set agents and enterprise (StateAnchor-only) agents
/// without EHRGate needing to know which profile a given agent used at registration.
contract EHRGate {
    struct Gate {
        address coveredEntity;
        bool isUnlocked;
        uint256 grantedAt;
    }

    XibalbaAgentRegistry public immutable registry;
    SmartBAAFactory public immutable baaFactory;
    IAgentAuthorityResolver public immutable resolver;

    /// @notice Minimum effective AIS (post ZK-boost) an agent must hold to access PHI.
    /// Mutable (not immutable) because the AIS scale/formula weights are configurable
    /// per §4.3 and this threshold should move with them, not be frozen at deploy time.
    uint256 public minAisThreshold;
    address public admin;

    // patient => recordHash => agent => Gate
    mapping(address => mapping(bytes32 => mapping(address => Gate))) public accessGates;

    event AccessGranted(address indexed patient, bytes32 indexed recordHash, address indexed agent, address coveredEntity);
    event AccessRevoked(address indexed patient, bytes32 indexed recordHash, address indexed agent);
    event AccessLogged(address indexed patient, bytes32 indexed recordHash, address indexed agent, bool successful);
    event ThresholdUpdated(uint256 newThreshold);

    error NotAdmin();
    error GateAlreadyUnlocked();

    modifier onlyAdmin() {
        if (msg.sender != admin) revert NotAdmin();
        _;
    }

    constructor(address _registry, address _baaFactory, address _resolver, uint256 _minAisThreshold, address _admin) {
        registry = XibalbaAgentRegistry(_registry);
        baaFactory = SmartBAAFactory(_baaFactory);
        resolver = IAgentAuthorityResolver(_resolver);
        minAisThreshold = _minAisThreshold;
        admin = _admin;
    }

    function setThreshold(uint256 newThreshold) external onlyAdmin {
        minAisThreshold = newThreshold;
        emit ThresholdUpdated(newThreshold);
    }

    /// @notice Patient grants `agent` access to `recordHash`, recording which covered
    /// entity vouches for that agent (checked against SmartBAAFactory at read time).
    function grantAccess(bytes32 recordHash, address agent, address coveredEntity) external {
        Gate storage g = accessGates[msg.sender][recordHash][agent];
        if (g.isUnlocked) revert GateAlreadyUnlocked();
        g.coveredEntity = coveredEntity;
        g.isUnlocked = true;
        g.grantedAt = block.timestamp;
        emit AccessGranted(msg.sender, recordHash, agent, coveredEntity);
    }

    function revokeAccess(bytes32 recordHash, address agent) external {
        accessGates[msg.sender][recordHash][agent].isUnlocked = false;
        emit AccessRevoked(msg.sender, recordHash, agent);
    }

    /// @notice Three independent checks, evaluated in order, each returning false (a
    /// "denied" entry for a rogue caller instead of the whole call reverting and leaving
    /// no on-chain trace of the attempt.
    function checkAccess(address patient, bytes32 recordHash) public view returns (bool) {
        Gate storage g = accessGates[patient][recordHash][msg.sender];
        if (!g.isUnlocked) return false;
        if (!baaFactory.isBAAActive(g.coveredEntity, msg.sender)) return false;
        if (!resolver.isAuthorityRegistered(msg.sender)) return false;
        if (resolver.getAis(msg.sender) < minAisThreshold) return false;
        return true;
    }
}
