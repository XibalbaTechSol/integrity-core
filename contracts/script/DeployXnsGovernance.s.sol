// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {XibalbaNameService} from "../src/framework/XibalbaNameService.sol";
import {IntegrityGovernance} from "../src/oracle/IntegrityGovernance.sol";

/// @title DeployXnsGovernance
/// @notice Incremental deploy: adds `XibalbaNameService` (XNS) and `IntegrityGovernance` to an
/// ALREADY-LIVE protocol deployment. Both are wired into genesis `Deploy.s.sol` but their Base
/// Sepolia broadcast was deferred ("build now, defer deploy" — PRODUCTION_GAPS.md §4); running
/// genesis again would remint every existing singleton and orphan all registered agents, so this
/// follows the same incremental pattern as `DeployMarkets.s.sol`/`DeployEHRGate.s.sol`: read the
/// existing `../deployments.<network>.json`, deploy only the two new contracts against the
/// existing `XibalbaAgentRegistry`/`IntegrityToken`, and merge their addresses into that SAME file.
///
/// @dev "Funder signs, agent owns": the FUNDER key signs + pays gas, but the guardian/admin roles
/// go to the Xibalba agent (`XIBALBA_AGENT_ADDRESS`, default the FAUCET_INFO "Agent Derived
/// Address"). So IntegrityGovernance's guardian (Ownable owner) and XibalbaNameService's
/// DEFAULT_ADMIN_ROLE/REGISTRAR_ROLE holder is the agent, not the funder.
///
/// Run against Base Sepolia with:
///   forge script script/DeployXnsGovernance.s.sol --rpc-url base_sepolia --broadcast --verify
contract DeployXnsGovernance is Script {
    // Governance genesis params — mirror Deploy.s.sol's GOV_* constants (kept in sync manually,
    // same as DeployEHRGate mirrors EHR_GATE_MIN_AIS_THRESHOLD).
    uint256 constant GOV_VOTING_PERIOD = 3 days;
    uint256 constant GOV_TIMELOCK_DELAY = 2 days;
    uint256 constant GOV_PROPOSAL_THRESHOLD = 1_000 ether;
    uint256 constant GOV_QUORUM_VOTES = 10_000 ether;

    // Default Xibalba agent (FAUCET_INFO.md "Agent Derived Address"). Overridable via env.
    address constant DEFAULT_AGENT = 0xabfeEaCbA00F38810E697b2970399fE03080FBeB;

    address deployer;
    address agent;
    address registry;
    address itk;

    XibalbaNameService xns;
    IntegrityGovernance gov;

    string existingJson;
    string network;
    string path;

    function run() external {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        deployer = vm.addr(deployerKey);
        // Guardian/admin owner of both contracts — the Xibalba agent, not the funder.
        agent = vm.envOr("XIBALBA_AGENT_ADDRESS", DEFAULT_AGENT);

        network = block.chainid == 84532 ? "baseSepolia" : "local";
        path = string.concat("../deployments.", network, ".json");
        existingJson = vm.readFile(path);

        registry = vm.parseJsonAddress(existingJson, ".singletons.XibalbaAgentRegistry");
        itk = vm.parseJsonAddress(existingJson, ".singletons.IntegrityToken");

        vm.startBroadcast(deployerKey);
        // XNS: admin = agent (holds DEFAULT_ADMIN_ROLE + REGISTRAR_ROLE); resolves registrations
        // against the existing registry.
        xns = new XibalbaNameService(agent, registry);
        // Governance: guardian (Ownable owner) = agent; locks the existing $ITK to propose/vote.
        gov = new IntegrityGovernance(
            agent, IERC20(itk), GOV_VOTING_PERIOD, GOV_TIMELOCK_DELAY, GOV_PROPOSAL_THRESHOLD, GOV_QUORUM_VOTES
        );
        vm.stopBroadcast();

        _logSummary();
        _mergeDeploymentsFile();
    }

    function _logSummary() internal view {
        console2.log("=== Integrity Protocol XNS + Governance deploy ===");
        console2.log("network:               ", network);
        console2.log("signer/payer (funder): ", deployer);
        console2.log("guardian/admin (agent):", agent);
        console2.log("existing AgentRegistry:", registry);
        console2.log("existing IntegrityToken:", itk);
        console2.log("XibalbaNameService:    ", address(xns));
        console2.log("IntegrityGovernance:   ", address(gov));
    }

    /// @dev Re-serializes every singleton already in the live file, adding `XibalbaNameService`
    /// and `IntegrityGovernance`. `EHRGate` is guarded with `keyExistsJson` since the live Base
    /// Sepolia file does not have it yet (DeployEHRGate hasn't been broadcast) — it is preserved
    /// only if present, never invented.
    function _mergeDeploymentsFile() internal {
        string memory s = "singletons";
        vm.serializeAddress(s, "IntegrityToken", itk);
        vm.serializeAddress(s, "IntegrityGovernance", address(gov));
        vm.serializeAddress(s, "UltraPlonkVerifier", vm.parseJsonAddress(existingJson, ".singletons.UltraPlonkVerifier"));
        vm.serializeAddress(s, "XibalbaAgentRegistry", registry);
        vm.serializeAddress(s, "XibalbaNameService", address(xns));
        vm.serializeAddress(s, "DomainRegistry", vm.parseJsonAddress(existingJson, ".singletons.DomainRegistry"));
        vm.serializeAddress(s, "AgentPrimitivesFactory", vm.parseJsonAddress(existingJson, ".singletons.AgentPrimitivesFactory"));
        vm.serializeAddress(s, "CoveredEntityRegistry", vm.parseJsonAddress(existingJson, ".singletons.CoveredEntityRegistry"));
        vm.serializeAddress(s, "SmartBAAFactory", vm.parseJsonAddress(existingJson, ".singletons.SmartBAAFactory"));
        vm.serializeAddress(s, "HIPAAGuardrailRegistry", vm.parseJsonAddress(existingJson, ".singletons.HIPAAGuardrailRegistry"));
        vm.serializeAddress(s, "MarketFactory", vm.parseJsonAddress(existingJson, ".singletons.MarketFactory"));
        if (vm.keyExistsJson(existingJson, ".singletons.EHRGate")) {
            vm.serializeAddress(s, "EHRGate", vm.parseJsonAddress(existingJson, ".singletons.EHRGate"));
        }
        string memory singletonsJson =
            vm.serializeAddress(s, "A2ACapitalPool", vm.parseJsonAddress(existingJson, ".singletons.A2ACapitalPool"));

        // cloneTemplates + protocolAddresses unchanged — re-serialized field-by-field
        // (forge-std has no verbatim-copy primitive).
        string memory ct = "cloneTemplatesTmp";
        vm.serializeAddress(ct, "ReputationRegistry", vm.parseJsonAddress(existingJson, ".cloneTemplates.ReputationRegistry"));
        vm.serializeAddress(ct, "Slasher", vm.parseJsonAddress(existingJson, ".cloneTemplates.Slasher"));
        vm.serializeAddress(ct, "VerifierRegistry", vm.parseJsonAddress(existingJson, ".cloneTemplates.VerifierRegistry"));
        vm.serializeAddress(ct, "ComplianceGate", vm.parseJsonAddress(existingJson, ".cloneTemplates.ComplianceGate"));
        vm.serializeAddress(ct, "AgentProfile", vm.parseJsonAddress(existingJson, ".cloneTemplates.AgentProfile"));
        string memory cloneTemplatesJson =
            vm.serializeAddress(ct, "IntegrityMarket", vm.parseJsonAddress(existingJson, ".cloneTemplates.IntegrityMarket"));

        string memory p = "protocolAddressesTmp";
        vm.serializeAddress(p, "oracleSigner", vm.parseJsonAddress(existingJson, ".protocolAddresses.oracleSigner"));
        vm.serializeAddress(p, "disputer", vm.parseJsonAddress(existingJson, ".protocolAddresses.disputer"));
        vm.serializeAddress(p, "governance", vm.parseJsonAddress(existingJson, ".protocolAddresses.governance"));
        vm.serializeAddress(p, "arbitrator", vm.parseJsonAddress(existingJson, ".protocolAddresses.arbitrator"));
        vm.serializeAddress(p, "resolverSigner", vm.parseJsonAddress(existingJson, ".protocolAddresses.resolverSigner"));
        string memory protocolAddressesJson =
            vm.serializeAddress(p, "funderWallet", vm.parseJsonAddress(existingJson, ".protocolAddresses.funderWallet"));

        string memory root = "root";
        vm.serializeString(root, "singletons", singletonsJson);
        vm.serializeString(root, "cloneTemplates", cloneTemplatesJson);
        vm.serializeString(root, "protocolAddresses", protocolAddressesJson);
        string memory finalJson = vm.serializeUint(root, "chainId", block.chainid);

        vm.writeJson(finalJson, path);
        console2.log("Merged XNS + Governance into", path);
    }
}
