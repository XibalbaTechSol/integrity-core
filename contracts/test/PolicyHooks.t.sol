// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";
import {StateAnchor} from "../src/oracle/StateAnchor.sol";
import {AllowlistAnchorPolicy} from "../src/core/AllowlistAnchorPolicy.sol";
import {ConstraintExecutionPolicy} from "../src/core/ConstraintExecutionPolicy.sol";
import {IExecutionPolicy} from "../src/core/IExecutionPolicy.sol";
import {IAnchorPolicy} from "../src/core/IAnchorPolicy.sol";

contract Sink {
    uint256 public hits;

    receive() external payable {
        hits += 1;
    }
}

/// @notice A policy whose `check` REVERTS rather than returning `false` -- distinct from
/// `ConstraintExecutionPolicy`'s ordinary deny path. `docs/SPEC.md` §5.3 requires "a `false`
/// return OR a revert" to both fail closed identically; nothing in this suite exercised the
/// revert half before these tests.
contract RevertingExecutionPolicy is IExecutionPolicy {
    error PolicyExploded();

    function check(address, address, uint256, bytes calldata) external pure returns (bool) {
        revert PolicyExploded();
    }
}

contract RevertingAnchorPolicy is IAnchorPolicy {
    error PolicyExploded();

    function check(address, bytes32, uint256) external pure returns (bool) {
        revert PolicyExploded();
    }
}

contract PolicyHooksTest is Test {
    address controller = makeAddr("controller");
    address oracle = makeAddr("oracle");
    address stranger = makeAddr("stranger");

    SovereignAgent agent;
    StateAnchor anchor;
    Sink sink;

    function setUp() public {
        agent = new SovereignAgent("did:integrity:test", controller, oracle, address(this));
        anchor = new StateAnchor(controller);
        sink = new Sink();
        vm.deal(address(agent), 10 ether);
    }

    function testExecuteSkipsWhenPolicyUnset() public {
        vm.prank(controller);
        agent.execute(address(sink), 1 wei, "");
        assertEq(sink.hits(), 1);
        assertEq(agent.executionNonce(), 1);
    }

    function testExecuteDeniedDoesNotConsumeNonce() public {
        ConstraintExecutionPolicy policy =
            new ConstraintExecutionPolicy(controller, /* minAis */ 1, /* maxValue */ 0, false);
        vm.prank(controller);
        agent.setExecutionPolicy(address(policy));

        vm.prank(controller);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        agent.execute(address(sink), 0, "");
        assertEq(agent.executionNonce(), 0);
    }

    function testExecuteAllowsWhenAisMeetsFloor() public {
        ConstraintExecutionPolicy policy =
            new ConstraintExecutionPolicy(controller, 10, 0, false);
        vm.prank(controller);
        agent.setExecutionPolicy(address(policy));

        vm.prank(oracle);
        agent.updateAIS(10);

        vm.prank(controller);
        agent.execute(address(sink), 0, "");
        assertEq(sink.hits(), 1);
    }

    function testExecuteEnforcesValueCapAndAllowlist() public {
        ConstraintExecutionPolicy policy =
            new ConstraintExecutionPolicy(controller, 0, 1 ether, true);
        vm.prank(controller);
        policy.setTarget(address(sink), true);
        vm.prank(controller);
        agent.setExecutionPolicy(address(policy));

        vm.prank(controller);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        agent.execute(address(sink), 1 ether + 1, "");

        vm.prank(controller);
        agent.execute(address(sink), 1 ether, "");
        assertEq(sink.hits(), 1);

        address other = makeAddr("other");
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        agent.execute(other, 0, "");
    }

    function testAnchorSkipsWhenPolicyUnset() public {
        bytes32 root = keccak256("root-1");
        vm.prank(controller);
        uint256 epoch = anchor.anchorRoot(root);
        assertEq(epoch, 1);
        assertTrue(anchor.isAnchoredRoot(root));
        assertEq(anchor.latestRoot(), root);
    }

    function testAnchorDeniedWhenCallerNotAllowlisted() public {
        address[] memory initial;
        AllowlistAnchorPolicy policy = new AllowlistAnchorPolicy(controller, initial);
        vm.prank(controller);
        anchor.setAnchorPolicy(address(policy));

        vm.prank(controller);
        vm.expectRevert(StateAnchor.PolicyDenied.selector);
        anchor.anchorRoot(keccak256("root-2"));
        assertEq(anchor.latestEpoch(), 0);
    }

    function testAnchorAllowsAllowlistedCaller() public {
        address[] memory initial = new address[](1);
        initial[0] = controller;
        AllowlistAnchorPolicy policy = new AllowlistAnchorPolicy(controller, initial);
        vm.prank(controller);
        anchor.setAnchorPolicy(address(policy));

        bytes32 root = keccak256("root-3");
        vm.prank(controller);
        uint256 epoch = anchor.anchorRoot(root);
        assertEq(epoch, 1);
        assertEq(anchor.rootAtEpoch(1), root);
    }

    // --- fail-closed on a REVERTING policy, not just a false-returning one ----------------------

    function testExecuteRevertingPolicyFailsClosed() public {
        RevertingExecutionPolicy policy = new RevertingExecutionPolicy();
        vm.prank(controller);
        agent.setExecutionPolicy(address(policy));

        vm.prank(controller);
        vm.expectRevert(RevertingExecutionPolicy.PolicyExploded.selector);
        agent.execute(address(sink), 0, "");

        assertEq(agent.executionNonce(), 0, "a reverting policy must not consume the nonce");
        assertEq(sink.hits(), 0, "a reverting policy must not let the call through");
    }

    function testAnchorRevertingPolicyFailsClosed() public {
        RevertingAnchorPolicy policy = new RevertingAnchorPolicy();
        vm.prank(controller);
        anchor.setAnchorPolicy(address(policy));

        vm.prank(controller);
        vm.expectRevert(RevertingAnchorPolicy.PolicyExploded.selector);
        anchor.anchorRoot(keccak256("root-4"));

        assertEq(anchor.latestEpoch(), 0, "a reverting policy must not advance the epoch");
        assertEq(anchor.latestRoot(), bytes32(0), "a reverting policy must not write a root");
    }

    // --- policy setters are access-controlled, not permissionless --------------------------------

    function testSetExecutionPolicyOnlyController() public {
        ConstraintExecutionPolicy policy = new ConstraintExecutionPolicy(controller, 0, 0, false);

        vm.prank(stranger);
        vm.expectRevert(SovereignAgent.NotController.selector);
        agent.setExecutionPolicy(address(policy));
    }

    function testSetAnchorPolicyOnlyAdmin() public {
        address[] memory initial;
        AllowlistAnchorPolicy policy = new AllowlistAnchorPolicy(controller, initial);

        vm.prank(stranger);
        vm.expectRevert(
            abi.encodeWithSignature(
                "AccessControlUnauthorizedAccount(address,bytes32)", stranger, bytes32(0)
            )
        );
        anchor.setAnchorPolicy(address(policy));
    }
}
