// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {AgentPrimitivesFactory} from "../src/framework/AgentPrimitivesFactory.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {DomainRegistry} from "../src/framework/DomainRegistry.sol";
import {Slasher} from "../src/oracle/Slasher.sol";

/// @notice Redeploys Slasher (the deployed clone template at cloneTemplates.Slasher predates
/// `stakeFor`, so it has NO matching function selector -- every registerPrimitives() call
/// reverts with empty data at the stakeFor step, blocking ALL new agent registration on this
/// factory, discovered 2026-09-14 while registering xibalba-shield) and, since
/// AgentPrimitivesFactory.slasherImpl is immutable, a replacement factory pointing at the new
/// Slasher. Mirrors MigrateVerifierFactory.s.sol's exact pattern (this repo's own precedent for
/// this class of fix) -- new implementation, new factory, migrate REGISTRAR_ROLE on both
/// registries from the old factory to the new one, revoke from the old.
///
/// ReputationRegistry is ALSO stale (missing newer ZK-related functions, verified via bytecode
/// selector scan the same session) but its `initialize()` -- the only function registerPrimitives
/// calls -- is present and already confirmed working live. Deliberately NOT redeployed here to
/// keep this fix scoped to what's actually blocking registration; the ZK staleness is a real,
/// separate gap for a future session, not a hard block.
contract MigrateSlasherFactory is Script {
    function run() external {
        uint256 key = vm.envUint("FUNDER_PRIVATE_KEY");
        string memory json = vm.readFile("../deployments.baseSepolia.json");

        address registry = vm.parseJsonAddress(json, ".singletons.XibalbaAgentRegistry");
        address domainRegistry = vm.parseJsonAddress(json, ".singletons.DomainRegistry");
        address oldFactory = vm.parseJsonAddress(json, ".singletons.AgentPrimitivesFactory");
        address reputationImpl = vm.parseJsonAddress(json, ".cloneTemplates.ReputationRegistry");
        address verifierRegistryImpl = vm.parseJsonAddress(json, ".cloneTemplates.VerifierRegistry");
        address complianceGateImpl = vm.parseJsonAddress(json, ".cloneTemplates.ComplianceGate");
        address agentProfileImpl = vm.parseJsonAddress(json, ".cloneTemplates.AgentProfile");
        address oracle = vm.parseJsonAddress(json, ".protocolAddresses.oracleSigner");
        address disputer = vm.parseJsonAddress(json, ".protocolAddresses.disputer");
        address governance = vm.parseJsonAddress(json, ".protocolAddresses.governance");
        address itk = vm.parseJsonAddress(json, ".singletons.IntegrityToken");
        address verifier = vm.parseJsonAddress(json, ".singletons.UltraPlonkVerifier");

        vm.startBroadcast(key);

        Slasher newSlasher = new Slasher(itk);

        AgentPrimitivesFactory replacement = new AgentPrimitivesFactory(
            registry,
            domainRegistry,
            reputationImpl,
            address(newSlasher),
            verifierRegistryImpl,
            complianceGateImpl,
            agentProfileImpl,
            oracle,
            disputer,
            governance,
            itk,
            verifier
        );

        bytes32 registrar = XibalbaAgentRegistry(registry).REGISTRAR_ROLE();
        XibalbaAgentRegistry(registry).grantRole(registrar, address(replacement));
        DomainRegistry(domainRegistry).grantRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), address(replacement));
        XibalbaAgentRegistry(registry).revokeRole(registrar, oldFactory);
        DomainRegistry(domainRegistry).revokeRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), oldFactory);
        vm.stopBroadcast();

        console2.log("New Slasher implementation:", address(newSlasher));
        console2.log("New factory:", address(replacement));
        console2.log("Old factory revoked:", oldFactory);
    }
}
