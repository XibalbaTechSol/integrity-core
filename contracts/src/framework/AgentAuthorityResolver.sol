// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IAgentAuthorityResolver} from "./IAgentAuthorityResolver.sol";
import {XibalbaAgentRegistry} from "./XibalbaAgentRegistry.sol";

interface IReputationRegistryRead {
    function effectiveScore(address agent) external view returns (uint256);
}

interface ISovereignAgentAis {
    function ais() external view returns (uint256);
}

/// @title AgentAuthorityResolver
/// @notice Additive parallel resolution path (docs/IMPLEMENTATION_PLAN.md Stream 2 / §5.2a).
/// @dev Resolution order for a given agent address:
///   1. Sovereign profile: `XibalbaAgentRegistry.isRegisteredAgent` — read AIS from that
///      agent's own `ReputationRegistry` clone (source of truth for that profile).
///   2. Enterprise profile: `XibalbaAgentRegistry.isEnterpriseAgent` — read AIS directly
///      from the `SovereignAgent`-shaped account's cached `ais()` (oracle-signed, no
///      `ReputationRegistry` clone required).
/// Neither existing profile's storage or write paths are touched by this contract; it is
/// a pure read-side adapter, so it cannot introduce a new way to *set* AIS.
contract AgentAuthorityResolver is IAgentAuthorityResolver {
    XibalbaAgentRegistry public immutable registry;

    error NotRegistered(address agent);

    constructor(address registry_) {
        require(registry_ != address(0), "AgentAuthorityResolver: zero registry");
        registry = XibalbaAgentRegistry(registry_);
    }

    function isAuthorityRegistered(address agent) public view returns (bool) {
        return registry.isRegisteredAgent(agent) || registry.isEnterpriseAgent(agent);
    }

    function getAis(address agent) external view returns (uint256) {
        if (registry.isRegisteredAgent(agent)) {
            address reputationRegistry = registry.resolveAgent(agent).primitives.reputationRegistry;
            return IReputationRegistryRead(reputationRegistry).effectiveScore(agent);
        }
        if (registry.isEnterpriseAgent(agent)) {
            return ISovereignAgentAis(agent).ais();
        }
        revert NotRegistered(agent);
    }

    function getStateAnchor(address agent) external view returns (address) {
        if (registry.isRegisteredAgent(agent)) {
            return registry.resolveAgent(agent).primitives.stateAnchor;
        }
        (address stateAnchor,,, bool exists) = registry.enterpriseRecordOf(agent);
        if (!exists) revert NotRegistered(agent);
        return stateAnchor;
    }
}
