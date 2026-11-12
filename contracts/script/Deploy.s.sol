// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {IntegrityToken} from "../src/oracle/IntegrityToken.sol";
import {RejectAllZkVerifier} from "../src/oracle/RejectAllZkVerifier.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {AgentAuthorityResolver} from "../src/framework/AgentAuthorityResolver.sol";
import {XibalbaNameService} from "../src/framework/XibalbaNameService.sol";
import {DomainRegistry} from "../src/framework/DomainRegistry.sol";
import {CoveredEntityRegistry} from "../src/health/CoveredEntityRegistry.sol";
import {SmartBAAFactory} from "../src/health/SmartBAAFactory.sol";
import {HIPAAGuardrailRegistry} from "../src/health/HIPAAGuardrailRegistry.sol";
import {EHRGate} from "../src/health/EHRGate.sol";
import {ReputationRegistry} from "../src/oracle/ReputationRegistry.sol";
import {Slasher} from "../src/oracle/Slasher.sol";
import {VerifierRegistry} from "../src/oracle/VerifierRegistry.sol";
import {ComplianceGate} from "../src/health/ComplianceGate.sol";
import {AgentProfile} from "../src/framework/AgentProfile.sol";
import {AgentPrimitivesFactory} from "../src/framework/AgentPrimitivesFactory.sol";
import {IntegrityIdentityReadV1} from "../src/kernel/IntegrityIdentityReadV1.sol";
import {AllowlistAnchorPolicy} from "../src/core/AllowlistAnchorPolicy.sol";
import {ConstraintExecutionPolicy} from "../src/core/ConstraintExecutionPolicy.sol";
import {ITK} from "../src/trust/ITK.sol";
import {TrustConfig} from "../src/trust/TrustConfig.sol";
import {StakeVault} from "../src/trust/StakeVault.sol";
import {PolicyRegistry} from "../src/trust/PolicyRegistry.sol";
import {OpenPolicyModule} from "../src/trust/OpenPolicyModule.sol";
import {AISRegistry} from "../src/trust/AISRegistry.sol";
import {RewardRegistry} from "../src/trust/RewardRegistry.sol";
import {DiscountRewardModule} from "../src/trust/DiscountRewardModule.sol";
import {ActionAnchor} from "../src/trust/ActionAnchor.sol";

/// @title Deploy
/// @notice Deploys the full protocol genesis: every global singleton, all 5 EIP-1167
/// clone-implementation contracts, and `AgentPrimitivesFactory` — then wires
/// REGISTRAR_ROLE and bootstraps two open domains so agents can register immediately
/// after this script finishes. Writes every address to `../deployments.<network>.json`
/// (see docs/INTERFACE_CONTRACT.md §6 for the exact shape).
/// @dev Run against Base Sepolia with:
///   forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast --verify
/// Individual agents are NOT deployed here — this script only stands up the shared
/// protocol infrastructure an agent's own wallet later self-registers against (see
/// integrity-sdk's registration.py for that sequence).
contract Deploy is Script {
    // Minimum effective AIS (post ZK-boost) required to access PHI via EHRGate —
    // mirrors the README's verification-ladder "700+ institutional credit / 850+
    // TEE-bound institutional trust" framing and test/health/EHRGate.t.sol's own
    // THRESHOLD constant. Mutable post-deploy via EHRGate.setThreshold, not frozen here.
    uint256 constant EHR_GATE_MIN_AIS_THRESHOLD = 800;

    // v2 trust layer. An AISRegistry checkpoint below this score (basis points, 0..10000)
    // latches the agent's freeze. It must be > 0 or the freeze can never fire, and it sits
    // below the tier-0 identity ceiling (AIS 300/1000 = 3000 bps) so an honest but unverified
    // agent is not frozen by its first checkpoint. Override with FREEZE_THRESHOLD_BPS;
    // mutable post-deploy via StakeVault.setFreezeThreshold.
    uint256 constant DEFAULT_FREEZE_THRESHOLD_BPS = 1000;
    // DiscountRewardModule's documented default: the full score range maps to the full 50% cap.
    uint256 constant DISCOUNT_BPS_PER_POINT = 50;

    // Deployed/derived addresses, held as contract-level state purely so
    // `_writeDeploymentsFile` can read them after `run()`'s local variables are gone.
    address deployer;
    address oracleSigner;
    address disputer;
    address governance;
    address arbitrator;

    IntegrityToken itk;
    RejectAllZkVerifier verifier;
    XibalbaAgentRegistry registry;
    AgentAuthorityResolver authorityResolver;
    IntegrityIdentityReadV1 identityRead;
    AllowlistAnchorPolicy defaultAnchorPolicy;
    ConstraintExecutionPolicy defaultExecutionPolicy;
    XibalbaNameService xns;
    DomainRegistry domainRegistry;
    CoveredEntityRegistry entityRegistry;
    SmartBAAFactory baaFactory;
    HIPAAGuardrailRegistry guardrailRegistry;
    EHRGate ehrGate;

    ReputationRegistry reputationRegistryImpl;
    Slasher slasherImpl;
    VerifierRegistry verifierRegistryImpl;
    ComplianceGate complianceGateImpl;
    AgentProfile agentProfileImpl;

    AgentPrimitivesFactory factory;

    ITK itkV2;
    TrustConfig trustConfig;
    StakeVault stakeVault;
    PolicyRegistry policyRegistry;
    OpenPolicyModule openPolicyModule;
    AISRegistry aisRegistry;
    RewardRegistry rewardRegistry;
    DiscountRewardModule discountRewardModule;
    ActionAnchor actionAnchor;

    bytes32 generalDomainId;
    bytes32 healthcareDomainId;

    function run() external {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        deployer = vm.addr(deployerKey);

        // Protocol-held roles all default to the deployer for a single-operator
        // testnet deployment — see .env.example's NatSpec-equivalent comment on why a
        // production deployment should split these onto separate keys.
        oracleSigner = vm.envOr("ORACLE_SIGNER_ADDRESS", deployer);
        disputer = vm.envOr("DISPUTER_ADDRESS", deployer);
        governance = vm.envOr("GOVERNANCE_ADDRESS", deployer);
        arbitrator = vm.envOr("ARBITRATOR_ADDRESS", deployer);

        if (block.chainid != 31337) {
            require(oracleSigner != deployer, "P0: oracleSigner cannot be deployer");
            require(disputer != deployer, "P0: disputer cannot be deployer");
            require(governance != deployer, "P0: governance cannot be deployer");
            require(arbitrator != deployer, "P0: arbitrator cannot be deployer");
            require(oracleSigner != disputer, "P0: Oracle must be isolated");
        }

        vm.startBroadcast(deployerKey);

        _deploySingletons();
        _deployCloneImplementations();
        _deployFactory();
        _deployTrustLayer();
        _wireRoles();
        _bootstrapDomains();
        _wireTrustDomains();
        _handOffTrustAdmin();

        vm.stopBroadcast();

        _logSummary();
        _writeDeploymentsFile();
    }

    function _deploySingletons() internal {
        // Initial mint is intentionally 0 — the deployer mints $ITK to the funder
        // wallet (or a faucet contract, in a later phase) as a separate, auditable
        // step rather than baking an arbitrary genesis balance into the deploy tx.
        itk = new IntegrityToken(deployer, 0);
        // ZK proving is retired (docs/EXECUTION_PLAN.md A1). The PrimitiveSet templates still
        // need a verifier address until the Phase C cutover; this one rejects every proof, so the
        // ZK boost is unreachable by construction. See RejectAllZkVerifier.sol.
        verifier = new RejectAllZkVerifier();
        registry = new XibalbaAgentRegistry(deployer);
        authorityResolver = new AgentAuthorityResolver(address(registry));

        address[] memory oracleCallers = new address[](1);
        oracleCallers[0] = oracleSigner;
        defaultAnchorPolicy = new AllowlistAnchorPolicy(deployer, oracleCallers);
        defaultExecutionPolicy = new ConstraintExecutionPolicy(deployer, 0, type(uint256).max, false);

        // Read-only Integrity identity discovery facade. It intentionally exposes no
        // ERC-721 or native ERC-8004 ownership/transfer surface; see its NatSpec and
        // docs/INTERFACE_CONTRACT.md before integrating it.
        identityRead = new IntegrityIdentityReadV1(address(registry));
        // Deployed right after `registry` since XNS's register() checks
        // registry.isRegisteredAgent(msg.sender) — nothing else in this script depends
        // on XNS, so it has no other ordering constraint. XNS's own REGISTRAR_ROLE
        // (dispute intervention only, see XibalbaNameService.sol's NatSpec) is
        // deliberately left ungranted here — registration itself never needs it, and
        // granting dispute-resolution power isn't a genesis-time decision this script
        // should make silently; grant it to `governance` in a later transaction if and
        // when that capability is actually wanted.
        xns = new XibalbaNameService(deployer, address(registry));
        domainRegistry = new DomainRegistry(deployer);
        entityRegistry = new CoveredEntityRegistry(deployer);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, deployer);
        guardrailRegistry = new HIPAAGuardrailRegistry(deployer, oracleSigner);
        // Was previously deployed nowhere (PRODUCTION_GAPS.md §4) despite being the
        // actual PHI-access enforcement contract ComplianceGate's own NatSpec says it
        // does NOT replace — the three-way consent+BAA+AIS gate the Integrity Health vertical's
        // docs describe had no reachable contract to call on-chain until this line.
        ehrGate = new EHRGate(
            address(registry),
            address(baaFactory),
            address(authorityResolver),
            EHR_GATE_MIN_AIS_THRESHOLD,
            block.chainid != 31337 ? governance : deployer
        );
    }

    /// @dev Each clone-implementation contract's own constructor calls
    /// `_disableInitializers()` (see each contract's NatSpec) — deploying it here does
    /// NOT make it usable directly; only `AgentPrimitivesFactory`'s `Clones.clone(...)`
    /// calls against these addresses produce real, initializable agent primitives.
    function _deployCloneImplementations() internal {
        reputationRegistryImpl = new ReputationRegistry();
        slasherImpl = new Slasher(address(itk));
        verifierRegistryImpl = new VerifierRegistry();
        complianceGateImpl = new ComplianceGate(address(entityRegistry), address(baaFactory));
        agentProfileImpl = new AgentProfile(address(domainRegistry));
    }

    function _deployFactory() internal {
        factory = new AgentPrimitivesFactory(
            address(registry),
            address(domainRegistry),
            address(reputationRegistryImpl),
            address(slasherImpl),
            address(verifierRegistryImpl),
            address(complianceGateImpl),
            address(agentProfileImpl),
            oracleSigner,
            disputer,
            governance,
            address(itk),
            address(verifier)
        );
    }

    /// @dev Deploys and wires the v2 trust layer so the SovereignAgent execute gate ships LIVE.
    /// Without this the registry's `trustConfig` is zero and every agent's gate resolves to
    /// nothing: no freeze, no policy, no stake lock.
    ///
    /// Ordering matters. `registry.setTrustConfig` comes BEFORE the AIS registry is granted
    /// `AIS_REGISTRY_ROLE`: that role is what lets a checkpoint freeze an agent, and a freeze
    /// recorded in a vault the gate does not yet read would leave a frozen agent executing.
    /// This also runs before `_wireRoles`, which hands the registry's admin role to governance.
    function _deployTrustLayer() internal {
        // Distinct from `IntegrityToken` above (also displayed "$ITK"): this is the v2 stake
        // asset. The legacy token and everything importing it are untouched.
        itkV2 = new ITK(deployer, 0);
        stakeVault = new StakeVault(address(itkV2), deployer);
        policyRegistry = new PolicyRegistry(deployer);
        openPolicyModule = new OpenPolicyModule();
        rewardRegistry = new RewardRegistry(deployer);
        discountRewardModule = new DiscountRewardModule(address(rewardRegistry), DISCOUNT_BPS_PER_POINT);
        aisRegistry = new AISRegistry(deployer);
        actionAnchor = new ActionAnchor();

        trustConfig = new TrustConfig(deployer);
        trustConfig.setStakeVault(address(stakeVault));
        trustConfig.setPolicyRegistry(address(policyRegistry));
        trustConfig.setRewardDiscountModule(address(discountRewardModule));

        uint256 threshold = vm.envOr("FREEZE_THRESHOLD_BPS", DEFAULT_FREEZE_THRESHOLD_BPS);
        require(threshold > 0 && threshold <= 10_000, "FREEZE_THRESHOLD_BPS must be in 1..10000");
        // forge-lint: disable-next-line(unsafe-typecast)
        stakeVault.setFreezeThreshold(uint32(threshold));

        aisRegistry.setStakeVault(address(stakeVault));
        aisRegistry.setRewardRegistry(address(rewardRegistry));
        aisRegistry.setAgentRegistry(address(registry));

        // The gate goes live here; only then may anything be able to freeze.
        registry.setTrustConfig(address(trustConfig));

        stakeVault.grantRole(stakeVault.AIS_REGISTRY_ROLE(), address(aisRegistry));
        stakeVault.grantRole(stakeVault.DISPUTER_ROLE(), disputer);
        rewardRegistry.grantRole(rewardRegistry.NOTIFIER_ROLE(), address(aisRegistry));
        aisRegistry.grantRole(aisRegistry.SCORER_ROLE(), oracleSigner);
    }

    /// @dev Gives each bootstrapped domain a policy module and a reward module. A registered
    /// agent in a domain with no policy module fail-closes on every `execute`.
    function _wireTrustDomains() internal {
        bytes32[2] memory domainIds = [generalDomainId, healthcareDomainId];
        for (uint256 i; i < domainIds.length; i++) {
            policyRegistry.setModule(domainIds[i], address(openPolicyModule));
            rewardRegistry.setModule(domainIds[i], address(discountRewardModule));
        }
    }

    /// @dev Off local chains the deployer keeps no authority over the trust layer, matching
    /// `_wireRoles`. Runs last because `_wireTrustDomains` needs the deployer's admin role.
    function _handOffTrustAdmin() internal {
        if (block.chainid == 31337) return;

        itkV2.grantRole(itkV2.MINTER_ROLE(), governance);
        itkV2.revokeRole(itkV2.MINTER_ROLE(), deployer);
        policyRegistry.grantRole(policyRegistry.GRAPH_CURATOR_ROLE(), governance);
        policyRegistry.revokeRole(policyRegistry.GRAPH_CURATOR_ROLE(), deployer);

        itkV2.grantRole(itkV2.DEFAULT_ADMIN_ROLE(), governance);
        itkV2.revokeRole(itkV2.DEFAULT_ADMIN_ROLE(), deployer);
        trustConfig.grantRole(trustConfig.DEFAULT_ADMIN_ROLE(), governance);
        trustConfig.revokeRole(trustConfig.DEFAULT_ADMIN_ROLE(), deployer);
        stakeVault.grantRole(stakeVault.DEFAULT_ADMIN_ROLE(), governance);
        stakeVault.revokeRole(stakeVault.DEFAULT_ADMIN_ROLE(), deployer);
        policyRegistry.grantRole(policyRegistry.DEFAULT_ADMIN_ROLE(), governance);
        policyRegistry.revokeRole(policyRegistry.DEFAULT_ADMIN_ROLE(), deployer);
        rewardRegistry.grantRole(rewardRegistry.DEFAULT_ADMIN_ROLE(), governance);
        rewardRegistry.revokeRole(rewardRegistry.DEFAULT_ADMIN_ROLE(), deployer);
        aisRegistry.grantRole(aisRegistry.DEFAULT_ADMIN_ROLE(), governance);
        aisRegistry.revokeRole(aisRegistry.DEFAULT_ADMIN_ROLE(), deployer);
    }

    /// @dev Only AgentPrimitivesFactory should ever hold REGISTRAR_ROLE on either
    /// registry — see XibalbaAgentRegistry.sol / DomainRegistry.sol NatSpec for why
    /// that invariant matters (it's what guarantees "an agent exists" implies "it is
    /// fully, atomically indexed").
    function _wireRoles() internal {
        registry.grantRole(registry.REGISTRAR_ROLE(), address(factory));
        domainRegistry.grantRole(domainRegistry.REGISTRAR_ROLE(), address(factory));

        if (block.chainid != 31337) {
            // Mainnet Readiness P0 #1: transfer ITK minting to governance to separate it from
            // oracle/scoring key. `governance` is the configured governance address (a multisig in
            // production); the IntegrityGovernance contract that used to hold these roles was cut in
            // docs/EXECUTION_PLAN.md A1, and the deployer still never keeps admin off local chains.
            itk.grantRole(itk.MINTER_ROLE(), governance);
            itk.revokeRole(itk.MINTER_ROLE(), deployer);

            // Transfer all singleton admin roles to governance
            registry.grantRole(registry.DEFAULT_ADMIN_ROLE(), governance);
            registry.revokeRole(registry.DEFAULT_ADMIN_ROLE(), deployer);
            domainRegistry.grantRole(domainRegistry.DEFAULT_ADMIN_ROLE(), governance);
            domainRegistry.revokeRole(domainRegistry.DEFAULT_ADMIN_ROLE(), deployer);
            entityRegistry.grantRole(entityRegistry.DEFAULT_ADMIN_ROLE(), governance);
            entityRegistry.revokeRole(entityRegistry.DEFAULT_ADMIN_ROLE(), deployer);
            itk.grantRole(itk.DEFAULT_ADMIN_ROLE(), governance);
            itk.revokeRole(itk.DEFAULT_ADMIN_ROLE(), deployer);
            guardrailRegistry.grantRole(guardrailRegistry.DEFAULT_ADMIN_ROLE(), governance);
            guardrailRegistry.revokeRole(guardrailRegistry.DEFAULT_ADMIN_ROLE(), deployer);
            defaultAnchorPolicy.grantRole(defaultAnchorPolicy.DEFAULT_ADMIN_ROLE(), governance);
            defaultAnchorPolicy.revokeRole(defaultAnchorPolicy.DEFAULT_ADMIN_ROLE(), deployer);
            defaultExecutionPolicy.grantRole(defaultExecutionPolicy.DEFAULT_ADMIN_ROLE(), governance);
            defaultExecutionPolicy.revokeRole(defaultExecutionPolicy.DEFAULT_ADMIN_ROLE(), deployer);
        }
    }

    /// @dev Bootstraps two Open domains at genesis so the first agents (including the
    /// integrity-demo healthcare showcase) can register immediately without a separate
    /// domain-registration transaction. Both Open, not Permissioned — domain-level
    /// vetting is a governance decision for later, not a blocker for standing up the
    /// protocol on testnet.
    function _bootstrapDomains() internal {
        generalDomainId = domainRegistry.registerDomain("general.integrity", DomainRegistry.JoinMode.Open);
        healthcareDomainId = domainRegistry.registerDomain("healthcare.integrity", DomainRegistry.JoinMode.Open);
    }

    function _logSummary() internal view {
        console2.log("=== Integrity Protocol genesis deploy ===");
        console2.log("deployer:              ", deployer);
        console2.log("IntegrityToken:        ", address(itk));
        console2.log("ZkVerifier (reject-all):", address(verifier));
        console2.log("governance (admin):    ", governance);
        console2.log("XibalbaAgentRegistry:  ", address(registry));
        console2.log("AgentAuthorityResolver:", address(authorityResolver));
        console2.log("AllowlistAnchorPolicy: ", address(defaultAnchorPolicy));
        console2.log("ConstraintExecPolicy:  ", address(defaultExecutionPolicy));
        console2.log("IntegrityIdentityReadV1:", address(identityRead));
        console2.log("XibalbaNameService:    ", address(xns));
        console2.log("DomainRegistry:        ", address(domainRegistry));
        console2.log("CoveredEntityRegistry: ", address(entityRegistry));
        console2.log("SmartBAAFactory:       ", address(baaFactory));
        console2.log("HIPAAGuardrailRegistry:", address(guardrailRegistry));
        console2.log("EHRGate:               ", address(ehrGate));
        console2.log("ReputationRegistryImpl:", address(reputationRegistryImpl));
        console2.log("SlasherImpl:           ", address(slasherImpl));
        console2.log("VerifierRegistryImpl:  ", address(verifierRegistryImpl));
        console2.log("ComplianceGateImpl:    ", address(complianceGateImpl));
        console2.log("AgentProfileImpl:      ", address(agentProfileImpl));
        console2.log("AgentPrimitivesFactory:", address(factory));
        console2.log("--- v2 trust layer ---");
        console2.log("ITK (v2 stake asset):  ", address(itkV2));
        console2.log("TrustConfig:           ", address(trustConfig));
        console2.log("StakeVault:            ", address(stakeVault));
        console2.log("PolicyRegistry:        ", address(policyRegistry));
        console2.log("OpenPolicyModule:      ", address(openPolicyModule));
        console2.log("AISRegistry:           ", address(aisRegistry));
        console2.log("RewardRegistry:        ", address(rewardRegistry));
        console2.log("DiscountRewardModule:  ", address(discountRewardModule));
        console2.log("ActionAnchor:          ", address(actionAnchor));
    }

    /// @dev Writes the new nested shape (singletons / cloneTemplates / protocolAddresses)
    /// documented in docs/INTERFACE_CONTRACT.md §6 — deliberately NOT the old flat
    /// `{"contracts": {...}}` shape, and deliberately excludes any per-agent primitive
    /// address (those don't belong in a static genesis file — see §6 for why).
    function _writeDeploymentsFile() internal {
        string memory singletons = "singletons";
        vm.serializeAddress(singletons, "IntegrityToken", address(itk));
        vm.serializeAddress(singletons, "ZkVerifier", address(verifier));
        vm.serializeAddress(singletons, "XibalbaAgentRegistry", address(registry));
        vm.serializeAddress(singletons, "AgentAuthorityResolver", address(authorityResolver));
        vm.serializeAddress(singletons, "AllowlistAnchorPolicy", address(defaultAnchorPolicy));
        vm.serializeAddress(singletons, "ConstraintExecutionPolicy", address(defaultExecutionPolicy));
        vm.serializeAddress(singletons, "IntegrityIdentityReadV1", address(identityRead));
        vm.serializeAddress(singletons, "XibalbaNameService", address(xns));
        vm.serializeAddress(singletons, "DomainRegistry", address(domainRegistry));
        vm.serializeAddress(singletons, "AgentPrimitivesFactory", address(factory));
        vm.serializeAddress(singletons, "CoveredEntityRegistry", address(entityRegistry));
        vm.serializeAddress(singletons, "SmartBAAFactory", address(baaFactory));
        vm.serializeAddress(singletons, "HIPAAGuardrailRegistry", address(guardrailRegistry));
        vm.serializeAddress(singletons, "ITK", address(itkV2));
        vm.serializeAddress(singletons, "TrustConfig", address(trustConfig));
        vm.serializeAddress(singletons, "StakeVault", address(stakeVault));
        vm.serializeAddress(singletons, "PolicyRegistry", address(policyRegistry));
        vm.serializeAddress(singletons, "OpenPolicyModule", address(openPolicyModule));
        vm.serializeAddress(singletons, "AISRegistry", address(aisRegistry));
        vm.serializeAddress(singletons, "RewardRegistry", address(rewardRegistry));
        vm.serializeAddress(singletons, "DiscountRewardModule", address(discountRewardModule));
        vm.serializeAddress(singletons, "ActionAnchor", address(actionAnchor));
        string memory singletonsJson = vm.serializeAddress(singletons, "EHRGate", address(ehrGate));

        string memory cloneTemplates = "cloneTemplates";
        vm.serializeAddress(cloneTemplates, "ReputationRegistry", address(reputationRegistryImpl));
        vm.serializeAddress(cloneTemplates, "Slasher", address(slasherImpl));
        vm.serializeAddress(cloneTemplates, "VerifierRegistry", address(verifierRegistryImpl));
        vm.serializeAddress(cloneTemplates, "ComplianceGate", address(complianceGateImpl));
        string memory cloneTemplatesJson = vm.serializeAddress(cloneTemplates, "AgentProfile", address(agentProfileImpl));

        string memory protocolAddresses = "protocolAddresses";
        vm.serializeAddress(protocolAddresses, "oracleSigner", oracleSigner);
        vm.serializeAddress(protocolAddresses, "disputer", disputer);
        vm.serializeAddress(protocolAddresses, "governance", governance);
        vm.serializeAddress(protocolAddresses, "arbitrator", arbitrator);
        string memory protocolAddressesJson = vm.serializeAddress(protocolAddresses, "funderWallet", deployer);

        string memory domains = "domains";
        vm.serializeBytes32(domains, "general.integrity", generalDomainId);
        string memory domainsJson = vm.serializeBytes32(domains, "healthcare.integrity", healthcareDomainId);

        string memory root = "root";
        vm.serializeUint(root, "chainId", block.chainid);
        vm.serializeString(root, "network", block.chainid == 84532 ? "base-sepolia" : "local");
        vm.serializeString(root, "singletons", singletonsJson);
        vm.serializeString(root, "cloneTemplates", cloneTemplatesJson);
        vm.serializeString(root, "protocolAddresses", protocolAddressesJson);
        string memory finalJson = vm.serializeString(root, "domains", domainsJson);

        string memory network = block.chainid == 84532 ? "baseSepolia" : "local";
        string memory path = string.concat("../deployments.", network, ".json");
        vm.writeJson(finalJson, path);
        console2.log("Wrote deployment record to", path);
    }
}
