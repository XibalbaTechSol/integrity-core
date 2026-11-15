// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {IPolicyModule} from "../../src/trust/IPolicyModule.sol";
import {DiscountRewardModule} from "../../src/trust/DiscountRewardModule.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {GateRegistryFixture} from "./GateRegistryFixture.sol";

/// @dev Test-only fixture; deliberately not in src/.
contract GateAllowModule is IPolicyModule {
    uint16 public immutable weight;

    constructor(uint16 weight_) {
        weight = weight_;
    }

    function checkCompliance(address, bytes32, address, bytes calldata) external view returns (bool, uint16) {
        return (true, weight);
    }
}

contract GateTarget {
    uint256 public pings;

    function ping() external payable {
        pings++;
    }

    function other() external payable {}
}

/// @notice Gate behavior under the PROTOCOL-PINNED trust model: the stake vault / policy registry /
/// reward module / domain are resolved at call time from a governance-owned `TrustConfig` and the
/// registry record, not from controller-set storage. Wiring = governance pointing the registry at
/// the `TrustConfig`; there are no per-agent trust setters any more.
contract ExecuteGatingTest is GateRegistryFixture {
    SovereignAgent agent;
    ITK itk;
    StakeVault vault;
    PolicyRegistry policy;
    DiscountRewardModule discount;
    TrustConfig trustConfig;
    GateTarget tgt;
    GateAllowModule module;

    address admin = makeAddr("admin");
    address governance = makeAddr("governance");
    address controller;
    uint256 controllerPk;
    address stranger = makeAddr("stranger");

    bytes32 constant GRAPH_DOMAIN = keccak256("graph-domain");
    bytes32 constant PLAIN_DOMAIN = keccak256("plain-domain");
    bytes32 constant FROM = bytes32(uint256(1));
    bytes32 constant REL = bytes32(uint256(2));
    bytes32 constant TO = bytes32(uint256(3));
    bytes32 constant OTHER_TO = bytes32(uint256(4));
    uint16 constant RISK = 1000; // 10%
    uint256 constant STAKE = 1000 ether;
    string constant DID = "did:integrity:gate";

    bytes32 leafA;
    bytes32 leafB;

    function setUp() public {
        // v3 AgentRegistry + governance-owned TrustConfig; the agent is built for the registry.
        (controller, controllerPk) = makeAddrAndKey("controller");
        _deployRegistry(admin);
        _ensureDomain("graph-domain");
        _ensureDomain("plain-domain");
        agent = _newAgent(DID, controller);
        tgt = new GateTarget();
        module = new GateAllowModule(2000); // 20%

        vm.startPrank(admin);
        itk = new ITK(admin, 0);
        vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), admin);
        policy = new PolicyRegistry(admin);
        policy.setModule(PLAIN_DOMAIN, address(module));
        discount = new DiscountRewardModule(governance, 50);
        trustConfig = new TrustConfig(governance);
        itk.mint(address(agent), 10_000 ether);
        vm.stopPrank();

        // Governance pins the three trust singletons (but does NOT yet point the registry at the
        // config — that is the "wire" switch in _stakeAndWire).
        vm.startPrank(governance);
        trustConfig.setStakeVault(address(vault));
        trustConfig.setPolicyRegistry(address(policy));
        trustConfig.setRewardDiscountModule(address(discount));
        vm.stopPrank();

        // Edge leaves bind the SPECIFIC target contract now.
        leafA = policy.leafOf(FROM, REL, TO, address(tgt), GateTarget.ping.selector, RISK);
        leafB = policy.leafOf(FROM, REL, OTHER_TO, address(tgt), GateTarget.ping.selector, RISK);
        bytes32 root =
            leafA < leafB ? keccak256(abi.encodePacked(leafA, leafB)) : keccak256(abi.encodePacked(leafB, leafA));
        vm.prank(admin);
        policy.setGraphRoot(GRAPH_DOMAIN, root);

        vm.deal(address(agent), 100 ether);
    }

    // ---- helpers

    /// @dev Stakes via the (still inert: unbound) plain execute, WIRES the trust layer by pointing
    /// the registry at the governance-owned TrustConfig, then binds the agent as the actor of a
    /// record in `domain`. v3 order: binding requires the domain to have a live policy, so it can
    /// only happen once the TrustConfig is wired.
    function _stakeAndWire(bytes32 domain) internal {
        vm.startPrank(controller);
        agent.execute(address(itk), 0, abi.encodeCall(itk.approve, (address(vault), type(uint256).max)));
        agent.execute(address(vault), 0, abi.encodeCall(vault.stake, (STAKE)));
        vm.stopPrank();

        vm.prank(admin);
        agentRegistry.setTrustConfig(address(trustConfig));
        _bind(agent, controllerPk, domain, controller);
    }

    function _freeze() internal {
        vm.startPrank(admin);
        vault.setFreezeThreshold(500);
        vault.onCheckpoint(address(agent), 1); // below threshold -> latch
        vm.stopPrank();
    }

    function _proof() internal view returns (bytes32[] memory p) {
        p = new bytes32[](1);
        p[0] = leafB;
    }

    function _plain(uint256 value) internal {
        vm.prank(controller);
        agent.execute(address(tgt), value, abi.encodeCall(GateTarget.ping, ()));
    }

    function _edge(uint256 value, bytes memory data, bytes32[] memory proof) internal {
        vm.prank(controller);
        agent.execute(address(tgt), value, data, FROM, REL, TO, RISK, proof);
    }

    // ---- backward compat (R1/R2): unregistered / unwired behaves as before

    function test_unregistered_plainExecuteBehavesAsBefore() public {
        // Agent is NOT registered -> gate fully inert, no staking, no reverts.
        _plain(1 ether);
        assertEq(tgt.pings(), 1);
        assertEq(agent.executionNonce(), 1);
        assertEq(address(tgt).balance, 1 ether);
    }

    function test_unwired_updateAISStillWorks() public {
        SovereignAgent a = new SovereignAgent("d", controller, stranger, address(0));
        vm.prank(stranger);
        a.updateAIS(42);
        assertEq(a.ais(), 42);
    }

    function test_registeredButNoTrustConfig_gateInert() public {
        // Bound, then governance clears the registry's TrustConfig -> inert. (v3 cannot bind
        // without a wired TrustConfig: the domain must have a live policy at bind time.)
        vm.prank(admin);
        agentRegistry.setTrustConfig(address(trustConfig));
        _bind(agent, controllerPk, PLAIN_DOMAIN, controller);
        vm.prank(admin);
        agentRegistry.setTrustConfig(address(0));
        _plain(1 ether);
        assertEq(tgt.pings(), 1);
        assertEq(vault.stakeOf(address(agent)).locked, 0);
    }

    // ---- the removed controller setters no longer exist

    function test_trustSettersAreGone() public {
        (bool okVault,) = address(agent).call(abi.encodeWithSignature("setStakeVault(address)", address(vault)));
        (bool okPol,) = address(agent).call(abi.encodeWithSignature("setPolicyRegistry(address)", address(policy)));
        (bool okMod,) =
            address(agent).call(abi.encodeWithSignature("setRewardDiscountModule(address)", address(discount)));
        (bool okDom,) = address(agent).call(abi.encodeWithSignature("setDomainId(bytes32)", GRAPH_DOMAIN));
        assertFalse(okVault, "setStakeVault must not exist");
        assertFalse(okPol, "setPolicyRegistry must not exist");
        assertFalse(okMod, "setRewardDiscountModule must not exist");
        assertFalse(okDom, "setDomainId must not exist");
    }

    // ---- freeze

    function test_frozen_revertsPlain() public {
        _stakeAndWire(PLAIN_DOMAIN);
        _freeze();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agent.execute(address(tgt), 1 ether, abi.encodeCall(GateTarget.ping, ()));
    }

    function test_frozen_revertsPlainZeroValue() public {
        _stakeAndWire(PLAIN_DOMAIN);
        _freeze();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agent.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
    }

    function test_frozen_revertsEdgeOverload() public {
        _stakeAndWire(GRAPH_DOMAIN);
        _freeze();
        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        bytes32[] memory p = _proof();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agent.execute(address(tgt), 0, d, FROM, REL, TO, RISK, p);
    }

    // ---- edge overload

    function test_edge_invalidProofReverts() public {
        _stakeAndWire(GRAPH_DOMAIN);
        bytes32[] memory bad = new bytes32[](1);
        bad[0] = bytes32(uint256(0xdead));
        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeNotProven.selector);
        agent.execute(address(tgt), 0, d, FROM, REL, TO, RISK, bad);
    }

    function test_edge_selectorMismatchReverts() public {
        _stakeAndWire(GRAPH_DOMAIN);
        bytes memory d = abi.encodeCall(GateTarget.other, ()); // committed selector is ping
        bytes32[] memory p = _proof();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeNotProven.selector);
        agent.execute(address(tgt), 0, d, FROM, REL, TO, RISK, p);
    }

    function test_edge_wrongRiskWeightReverts() public {
        _stakeAndWire(GRAPH_DOMAIN);
        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        bytes32[] memory p = _proof();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeNotProven.selector);
        agent.execute(address(tgt), 0, d, FROM, REL, TO, RISK - 1, p);
    }

    function test_edge_succeedsAndLocks() public {
        _stakeAndWire(GRAPH_DOMAIN);
        _edge(5 ether, abi.encodeCall(GateTarget.ping, ()), _proof());
        // floor 0 + 5 ether * 1000 / 10000 = 0.5 ether
        assertEq(vault.stakeOf(address(agent)).locked, 0.5 ether);
        assertEq(tgt.pings(), 1);
    }

    // ---- anti-bypass

    function test_plain_revertsEdgeClaimRequiredWhenGraphRootSet() public {
        _stakeAndWire(GRAPH_DOMAIN);
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeClaimRequired.selector);
        agent.execute(address(tgt), 0, abi.encodeCall(GateTarget.ping, ()));
    }

    // ---- stake / lock

    function test_plain_succeedsAndLocksWhenCompliant() public {
        _stakeAndWire(PLAIN_DOMAIN);
        _plain(10 ether);
        // module weight 20% -> 2 ether
        assertEq(vault.stakeOf(address(agent)).locked, 2 ether);
        assertEq(tgt.pings(), 1);
        assertEq(agent.executionNonce(), 3); // approve, stake, ping
    }

    function test_plain_revertsWhenStakeInsufficient() public {
        _stakeAndWire(PLAIN_DOMAIN);
        vm.deal(address(agent), 6000 ether);
        // required = 20% of 6000 ether = 1200 ether > 1000 ether staked
        vm.prank(controller);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        agent.execute(address(tgt), 6000 ether, abi.encodeCall(GateTarget.ping, ()));
    }

    function test_lock_includesDomainFloor() public {
        _stakeAndWire(PLAIN_DOMAIN);
        vm.prank(admin);
        policy.setDomainFloor(PLAIN_DOMAIN, 1 ether);
        _plain(10 ether);
        // absolute floor 1 ether + 20% of 10 ether = 3 ether
        assertEq(vault.stakeOf(address(agent)).locked, 3 ether);
    }

    function test_edge_failsClosedWhenPolicyPinCleared() public {
        _stakeAndWire(GRAPH_DOMAIN);
        // Governance clears the policy-registry pin -> edge claim cannot be proven.
        vm.prank(governance);
        trustConfig.setPolicyRegistry(address(0));
        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        bytes32[] memory p = _proof();
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.EdgeNotProven.selector);
        agent.execute(address(tgt), 0, d, FROM, REL, TO, RISK, p);
    }

    function test_lock_discountHalvesAt5000Bps() public {
        _stakeAndWire(PLAIN_DOMAIN);
        // Full score swing 0 -> 10000 bps = 100 points * 50 = 5000 bps = cap.
        vm.prank(governance);
        discount.onPositiveCheckpoint(address(agent), 0, 10000, bytes32(0));
        assertEq(discount.trustDiscountBps(address(agent)), 5000);

        _plain(10 ether);
        // undiscounted 2 ether -> halved to 1 ether
        assertEq(vault.stakeOf(address(agent)).locked, 1 ether);
    }
}
