// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {AccessControlUpgradeable} from "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {CoveredEntityRegistry} from "./CoveredEntityRegistry.sol";
import {SmartBAAFactory} from "./SmartBAAFactory.sol";

/// @title ComplianceGate
/// @notice Per-agent EIP-1167 clone declaring which regulated vertical (if any) an agent
/// operates in, and exposing a single live read that other packages (integrity-oracle's
/// S_compliance AIS component, integrity-dashboard's Integrity Health panel) can call without
/// needing to know Integrity Health's internal multi-contract structure.
/// @dev Never fakes compliance: `isHealthcareCompliant` returns false unless the agent
/// declared `Vertical.Healthcare` AND a live on-chain read against the real,
/// already-tested `CoveredEntityRegistry`/`SmartBAAFactory` stack passes. The
/// self-declared flags below (mirroring integrity_sdk/telemetry/conventions.py's
/// `IntegrityAttributes.COMPLIANCE_*` span attributes) are exactly that — self-declared,
/// off-chain-attested claims — and are kept separate from the live-verified boolean so
/// no consumer can confuse the two. This contract does NOT replace `EHRGate` as the
/// PHI-access enforcement boundary; EHRGate still performs its own live checks at access
/// time. ComplianceGate is a read-optimized compliance summary, not a second enforcement
/// point.
contract ComplianceGate is Initializable, AccessControlUpgradeable {
    /// @dev New values appended after Healthcare -- existing numeric ids (None=0,
    /// Healthcare=1) never change, so this extension is additive-only and does not
    /// disturb any already-declared agent's stored vertical. PredictionMarket/Trading
    /// map to the same `IntegrityMarket`/`MarketFactory` application layer;
    /// CapitalAllocation maps to `A2ACapitalPool`. None of these verticals have a
    /// live-verified `is*Compliant` read yet (unlike Healthcare's
    /// `isHealthcareCompliant`) -- they exist so an agent can declare its operating
    /// domain for dashboard badges/discovery, same as Healthcare's self-declared flags,
    /// without implying an equivalent regulatory-grade on-chain check exists for them.
    enum Vertical {
        None,
        Healthcare,
        PredictionMarket,
        Trading,
        CapitalAllocation
    }

    /// @dev Shared across every clone: baked into the implementation contract's runtime
    /// bytecode at its own one-time deployment. EIP-1167 clones delegatecall into that
    /// bytecode, so every agent's clone reads the SAME immutable Integrity Health registry
    /// addresses — exactly the intent, since domain-level compliance infrastructure
    /// stays global while only the per-agent declaration/state is cloned.
    CoveredEntityRegistry public immutable coveredEntityRegistry;
    SmartBAAFactory public immutable baaFactory;

    address public agent;
    Vertical public vertical;

    // Self-declared, off-chain-attested flags — mirror telemetry/conventions.py's
    // IntegrityAttributes.COMPLIANCE_* span attributes. Never consulted by
    // isHealthcareCompliant, which only trusts live on-chain state.
    bool public hipaaEligible;
    bool public zdrEnabled;
    bool public externalWebAccessDeclared;
    string public dataResidencyRegion;

    event VerticalDeclared(address indexed agent, Vertical vertical);
    event SelfDeclaredComplianceUpdated(
        bool hipaaEligible, bool zdrEnabled, bool externalWebAccessDeclared, string dataResidencyRegion
    );

    constructor(address _coveredEntityRegistry, address _baaFactory) {
        coveredEntityRegistry = CoveredEntityRegistry(_coveredEntityRegistry);
        baaFactory = SmartBAAFactory(_baaFactory);
        _disableInitializers();
    }

    function initialize(address _agent, address admin, Vertical _vertical) external initializer {
        __AccessControl_init();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        agent = _agent;
        vertical = _vertical;
        emit VerticalDeclared(_agent, _vertical);
    }

    /// @notice Updates the agent's self-declared (not on-chain-verified) compliance
    /// posture. Routed through the agent's SovereignAgent.execute per the protocol's
    /// call-routing convention (admin == the agent's SovereignAgent address).
    function setSelfDeclaredCompliance(
        bool _hipaaEligible,
        bool _zdrEnabled,
        bool _externalWebAccessDeclared,
        string calldata _dataResidencyRegion
    ) external onlyRole(DEFAULT_ADMIN_ROLE) {
        hipaaEligible = _hipaaEligible;
        zdrEnabled = _zdrEnabled;
        externalWebAccessDeclared = _externalWebAccessDeclared;
        dataResidencyRegion = _dataResidencyRegion;
        emit SelfDeclaredComplianceUpdated(
            _hipaaEligible, _zdrEnabled, _externalWebAccessDeclared, _dataResidencyRegion
        );
    }

    /// @notice True only if this agent declared the Healthcare vertical AND a live,
    /// currently-Active BAA exists between `coveredEntity` and this agent. Never returns
    /// true based on self-declared flags alone.
    function isHealthcareCompliant(address coveredEntity) external view returns (bool) {
        if (vertical != Vertical.Healthcare) return false;
        if (!coveredEntityRegistry.isActiveCoveredEntity(coveredEntity)) return false;
        return baaFactory.isBAAActive(coveredEntity, agent);
    }
}
