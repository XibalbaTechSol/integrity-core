// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {StateAnchor} from "../src/oracle/StateAnchor.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";
import {
    AllowAnchorPolicy,
    DenyAnchorPolicy,
    RevertAnchorPolicy,
    AllowExecutionPolicy,
    DenyExecutionPolicy,
    RevertExecutionPolicy,
    Sink
} from "./mocks/PolicyMocks.sol";

/// @notice Locks the §5.3 fail-closed policy hooks. A denied or reverting policy
/// MUST leave anchoring and execution state unchanged.
contract PolicyHookInvariantsTest is Test {
    StateAnchor internal anchor;
    SovereignAgent internal agent;
    Sink internal sink;

    address internal admin = makeAddr("admin");
    address internal controller = makeAddr("controller");
    address internal oracle = makeAddr("oracle");
    address internal stranger = makeAddr("stranger");
    address internal factory = makeAddr("factory");

    bytes32 internal constant ROOT_A = keccak256("root-a");
    bytes32 internal constant ROOT_B = keccak256("root-b");

    function setUp() public {
        anchor = new StateAnchor(admin);
        agent = new SovereignAgent("did:integrity:test", controller, oracle, factory);
        sink = new Sink();
        vm.deal(address(agent), 1 ether);
    }

    function test_ZeroAnchorPolicy_AllowsTestnetAnchor() public {
        vm.prank(admin);
        uint256 epoch = anchor.anchorRoot(ROOT_A);
        assertEq(epoch, 1);
        assertEq(anchor.latestRoot(), ROOT_A);
        assertTrue(anchor.isAnchoredRoot(ROOT_A));
    }

    function test_AllowAnchorPolicy_WritesRoot() public {
        vm.prank(admin);
        anchor.setAnchorPolicy(new AllowAnchorPolicy());

        vm.prank(admin);
        uint256 epoch = anchor.anchorRoot(ROOT_A);
        assertEq(epoch, 1);
        assertEq(anchor.latestEpoch(), 1);
        assertEq(anchor.latestRoot(), ROOT_A);
    }

    function test_DenyAnchorPolicy_LeavesEpochAndRootUnchanged() public {
        vm.startPrank(admin);
        anchor.anchorRoot(ROOT_A);
        anchor.setAnchorPolicy(new DenyAnchorPolicy());
        vm.stopPrank();

        uint256 epochBefore = anchor.latestEpoch();
        bytes32 rootBefore = anchor.latestRoot();
        uint256 tsBefore = anchor.latestTimestamp();

        vm.prank(admin);
        vm.expectRevert(StateAnchor.AnchorPolicyDenied.selector);
        anchor.anchorRoot(ROOT_B);

        assertEq(anchor.latestEpoch(), epochBefore);
        assertEq(anchor.latestRoot(), rootBefore);
        assertEq(anchor.latestTimestamp(), tsBefore);
        assertFalse(anchor.isAnchoredRoot(ROOT_B));
    }

    function test_RevertAnchorPolicy_LeavesEpochAndRootUnchanged() public {
        vm.startPrank(admin);
        anchor.anchorRoot(ROOT_A);
        anchor.setAnchorPolicy(new RevertAnchorPolicy());
        vm.stopPrank();

        uint256 epochBefore = anchor.latestEpoch();
        bytes32 rootBefore = anchor.latestRoot();

        vm.prank(admin);
        vm.expectRevert(RevertAnchorPolicy.AnchorPolicyReverted.selector);
        anchor.anchorRoot(ROOT_B);

        assertEq(anchor.latestEpoch(), epochBefore);
        assertEq(anchor.latestRoot(), rootBefore);
        assertFalse(anchor.isAnchoredRoot(ROOT_B));
    }

    function test_SetAnchorPolicy_OnlyAdmin() public {
        vm.prank(stranger);
        vm.expectRevert();
        anchor.setAnchorPolicy(new AllowAnchorPolicy());
    }

    function test_ZeroExecutionPolicy_AllowsTestnetExecute() public {
        vm.prank(controller);
        agent.execute(address(sink), 0, abi.encodeCall(Sink.ping, ()));
        assertEq(sink.hits(), 1);
        assertEq(agent.executionNonce(), 1);
    }

    function test_AllowExecutionPolicy_ExecutesCall() public {
        vm.prank(controller);
        agent.setExecutionPolicy(new AllowExecutionPolicy());

        vm.prank(controller);
        agent.execute(address(sink), 0.1 ether, abi.encodeCall(Sink.ping, ()));
        assertEq(sink.hits(), 1);
        assertEq(address(sink).balance, 0.1 ether);
        assertEq(agent.executionNonce(), 1);
    }

    function test_DenyExecutionPolicy_LeavesNonceAndCalleeUnchanged() public {
        vm.prank(controller);
        agent.setExecutionPolicy(new DenyExecutionPolicy());

        uint256 nonceBefore = agent.executionNonce();
        uint256 hitsBefore = sink.hits();

        vm.prank(controller);
        vm.expectRevert(SovereignAgent.ExecutionPolicyDenied.selector);
        agent.execute(address(sink), 0.1 ether, abi.encodeCall(Sink.ping, ()));

        assertEq(agent.executionNonce(), nonceBefore);
        assertEq(sink.hits(), hitsBefore);
        assertEq(address(sink).balance, 0);
    }

    function test_RevertExecutionPolicy_LeavesNonceAndCalleeUnchanged() public {
        vm.prank(controller);
        agent.setExecutionPolicy(new RevertExecutionPolicy());

        uint256 nonceBefore = agent.executionNonce();

        vm.prank(controller);
        vm.expectRevert(RevertExecutionPolicy.ExecutionPolicyReverted.selector);
        agent.execute(address(sink), 0, abi.encodeCall(Sink.ping, ()));

        assertEq(agent.executionNonce(), nonceBefore);
        assertEq(sink.hits(), 0);
    }

    function test_SetExecutionPolicy_OnlyController() public {
        vm.prank(stranger);
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.setExecutionPolicy(new AllowExecutionPolicy());
    }

    function test_StrangerCannotExecuteEvenWithAllowPolicy() public {
        vm.prank(controller);
        agent.setExecutionPolicy(new AllowExecutionPolicy());

        vm.prank(stranger);
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.execute(address(sink), 0, abi.encodeCall(Sink.ping, ()));
        assertEq(sink.hits(), 0);
    }
}
