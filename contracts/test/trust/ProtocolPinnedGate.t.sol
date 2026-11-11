// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {StateAnchor} from "../../src/oracle/StateAnchor.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";
import {Slasher} from "../../src/oracle/Slasher.sol";
import {VerifierRegistry} from "../../src/oracle/VerifierRegistry.sol";
import {ComplianceGate} from "../../src/health/ComplianceGate.sol";
import {AgentProfile} from "../../src/framework/AgentProfile.sol";
import {XibalbaAgentRegistry} from "../../src/framework/XibalbaAgentRegistry.sol";
import {DomainRegistry} from "../../src/framework/DomainRegistry.sol";
import {AgentPrimitivesFactory} from "../../src/framework/AgentPrimitivesFactory.sol";
import {CoveredEntityRegistry} from "../../src/health/CoveredEntityRegistry.sol";
import {SmartBAAFactory} from "../../src/health/SmartBAAFactory.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {DiscountRewardModule} from "../../src/trust/DiscountRewardModule.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {IPolicyModule} from "../../src/trust/IPolicyModule.sol";
import {GateTarget} from "./ExecuteGating.t.sol";

contract AllowModule is IPolicyModule {
    function checkCompliance(address, bytes32, address, bytes calldata) external pure returns (bool, uint16) {
        return (true, 1000);
    }
}

contract DenyModule is IPolicyModule {
    function checkCompliance(address, bytes32, address, bytes calldata) external pure returns (bool, uint16) {
        return (false, 0);
    }
}

/// @notice Mutation-checked regressions for the protocol-pinned trust gate (Critical fix) plus the
/// leaf target-binding and the frozen-unstake backstop. The full real registration stack is wired
/// here (mirroring AgentPrimitivesFactory.t.sol) so the gate is exercised exactly as production.
///
/// The governance-owned `TrustConfig` is wired into the registry in `setUp`, BEFORE any agent
/// onboards — this reproduces the live scenario where every new agent runs its pre-registration
/// `execute` calls while the trust layer is already globally active. The gate must stay inert for
/// an unregistered agent (R11) or onboarding bricks.
contract ProtocolPinnedGateTest is Test {
    // Protocol singletons.
    XibalbaAgentRegistry registry;
    DomainRegistry domainRegistry;
    IntegrityToken itk;
    CoveredEntityRegistry entityRegistry;
    SmartBAAFactory baaFactory;

    // Clone implementations.
    ReputationRegistry reputationRegistryImpl;
    Slasher slasherImpl;
    VerifierRegistry verifierRegistryImpl;
    ComplianceGate complianceGateImpl;
    AgentProfile agentProfileImpl;

    AgentPrimitivesFactory factory;

    // Trust layer.
    StakeVault vault;
    PolicyRegistry policy;
    DiscountRewardModule discount;
    TrustConfig trustConfig;
    AllowModule allowModule;

    address protocolAdmin = makeAddr("protocolAdmin");
    address oracleSigner = makeAddr("oracleSigner");
    address disputer = makeAddr("disputer");
    address governance = makeAddr("governance");
    address arbitrator = makeAddr("arbitrator");
    address initialZkVerifier = makeAddr("initialZkVerifier");

    bytes32 domainId;
    bytes32 graphDomainId;

    // Edge-claim fixtures.
    GateTarget tgt;
    bytes32 constant FROM = bytes32(uint256(1));
    bytes32 constant REL = bytes32(uint256(2));
    bytes32 constant TO = bytes32(uint256(3));
    bytes32 constant OTHER_TO = bytes32(uint256(4));
    uint16 constant RISK = 1000;
    bytes32 leafA;
    bytes32 leafB;

    function setUp() public {
        itk = new IntegrityToken(protocolAdmin, 1_000_000 ether);
        registry = new XibalbaAgentRegistry(protocolAdmin);
        domainRegistry = new DomainRegistry(protocolAdmin);
        entityRegistry = new CoveredEntityRegistry(protocolAdmin);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, protocolAdmin);

        reputationRegistryImpl = new ReputationRegistry();
        slasherImpl = new Slasher(address(itk));
        verifierRegistryImpl = new VerifierRegistry();
        complianceGateImpl = new ComplianceGate(address(entityRegistry), address(baaFactory));
        agentProfileImpl = new AgentProfile(address(domainRegistry));

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
            initialZkVerifier
        );

        vm.startPrank(protocolAdmin);
        registry.grantRole(registry.REGISTRAR_ROLE(), address(factory));
        domainRegistry.grantRole(domainRegistry.REGISTRAR_ROLE(), address(factory));
        domainId = domainRegistry.registerDomain("general.integrity", DomainRegistry.JoinMode.Open);
        graphDomainId = domainRegistry.registerDomain("graph.integrity", DomainRegistry.JoinMode.Open);
        vm.stopPrank();

        // Trust layer, pinned through a governance-owned TrustConfig.
        tgt = new GateTarget();
        allowModule = new AllowModule();
        vault = new StakeVault(address(itk), protocolAdmin);
        policy = new PolicyRegistry(protocolAdmin);
        discount = new DiscountRewardModule(governance, 50);
        trustConfig = new TrustConfig(governance);

        vm.startPrank(protocolAdmin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), protocolAdmin);
        policy.setModule(domainId, address(allowModule));
        vm.stopPrank();

        // Graph domain: committed edge tree bound to the specific target `tgt`.
        leafA = policy.leafOf(FROM, REL, TO, address(tgt), GateTarget.ping.selector, RISK);
        leafB = policy.leafOf(FROM, REL, OTHER_TO, address(tgt), GateTarget.ping.selector, RISK);
        bytes32 root =
            leafA < leafB ? keccak256(abi.encodePacked(leafA, leafB)) : keccak256(abi.encodePacked(leafB, leafA));
        vm.prank(protocolAdmin);
        policy.setGraphRoot(graphDomainId, root);

        vm.startPrank(governance);
        trustConfig.setStakeVault(address(vault));
        trustConfig.setPolicyRegistry(address(policy));
        trustConfig.setRewardDiscountModule(address(discount));
        vm.stopPrank();

        // Wire the registry at the TrustConfig BEFORE any agent onboards.
        vm.prank(protocolAdmin);
        registry.setTrustConfig(address(trustConfig));
    }

    // --------------------------------------------------------------- helpers

    /// @dev Full self-sovereign onboarding through the real factory. The pre-registration execute
    /// calls (grant ANCHOR_ROLE, anchorRoot) run while the trust layer is globally active.
    function _onboard(string memory did, uint256 pk, bytes32 dom)
        internal
        returns (SovereignAgent sa, address wallet)
    {
        wallet = vm.addr(pk);
        vm.deal(wallet, 1 ether);

        vm.prank(wallet);
        sa = new SovereignAgent(did, wallet, oracleSigner, address(factory));
        vm.prank(wallet);
        StateAnchor anchor = new StateAnchor(address(sa));

        // Precompute before the prank: an external staticcall here would consume the prank.
        bytes32 anchorRole = anchor.ANCHOR_ROLE();
        vm.prank(wallet);
        sa.execute(address(anchor), 0, abi.encodeCall(AccessControl.grantRole, (anchorRole, oracleSigner)));
        vm.prank(wallet);
        sa.execute(address(anchor), 0, abi.encodeCall(StateAnchor.anchorRoot, (keccak256(bytes(did)))));

        vm.prank(wallet);
        factory.registerCore(address(sa), address(anchor), did, dom);
    }

    /// @dev Stakes `amount` directly as the agent contract (msg.sender == agent), bypassing the
    /// gated `execute` path — isolates the stake setup from the gate under test.
    function _stake(SovereignAgent sa, uint256 amount) internal {
        vm.prank(protocolAdmin);
        itk.transfer(address(sa), amount);
        vm.prank(address(sa));
        itk.approve(address(vault), type(uint256).max);
        vm.prank(address(sa));
        vault.stake(amount);
    }

    function _freeze(address agent) internal {
        vm.startPrank(protocolAdmin);
        vault.setFreezeThreshold(500);
        vault.onCheckpoint(agent, 1);
        vm.stopPrank();
    }

    function _proof() internal view returns (bytes32[] memory p) {
        p = new bytes32[](1);
        p[0] = leafB;
    }

    // ----------------------------------------------- 1. fake-factory registration reverts (R10)

    /// MUTATION: delete `if (sa.factory() != address(this)) revert FactoryMismatch();` in
    /// `registerCore` -> this reverts with MemoryNotInitialized instead, test FAILS.
    function test_1a_registerCore_fakeFactoryReverts() public {
        address wallet = makeAddr("evil1a");
        vm.prank(wallet);
        SovereignAgent sa = new SovereignAgent("did:integrity:fake-core", wallet, oracleSigner, address(0xFACE));
        vm.prank(wallet);
        StateAnchor anchor = new StateAnchor(address(sa));

        vm.prank(wallet);
        vm.expectRevert(AgentPrimitivesFactory.FactoryMismatch.selector);
        factory.registerCore(address(sa), address(anchor), "did:integrity:fake-core", domainId);
    }

    /// MUTATION: delete the FactoryMismatch require in `registerPrimitives` -> MemoryNotInitialized
    /// instead, test FAILS.
    function test_1b_registerPrimitives_fakeFactoryReverts() public {
        address wallet = makeAddr("evil1b");
        vm.prank(wallet);
        SovereignAgent sa = new SovereignAgent("did:integrity:fake-prim", wallet, oracleSigner, address(0xFACE));
        vm.prank(wallet);
        StateAnchor anchor = new StateAnchor(address(sa));

        vm.prank(wallet);
        vm.expectRevert(AgentPrimitivesFactory.FactoryMismatch.selector);
        factory.registerPrimitives(
            address(sa), address(anchor), "did:integrity:fake-prim", domainId, ComplianceGate.Vertical.None, ""
        );
    }

    // ----------------------------------------------- 2. unregistered agent still executes (R11 inert)

    /// A SovereignAgent bound to the REAL factory but NOT yet registered runs a plain execute with
    /// the gate fully inert, even though the TrustConfig is globally wired with a live policy
    /// registry and there is no module for domain 0.
    /// MUTATION: in `_resolveGate`, remove the `isRegisteredAgent` guard AND call `resolveAgent`
    /// directly (drop its try/catch) -> `resolveAgent` reverts `UnknownAgent` and execute bricks,
    /// test FAILS. (Removing only the guard leaves the catch; the test still passes.)
    function test_2_unregisteredAgentExecutesInert() public {
        address wallet = makeAddr("unreg2");
        vm.prank(wallet);
        SovereignAgent sa = new SovereignAgent("did:integrity:unreg", wallet, oracleSigner, address(factory));

        assertFalse(registry.isRegisteredAgent(address(sa)));

        vm.prank(wallet);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
        assertEq(tgt.pings(), 1);
        assertEq(sa.executionNonce(), 1);
        // Gate inert: no stake was locked.
        assertEq(vault.stakeOf(address(sa)).locked, 0);
    }

    // ----------------------------------------------- 3. registered + frozen cannot execute either overload

    /// MUTATION: make `_checkFrozen` a no-op (early `return`) -> both overloads stop reverting
    /// `Frozen`, test FAILS.
    function test_3_registeredFrozenCannotExecuteEitherOverload() public {
        (SovereignAgent saPlain, address wPlain) = _onboard("did:integrity:frz-plain", 0x3A, domainId);
        (SovereignAgent saGraph, address wGraph) = _onboard("did:integrity:frz-graph", 0x3B, graphDomainId);
        _stake(saPlain, 1000 ether);
        _stake(saGraph, 1000 ether);
        _freeze(address(saPlain));
        _freeze(address(saGraph));

        // plain overload
        vm.prank(wPlain);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        saPlain.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));

        // edge overload
        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        vm.prank(wGraph);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        saGraph.execute(address(tgt), 0, d, FROM, REL, TO, RISK, _proof());

        // The controller has NO setter to swap the vault/registry/domain and escape.
        (bool g1,) = address(saPlain).call(abi.encodeWithSignature("setStakeVault(address)", address(0)));
        (bool g2,) = address(saPlain).call(abi.encodeWithSignature("setDomainId(bytes32)", bytes32(0)));
        assertFalse(g1, "setStakeVault must not exist");
        assertFalse(g2, "setDomainId must not exist");
    }

    // ----------------------------------------------- 4. pin is unspoofable + reads live governance source

    /// The gate reads the governance TrustConfig at CALL time, and the controller cannot redirect
    /// it. Governance repoints the policy pin to a DENY registry mid-life and the agent's next call
    /// is denied — proving the source is the live governance config, not agent storage.
    /// MUTATION: in `_resolveGate`, drop the `policyRegistry_ = p;` assignment (leave it zero) ->
    /// the policy gate is skipped, the repointed DENY registry is never consulted, test FAILS.
    function test_4_pinIsUnspoofableAndLive() public {
        (SovereignAgent sa, address wallet) = _onboard("did:integrity:pin4", 0x40, domainId);
        _stake(sa, 1000 ether);

        // Baseline: the allow-module lets a compliant call through.
        vm.prank(wallet);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
        assertEq(tgt.pings(), 1);

        // No controller setter exists to redirect the gate.
        (bool gone,) = address(sa).call(abi.encodeWithSignature("setPolicyRegistry(address)", address(0)));
        assertFalse(gone, "setPolicyRegistry must not exist");

        // Governance repoints the policy registry to one whose module DENIES. The gate follows.
        PolicyRegistry denyPolicy = new PolicyRegistry(protocolAdmin);
        DenyModule denyModule = new DenyModule();
        vm.prank(protocolAdmin);
        denyPolicy.setModule(domainId, address(denyModule));
        vm.prank(governance);
        trustConfig.setPolicyRegistry(address(denyPolicy));

        vm.prank(wallet);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
    }

    // ----------------------------------------------- 5. unstake-while-frozen reverts (A5)

    /// MUTATION: delete `if (_stakes[msg.sender].frozen) revert StakeFrozen();` in
    /// `StakeVault.withdraw` -> the frozen agent withdraws its collateral, test FAILS.
    /// The withdrawal is queued BEFORE the freeze, so only the payout-time check can stop it.
    function test_5_unstakeWhileFrozenReverts() public {
        address staker = makeAddr("staker5");
        vm.prank(protocolAdmin);
        itk.transfer(staker, 1000 ether);
        vm.startPrank(staker);
        itk.approve(address(vault), type(uint256).max);
        vault.stake(1000 ether);
        vault.requestUnstake(1000 ether);
        vm.stopPrank();

        _freeze(staker);
        vm.warp(block.timestamp + vault.unbondingDelay());

        vm.prank(staker);
        vm.expectRevert(StakeVault.StakeFrozen.selector);
        vault.withdraw();

        vm.prank(staker);
        vm.expectRevert(StakeVault.StakeFrozen.selector);
        vault.requestUnstake(1);
    }

    // ----------------------------------------------- 6. leaf target-binding (Important-1)

    /// MUTATION: drop `target` from `PolicyRegistry.leafOf`'s `abi.encode` -> the wrong-target edge
    /// hashes to the committed leaf and `checkGraphEdge` returns true, test FAILS.
    function test_6_leafBindsTarget() public view {
        // Correct target: committed -> true.
        assertTrue(policy.checkGraphEdge(graphDomainId, FROM, REL, TO, address(tgt), GateTarget.ping.selector, RISK, _proof()));
        // Same triple/selector/risk, DIFFERENT target -> different leaf, not in the tree.
        assertFalse(policy.checkGraphEdge(graphDomainId, FROM, REL, TO, address(0xBEEF), GateTarget.ping.selector, RISK, _proof()));
    }

    // ----------------------------------------------- 7. end-to-end onboarding through the new gate (R11)

    /// The full registration sequence completes with the trust layer globally active: the
    /// pre-registration execute calls stay inert, registration succeeds, and the now-registered
    /// agent is gated.
    /// MUTATION: in `_resolveGate`, change the `resolveAgent` catch from `return (0,0,0,0)` to
    /// `catch {}` (swallow) -> an unregistered agent resolves the live pins with domainId 0, the
    /// pre-registration execute hits `checkCompliance` for domain 0 -> `NoModuleConfigured`,
    /// onboarding bricks, test FAILS.
    function test_7_endToEndOnboardingThroughGate() public {
        (SovereignAgent sa,) = _onboard("did:integrity:e2e7", 0x70, domainId);

        // Registration completed.
        XibalbaAgentRegistry.AgentRecord memory rec = registry.resolveAgent(address(sa));
        assertEq(rec.primitives.sovereignAgent, address(sa));
        assertEq(rec.domainId, domainId);

        // And the now-registered agent is gated: a compliant staked call locks stake.
        _stake(sa, 1000 ether);
        vm.deal(address(sa), 10 ether);
        address wallet = rec.controller;
        vm.prank(wallet);
        sa.execute(address(tgt), 10 ether, abi.encodeCall(GateTarget.ping, ()));
        // allow-module weight 1000 bps of 10 ether = 1 ether locked.
        assertEq(vault.stakeOf(address(sa)).locked, 1 ether);
    }
}
