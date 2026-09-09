// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {AgentPrimitivesFactory} from "../src/framework/AgentPrimitivesFactory.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {DomainRegistry} from "../src/framework/DomainRegistry.sol";

/// @notice Replace the immutable verifier pointer for future primitive registrations.
/// Existing EIP-1167 clones are intentionally not rewritten here; their SovereignAgent
/// controllers must explicitly stage and adopt the new verifier version per clone.
contract MigrateVerifierFactory is Script {
    function run() external {
        uint256 key = vm.envUint("FUNDER_PRIVATE_KEY");
        address newVerifier = vm.envAddress("NEW_VERIFIER");
        string memory json = vm.readFile("../deployments.baseSepolia.json");

        address registry = vm.parseJsonAddress(json, ".singletons.XibalbaAgentRegistry");
        address domainRegistry = vm.parseJsonAddress(json, ".singletons.DomainRegistry");
        address oldFactory = vm.parseJsonAddress(json, ".singletons.AgentPrimitivesFactory");
        address reputationImpl = vm.parseJsonAddress(json, ".cloneTemplates.ReputationRegistry");
        address slasherImpl = vm.parseJsonAddress(json, ".cloneTemplates.Slasher");
        address verifierRegistryImpl = vm.parseJsonAddress(json, ".cloneTemplates.VerifierRegistry");
        address complianceGateImpl = vm.parseJsonAddress(json, ".cloneTemplates.ComplianceGate");
        address agentProfileImpl = vm.parseJsonAddress(json, ".cloneTemplates.AgentProfile");
        address oracle = vm.parseJsonAddress(json, ".protocolAddresses.oracleSigner");
        address disputer = vm.parseJsonAddress(json, ".protocolAddresses.disputer");
        address governance = vm.parseJsonAddress(json, ".protocolAddresses.governance");
        address itk = vm.parseJsonAddress(json, ".singletons.IntegrityToken");

        vm.startBroadcast(key);
        AgentPrimitivesFactory replacement = new AgentPrimitivesFactory(
            registry,
            domainRegistry,
            reputationImpl,
            slasherImpl,
            verifierRegistryImpl,
            complianceGateImpl,
            agentProfileImpl,
            oracle,
            disputer,
            governance,
            itk,
            newVerifier
        );

        bytes32 registrar = XibalbaAgentRegistry(registry).REGISTRAR_ROLE();
        XibalbaAgentRegistry(registry).grantRole(registrar, address(replacement));
        DomainRegistry(domainRegistry).grantRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), address(replacement));
        XibalbaAgentRegistry(registry).revokeRole(registrar, oldFactory);
        DomainRegistry(domainRegistry).revokeRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), oldFactory);
        vm.stopBroadcast();

        console2.log("New factory:", address(replacement));
        console2.log("New verifier:", newVerifier);
        console2.log("Old factory revoked:", oldFactory);
    }
}
