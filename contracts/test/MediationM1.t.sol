// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";
import {ConstraintExecutionPolicy} from "../src/core/ConstraintExecutionPolicy.sol";

contract MockErc20 {
    event Transfer(address indexed to, uint256 amount);

    function transfer(address to, uint256 amount) external returns (bool) {
        emit Transfer(to, amount);
        return true;
    }
}

contract MediationM1Test is Test {
    address controller = makeAddr("controller");
    address oracle = makeAddr("oracle");
    SovereignAgent agent;
    ConstraintExecutionPolicy policy;
    MockErc20 token;

    function setUp() public {
        agent = new SovereignAgent("did:integrity:m1", controller, oracle, address(this));
        policy = new ConstraintExecutionPolicy(controller, 0, 0, false);
        token = new MockErc20();
        vm.prank(controller);
        agent.setExecutionPolicy(address(policy));
    }

    function testTokenTransferAllowedUnderCap() public {
        vm.startPrank(controller);
        policy.setTokenCap(address(token), 100);
        policy.setEnforceTokenCaps(true);
        bytes memory data = abi.encodeWithSelector(MockErc20.transfer.selector, makeAddr("to"), 100);
        agent.execute(address(token), 0, data);
        vm.stopPrank();
    }

    function testTokenTransferDeniedOverCap() public {
        vm.startPrank(controller);
        policy.setTokenCap(address(token), 100);
        policy.setEnforceTokenCaps(true);
        bytes memory data = abi.encodeWithSelector(MockErc20.transfer.selector, makeAddr("to"), 101);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        agent.execute(address(token), 0, data);
        vm.stopPrank();
    }

    function testUnknownTokenDeniedWhenCapsEnforced() public {
        vm.startPrank(controller);
        policy.setEnforceTokenCaps(true);
        bytes memory data = abi.encodeWithSelector(MockErc20.transfer.selector, makeAddr("to"), 1);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        agent.execute(address(token), 0, data);
        vm.stopPrank();
    }
}
