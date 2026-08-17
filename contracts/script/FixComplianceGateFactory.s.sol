// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {VmSafe} from "forge-std/Vm.sol";

import {ComplianceGate} from "../src/health/ComplianceGate.sol";
import {AgentPrimitivesFactory} from "../src/framework/AgentPrimitivesFactory.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {DomainRegistry} from "../src/framework/DomainRegistry.sol";

/// @title FixComplianceGateFactory
/// @notice Incremental deploy fixing a real source-vs-deployed-bytecode drift found
/// 2026-07-09: the live `ComplianceGate` implementation (and therefore
/// `AgentPrimitivesFactory`, which holds `complianceGateImpl` as `immutable`) was
/// deployed by genesis `Deploy.s.sol` BEFORE `ComplianceGate.Vertical` was extended from
/// `{None, Healthcare}` to `{None, Healthcare, PredictionMarket, Trading,
/// CapitalAllocation}` (see contracts/src/markets/ work, same session). Solidity's ABI
/// decoder rejects any enum value outside the range the DEPLOYED bytecode was compiled
/// with, so `registerPrimitives(..., vertical=2|3|4)` reverts against the live factory
/// today even though the current source supports all 5 values.
///
/// Fix: deploy a new `ComplianceGate` implementation from current source (all 5 Vertical
/// values valid), then a new `AgentPrimitivesFactory` pointing at it (required because
/// `complianceGateImpl` is `immutable` -- there's no setter, the whole factory must be
/// redeployed). The 4 OTHER clone implementations (ReputationRegistry/Slasher/
/// VerifierRegistry/AgentProfile) are UNCHANGED and reused as-is; only ComplianceGate
/// needed fixing.
///
/// Safe for already-registered agents: an EIP-1167 clone's delegatecall target is fixed
/// at clone time to whatever implementation address `Clones.clone()` was called with. An
/// existing agent's ComplianceGate clone keeps delegatecalling the OLD implementation
/// address forever -- that address, and its bytecode, are never touched or removed by
/// this script. Only NEW registrations (via the new factory) get the fixed 5-value
/// enum support.
///
/// Per XibalbaAgentRegistry.sol / DomainRegistry.sol's stated invariant ("only
/// AgentPrimitivesFactory should ever hold REGISTRAR_ROLE"), this script also revokes
/// REGISTRAR_ROLE from the OLD factory once the new one holds it, so exactly one factory
/// is ever authorized at a time.
/// @dev Run against Base Sepolia with:
///   forge script script/FixComplianceGateFactory.s.sol --rpc-url base_sepolia --broadcast --verify
/// Requires `../deployments.<network>.json` to already exist.
contract FixComplianceGateFactory is Script {
    address deployer;
    address oracleSigner;
    address disputer;
    address governance;

    address registry;
    address domainRegistry;
    address entityRegistry;
    address baaFactory;
    address itk;
    address initialZkVerifier;
    address reputationRegistryImpl;
    address slasherImpl;
    address verifierRegistryImpl;
    address agentProfileImpl;
    address oldFactory;

    ComplianceGate newComplianceGateImpl;
    AgentPrimitivesFactory newFactory;

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
        domainRegistry = vm.parseJsonAddress(existingJson, ".singletons.DomainRegistry");
        entityRegistry = vm.parseJsonAddress(existingJson, ".singletons.CoveredEntityRegistry");
        baaFactory = vm.parseJsonAddress(existingJson, ".singletons.SmartBAAFactory");
        itk = vm.parseJsonAddress(existingJson, ".singletons.IntegrityToken");
        initialZkVerifier = vm.parseJsonAddress(existingJson, ".singletons.UltraPlonkVerifier");
        oldFactory = vm.parseJsonAddress(existingJson, ".singletons.AgentPrimitivesFactory");

        reputationRegistryImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.ReputationRegistry");
        slasherImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.Slasher");
        verifierRegistryImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.VerifierRegistry");
        agentProfileImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.AgentProfile");

        oracleSigner = vm.parseJsonAddress(existingJson, ".protocolAddresses.oracleSigner");
        disputer = vm.parseJsonAddress(existingJson, ".protocolAddresses.disputer");
        governance = vm.parseJsonAddress(existingJson, ".protocolAddresses.governance");

        vm.startBroadcast(deployerKey);

        newComplianceGateImpl = new ComplianceGate(entityRegistry, baaFactory);

        newFactory = new AgentPrimitivesFactory(
            registry,
            domainRegistry,
            reputationRegistryImpl,
            slasherImpl,
            verifierRegistryImpl,
            address(newComplianceGateImpl),
            agentProfileImpl,
            oracleSigner,
            disputer,
            governance,
            itk,
            initialZkVerifier
        );

        XibalbaAgentRegistry(registry).grantRole(XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), address(newFactory));
        DomainRegistry(domainRegistry).grantRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), address(newFactory));
        // Maintain "exactly one factory holds REGISTRAR_ROLE" -- revoke the old one only
        // AFTER the new one is confirmed granted, so there's never a window with zero
        // authorized factories.
        XibalbaAgentRegistry(registry).revokeRole(XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), oldFactory);
        DomainRegistry(domainRegistry).revokeRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), oldFactory);

        vm.stopBroadcast();

        _logSummary();

        // Discovered the hard way running this script: `vm.writeJson` (inside
        // `_mergeDeploymentsFile`) is a filesystem cheatcode that executes even
        // during a dry run (`forge script` without `--broadcast`) -- only the
        // on-chain transactions are skipped, not the file write. An unguarded
        // dry run therefore silently overwrites the real deployments file with
        // addresses that were only ever simulated, never actually deployed.
        // Guard against that: only merge when this is a real broadcast.
        if (vmSafe.isContext(VmSafe.ForgeContext.ScriptBroadcast) || vmSafe.isContext(VmSafe.ForgeContext.ScriptResume))
        {
            _mergeDeploymentsFile();
        } else {
            console2.log("Dry run (no --broadcast) -- skipping deployments file write.");
        }
    }

    function _logSummary() internal view {
        console2.log("=== ComplianceGate/AgentPrimitivesFactory fix deploy ===");
        console2.log("network:                  ", network);
        console2.log("old AgentPrimitivesFactory:", oldFactory);
        console2.log("new ComplianceGateImpl:   ", address(newComplianceGateImpl));
        console2.log("new AgentPrimitivesFactory:", address(newFactory));
    }

    /// @dev Same re-serialize-the-whole-file pattern as DeployMarkets.s.sol -- reads
    /// every existing field back via vm.parseJson*, updates only
    /// `singletons.AgentPrimitivesFactory` and `cloneTemplates.ComplianceGate`.
    function _mergeDeploymentsFile() internal {
        string memory singletons = "singletons";
        vm.serializeAddress(singletons, "IntegrityToken", itk);
        vm.serializeAddress(singletons, "UltraPlonkVerifier", initialZkVerifier);
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
        vm.serializeAddress(singletons, "DomainRegistry", domainRegistry);
        vm.serializeAddress(singletons, "AgentPrimitivesFactory", address(newFactory));
        vm.serializeAddress(singletons, "CoveredEntityRegistry", entityRegistry);
        vm.serializeAddress(singletons, "SmartBAAFactory", baaFactory);
        vm.serializeAddress(
            singletons,
            "HIPAAGuardrailRegistry",
            vm.parseJsonAddress(existingJson, ".singletons.HIPAAGuardrailRegistry")
        );
        vm.serializeAddress(singletons, "MarketFactory", vm.parseJsonAddress(existingJson, ".singletons.MarketFactory"));
        string memory singletonsJson = vm.serializeAddress(
            singletons, "A2ACapitalPool", vm.parseJsonAddress(existingJson, ".singletons.A2ACapitalPool")
        );

        string memory cloneTemplates = "cloneTemplates";
        vm.serializeAddress(cloneTemplates, "ReputationRegistry", reputationRegistryImpl);
        vm.serializeAddress(cloneTemplates, "Slasher", slasherImpl);
        vm.serializeAddress(cloneTemplates, "VerifierRegistry", verifierRegistryImpl);
        vm.serializeAddress(cloneTemplates, "ComplianceGate", address(newComplianceGateImpl));
        vm.serializeAddress(cloneTemplates, "AgentProfile", agentProfileImpl);
        string memory cloneTemplatesJson = vm.serializeAddress(
            cloneTemplates, "IntegrityMarket", vm.parseJsonAddress(existingJson, ".cloneTemplates.IntegrityMarket")
        );

        string memory protocolAddresses = "protocolAddresses";
        vm.serializeAddress(protocolAddresses, "oracleSigner", oracleSigner);
        vm.serializeAddress(protocolAddresses, "disputer", disputer);
        vm.serializeAddress(protocolAddresses, "governance", governance);
        vm.serializeAddress(
            protocolAddresses, "arbitrator", vm.parseJsonAddress(existingJson, ".protocolAddresses.arbitrator")
        );
        vm.serializeAddress(
            protocolAddresses, "resolverSigner", vm.parseJsonAddress(existingJson, ".protocolAddresses.resolverSigner")
        );
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
