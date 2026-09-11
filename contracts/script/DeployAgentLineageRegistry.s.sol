// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {AgentLineageRegistry} from "../src/framework/AgentLineageRegistry.sol";

/// @notice Deploy the append-only lineage attestation registry for an existing agent registry.
/// Deployment records are intentionally updated separately after address readback.
contract DeployAgentLineageRegistry is Script {
    function run() external returns (AgentLineageRegistry deployed) {
        uint256 key = vm.envUint("FUNDER_PRIVATE_KEY");
        string memory json = vm.readFile("../deployments.baseSepolia.json");
        address agentRegistry = vm.parseJsonAddress(json, ".singletons.XibalbaAgentRegistry");

        vm.startBroadcast(key);
        deployed = new AgentLineageRegistry(agentRegistry);
        vm.stopBroadcast();

        console2.log("Agent registry:", agentRegistry);
        console2.log("Agent lineage registry:", address(deployed));
    }
}
