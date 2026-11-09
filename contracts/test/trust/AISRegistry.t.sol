// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AISRegistry} from "../../src/trust/AISRegistry.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {ITK} from "../../src/trust/ITK.sol";

contract AISRegistryTest is Test {
    AISRegistry registry;

    address admin = makeAddr("admin");
    address scorer = makeAddr("scorer");
    address stranger = makeAddr("stranger");
    address agent = makeAddr("agent");

    bytes32 constant ROOT_A = keccak256("evidence-A");
    bytes32 constant ROOT_B = keccak256("evidence-B");

    event CheckpointPosted(address indexed agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot);

    function setUp() public {
        vm.prank(admin);
        registry = new AISRegistry(admin);

        // postCheckpoint requires a wired StakeVault (threshold 0 => never freezes here).
        ITK itk = new ITK(admin, 0);
        StakeVault vault = new StakeVault(address(itk), admin);

        vm.startPrank(admin);
        registry.grantRole(registry.SCORER_ROLE(), scorer);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(registry));
        registry.setStakeVault(address(vault));
        vm.stopPrank();
    }

    function test_postCheckpoint_storesAndEmits() public {
        vm.expectEmit(true, false, false, true, address(registry));
        emit CheckpointPosted(agent, 7500, 1_700_000_000, ROOT_A);

        vm.prank(scorer);
        registry.postCheckpoint(agent, 7500, 1_700_000_000, ROOT_A, 0);

        (uint32 score, uint64 windowEnd, bytes32 evidenceRoot) = registry.latest(agent);
        assertEq(score, 7500);
        assertEq(windowEnd, 1_700_000_000);
        assertEq(evidenceRoot, ROOT_A);
    }

    function test_postCheckpoint_revertsForNonScorer() public {
        bytes32 role = registry.SCORER_ROLE();
        vm.prank(stranger);
        vm.expectRevert(
            abi.encodeWithSelector(bytes4(keccak256("AccessControlUnauthorizedAccount(address,bytes32)")), stranger, role)
        );
        registry.postCheckpoint(agent, 5000, 1, ROOT_A, 0);
    }

    function test_postCheckpoint_revertsAboveMaxScore() public {
        vm.prank(scorer);
        vm.expectRevert(AISRegistry.ScoreOutOfRange.selector);
        registry.postCheckpoint(agent, 10001, 1, ROOT_A, 0);
    }

    function test_postCheckpoint_acceptsBoundaryScores() public {
        vm.startPrank(scorer);
        registry.postCheckpoint(agent, 0, 1, ROOT_A, 0);
        registry.postCheckpoint(agent, 10000, 2, ROOT_B, 0);
        vm.stopPrank();

        (uint32 score,,) = registry.latest(agent);
        assertEq(score, 10000);
    }

    function test_postCheckpoint_laterOverwritesPrior() public {
        vm.startPrank(scorer);
        registry.postCheckpoint(agent, 6000, 100, ROOT_A, 0);
        registry.postCheckpoint(agent, 8200, 200, ROOT_B, 0);
        vm.stopPrank();

        (uint32 score, uint64 windowEnd, bytes32 evidenceRoot) = registry.latest(agent);
        assertEq(score, 8200);
        assertEq(windowEnd, 200);
        assertEq(evidenceRoot, ROOT_B);
    }

    function test_postCheckpoint_isKeyedPerAgent() public {
        address other = makeAddr("other");
        vm.startPrank(scorer);
        registry.postCheckpoint(agent, 4000, 100, ROOT_A, 0);
        registry.postCheckpoint(other, 9000, 100, ROOT_B, 0);
        vm.stopPrank();

        (uint32 scoreAgent,, bytes32 rootAgent) = registry.latest(agent);
        (uint32 scoreOther,, bytes32 rootOther) = registry.latest(other);
        assertEq(scoreAgent, 4000);
        assertEq(rootAgent, ROOT_A);
        assertEq(scoreOther, 9000);
        assertEq(rootOther, ROOT_B);
    }
}
