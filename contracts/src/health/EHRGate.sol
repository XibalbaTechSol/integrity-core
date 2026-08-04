// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ReputationRegistry} from "../oracle/ReputationRegistry.sol";
import {SmartBAAFactory} from "./SmartBAAFactory.sol";
import {XibalbaAgentRegistry} from "../framework/XibalbaAgentRegistry.sol";

/// @title EHRGate
/// @notice Patient-controlled access gate for AI agents requesting PHI (Protected Health
/// Information), with two additional institutional-level checks layered on top of raw
/// patient consent: an active Business Associate Agreement between the record's covered
/// entity and the requesting agent, and a minimum on-chain reputation score.
/// @dev The old prototype's EHRGate only ever checked patient consent — it never
/// actually enforced the BAA or reputation side of HIPAA compliance on-chain, so a
/// patient who consented had no real protection against a low-reputation or
/// contractually-unbound agent. All three checks are now required simultaneously
/// (patient consent AND active BAA AND AIS >= threshold): consent alone is necessary
/// but not sufficient — a patient can be tricked into granting access, but they cannot
/// grant access to an agent lacking institutional accountability.
///
/// Reputation used to be read from one immutable, global `ReputationRegistry`. Now that
/// every agent owns its own `ReputationRegistry` clone (see AgentPrimitivesFactory),
/// there is no single address to point at — this contract instead holds the shared
/// `XibalbaAgentRegistry` index and resolves `msg.sender`'s own clone address on every
/// call. That resolution is itself a meaningful check: an address that was never
/// registered through AgentPrimitivesFactory has no entry in the registry, so
/// `checkAccess` reverts before it can even reach the reputation check, closing off any
/// attempt to gate access using a hand-rolled contract that only pretends to be a
/// Sovereign Agent.
contract EHRGate {
    struct Gate {
        address coveredEntity;
        bool isUnlocked;
        uint256 grantedAt;
    }

    XibalbaAgentRegistry public immutable registry;
    SmartBAAFactory public immutable baaFactory;

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

    constructor(address _registry, address _baaFactory, uint256 _minAisThreshold, address _admin) {
        registry = XibalbaAgentRegistry(_registry);
        baaFactory = SmartBAAFactory(_baaFactory);
        minAisThreshold = _minAisThreshold;
        admin = _admin;
    }

    function setThreshold(uint256 newThreshold) external onlyAdmin {
        minAisThreshold = newThreshold;
        emit ThresholdUpdated(newThreshold);
    }

    /// @notice The patient explicitly grants a specific agent access to a specific
    /// record, scoped to the covered entity that holds it (so the BAA check below has
    /// something concrete to check against).
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

    /// @notice Checks all three gating conditions for `msg.sender` (expected to be the
    /// requesting SovereignAgent contract) against `patient`'s record. Returns `false`
    /// (does not revert) if `msg.sender` was never registered through
    /// AgentPrimitivesFactory, so that `verifyAndLogAccess` can still emit an auditable
    /// "denied" entry for a rogue caller instead of the whole call reverting and leaving
    /// no on-chain trace of the attempt.
    function checkAccess(address patient, bytes32 recordHash) public view returns (bool) {
        Gate storage g = accessGates[patient][recordHash][msg.sender];
        if (!g.isUnlocked) return false;
        if (!baaFactory.isBAAActive(g.coveredEntity, msg.sender)) return false;
        if (!registry.isRegisteredAgent(msg.sender)) return false;
        address reputationRegistry = registry.resolveAgent(msg.sender).primitives.reputationRegistry;
        if (ReputationRegistry(reputationRegistry).effectiveScore(msg.sender) < minAisThreshold) return false;
        return true;
    }

    /// @notice Same check as `checkAccess`, but emits an auditable log either way —
    /// intended to be called immediately before an agent performs off-chain inference
    /// over PHI, so there's an on-chain record of every access attempt (granted or
    /// denied) that integrity-oracle/bcc_middleware can correlate with the OPA policy
    /// decision made for the same request.
    function verifyAndLogAccess(address patient, bytes32 recordHash) external returns (bool) {
        bool granted = checkAccess(patient, recordHash);
        emit AccessLogged(patient, recordHash, msg.sender, granted);
        return granted;
    }
}
