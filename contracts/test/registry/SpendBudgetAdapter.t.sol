// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {SpendBudgetAdapter} from "../../src/registry/SpendBudgetAdapter.sol";

/// @notice Boundary-tested against the exact per-op/cumulative shape `IntegrityKernel`'s own
/// spend-budget check uses (`PRODUCTION_GAPS.md` §51's own comparison discipline), plus
/// registry-integration coverage proving `SpendBudgetAdapter` round-trips through
/// `AdapterRegistry.evaluate` correctly.
contract SpendBudgetAdapterTest is Test {
    AdapterRegistry registry;
    SpendBudgetAdapter adapter;

    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant GAS_BOUND = 200_000;

    address subject = makeAddr("subject");

    function setUp() public {
        registry = new AdapterRegistry();
        adapter = new SpendBudgetAdapter(PER_OP_BUDGET, CUMULATIVE_BUDGET);
        registry.register(address(adapter), GAS_BOUND, keccak256("spend-budget-v1"));
    }

    function test_constructorRevertsOnZeroPerOpBudget() public {
        vm.expectRevert(SpendBudgetAdapter.ZeroBudget.selector);
        new SpendBudgetAdapter(0, CUMULATIVE_BUDGET);
    }

    function test_constructorRevertsOnZeroCumulativeBudget() public {
        vm.expectRevert(SpendBudgetAdapter.ZeroBudget.selector);
        new SpendBudgetAdapter(PER_OP_BUDGET, 0);
    }

    // --- direct calls (bypassing the registry) ------------------------------------------------

    function test_spendExactlyAtPerOpBudgetSucceeds() public {
        adapter.check(subject, PER_OP_BUDGET);
        assertEq(adapter.cumulativeSpentWei(subject), PER_OP_BUDGET);
    }

    function test_spendOneWeiOverPerOpBudgetReverts() public {
        vm.expectRevert(
            abi.encodeWithSelector(SpendBudgetAdapter.PerOperationBudgetExceeded.selector, PER_OP_BUDGET + 1, PER_OP_BUDGET)
        );
        adapter.check(subject, PER_OP_BUDGET + 1);
        assertEq(adapter.cumulativeSpentWei(subject), 0);
    }

    function test_cumulativeSpendExactlyAtBudgetSucceedsAcrossMultipleCalls() public {
        adapter.check(subject, PER_OP_BUDGET);
        adapter.check(subject, PER_OP_BUDGET);
        adapter.check(subject, CUMULATIVE_BUDGET - 2 * PER_OP_BUDGET); // tops out exactly at 3 ether
        assertEq(adapter.cumulativeSpentWei(subject), CUMULATIVE_BUDGET);
    }

    function test_cumulativeSpendOneWeiOverBudgetRevertsWithNoStateChange() public {
        // Three ops of PER_OP_BUDGET each reach the cumulative cap EXACTLY (3 x 1 ether = 3
        // ether) -- a fourth op of just 1 wei stays well within the per-op limit but pushes
        // cumulative one wei over, isolating the cumulative check specifically.
        adapter.check(subject, PER_OP_BUDGET);
        adapter.check(subject, PER_OP_BUDGET);
        adapter.check(subject, PER_OP_BUDGET);
        uint256 priorCumulative = adapter.cumulativeSpentWei(subject);
        assertEq(priorCumulative, CUMULATIVE_BUDGET);

        vm.expectRevert(
            abi.encodeWithSelector(
                SpendBudgetAdapter.CumulativeBudgetExceeded.selector, priorCumulative, 1, CUMULATIVE_BUDGET
            )
        );
        adapter.check(subject, 1);
        assertEq(adapter.cumulativeSpentWei(subject), priorCumulative);
    }

    function test_cumulativeTrackingIsIndependentPerSubject() public {
        address otherSubject = makeAddr("otherSubject");
        adapter.check(subject, PER_OP_BUDGET);
        adapter.check(otherSubject, PER_OP_BUDGET);

        assertEq(adapter.cumulativeSpentWei(subject), PER_OP_BUDGET);
        assertEq(adapter.cumulativeSpentWei(otherSubject), PER_OP_BUDGET);
    }

    // --- through the registry ----------------------------------------------------------------

    function test_evaluateThroughRegistrySucceedsWithinBudget() public {
        assertTrue(registry.evaluate(address(adapter), subject, PER_OP_BUDGET));
        assertEq(adapter.cumulativeSpentWei(subject), PER_OP_BUDGET);
    }

    function test_evaluateThroughRegistryBubblesUpPerOpBudgetExceeded() public {
        vm.expectRevert(
            abi.encodeWithSelector(SpendBudgetAdapter.PerOperationBudgetExceeded.selector, PER_OP_BUDGET + 1, PER_OP_BUDGET)
        );
        registry.evaluate(address(adapter), subject, PER_OP_BUDGET + 1);
    }
}
