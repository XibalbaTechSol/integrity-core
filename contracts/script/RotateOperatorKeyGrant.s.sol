// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {VmSafe} from "forge-std/Vm.sol";

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {AgentPrimitivesFactory} from "../src/framework/AgentPrimitivesFactory.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {DomainRegistry} from "../src/framework/DomainRegistry.sol";
import {SmartBAAFactory} from "../src/health/SmartBAAFactory.sol";
import {Slasher} from "../src/oracle/Slasher.sol";

/// @title RotateOperatorKeyGrant
/// @notice Phase 1 of 2 of rotating the single-operator testnet key (arbitrator/disputer/
/// funderWallet/governance/oracleSigner all point at one EOA, per `deployments.baseSepolia.
/// json`'s `protocolAddresses` -- a private key value for this address was accidentally
/// printed to a chat transcript; low real risk (documented testnet-only key, already
/// plaintext in `contracts/.env`) but rotating it out of caution).
///
/// GRANTS ONLY -- deliberately does not revoke the old key from anything. Verify the new
/// key actually works (this script logs everything it did; check it against the new key's
/// `hasRole`/`owner()` reads) before running `RotateOperatorKeyRevoke.s.sol`. Splitting
/// grant from revoke into two broadcasts means a bug here leaves the OLD key still fully
/// functional rather than bricking access mid-rotation.
///
/// Three categories of role, each needing a different approach (see the audit's own
/// rotation research):
///   1. Singleton `DEFAULT_ADMIN_ROLE`/`MINTER_ROLE` (AccessControl) and `governance`
///      (Ownable) -- self-service, old key just grants directly.
///   2. `oracleSigner`/`disputer` are `immutable` in `AgentPrimitivesFactory` -- can't be
///      changed on the existing factory. Deploy a new factory (reusing every existing
///      clone-implementation address unchanged) and swap `REGISTRAR_ROLE`, same pattern as
///      `FixComplianceGateFactory.s.sol`. Only affects FUTURE agent registrations.
///   3. Existing `Slasher` clones' `DEFAULT_ADMIN_ROLE`/`DISPUTER_ROLE`: `governance` is
///      passed straight through as `admin` at `initialize()` time (see
///      `AgentPrimitivesFactory.registerPrimitives`'s `Slasher(slasher).initialize
///      (governance, disputer)`), so the protocol key is the DIRECT admin on every
///      already-registered agent's Slasher clone -- self-service per clone.
///
/// NOT covered (confirmed out of scope, not a regression from this rotation):
///   - `ReputationRegistry.ORACLE_ROLE` and `StateAnchor.ANCHOR_ROLE` on existing clones:
///     admin = that agent's own SovereignAgent, not this operator key. Only an agent's own
///     controller can grant there (see the separate per-agent step for xibalba/xibalba-
///     quant, the two agents this operator also controls the controller key for).
///   - The one existing `IntegrityMarket`'s `RESOLVER_ROLE`: its `creator`
///     (0x62985f8EA627185eb1E2c4CedEc39260f0DC8E14) is a different address entirely, not
///     this operator key -- nothing to rotate here.
///   - `IntegrityGovernance.owner()`: confirmed via a dry run and a direct `owner()` read
///     that it is `0xabfeEaCbA00F38810E697b2970399fE03080FBeB`, NOT the old operator key --
///     `deployments.baseSepolia.json`'s `protocolAddresses.governance` field is stale for
///     this specific contract (likely an earlier, separately-key-rotated ownership
///     transfer that was never written back to that file). The old key was never the
///     owner here, so there is nothing for it to lose, and nothing this script can grant
///     to the new key either -- out of scope, flagged for the record rather than guessed.
/// @dev forge script script/RotateOperatorKeyGrant.s.sol --rpc-url base_sepolia --broadcast
contract RotateOperatorKeyGrant is Script {
    address oldKey;
    address newKey;

    address itk;
    address registry;
    address domainRegistry;
    address entityRegistry;
    address xns;
    address hipaaRegistry;
    address a2aPool;
    address baaFactory;
    address governanceContract;
    address oldFactory;

    address reputationRegistryImpl;
    address slasherImpl;
    address verifierRegistryImpl;
    address complianceGateImpl;
    address agentProfileImpl;
    address initialZkVerifier;

    AgentPrimitivesFactory newFactory;

    string existingJson;
    string path;

    function run() external {
        uint256 oldKeyPk = vm.envUint("FUNDER_PRIVATE_KEY");
        oldKey = vm.addr(oldKeyPk);
        newKey = vm.envAddress("NEW_OPERATOR_ADDRESS");

        path = "../deployments.baseSepolia.json";
        existingJson = vm.readFile(path);

        itk = vm.parseJsonAddress(existingJson, ".singletons.IntegrityToken");
        registry = vm.parseJsonAddress(existingJson, ".singletons.XibalbaAgentRegistry");
        domainRegistry = vm.parseJsonAddress(existingJson, ".singletons.DomainRegistry");
        entityRegistry = vm.parseJsonAddress(existingJson, ".singletons.CoveredEntityRegistry");
        xns = vm.parseJsonAddress(existingJson, ".singletons.XibalbaNameService");
        hipaaRegistry = vm.parseJsonAddress(existingJson, ".singletons.HIPAAGuardrailRegistry");
        a2aPool = vm.parseJsonAddress(existingJson, ".singletons.A2ACapitalPool");
        baaFactory = vm.parseJsonAddress(existingJson, ".singletons.SmartBAAFactory");
        governanceContract = vm.parseJsonAddress(existingJson, ".singletons.IntegrityGovernance");
        oldFactory = vm.parseJsonAddress(existingJson, ".singletons.AgentPrimitivesFactory");

        reputationRegistryImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.ReputationRegistry");
        slasherImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.Slasher");
        verifierRegistryImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.VerifierRegistry");
        complianceGateImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.ComplianceGate");
        agentProfileImpl = vm.parseJsonAddress(existingJson, ".cloneTemplates.AgentProfile");
        initialZkVerifier = vm.parseJsonAddress(existingJson, ".singletons.UltraPlonkVerifier");

        // Real Sepolia-registered agents' Slasher clones (resolved live from
        // XibalbaAgentRegistry off-chain before this script ran; hardcoded here rather
        // than re-resolved on-chain because the DID->address lookup needs the oracle's
        // Postgres cache, not anything Solidity can read cheaply in a script).
        address[4] memory slasherClones = [
            0x9055Ec7d095CA5190073994ff285c84e05Ecd38d, // xibalba
            0x9B115c234301ce6568c037BafB29408F587a4F49, // dde5c263 (unknown controller)
            0x596f20D8B18a54ba7A0dd45E823Ce61458155d80, // f96ae072 (unknown controller)
            0xfCFecb037aD31C3f935EE33431a0afBA18d263c8 // xibalba-quant
        ];

        vm.startBroadcast(oldKeyPk);

        // --- 1. Singleton DEFAULT_ADMIN_ROLE grants (AccessControl) ---
        AccessControl(itk).grantRole(0x00, newKey);
        AccessControl(registry).grantRole(0x00, newKey);
        AccessControl(domainRegistry).grantRole(0x00, newKey);
        AccessControl(entityRegistry).grantRole(0x00, newKey);
        // XibalbaNameService deliberately NOT touched here: the old key does not actually
        // hold DEFAULT_ADMIN_ROLE on it on-chain (confirmed via a dry run of this script,
        // which reverted AccessControlUnauthorizedAccount) -- a pre-existing drift from
        // an earlier deploy/key-rotation this task didn't cause and won't try to fix.
        // Nothing to grant or revoke here either way; XNS's real admin is unaffected.
        AccessControl(hipaaRegistry).grantRole(0x00, newKey);
        AccessControl(a2aPool).grantRole(0x00, newKey);
        AccessControl(baaFactory).grantRole(0x00, newKey);

        // --- 2. MINTER_ROLE on IntegrityToken ---
        AccessControl(itk).grantRole(keccak256("MINTER_ROLE"), newKey);

        // --- 3. arbitrator on SmartBAAFactory (old key already holds its DEFAULT_ADMIN_ROLE) ---
        SmartBAAFactory(baaFactory).setArbitrator(newKey);

        // --- 4. IntegrityGovernance ownership: SKIPPED, see contract docstring — old key
        // is not the real owner on-chain (confirmed via owner() read), so there is
        // nothing to transfer.

        // --- 5. New AgentPrimitivesFactory with new oracleSigner/disputer/governance ---
        newFactory = new AgentPrimitivesFactory(
            registry,
            domainRegistry,
            reputationRegistryImpl,
            slasherImpl,
            verifierRegistryImpl,
            complianceGateImpl,
            agentProfileImpl,
            newKey, // oracleSigner
            newKey, // disputer
            newKey, // governance
            itk,
            initialZkVerifier
        );
        XibalbaAgentRegistry(registry).grantRole(XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), address(newFactory));
        DomainRegistry(domainRegistry).grantRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), address(newFactory));
        // Same "exactly one authorized factory" invariant as FixComplianceGateFactory.s.sol
        // — safe to revoke the OLD factory here (not the old KEY, a different thing) since
        // the new factory is already confirmed granted in the two lines above.
        XibalbaAgentRegistry(registry).revokeRole(XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), oldFactory);
        DomainRegistry(domainRegistry).revokeRole(DomainRegistry(domainRegistry).REGISTRAR_ROLE(), oldFactory);

        // --- 6. Existing Slasher clones: governance is the direct DEFAULT_ADMIN_ROLE/DISPUTER_ROLE admin ---
        for (uint256 i = 0; i < slasherClones.length; i++) {
            Slasher(slasherClones[i]).grantRole(keccak256("DISPUTER_ROLE"), newKey);
            Slasher(slasherClones[i]).grantRole(0x00, newKey);
        }

        vm.stopBroadcast();

        console2.log("=== Operator key rotation: GRANT phase complete ===");
        console2.log("old key:   ", oldKey);
        console2.log("new key:   ", newKey);
        console2.log("new AgentPrimitivesFactory:", address(newFactory));
        console2.log("Verify new key's access before running RotateOperatorKeyRevoke.s.sol.");

        if (vmSafe.isContext(VmSafe.ForgeContext.ScriptBroadcast) || vmSafe.isContext(VmSafe.ForgeContext.ScriptResume)) {
            _mergeDeploymentsFile();
        } else {
            console2.log("Dry run (no --broadcast) -- skipping deployments file write.");
        }
    }

    /// @dev Updates singletons.AgentPrimitivesFactory + protocolAddresses.* to the new
    /// key. Does NOT touch resolverSigner (per-market RESOLVER_ROLE, this operator key was
    /// never that market's creator/admin — confirmed out of scope, see contract docstring).
    function _mergeDeploymentsFile() internal {
        string memory singletons = "singletons";
        vm.serializeAddress(singletons, "IntegrityToken", itk);
        vm.serializeAddress(singletons, "UltraPlonkVerifier", initialZkVerifier);
        vm.serializeAddress(singletons, "XibalbaAgentRegistry", registry);
        vm.serializeAddress(singletons, "XibalbaNameService", xns);
        vm.serializeAddress(singletons, "DomainRegistry", domainRegistry);
        vm.serializeAddress(singletons, "AgentPrimitivesFactory", address(newFactory));
        vm.serializeAddress(singletons, "CoveredEntityRegistry", entityRegistry);
        vm.serializeAddress(singletons, "SmartBAAFactory", baaFactory);
        vm.serializeAddress(singletons, "HIPAAGuardrailRegistry", hipaaRegistry);
        vm.serializeAddress(
            singletons, "MarketFactory", vm.parseJsonAddress(existingJson, ".singletons.MarketFactory")
        );
        vm.serializeAddress(singletons, "IntegrityGovernance", governanceContract);
        string memory singletonsJson = vm.serializeAddress(singletons, "A2ACapitalPool", a2aPool);

        string memory cloneTemplates = "cloneTemplates";
        vm.serializeAddress(cloneTemplates, "ReputationRegistry", reputationRegistryImpl);
        vm.serializeAddress(cloneTemplates, "Slasher", slasherImpl);
        vm.serializeAddress(cloneTemplates, "VerifierRegistry", verifierRegistryImpl);
        vm.serializeAddress(cloneTemplates, "ComplianceGate", complianceGateImpl);
        vm.serializeAddress(cloneTemplates, "AgentProfile", agentProfileImpl);
        string memory cloneTemplatesJson = vm.serializeAddress(
            cloneTemplates, "IntegrityMarket", vm.parseJsonAddress(existingJson, ".cloneTemplates.IntegrityMarket")
        );

        string memory protocolAddresses = "protocolAddresses";
        vm.serializeAddress(protocolAddresses, "oracleSigner", newKey);
        vm.serializeAddress(protocolAddresses, "disputer", newKey);
        vm.serializeAddress(protocolAddresses, "governance", newKey);
        vm.serializeAddress(protocolAddresses, "arbitrator", newKey);
        vm.serializeAddress(
            protocolAddresses, "resolverSigner", vm.parseJsonAddress(existingJson, ".protocolAddresses.resolverSigner")
        );
        string memory protocolAddressesJson = vm.serializeAddress(protocolAddresses, "funderWallet", newKey);

        // NOTE: the live file's "domains" field is currently `null` (not the populated
        // object FixComplianceGateFactory.s.sol's near-identical merge logic assumed when
        // it was written) -- parsing bytes32 values out of it reverts. Preserved as an
        // empty object here rather than fabricating hash values that don't exist on-chain
        // in this field anymore; this script doesn't touch domain data either way.
        string memory domainsJson = "{}";

        string memory root = "root";
        vm.serializeUint(root, "chainId", block.chainid);
        vm.serializeString(root, "network", "base-sepolia");
        vm.serializeString(root, "singletons", singletonsJson);
        vm.serializeString(root, "cloneTemplates", cloneTemplatesJson);
        vm.serializeString(root, "protocolAddresses", protocolAddressesJson);
        string memory finalJson = vm.serializeString(root, "domains", domainsJson);

        vm.writeJson(finalJson, path);
        console2.log("Updated deployment record at", path);
    }
}
