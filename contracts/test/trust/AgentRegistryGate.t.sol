// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {DomainRegistry} from "../../src/framework/DomainRegistry.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {DiscountRewardModule} from "../../src/trust/DiscountRewardModule.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {GateTarget} from "./ExecuteGating.t.sol";
import {AllowModule, DenyModule} from "./ProtocolPinnedGate.t.sol";
import {GateRegistryFixture} from "./GateRegistryFixture.sol";

/// @notice The protocol-pinned gate under registration v3: `SovereignAgent._resolveGate` reads the
/// `AgentRegistry` the agent was built for (`factory`), and that registry's governance-owned
/// `TrustConfig`. Ports of ProtocolPinnedGate tests 2/3/4/7 (which exercised the held v2
/// `AgentPrimitivesFactory` path) plus the v3-specific pin and inertness cases.
///
/// The TrustConfig is wired BEFORE any agent binds, reproducing the live case: every pre-binding
/// `execute` runs while the trust layer is globally active, so the gate must be inert until bound.
contract AgentRegistryGateTest is GateRegistryFixture {
    IntegrityToken itk;
    StakeVault vault;
    PolicyRegistry policy;
    DiscountRewardModule discount;
    TrustConfig trustConfig;
    GateTarget tgt;

    address protocolAdmin = makeAddr("protocolAdmin");
    address governance = makeAddr("governance");

    bytes32 domainId;
    bytes32 graphDomainId;

    bytes32 constant FROM = bytes32(uint256(1));
    bytes32 constant REL = bytes32(uint256(2));
    bytes32 constant TO = bytes32(uint256(3));
    bytes32 constant OTHER_TO = bytes32(uint256(4));
    uint16 constant RISK = 1000;
    bytes32 leafB;

    function setUp() public {
        _deployRegistry(protocolAdmin);
        domainId = _ensureDomain("general.integrity");
        graphDomainId = _ensureDomain("graph.integrity");

        itk = new IntegrityToken(protocolAdmin, 1_000_000 ether);
        tgt = new GateTarget();
        vault = new StakeVault(address(itk), protocolAdmin);
        policy = new PolicyRegistry(protocolAdmin);
        discount = new DiscountRewardModule(governance, 50);
        trustConfig = new TrustConfig(governance);
        AllowModule allow = new AllowModule();

        vm.startPrank(protocolAdmin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), protocolAdmin);
        policy.setModule(domainId, address(allow));
        vm.stopPrank();

        bytes32 leafA = policy.leafOf(FROM, REL, TO, address(tgt), GateTarget.ping.selector, RISK);
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

        vm.prank(protocolAdmin);
        agentRegistry.setTrustConfig(address(trustConfig));
    }

    // --------------------------------------------------------------- helpers

    function _agent(string memory did, uint256 pk) internal returns (SovereignAgent sa, address wallet) {
        wallet = vm.addr(pk);
        sa = _newAgent(did, wallet);
    }

    function _stake(SovereignAgent sa, uint256 amount) internal {
        vm.prank(protocolAdmin);
        itk.transfer(address(sa), amount);
        vm.prank(address(sa));
        itk.approve(address(vault), type(uint256).max);
        vm.prank(address(sa));
        vault.stake(amount);
    }

    function _freeze(address a) internal {
        vm.startPrank(protocolAdmin);
        vault.setFreezeThreshold(500);
        vault.onCheckpoint(a, 1);
        vm.stopPrank();
    }

    function _proof() internal view returns (bytes32[] memory p) {
        p = new bytes32[](1);
        p[0] = leafB;
    }

    // --------------------------------------------- unbound agents are inert (onboarding never bricks)

    /// Built for the real registry, not yet bound, trust layer globally wired with no module for
    /// domain 0: a plain execute succeeds with the gate inert.
    /// MUTATION: in `_resolveGate`, remove the `isRegisteredAgent` guard AND drop the `resolveAgent`
    /// try/catch -> `resolveAgent` reverts for an unbound actor and execute bricks, test FAILS.
    function test_unboundAgentExecutesInert() public {
        (SovereignAgent sa, address wallet) = _agent("did:integrity:unbound", 0x21);
        assertFalse(agentRegistry.isRegisteredAgent(address(sa)));

        vm.prank(wallet);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
        assertEq(tgt.pings(), 1);
        assertEq(vault.stakeOf(address(sa)).locked, 0);
    }

    /// An existence-only record (no actor) does not gate anything, and a retired actor's gate is
    /// inert again: gating follows the live actor binding, not the record's existence.
    function test_retiredActorIsInert() public {
        (SovereignAgent sa, address wallet) = _agent("did:integrity:retire", 0x22);
        bytes32 fp = _bind(sa, 0x22, domainId, wallet);
        _stake(sa, 1000 ether);
        _freeze(address(sa));

        vm.prank(wallet);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));

        vm.prank(wallet);
        agentRegistry.retire(fp);
        vm.prank(wallet);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
        assertEq(tgt.pings(), 1);
    }

    // --------------------------------------------- bound + frozen cannot execute either overload

    /// MUTATION: make `_checkFrozen` a no-op -> both overloads stop reverting `Frozen`, test FAILS.
    function test_boundFrozenCannotExecuteEitherOverload() public {
        (SovereignAgent saPlain, address wPlain) = _agent("did:integrity:frz-plain", 0x3A);
        (SovereignAgent saGraph, address wGraph) = _agent("did:integrity:frz-graph", 0x3B);
        _bind(saPlain, 0x3A, domainId, wPlain);
        _bind(saGraph, 0x3B, graphDomainId, wGraph);
        _stake(saPlain, 1000 ether);
        _stake(saGraph, 1000 ether);
        _freeze(address(saPlain));
        _freeze(address(saGraph));

        vm.prank(wPlain);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        saPlain.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));

        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        bytes32[] memory p = _proof();
        vm.prank(wGraph);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        saGraph.execute(address(tgt), 0, d, FROM, REL, TO, RISK, p);

        (bool g1,) = address(saPlain).call(abi.encodeWithSignature("setStakeVault(address)", address(0)));
        (bool g2,) = address(saPlain).call(abi.encodeWithSignature("setDomainId(bytes32)", bytes32(0)));
        assertFalse(g1, "setStakeVault must not exist");
        assertFalse(g2, "setDomainId must not exist");
    }

    // --------------------------------------------- the pin reads the live governance source

    /// MUTATION: in `_resolveGate`, drop `policyRegistry_ = p;` -> the repointed DENY registry is
    /// never consulted, test FAILS.
    function test_pinIsLiveGovernanceConfig() public {
        (SovereignAgent sa, address wallet) = _agent("did:integrity:pin", 0x40);
        _bind(sa, 0x40, domainId, wallet);
        _stake(sa, 1000 ether);

        vm.prank(wallet);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
        assertEq(tgt.pings(), 1);

        PolicyRegistry denyPolicy = new PolicyRegistry(protocolAdmin);
        DenyModule deny = new DenyModule();
        vm.prank(protocolAdmin);
        denyPolicy.setModule(domainId, address(deny));
        vm.prank(governance);
        trustConfig.setPolicyRegistry(address(denyPolicy));

        vm.prank(wallet);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
    }

    /// The domain the gate evaluates comes from the registry record, and follows a guardian's
    /// `setDomain`: moving the agent into the graph domain makes a plain call require an edge claim.
    /// MUTATION: in `_resolveGate`, read `domainId_` from anything but `resolveAgent(this)` (e.g.
    /// leave it zero) -> the plain call is checked against domain 0 and does not revert
    /// `EdgeClaimRequired`, test FAILS.
    function test_domainComesFromTheRegistryRecord() public {
        (SovereignAgent sa, address wallet) = _agent("did:integrity:dom", 0x41);
        bytes32 fp = _bind(sa, 0x41, domainId, wallet);
        _stake(sa, 1000 ether);

        vm.prank(wallet);
        agentRegistry.setDomain(fp, graphDomainId);

        vm.prank(wallet);
        vm.expectRevert(SovereignAgent.EdgeClaimRequired.selector);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
    }

    // --------------------------------------------- the binding is unspoofable

    /// An agent built for a DIFFERENT registry has a different runtime codehash (`factory` is an
    /// immutable), so the real registry refuses to bind it: the gate it would resolve is its own
    /// pick, and `isGatedAccount` tells counterparties it is not gated by this registry.
    function test_agentBuiltForAnotherRegistryCannotBeBound() public {
        AgentRegistry other = new AgentRegistry(protocolAdmin, address(domainRegistry));
        address wallet = vm.addr(0x50);
        SovereignAgent foreign = new SovereignAgent("did:integrity:foreign", wallet, address(0), address(other));
        assertTrue(address(foreign).codehash != agentRegistry.agentCodehash());
        assertFalse(agentRegistry.isGatedAccount(address(foreign)));

        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.NotGatedAccount.selector, address(foreign)));
        this.bindExternal(foreign, 0x50, domainId, wallet);
    }

    /// External shim so `expectRevert` targets the `register` call, not the fixture's signing views.
    function bindExternal(SovereignAgent a, uint256 pk, bytes32 dom, address g) external {
        _bind(a, pk, dom, g);
    }

    // --------------------------------------------- end-to-end onboarding through the gate

    /// Pre-binding executes stay inert with the trust layer live; binding succeeds; the bound agent
    /// is gated (a compliant staked call locks stake).
    /// MUTATION: in `_resolveGate`, change the `resolveAgent` catch to `catch {}` and drop the
    /// guard -> the pre-binding execute resolves domain 0, hits `NoModuleConfigured`, test FAILS.
    function test_endToEndOnboardingThroughGate() public {
        (SovereignAgent sa, address wallet) = _agent("did:integrity:e2e", 0x70);

        vm.prank(wallet);
        sa.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));

        _bind(sa, 0x70, domainId, wallet);
        AgentRegistry.AgentRecord memory rec = agentRegistry.resolveAgent(address(sa));
        assertEq(rec.actor, address(sa));
        assertEq(rec.domainId, domainId);

        _stake(sa, 1000 ether);
        vm.deal(address(sa), 10 ether);
        vm.prank(wallet);
        sa.execute(address(tgt), 10 ether, abi.encodeCall(GateTarget.ping, ()));
        assertEq(vault.stakeOf(address(sa)).locked, 1 ether); // allow weight 1000 bps of 10 ether
    }
}
