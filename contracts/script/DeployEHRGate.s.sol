// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {EHRGate} from "../src/health/EHRGate.sol";

/// @title DeployEHRGate
/// @notice Incremental deploy: adds `EHRGate` -- the actual PHI-access enforcement
/// contract (see `EHRGate.sol`'s own NatSpec; `ComplianceGate` explicitly does NOT
/// replace it) -- to an ALREADY-LIVE protocol deployment that predates EHRGate being
/// added to `Deploy.s.sol` (PRODUCTION_GAPS.md §4: EHRGate was never deployed anywhere,
/// including on live Base Sepolia, despite being real and fully tested in isolation).
/// Same incremental-deploy convention as `DeployMarkets.s.sol`: reads the existing
/// `../deployments.<network>.json`, deploys only the new contract against the existing
/// `XibalbaAgentRegistry`/`SmartBAAFactory` addresses, and merges the new address into
/// that SAME file rather than overwriting or re-running full genesis (which would
/// orphan every already-registered agent).
/// @dev Run against Base Sepolia with:
///   forge script script/DeployEHRGate.s.sol --rpc-url base_sepolia --broadcast --verify
/// Requires `../deployments.<network>.json` to already exist (i.e. `Deploy.s.sol` has
/// already run once against this network) and to have both `XibalbaAgentRegistry` and
/// `SmartBAAFactory` singleton addresses. Deliberately NOT run automatically as part of
/// this change -- deploying to a live network is a real, gas-costing, operator-triggered
/// action, not something a code change should do on its own.
contract DeployEHRGate is Script {
    // Mirrors Deploy.s.sol's EHR_GATE_MIN_AIS_THRESHOLD -- kept in sync manually since
    // this script targets an already-live deployment that predates that constant.
    uint256 constant EHR_GATE_MIN_AIS_THRESHOLD = 800;

    address deployer;
    address registry;
    address baaFactory;

    EHRGate ehrGate;

    string existingJson;
    string network;
    string path;

    function run() external {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        deployer = vm.addr(deployerKey);

        network = block.chainid == 84532 ? "baseSepolia" : "local";
        path = string.concat("../deployments.", network, ".json");
        existingJson = vm.readFile(path);

        registry = vm.parseJsonAddress(existingJson, ".singletons.XibalbaAgentRegistry");
        baaFactory = vm.parseJsonAddress(existingJson, ".singletons.SmartBAAFactory");

        vm.startBroadcast(deployerKey);
        ehrGate = new EHRGate(registry, baaFactory, EHR_GATE_MIN_AIS_THRESHOLD, deployer);
        vm.stopBroadcast();

        _logSummary();
        _mergeDeploymentsFile();
    }

    function _logSummary() internal view {
        console2.log("=== Integrity Protocol EHRGate deploy ===");
        console2.log("network:               ", network);
        console2.log("existing AgentRegistry:", registry);
        console2.log("existing SmartBAAFactory:", baaFactory);
        console2.log("EHRGate:               ", address(ehrGate));
    }

    /// @dev Re-serializes every singleton already in the file (read back via
    /// `vm.parseJsonAddress`), adding only `EHRGate` -- safe to run against a live file
    /// with real registered agents without losing any existing record. Every key this
    /// repo's `Deploy.s.sol`/`DeployMarkets.s.sol` are known to have written is parsed
    /// unconditionally; `XibalbaNameService` is guarded with `keyExistsJson` since it's
    /// confirmed absent from the live Base Sepolia file today (PRODUCTION_GAPS.md §4 --
    /// a separate, pre-existing staleness this script doesn't attempt to silently paper
    /// over by inventing a value) and would otherwise hard-revert this entire script.
    function _mergeDeploymentsFile() internal {
        string memory singletons = "singletons";
        vm.serializeAddress(
            singletons, "IntegrityToken", vm.parseJsonAddress(existingJson, ".singletons.IntegrityToken")
        );
        vm.serializeAddress(
            singletons, "UltraPlonkVerifier", vm.parseJsonAddress(existingJson, ".singletons.UltraPlonkVerifier")
        );
        vm.serializeAddress(singletons, "XibalbaAgentRegistry", registry);
        if (vm.keyExistsJson(existingJson, ".singletons.XibalbaNameService")) {
            vm.serializeAddress(
                singletons, "XibalbaNameService", vm.parseJsonAddress(existingJson, ".singletons.XibalbaNameService")
            );
        } else {
            console2.log("NOTE: .singletons.XibalbaNameService was absent from the existing file before this run too -- not written here either. See PRODUCTION_GAPS.md Sec4.");
        }
        vm.serializeAddress(
            singletons, "DomainRegistry", vm.parseJsonAddress(existingJson, ".singletons.DomainRegistry")
        );
        vm.serializeAddress(
            singletons, "AgentPrimitivesFactory", vm.parseJsonAddress(existingJson, ".singletons.AgentPrimitivesFactory")
        );
        vm.serializeAddress(
            singletons, "CoveredEntityRegistry", vm.parseJsonAddress(existingJson, ".singletons.CoveredEntityRegistry")
        );
        vm.serializeAddress(singletons, "SmartBAAFactory", baaFactory);
        vm.serializeAddress(
            singletons, "HIPAAGuardrailRegistry", vm.parseJsonAddress(existingJson, ".singletons.HIPAAGuardrailRegistry")
        );
        vm.serializeAddress(
            singletons, "MarketFactory", vm.parseJsonAddress(existingJson, ".singletons.MarketFactory")
        );
        vm.serializeAddress(
            singletons, "A2ACapitalPool", vm.parseJsonAddress(existingJson, ".singletons.A2ACapitalPool")
        );
        vm.serializeAddress(
            singletons, "IntegrityGovernance", vm.parseJsonAddress(existingJson, ".singletons.IntegrityGovernance")
        );
        string memory singletonsJson = vm.serializeAddress(singletons, "EHRGate", address(ehrGate));

        // cloneTemplates and protocolAddresses are untouched by this script -- neither
        // changes here, so both are just re-parsed field-by-field and re-serialized
        // (forge-std has no "copy this JSON object verbatim" primitive).
        string memory cloneTemplatesJson = _rawSection(existingJson, "cloneTemplates");
        string memory protocolAddressesJson = _rawSection(existingJson, "protocolAddresses");

        // network/domains are likewise untouched by this script but were silently
        // dropped by an earlier version of this merge (it only re-serialized
        // singletons/cloneTemplates/protocolAddresses/chainId) -- caught when the first
        // real Base Sepolia run of this script erased IntegrityGovernance, network, and
        // domains entirely. vm.writeJson replaces the whole file, so any field not
        // explicitly re-parsed here is lost, not merged.
        string memory root = "root";
        vm.serializeString(root, "singletons", singletonsJson);
        vm.serializeString(root, "cloneTemplates", cloneTemplatesJson);
        vm.serializeString(root, "protocolAddresses", protocolAddressesJson);
        vm.serializeString(root, "network", vm.parseJsonString(existingJson, ".network"));
        vm.serializeString(root, "domains", _rawDomains(existingJson));
        string memory finalJson = vm.serializeUint(root, "chainId", block.chainid);

        vm.writeJson(finalJson, path);
        console2.log("Merged EHRGate into", path);
    }

    /// @dev domains has dynamic keys (bytes32-valued, one per registered domain name),
    /// unlike every other section here which has a fixed known key set -- re-serialized
    /// by walking vm.parseJsonKeys rather than a hardcoded field list.
    function _rawDomains(string memory json) internal returns (string memory) {
        string[] memory keys = vm.parseJsonKeys(json, ".domains");
        if (keys.length == 0) {
            return "{}";
        }
        string memory d = "domainsTmp";
        string memory result;
        for (uint256 i = 0; i < keys.length; i++) {
            result = vm.serializeBytes32(d, keys[i], vm.parseJsonBytes32(json, string.concat(".domains.", keys[i])));
        }
        return result;
    }

    /// @dev forge-std has no "copy this JSON object verbatim" primitive, so
    /// `cloneTemplates`/`protocolAddresses` -- neither of which this script changes --
    /// are re-serialized the same way `_mergeDeploymentsFile` handles `singletons`:
    /// parse each known field back out, then re-serialize it unchanged.
    function _rawSection(string memory json, string memory sectionKey) internal returns (string memory) {
        if (keccak256(bytes(sectionKey)) == keccak256(bytes("cloneTemplates"))) {
            string memory s = "cloneTemplatesTmp";
            vm.serializeAddress(s, "ReputationRegistry", vm.parseJsonAddress(json, ".cloneTemplates.ReputationRegistry"));
            vm.serializeAddress(s, "Slasher", vm.parseJsonAddress(json, ".cloneTemplates.Slasher"));
            vm.serializeAddress(s, "VerifierRegistry", vm.parseJsonAddress(json, ".cloneTemplates.VerifierRegistry"));
            vm.serializeAddress(s, "ComplianceGate", vm.parseJsonAddress(json, ".cloneTemplates.ComplianceGate"));
            vm.serializeAddress(s, "AgentProfile", vm.parseJsonAddress(json, ".cloneTemplates.AgentProfile"));
            return vm.serializeAddress(s, "IntegrityMarket", vm.parseJsonAddress(json, ".cloneTemplates.IntegrityMarket"));
        }
        string memory p = "protocolAddressesTmp";
        vm.serializeAddress(p, "oracleSigner", vm.parseJsonAddress(json, ".protocolAddresses.oracleSigner"));
        vm.serializeAddress(p, "disputer", vm.parseJsonAddress(json, ".protocolAddresses.disputer"));
        vm.serializeAddress(p, "governance", vm.parseJsonAddress(json, ".protocolAddresses.governance"));
        vm.serializeAddress(p, "arbitrator", vm.parseJsonAddress(json, ".protocolAddresses.arbitrator"));
        vm.serializeAddress(p, "resolverSigner", vm.parseJsonAddress(json, ".protocolAddresses.resolverSigner"));
        return vm.serializeAddress(p, "funderWallet", vm.parseJsonAddress(json, ".protocolAddresses.funderWallet"));
    }
}
