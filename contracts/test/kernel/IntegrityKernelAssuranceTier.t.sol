// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {stdStorage, StdStorage} from "forge-std/StdStorage.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";

import {IntegrityKernel} from "../../src/kernel/IntegrityKernel.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";

/// @title IntegrityKernelAssuranceTierTest
/// @notice Covers `IntegrityKernel.requireAssuranceTier` (docs/EXECUTION_PLAN.md, A4).
/// @dev The kernel's hooks are called directly while pranking as the bound account -- the only
/// caller `onlyBoundAccount` admits -- so each property is isolated from `IntegrityAccount`'s own
/// execution plumbing, which `IntegrityAccount.t.sol` already covers end to end. The properties:
///  - tier required (the reference configuration): no live ZK boost reverts `AssuranceTierNotMet`,
///    a live boost passes;
///  - tier disabled: no boost passes, while the reputation floor, snapshot staleness and native
///    budget still bind -- disabling the tier must remove exactly one gate, never more.
contract IntegrityKernelAssuranceTierTest is Test {
    using stdStorage for StdStorage;

    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant ABOVE_FLOOR_SCORE = 800;
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days;

    address constant ACCOUNT = address(0xA11CE);

    ReputationRegistry reputation;

    function setUp() public {
        ReputationRegistry implementation = new ReputationRegistry();
        reputation = ReputationRegistry(Clones.clone(address(implementation)));
        // This test contract is both admin and oracle, so it can push scores directly.
        reputation.initialize(address(this), address(this), address(0), address(0));
        reputation.updateScore(ACCOUNT, ABOVE_FLOOR_SCORE);
    }

    function _kernel(bool requireAssuranceTier) internal returns (IntegrityKernel) {
        return new IntegrityKernel(
            ACCOUNT,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0), // no tracked token
            0,
            0,
            requireAssuranceTier
        );
    }

    /// @dev Same storage write `IntegrityAccount.t.sol` uses: `AgentScore.zkBoostExpiry`.
    function _setZkBoostExpiry(address subject, uint256 expiry) internal {
        stdstore.target(address(reputation)).sig("scores(address)").with_key(subject).depth(2).checked_write(expiry);
    }

    function _preCheck(IntegrityKernel kernel) internal returns (bytes memory) {
        vm.prank(ACCOUNT);
        return kernel.preCheck(address(0), 0, "");
    }

    function test_flagIsExposedAsConfigured() public {
        assertTrue(_kernel(true).requireAssuranceTier());
        assertFalse(_kernel(false).requireAssuranceTier());
    }

    function test_tierRequired_revertsWithoutLiveBoost() public {
        IntegrityKernel kernel = _kernel(true);
        assertFalse(kernel.snapshotIsZkBoosted());
        vm.prank(ACCOUNT);
        vm.expectRevert(abi.encodeWithSelector(IntegrityKernel.AssuranceTierNotMet.selector, ACCOUNT));
        kernel.preCheck(address(0), 0, "");
    }

    function test_tierRequired_passesWithLiveBoost() public {
        _setZkBoostExpiry(ACCOUNT, block.timestamp + 7 days);
        IntegrityKernel kernel = _kernel(true);
        assertTrue(kernel.snapshotIsZkBoosted());
        _preCheck(kernel);
        assertTrue(kernel.armed());
    }

    function test_tierDisabled_passesWithoutBoost() public {
        IntegrityKernel kernel = _kernel(false);
        assertFalse(kernel.snapshotIsZkBoosted());
        _preCheck(kernel);
        assertTrue(kernel.armed());
    }

    function test_tierDisabled_stillEnforcesReputationFloor() public {
        reputation.updateScore(ACCOUNT, MIN_EFFECTIVE_SCORE - 1);
        IntegrityKernel kernel = _kernel(false);
        vm.prank(ACCOUNT);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.ReputationBelowFloor.selector, MIN_EFFECTIVE_SCORE - 1, MIN_EFFECTIVE_SCORE
            )
        );
        kernel.preCheck(address(0), 0, "");
    }

    function test_tierDisabled_stillFailsClosedOnStaleSnapshot() public {
        IntegrityKernel kernel = _kernel(false);
        uint256 takenAt = kernel.snapshotTakenAt();
        vm.warp(takenAt + REPUTATION_EPOCH_LENGTH + 1);
        vm.prank(ACCOUNT);
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityKernel.SnapshotStale.selector, takenAt, block.timestamp, REPUTATION_EPOCH_LENGTH
            )
        );
        kernel.preCheck(address(0), 0, "");
    }

    function test_tierDisabled_stillEnforcesPerOperationBudget() public {
        IntegrityKernel kernel = _kernel(false);
        vm.deal(ACCOUNT, 2 ether);
        bytes memory hookData = _preCheck(kernel);
        // The wrapped call spends the whole 2 ether balance: over the 1 ether per-op budget.
        vm.deal(ACCOUNT, 0);
        vm.prank(ACCOUNT);
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityKernel.PerOperationBudgetExceeded.selector, 2 ether, PER_OP_BUDGET)
        );
        kernel.postCheck(hookData);
    }
}
