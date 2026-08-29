// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {IntegrityMarket} from "../src/markets/IntegrityMarket.sol";
import {MarketFactory} from "../src/markets/MarketFactory.sol";
import {A2ACapitalPool} from "../src/markets/A2ACapitalPool.sol";

/// @title DeployMarkets
/// @notice Incremental deploy: adds the market/application layer (IntegrityMarket
/// implementation, MarketFactory, A2ACapitalPool) to an ALREADY-LIVE protocol
/// deployment, without touching -- let alone re-deploying -- any existing singleton.
/// Re-running the full genesis `Deploy.s.sol` against a network that already has real
/// registered agents would orphan every one of them (a fresh XibalbaAgentRegistry has
/// zero agents, a fresh IntegrityToken has zero balances). This script instead reads
/// the existing `../deployments.<network>.json` written by `Deploy.s.sol`, deploys the
/// new contracts against the existing IntegrityToken/XibalbaAgentRegistry addresses,
/// and merges the new addresses into that SAME file (preserving every existing field)
/// rather than overwriting it.
/// @dev Run against Base Sepolia with:
///   forge script script/DeployMarkets.s.sol --rpc-url base_sepolia --broadcast --verify
/// Requires `../deployments.<network>.json` to already exist (i.e. `Deploy.s.sol` has
/// already run once against this network).
contract DeployMarkets is Script {
    address deployer;
    address oracleSigner;
    address resolverSigner;

    address itk;
    address registry;

    IntegrityMarket marketImpl;
    MarketFactory marketFactory;
    A2ACapitalPool capitalPool;

    string existingJson;
    string network;
    string path;

    function run() external {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        deployer = vm.addr(deployerKey);

        network = block.chainid == 84532 ? "baseSepolia" : "local";
        path = string.concat("../deployments.", network, ".json");
        existingJson = vm.readFile(path);

        itk = vm.parseJsonAddress(existingJson, ".singletons.IntegrityToken");
        registry = vm.parseJsonAddress(existingJson, ".singletons.XibalbaAgentRegistry");
        oracleSigner = vm.parseJsonAddress(existingJson, ".protocolAddresses.oracleSigner");
        // Demo resolver for IntegrityMarket -- see IntegrityMarket.sol's contract-level
        // NatSpec on the RESOLVER_ROLE trust boundary. Defaults to the existing oracle
        // signer (the party already trusted to push AIS/telemetry state) rather than
        // introducing a brand-new protocol key for this MVP.
        resolverSigner = vm.envOr("RESOLVER_ADDRESS", oracleSigner);

        vm.startBroadcast(deployerKey);
        marketImpl = new IntegrityMarket(itk, registry);
        marketFactory = new MarketFactory(registry, address(marketImpl));
        capitalPool = new A2ACapitalPool(itk, registry, deployer);
        capitalPool.grantRole(capitalPool.BREACH_REPORTER_ROLE(), oracleSigner);
        vm.stopBroadcast();

        _logSummary();
        _mergeDeploymentsFile();
    }

    function _logSummary() internal view {
        console2.log("=== Integrity Protocol market-layer deploy ===");
        console2.log("network:                ", network);
        console2.log("existing IntegrityToken:", itk);
        console2.log("existing AgentRegistry: ", registry);
        console2.log("IntegrityMarketImpl:    ", address(marketImpl));
        console2.log("MarketFactory:          ", address(marketFactory));
        console2.log("A2ACapitalPool:         ", address(capitalPool));
        console2.log("resolverSigner:         ", resolverSigner);
    }

    /// @dev Re-serializes the ENTIRE existing deployments file (every field
    /// `Deploy.s.sol` originally wrote, read back via `vm.parseJson*`), adding only the
    /// 3 new addresses -- so this script is safe to run against a live file with real
    /// registered agents without losing any existing record. Keys containing a literal
    /// "." (the domain names) need the bracket path form, not the dotted form, or
    /// forge-std's jq-like parser would treat the dot as a nesting separator.
    function _mergeDeploymentsFile() internal {
        string memory singletons = "singletons";
        vm.serializeAddress(singletons, "IntegrityToken", itk);
        vm.serializeAddress(
            singletons, "UltraPlonkVerifier", vm.parseJsonAddress(existingJson, ".singletons.UltraPlonkVerifier")
        );
        vm.serializeAddress(singletons, "XibalbaAgentRegistry", registry);
        if (vm.keyExistsJson(existingJson, ".singletons.IntegrityIdentityReadV1")) {
            vm.serializeAddress(
                singletons,
                "IntegrityIdentityReadV1",
                vm.parseJsonAddress(existingJson, ".singletons.IntegrityIdentityReadV1")
            );
        }
        vm.serializeAddress(
            singletons, "XibalbaNameService", vm.parseJsonAddress(existingJson, ".singletons.XibalbaNameService")
        );
        vm.serializeAddress(
            singletons, "DomainRegistry", vm.parseJsonAddress(existingJson, ".singletons.DomainRegistry")
        );
        vm.serializeAddress(
            singletons,
            "AgentPrimitivesFactory",
            vm.parseJsonAddress(existingJson, ".singletons.AgentPrimitivesFactory")
        );
        vm.serializeAddress(
            singletons, "CoveredEntityRegistry", vm.parseJsonAddress(existingJson, ".singletons.CoveredEntityRegistry")
        );
        vm.serializeAddress(
            singletons, "SmartBAAFactory", vm.parseJsonAddress(existingJson, ".singletons.SmartBAAFactory")
        );
        vm.serializeAddress(
            singletons,
            "HIPAAGuardrailRegistry",
            vm.parseJsonAddress(existingJson, ".singletons.HIPAAGuardrailRegistry")
        );
        vm.serializeAddress(singletons, "MarketFactory", address(marketFactory));
        string memory singletonsJson = vm.serializeAddress(singletons, "A2ACapitalPool", address(capitalPool));

        string memory cloneTemplates = "cloneTemplates";
        vm.serializeAddress(
            cloneTemplates,
            "ReputationRegistry",
            vm.parseJsonAddress(existingJson, ".cloneTemplates.ReputationRegistry")
        );
        vm.serializeAddress(cloneTemplates, "Slasher", vm.parseJsonAddress(existingJson, ".cloneTemplates.Slasher"));
        vm.serializeAddress(
            cloneTemplates, "VerifierRegistry", vm.parseJsonAddress(existingJson, ".cloneTemplates.VerifierRegistry")
        );
        vm.serializeAddress(
            cloneTemplates, "ComplianceGate", vm.parseJsonAddress(existingJson, ".cloneTemplates.ComplianceGate")
        );
        vm.serializeAddress(
            cloneTemplates, "AgentProfile", vm.parseJsonAddress(existingJson, ".cloneTemplates.AgentProfile")
        );
        string memory cloneTemplatesJson = vm.serializeAddress(cloneTemplates, "IntegrityMarket", address(marketImpl));

        string memory protocolAddresses = "protocolAddresses";
        vm.serializeAddress(protocolAddresses, "oracleSigner", oracleSigner);
        vm.serializeAddress(
            protocolAddresses, "disputer", vm.parseJsonAddress(existingJson, ".protocolAddresses.disputer")
        );
        vm.serializeAddress(
            protocolAddresses, "governance", vm.parseJsonAddress(existingJson, ".protocolAddresses.governance")
        );
        vm.serializeAddress(
            protocolAddresses, "arbitrator", vm.parseJsonAddress(existingJson, ".protocolAddresses.arbitrator")
        );
        vm.serializeAddress(protocolAddresses, "resolverSigner", resolverSigner);
        string memory protocolAddressesJson = vm.serializeAddress(
            protocolAddresses, "funderWallet", vm.parseJsonAddress(existingJson, ".protocolAddresses.funderWallet")
        );

        string memory domains = "domains";
        vm.serializeBytes32(
            domains, "general.integrity", vm.parseJsonBytes32(existingJson, '.domains["general.integrity"]')
        );
        string memory domainsJson = vm.serializeBytes32(
            domains, "healthcare.integrity", vm.parseJsonBytes32(existingJson, '.domains["healthcare.integrity"]')
        );

        string memory root = "root";
        vm.serializeUint(root, "chainId", block.chainid);
        vm.serializeString(root, "network", block.chainid == 84532 ? "base-sepolia" : "local");
        vm.serializeString(root, "singletons", singletonsJson);
        vm.serializeString(root, "cloneTemplates", cloneTemplatesJson);
        vm.serializeString(root, "protocolAddresses", protocolAddressesJson);
        string memory finalJson = vm.serializeString(root, "domains", domainsJson);

        vm.writeJson(finalJson, path);
        console2.log("Updated deployment record at", path);
    }
}
