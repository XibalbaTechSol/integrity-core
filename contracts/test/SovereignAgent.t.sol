// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";

contract Target {
    uint256 public value;

    function setValue(uint256 v) external payable {
        value = v;
    }

    function alwaysReverts() external pure {
        revert("Target: nope");
    }
}

contract SovereignAgentTest is Test {
    SovereignAgent agent;
    Target target;

    address controller = makeAddr("controller");
    address stranger = makeAddr("stranger");

    function setUp() public {
        agent = new SovereignAgent("did:integrity:abc123", controller, address(this));
        target = new Target();
    }

    function test_initialState() public view {
        assertEq(agent.agentDID(), "did:integrity:abc123");
        assertEq(agent.registry(), address(this));
        assertTrue(agent.hasRole(agent.DEFAULT_ADMIN_ROLE(), controller));
    }

    function test_controllerCanExecute() public {
        vm.prank(controller);
        agent.execute(address(target), 0, abi.encodeCall(Target.setValue, (42)));
        assertEq(target.value(), 42);
        assertEq(agent.executionNonce(), 1);
    }

    function test_strangerCannotExecute() public {
        vm.prank(stranger);
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.execute(address(target), 0, abi.encodeCall(Target.setValue, (1)));
    }

    /// @notice execute() must bubble up the callee's revert reason verbatim, not
    /// collapse it to a generic failure — this is load-bearing for controllers trying
    /// to debug why an action failed.
    function test_executeBubblesRevertReason() public {
        vm.prank(controller);
        vm.expectRevert("Target: nope");
        agent.execute(address(target), 0, abi.encodeCall(Target.alwaysReverts, ()));
    }

    function test_rotateController() public {
        address newController = makeAddr("newController");
        vm.prank(controller);
        agent.rotateController(newController);

        assertFalse(agent.hasRole(agent.DEFAULT_ADMIN_ROLE(), controller));
        assertTrue(agent.hasRole(agent.DEFAULT_ADMIN_ROLE(), newController));

        // old controller can no longer execute
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.execute(address(target), 0, "");

        // new controller can
        vm.prank(newController);
        agent.execute(address(target), 0, abi.encodeCall(Target.setValue, (5)));
        assertEq(target.value(), 5);
    }

    function test_executeForwardsAgentsOwnBalance() public {
        // The agent forwards *its own* held balance to the target; `execute` itself is
        // not payable — the agent must already hold the funds (e.g. received via its
        // `receive()`), matching how a real account contract would hold treasury.
        vm.deal(address(agent), 1 ether);
        vm.prank(controller);
        agent.execute(address(target), 1 ether, abi.encodeCall(Target.setValue, (1)));
        assertEq(address(target).balance, 1 ether);
    }
}
