// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {IntegrityToken} from "../src/oracle/IntegrityToken.sol";
import {IntegrityGovernance} from "../src/oracle/IntegrityGovernance.sol";
import {UltraPlonkVerifier} from "../src/oracle/UltraPlonkVerifier.sol";
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
import {IntegrityMarket} from "../src/markets/IntegrityMarket.sol";
import {MarketFactory} from "../src/markets/MarketFactory.sol";
import {A2ACapitalPool} from "../src/markets/A2ACapitalPool.sol";

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

    // IntegrityGovernance genesis parameters (testnet defaults). Voting window / timelock are
    // short enough to exercise the full lifecycle on a testnet cadence; threshold + quorum are
    // denominated in whole ITK. `governance` (the guardian) defaults to the deployer, same
    // single-operator posture as every other protocol role here.
    uint256 constant GOV_VOTING_PERIOD = 3 days;
    uint256 constant GOV_TIMELOCK_DELAY = 2 days;
    uint256 constant GOV_PROPOSAL_THRESHOLD = 1_000 ether;
    uint256 constant GOV_QUORUM_VOTES = 10_000 ether;

    // Deployed/derived addresses, held as contract-level state purely so
    // `_writeDeploymentsFile` can read them after `run()`'s local variables are gone.
    address deployer;
    address oracleSigner;
    address disputer;
    address governance;
    address arbitrator;
    address resolverSigner;

    IntegrityToken itk;
    IntegrityGovernance gov;
    UltraPlonkVerifier verifier;
    XibalbaAgentRegistry registry;
    AgentAuthorityResolver authorityResolver;
    IntegrityIdentityReadV1 identityRead;
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

    IntegrityMarket marketImpl;
    MarketFactory marketFactory;
    A2ACapitalPool capitalPool;

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
        // Demo resolver for IntegrityMarket -- see IntegrityMarket.sol's contract-level
        // NatSpec on the RESOLVER_ROLE trust boundary. Defaults to the deployer for a
        // single-operator testnet deployment, same as every other protocol-held role
        // above; integrity-demo's scenario engine is the intended real holder once it
        // deploys its own markets via MarketFactory.
        resolverSigner = vm.envOr("RESOLVER_ADDRESS", deployer);

        vm.startBroadcast(deployerKey);

        _deploySingletons();
        _deployCloneImplementations();
        _deployFactory();
        _deployMarkets();
        _wireRoles();
        _bootstrapDomains();

        vm.stopBroadcast();

        _logSummary();
        _writeDeploymentsFile();
    }

    function _deploySingletons() internal {
        // Initial mint is intentionally 0 — the deployer mints $ITK to the funder
        // wallet (or a faucet contract, in a later phase) as a separate, auditable
        // step rather than baking an arbitrary genesis balance into the deploy tx.
        itk = new IntegrityToken(deployer, 0);
        // Governance over protocol parameters; guardian = `governance` role (deployer on
        // testnet). Locks ITK to propose/vote, so it depends only on `itk` above.
        gov = new IntegrityGovernance(
            governance, itk, GOV_VOTING_PERIOD, GOV_TIMELOCK_DELAY, GOV_PROPOSAL_THRESHOLD, GOV_QUORUM_VOTES
        );
        verifier = new UltraPlonkVerifier();
        registry = new XibalbaAgentRegistry(deployer);
        authorityResolver = new AgentAuthorityResolver(address(registry));
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
            address(registry), address(baaFactory), address(authorityResolver), EHR_GATE_MIN_AIS_THRESHOLD, deployer
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

    /// @dev IntegrityMarket clones are deployed per-market by agents themselves via
    /// MarketFactory (see MarketFactory.sol's NatSpec on why market *creation* is
    /// deliberately ungated) -- this script only stands up the shared, non-initializable
    /// implementation and the factory that clones it, exactly like
    /// `_deployCloneImplementations`/`_deployFactory` do for the 5 identity primitives.
    /// A2ACapitalPool is a directly-deployed singleton (not agent-clonable — see its own
    /// NatSpec on why a shared allocator<->agent venue doesn't fit the per-creator
    /// clone pattern).
    function _deployMarkets() internal {
        marketImpl = new IntegrityMarket(address(itk), address(registry));
        marketFactory = new MarketFactory(address(registry), address(marketImpl));
        capitalPool = new A2ACapitalPool(address(itk), address(registry), deployer);
    }

    /// @dev Only AgentPrimitivesFactory should ever hold REGISTRAR_ROLE on either
    /// registry — see XibalbaAgentRegistry.sol / DomainRegistry.sol NatSpec for why
    /// that invariant matters (it's what guarantees "an agent exists" implies "it is
    /// fully, atomically indexed").
    function _wireRoles() internal {
        registry.grantRole(registry.REGISTRAR_ROLE(), address(factory));
        domainRegistry.grantRole(domainRegistry.REGISTRAR_ROLE(), address(factory));
        // The oracle signer is the one expected to actually call flagBreach (it's the
        // party watching telemetry/Slasher disputes off-chain), not just the deployer
        // admin the constructor already granted this to.
        capitalPool.grantRole(capitalPool.BREACH_REPORTER_ROLE(), oracleSigner);
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
        console2.log("IntegrityGovernance:   ", address(gov));
        console2.log("UltraPlonkVerifier:    ", address(verifier));
        console2.log("XibalbaAgentRegistry:  ", address(registry));
        console2.log("AgentAuthorityResolver:", address(authorityResolver));
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
        console2.log("IntegrityMarketImpl:   ", address(marketImpl));
        console2.log("MarketFactory:         ", address(marketFactory));
        console2.log("A2ACapitalPool:        ", address(capitalPool));
    }

    /// @dev Writes the new nested shape (singletons / cloneTemplates / protocolAddresses)
    /// documented in docs/INTERFACE_CONTRACT.md §6 — deliberately NOT the old flat
    /// `{"contracts": {...}}` shape, and deliberately excludes any per-agent primitive
    /// address (those don't belong in a static genesis file — see §6 for why).
    function _writeDeploymentsFile() internal {
        string memory singletons = "singletons";
        vm.serializeAddress(singletons, "IntegrityToken", address(itk));
        vm.serializeAddress(singletons, "IntegrityGovernance", address(gov));
        vm.serializeAddress(singletons, "UltraPlonkVerifier", address(verifier));
        vm.serializeAddress(singletons, "XibalbaAgentRegistry", address(registry));
        vm.serializeAddress(singletons, "AgentAuthorityResolver", address(authorityResolver));
        vm.serializeAddress(singletons, "IntegrityIdentityReadV1", address(identityRead));
        vm.serializeAddress(singletons, "XibalbaNameService", address(xns));
        vm.serializeAddress(singletons, "DomainRegistry", address(domainRegistry));
        vm.serializeAddress(singletons, "AgentPrimitivesFactory", address(factory));
        vm.serializeAddress(singletons, "CoveredEntityRegistry", address(entityRegistry));
        vm.serializeAddress(singletons, "SmartBAAFactory", address(baaFactory));
        vm.serializeAddress(singletons, "HIPAAGuardrailRegistry", address(guardrailRegistry));
        vm.serializeAddress(singletons, "EHRGate", address(ehrGate));
        vm.serializeAddress(singletons, "MarketFactory", address(marketFactory));
        string memory singletonsJson = vm.serializeAddress(singletons, "A2ACapitalPool", address(capitalPool));

        string memory cloneTemplates = "cloneTemplates";
        vm.serializeAddress(cloneTemplates, "ReputationRegistry", address(reputationRegistryImpl));
        vm.serializeAddress(cloneTemplates, "Slasher", address(slasherImpl));
        vm.serializeAddress(cloneTemplates, "VerifierRegistry", address(verifierRegistryImpl));
        vm.serializeAddress(cloneTemplates, "ComplianceGate", address(complianceGateImpl));
        vm.serializeAddress(cloneTemplates, "AgentProfile", address(agentProfileImpl));
        string memory cloneTemplatesJson = vm.serializeAddress(cloneTemplates, "IntegrityMarket", address(marketImpl));

        string memory protocolAddresses = "protocolAddresses";
        vm.serializeAddress(protocolAddresses, "oracleSigner", oracleSigner);
        vm.serializeAddress(protocolAddresses, "disputer", disputer);
        vm.serializeAddress(protocolAddresses, "governance", governance);
        vm.serializeAddress(protocolAddresses, "arbitrator", arbitrator);
        vm.serializeAddress(protocolAddresses, "resolverSigner", resolverSigner);
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
