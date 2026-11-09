// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ActionAnchor} from "../../src/trust/ActionAnchor.sol";

contract ActionAnchorTest is Test {
    ActionAnchor anchor;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    bytes32 leaf0;
    bytes32 leaf1;
    bytes32 leaf2;
    bytes32 leaf3;
    bytes32 parent01;
    bytes32 parent23;
    bytes32 root;

    function _hashPair(bytes32 a, bytes32 b) internal pure returns (bytes32) {
        return a < b ? keccak256(abi.encodePacked(a, b)) : keccak256(abi.encodePacked(b, a));
    }

    function setUp() public {
        anchor = new ActionAnchor();

        leaf0 = keccak256(abi.encodePacked("alice:action:1"));
        leaf1 = keccak256(abi.encodePacked("alice:action:2"));
        leaf2 = keccak256(abi.encodePacked("alice:action:3"));
        leaf3 = keccak256(abi.encodePacked("alice:action:4"));

        parent01 = _hashPair(leaf0, leaf1);
        parent23 = _hashPair(leaf2, leaf3);
        root = _hashPair(parent01, parent23);
    }

    function test_anchorRootRecordsUnderCallerAndReturnsEpoch() public {
        vm.prank(alice);
        uint256 epoch = anchor.anchorRoot(root);

        assertEq(epoch, 1);
        assertEq(anchor.epoch(alice), 1);
        assertEq(anchor.latestRoot(alice), root);
    }

    function test_epochIsIndependentPerAgent() public {
        vm.prank(alice);
        anchor.anchorRoot(root);
        vm.prank(alice);
        anchor.anchorRoot(keccak256("alice-2"));

        vm.prank(bob);
        uint256 bobEpoch = anchor.anchorRoot(keccak256("bob-1"));

        assertEq(anchor.epoch(alice), 2);
        assertEq(anchor.epoch(bob), 1);
        assertEq(bobEpoch, 1);
        assertEq(anchor.latestRoot(bob), keccak256("bob-1"));
        assertEq(anchor.latestRoot(alice), keccak256("alice-2"));
    }

    function test_emptyRootReverts() public {
        vm.prank(alice);
        vm.expectRevert(ActionAnchor.EmptyRoot.selector);
        anchor.anchorRoot(bytes32(0));
    }

    function test_rootAnchoredEventEmitted() public {
        vm.expectEmit(true, false, false, true, address(anchor));
        emit ActionAnchor.RootAnchored(alice, 1, root);

        vm.prank(alice);
        anchor.anchorRoot(root);
    }

    function test_leafIncludedUnderLatestRootVerifies() public {
        vm.prank(alice);
        anchor.anchorRoot(root);

        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaf1;
        proof[1] = parent23;
        assertTrue(anchor.verifyLeaf(alice, leaf0, proof));
    }

    function test_wrongLeafFailsVerification() public {
        vm.prank(alice);
        anchor.anchorRoot(root);

        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaf1;
        proof[1] = parent23;
        assertFalse(anchor.verifyLeaf(alice, leaf2, proof));
    }

    function test_crossAgentRootReturnsFalse() public {
        // alice's leaf is provable under alice's root...
        vm.prank(alice);
        anchor.anchorRoot(root);

        // ...but bob anchors an unrelated root; alice's proof must not verify under bob.
        vm.prank(bob);
        anchor.anchorRoot(keccak256("bob-root"));

        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaf1;
        proof[1] = parent23;
        assertTrue(anchor.verifyLeaf(alice, leaf0, proof));
        assertFalse(anchor.verifyLeaf(bob, leaf0, proof));
    }

    function test_noAnchorMeansNoVerification() public view {
        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaf1;
        proof[1] = parent23;
        assertFalse(anchor.verifyLeaf(alice, leaf0, proof));
    }

    function test_latestRootSupersedesOldRootForVerification() public {
        vm.prank(alice);
        anchor.anchorRoot(root);
        vm.prank(alice);
        anchor.anchorRoot(keccak256("alice-new"));

        bytes32[] memory proof = new bytes32[](2);
        proof[0] = leaf1;
        proof[1] = parent23;
        assertFalse(anchor.verifyLeaf(alice, leaf0, proof));
    }
}
