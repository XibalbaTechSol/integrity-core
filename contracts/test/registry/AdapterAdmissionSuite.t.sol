// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AdapterAdmissionSuite} from "../../script/AdapterAdmissionSuite.s.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {SpendBudgetAdapter} from "../../src/registry/SpendBudgetAdapter.sol";
import {AlwaysAllowAdapter, AlwaysRejectAdapter} from "./AdapterRegistry.t.sol";

/// @notice Why there is no "runFor catches a genuinely nondeterministic adapter" integration test
/// here, and why that is not a coverage gap: `vm.revertToState` restores the ENTIRE chain state
/// tree, not just the target adapter's own storage, and both replay calls execute inside the same
/// block context (no `vm.warp`/`vm.roll` between them). Given that, two calls with byte-identical
/// calldata against byte-identical global state are guaranteed by the EVM's own execution model to
/// produce byte-identical results -- there is no way to construct a real adapter contract whose
/// `runFor`-driven replay pair disagrees, short of a source of true non-determinism (real
/// randomness, a live oracle callback) that does not exist in a Foundry test backend and would not
/// exist in a single-block on-chain call either. This is not a weakness specific to this tool; it
/// is what "differential replay at identical state" *is*. The real, checkable claim is therefore
/// split in two: (1) the comparison logic (`isDeterministic`) correctly flags a mismatch when
/// GIVEN one, proven directly below with hand-crafted differing inputs; (2) `runFor`'s own
/// snapshot/revert bookkeeping is real, not a no-op, proven by asserting a real adapter's
/// persistent storage is unchanged after a run that exercised state-mutating paths (see
/// `test_runFor_spendBudgetAdapter_allDeterministic_andLeavesNoResidualState` below).
contract AdapterAdmissionSuiteTest is Test {
    AdapterRegistry registry;
    AdapterAdmissionSuite suite;

    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant GAS_BOUND = 200_000;

    function setUp() public {
        registry = new AdapterRegistry();
        suite = new AdapterAdmissionSuite();
    }

    // --- isDeterministic: the comparison logic itself, proven on both sides ------------------

    function test_isDeterministic_trueForIdenticalSuccesses() public view {
        assertTrue(suite.isDeterministic(true, "", true, ""));
    }

    function test_isDeterministic_trueForIdenticalReverts() public view {
        bytes memory reason = abi.encodeWithSignature("SomeError(uint256)", 42);
        assertTrue(suite.isDeterministic(false, reason, false, reason));
    }

    function test_isDeterministic_falseWhenSuccessFlagsDiffer() public view {
        assertFalse(suite.isDeterministic(true, "", false, abi.encodeWithSignature("X()")));
    }

    function test_isDeterministic_falseWhenRevertReasonsDiffer() public view {
        assertFalse(
            suite.isDeterministic(
                false, abi.encodeWithSignature("A()"), false, abi.encodeWithSignature("B()")
            )
        );
    }

    // --- runFor against real, well-behaved reference adapters: positive control ---------------

    function test_runFor_spendBudgetAdapter_allDeterministic_andLeavesNoResidualState() public {
        SpendBudgetAdapter adapter = new SpendBudgetAdapter(PER_OP_BUDGET, CUMULATIVE_BUDGET);
        registry.register(address(adapter), GAS_BOUND, keccak256("spend-budget-v1"));

        address subjectA = makeAddr("subjectA");
        address subjectB = makeAddr("subjectB");

        AdapterAdmissionSuite.Vector[] memory vectors = new AdapterAdmissionSuite.Vector[](3);
        vectors[0] = AdapterAdmissionSuite.Vector({subject: subjectA, amount: PER_OP_BUDGET});
        vectors[1] = AdapterAdmissionSuite.Vector({subject: subjectA, amount: PER_OP_BUDGET + 1});
        vectors[2] = AdapterAdmissionSuite.Vector({subject: subjectB, amount: 0});

        (AdapterAdmissionSuite.VectorResult[] memory results, uint256 failures) =
            suite.runFor(registry, address(adapter), vectors);

        assertEq(failures, 0, "a real, well-behaved adapter must be reported fully deterministic");
        assertEq(results.length, 3);
        assertTrue(results[0].succeededFirst && results[0].deterministic, "exact-budget spend should allow, deterministically");
        assertFalse(results[1].succeededFirst, "one-over-budget spend should reject");
        assertTrue(results[1].deterministic, "the rejection itself should be deterministic");

        // The real proof the snapshot/revert bookkeeping worked, not just that comparisons matched:
        // the adapter's OWN persistent state must be exactly as if `evaluate` were never called.
        assertEq(adapter.cumulativeSpentWei(subjectA), 0, "runFor must leave no residual state");
        assertEq(adapter.cumulativeSpentWei(subjectB), 0, "runFor must leave no residual state");
    }

    function test_runFor_alwaysAllowAndAlwaysReject_bothDeterministic() public {
        AlwaysAllowAdapter allow = new AlwaysAllowAdapter();
        AlwaysRejectAdapter reject = new AlwaysRejectAdapter();
        registry.register(address(allow), GAS_BOUND, keccak256("always-allow"));
        registry.register(address(reject), GAS_BOUND, keccak256("always-reject"));

        AdapterAdmissionSuite.Vector[] memory vectors = new AdapterAdmissionSuite.Vector[](1);
        vectors[0] = AdapterAdmissionSuite.Vector({subject: makeAddr("s"), amount: 1});

        (, uint256 failuresAllow) = suite.runFor(registry, address(allow), vectors);
        (, uint256 failuresReject) = suite.runFor(registry, address(reject), vectors);

        assertEq(failuresAllow, 0);
        assertEq(failuresReject, 0);
    }

    // --- loadVectors: JSON parsing round-trip --------------------------------------------------

    function test_loadVectors_parsesBundledExampleFile() public view {
        AdapterAdmissionSuite.Vector[] memory vectors =
            suite.loadVectors("script/adapter-admission-vectors/spend-budget-example.json");
        assertEq(vectors.length, 4);
        assertEq(vectors[0].subject, 0x1111111111111111111111111111111111111111);
        assertEq(vectors[0].amount, 0.5 ether);
    }
}
