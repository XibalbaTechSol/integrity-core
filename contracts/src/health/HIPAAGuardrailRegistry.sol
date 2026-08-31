// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title HIPAAGuardrailRegistry
/// @notice Anchors which version of the off-chain OPA HIPAA policy bundle
/// (`bcc_middleware/policies/*.rego`, §7 of the interface contract) is currently in
/// effect, and lets the oracle stamp an immutable, on-chain audit trail entry for each
/// PHI access decision bcc_middleware makes, referencing the exact policy hash that
/// governed it.
/// @dev This contract does not evaluate OPA policy itself — bcc_middleware and
/// integrity-sdk are the only components that call OPA's REST API (§7: "no local
/// regex-only fallback path"). What this contract adds is something OPA alone can't
/// give you: a tamper-evident, third-party-auditable record of *which* policy version
/// was live when a given decision was made, so a covered entity's later audit can
/// verify "the agent's access request was evaluated against policy version X" without
/// trusting bcc_middleware's own logs.
contract HIPAAGuardrailRegistry is AccessControl {
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    bytes32 public activePolicyHash;
    string public activePolicyVersion;
    uint256 public activeSince;

    struct AuditEntry {
        address agent;
        bytes32 patientRecordHash;
        bytes32 policyHash;
        bool allowed;
        uint256 timestamp;
    }

    AuditEntry[] public auditLog;

    event PolicyActivated(bytes32 indexed policyHash, string version, uint256 timestamp);
    event AccessAudited(
        uint256 indexed entryIndex,
        address indexed agent,
        bytes32 indexed patientRecordHash,
        bytes32 policyHash,
        bool allowed
    );

    error StalePolicyHash();
    error NoActivePolicy();

    constructor(address admin, address oracle) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        if (oracle != address(0)) {
            _grantRole(ORACLE_ROLE, oracle);
        }
    }

    /// @notice Marks a new OPA policy bundle hash (e.g. keccak256 of the concatenated
    /// `.rego` sources bcc_middleware just loaded) as the currently active one.
    function setActivePolicy(bytes32 policyHash, string calldata version) external onlyRole(DEFAULT_ADMIN_ROLE) {
        activePolicyHash = policyHash;
        activePolicyVersion = version;
        activeSince = block.timestamp;
        emit PolicyActivated(policyHash, version, block.timestamp);
    }

    /// @notice Anchors an audit entry for one PHI access decision. `policyHashUsed` must
    /// match whatever is currently marked active — this is what stops bcc_middleware (or
    /// a compromised oracle key) from retroactively claiming a stale or never-active
    /// policy version governed some past decision; the two must agree in real time.
    function anchorAccessAudit(address agent, bytes32 patientRecordHash, bytes32 policyHashUsed, bool allowed)
        external
        onlyRole(ORACLE_ROLE)
        returns (uint256 entryIndex)
    {
        if (activePolicyHash == bytes32(0)) revert NoActivePolicy();
        if (policyHashUsed != activePolicyHash) revert StalePolicyHash();

        entryIndex = auditLog.length;
        auditLog.push(
            AuditEntry({
                agent: agent,
                patientRecordHash: patientRecordHash,
                policyHash: policyHashUsed,
                allowed: allowed,
                timestamp: block.timestamp
            })
        );

        emit AccessAudited(entryIndex, agent, patientRecordHash, policyHashUsed, allowed);
    }

    function auditLogLength() external view returns (uint256) {
        return auditLog.length;
    }
}
