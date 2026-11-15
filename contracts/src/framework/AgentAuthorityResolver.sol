// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IAgentAuthorityResolver} from "./IAgentAuthorityResolver.sol";
import {AgentRegistry} from "./AgentRegistry.sol";
import {AISRegistry} from "../trust/AISRegistry.sol";

/// @title AgentAuthorityResolver
/// @notice Pure read-side adapter: registration from `AgentRegistry`, AIS from `AISRegistry`.
/// @dev Registration v3 replaced the per-agent `ReputationRegistry` clone (0..1000 scale) and the
/// enterprise profile with one registry and one AIS checkpoint store. `getAis` returns the
/// `AISRegistry` basis-point score (0..10000) unchanged: thresholds that consume it (e.g.
/// `EHRGate.minAisThreshold`) are configured in basis points. It cannot set AIS.
contract AgentAuthorityResolver is IAgentAuthorityResolver {
    AgentRegistry public immutable registry;
    AISRegistry public immutable aisRegistry;

    error NotRegistered(address agent);

    constructor(address registry_, address aisRegistry_) {
        require(registry_ != address(0), "AgentAuthorityResolver: zero registry");
        require(aisRegistry_ != address(0), "AgentAuthorityResolver: zero AIS registry");
        registry = AgentRegistry(registry_);
        aisRegistry = AISRegistry(aisRegistry_);
    }

    function isAuthorityRegistered(address agent) public view returns (bool) {
        return registry.isRegisteredAgent(agent);
    }

    function getAis(address agent) external view returns (uint256) {
        if (!registry.isRegisteredAgent(agent)) revert NotRegistered(agent);
        (uint32 score,,) = aisRegistry.latest(agent);
        return score;
    }
}
