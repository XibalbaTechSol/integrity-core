// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {IPolicyModule} from "../../src/trust/IPolicyModule.sol";
import {DiscountRewardModule} from "../../src/trust/DiscountRewardModule.sol";

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

contract ExecuteGatingTest is Test {
    SovereignAgent agent;
    ITK itk;
    StakeVault vault;
    PolicyRegistry registry;
    DiscountRewardModule discount;
    GateTarget tgt;
    GateAllowModule module;

    address admin = makeAddr("admin");
    address controller = makeAddr("controller");
    address stranger = makeAddr("stranger");

    bytes32 constant GRAPH_DOMAIN = keccak256("graph-domain");
    bytes32 constant PLAIN_DOMAIN = keccak256("plain-domain");
    bytes32 constant FROM = bytes32(uint256(1));
    bytes32 constant REL = bytes32(uint256(2));
    bytes32 constant TO = bytes32(uint256(3));
    bytes32 constant OTHER_TO = bytes32(uint256(4));
    uint16 constant RISK = 1000; // 10%
    uint256 constant STAKE = 1000 ether;

    bytes32 leafA;
    bytes32 leafB;

    function setUp() public {
        agent = new SovereignAgent("did:integrity:gate", controller, address(0), address(0));
        tgt = new GateTarget();
        module = new GateAllowModule(2000); // 20%

        vm.startPrank(admin);
        itk = new ITK(admin, 0);
        vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), admin);
        registry = new PolicyRegistry(admin);
        registry.setModule(PLAIN_DOMAIN, address(module));
        discount = new DiscountRewardModule(admin);
        itk.mint(address(agent), 10_000 ether);
        vm.stopPrank();

        leafA = registry.leafOf(FROM, REL, TO, GateTarget.ping.selector, RISK);
        leafB = registry.leafOf(FROM, REL, OTHER_TO, GateTarget.ping.selector, RISK);
        bytes32 root =
            leafA < leafB ? keccak256(abi.encodePacked(leafA, leafB)) : keccak256(abi.encodePacked(leafB, leafA));
        vm.prank(admin);
        registry.setGraphRoot(GRAPH_DOMAIN, root);

        vm.deal(address(agent), 100 ether);
    }

    // ---- helpers

    /// @dev Stakes via the (still unwired) plain execute, then wires the trust modules.
    function _stakeAndWire(bytes32 domain) internal {
        vm.startPrank(controller);
        agent.execute(address(itk), 0, abi.encodeCall(itk.approve, (address(vault), type(uint256).max)));
        agent.execute(address(vault), 0, abi.encodeCall(vault.stake, (STAKE)));
        agent.setStakeVault(address(vault));
        agent.setPolicyRegistry(address(registry));
        agent.setDomainId(domain);
        vm.stopPrank();
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

    // ---- backward compat (R1/R2)

    function test_unwired_plainExecuteBehavesAsBefore() public {
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

    // ---- setters

    function test_setters_controllerOnly() public {
        vm.startPrank(stranger);
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.setStakeVault(address(vault));
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.setPolicyRegistry(address(registry));
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.setRewardDiscountModule(address(discount));
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.setDomainId(GRAPH_DOMAIN);
        vm.stopPrank();
    }

    function test_setters_zeroClearsGating() public {
        _stakeAndWire(PLAIN_DOMAIN);
        vm.startPrank(controller);
        agent.setStakeVault(address(0));
        agent.setPolicyRegistry(address(0));
        vm.stopPrank();
        _plain(1 ether);
        assertEq(vault.stakeOf(address(agent)).locked, 0);
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
        registry.setDomainFloor(PLAIN_DOMAIN, 7);
        _plain(0);
        assertEq(vault.stakeOf(address(agent)).locked, 7);
    }

    function test_lock_discountHalvesAt5000Bps() public {
        _stakeAndWire(PLAIN_DOMAIN);
        vm.prank(admin);
        discount.onPositiveCheckpoint(address(agent), 0, 100, bytes32(0)); // 100*50 = 5000 bps (cap)
        assertEq(discount.trustDiscountBps(address(agent)), 5000);
        vm.prank(controller);
        agent.setRewardDiscountModule(address(discount));

        _plain(10 ether);
        // undiscounted 2 ether -> halved to 1 ether
        assertEq(vault.stakeOf(address(agent)).locked, 1 ether);
    }
}
