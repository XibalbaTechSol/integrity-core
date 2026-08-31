// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {ReputationFloorAdapter} from "../../src/registry/ReputationFloorAdapter.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";

/// @notice Mirrors `ReputationFloorLicenceHookTest` (`PRODUCTION_GAPS.md` §51) -- same
/// EIP-1167-clone `ReputationRegistry` setup pattern `IntegrityAccount.t.sol` uses, proving
/// `ReputationFloorAdapter` agrees exactly with the already-trusted `ReputationFloorLicenceHook`
/// shape, plus registry-integration coverage.
contract ReputationFloorAdapterTest is Test {
    AdapterRegistry registry;
    ReputationFloorAdapter adapter;
    ReputationRegistry reputation;

    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant GAS_BOUND = 200_000;

    address subject = makeAddr("subject");

    function setUp() public {
        address reputationImpl = address(new ReputationRegistry());
        reputation = ReputationRegistry(Clones.clone(reputationImpl));
        reputation.initialize(address(this), address(this), address(0), address(0));

        registry = new AdapterRegistry();
        adapter = new ReputationFloorAdapter(reputation, MIN_EFFECTIVE_SCORE);
        registry.register(address(adapter), GAS_BOUND, keccak256("reputation-floor-v1"));
    }

    // --- direct calls (bypassing the registry) ------------------------------------------------

    function test_checkRevertsWhenSubjectReputationBelowFloor() public {
        reputation.updateScore(subject, MIN_EFFECTIVE_SCORE - 1);
        vm.expectRevert(
            abi.encodeWithSelector(
                ReputationFloorAdapter.ReputationBelowFloor.selector, subject, MIN_EFFECTIVE_SCORE - 1, MIN_EFFECTIVE_SCORE
            )
        );
        adapter.check(subject, 0);
    }

    function test_checkSucceedsExactlyAtTheFloor() public {
        reputation.updateScore(subject, MIN_EFFECTIVE_SCORE);
        adapter.check(subject, 0); // does not revert
    }

    function test_checkSucceedsAboveTheFloor() public {
        reputation.updateScore(subject, MIN_EFFECTIVE_SCORE + 1);
        adapter.check(subject, 0); // does not revert
    }

    function test_readIsLiveNotCached() public {
        reputation.updateScore(subject, MIN_EFFECTIVE_SCORE - 1);
        vm.expectRevert();
        adapter.check(subject, 0);

        reputation.updateScore(subject, MIN_EFFECTIVE_SCORE);
        adapter.check(subject, 0); // succeeds immediately, same block, no cache to invalidate
    }

    // --- through the registry ----------------------------------------------------------------

    function test_evaluateThroughRegistrySucceedsAboveFloor() public {
        reputation.updateScore(subject, MIN_EFFECTIVE_SCORE + 100);
        assertTrue(registry.evaluate(address(adapter), subject, 0));
    }

    function test_evaluateThroughRegistryBubblesUpReputationBelowFloor() public {
        reputation.updateScore(subject, MIN_EFFECTIVE_SCORE - 1);
        vm.expectRevert(
            abi.encodeWithSelector(
                ReputationFloorAdapter.ReputationBelowFloor.selector, subject, MIN_EFFECTIVE_SCORE - 1, MIN_EFFECTIVE_SCORE
            )
        );
        registry.evaluate(address(adapter), subject, 0);
    }
}
