// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {AdapterRegistry} from "../src/registry/AdapterRegistry.sol";

/// @title AdapterAdmissionSuite
/// @notice Phase III whitepaper §6.2 obligation R1 ("determinism / differential replay") --
/// `AdapterRegistry.sol`'s own NatSpec names this as needing "an off-chain differential-replay
/// admission suite this repo has never built, not a contract-level check." This is that tool.
/// @dev **What R1 means, precisely** (per `docs/design/phase3-adapter-encoding-strategy-2026-08-25.md`):
/// submit the same `(subject, amount)` context twice against the same adapter, AT THE SAME chain
/// state, and confirm identical output. This tool does exactly that, generically, for ANY already-
/// registered `IAdapter` -- registration is permissionless (`AdapterRegistry.register`'s own
/// NatSpec), so this suite cannot assume anything about an adapter's internals; it only observes
/// `AdapterRegistry.evaluate`'s outward behavior.
/// @dev **Mechanism:** for each `(subject, amount)` vector, snapshot state
/// (`vm.snapshotState`), call `evaluate`, capture (success, revert data), revert the snapshot
/// (`vm.revertToState` -- undoes ANY storage mutation the call made, so the second call starts
/// from bit-identical state to the first), snapshot again, call again, revert again, then compare.
/// A real adapter's own persistent state (e.g. `SpendBudgetAdapter.cumulativeSpentWei`) is
/// therefore never actually advanced by this tool -- see `AdapterAdmissionSuite.t.sol` for a
/// direct assertion that it comes back to its pre-run value.
/// @dev **What this proves, and what it does not:** a PASS means both replay calls produced the
/// identical (success/revert, revert-reason-bytes) pair for every submitted vector -- real
/// evidence the adapter's `check` is a pure function of `(state, subject, amount)`, not of call
/// order, `msg.sender` identity beyond what's passed in, or hidden mutable state outside what
/// `vm.revertToState` restores. It does NOT prove the adapter is correct, safe, or behaves the
/// same across DIFFERENT chain states (e.g. across a real block boundary where `block.timestamp`
/// or `block.number` legitimately advances) -- only same-state replay, which is exactly R1's own
/// stated scope, not a wider claim.
/// @dev Read-only in intent: run via `forge script script/AdapterAdmissionSuite.s.sol --fork-url
/// <rpc>` (NEVER `--broadcast` -- there is nothing to broadcast; every mutation this script makes
/// is deliberately reverted before `run()` returns).
contract AdapterAdmissionSuite is Script {
    struct Vector {
        address subject;
        uint256 amount;
    }

    struct VectorResult {
        address subject;
        uint256 amount;
        bool succeededFirst;
        bool succeededSecond;
        bytes32 revertReasonHashFirst;
        bytes32 revertReasonHashSecond;
        bool deterministic;
    }

    /// @notice Entry point for `forge script`. Reads ADAPTER_REGISTRY, ADAPTER, and VECTORS_FILE
    /// (a JSON file with parallel `subjects`/`amounts` arrays) from the environment.
    function run() external {
        address registryAddr = vm.envAddress("ADAPTER_REGISTRY");
        address adapter = vm.envAddress("ADAPTER");
        string memory vectorsPath =
            vm.envOr("VECTORS_FILE", string("script/adapter-admission-vectors/spend-budget-example.json"));
        string memory outputPath =
            vm.envOr("OUTPUT_FILE", string("script/adapter-admission-vectors/last-report.json"));

        Vector[] memory vectors = loadVectors(vectorsPath);
        (VectorResult[] memory results, uint256 failures) = runFor(AdapterRegistry(registryAddr), adapter, vectors);

        writeReport(outputPath, adapter, results);

        require(failures == 0, "AdapterAdmissionSuite: nondeterminism detected -- see report/log above");
    }

    /// @notice The reusable core: differential-replays every vector against `adapter` through
    /// `registry`, snapshotting and reverting state around each call. Public (not external) and
    /// state-mutating-but-self-reverting so it can be called directly from a Foundry test as well
    /// as from `run()`.
    function runFor(AdapterRegistry registry, address adapter, Vector[] memory vectors)
        public
        returns (VectorResult[] memory results, uint256 failures)
    {
        require(vectors.length > 0, "AdapterAdmissionSuite: no vectors supplied");
        results = new VectorResult[](vectors.length);

        for (uint256 i = 0; i < vectors.length; i++) {
            Vector memory v = vectors[i];

            uint256 snap1 = vm.snapshotState();
            (bool ok1, bytes memory data1) = evaluateOnce(registry, adapter, v.subject, v.amount);
            vm.revertToState(snap1);

            uint256 snap2 = vm.snapshotState();
            (bool ok2, bytes memory data2) = evaluateOnce(registry, adapter, v.subject, v.amount);
            vm.revertToState(snap2);

            bool det = isDeterministic(ok1, data1, ok2, data2);
            results[i] = VectorResult({
                subject: v.subject,
                amount: v.amount,
                succeededFirst: ok1,
                succeededSecond: ok2,
                revertReasonHashFirst: keccak256(data1),
                revertReasonHashSecond: keccak256(data2),
                deterministic: det
            });

            if (!det) {
                failures++;
                console2.log("NONDETERMINISTIC vector index", i);
            } else {
                console2.log(ok1 ? "PASS (adapter allows) vector index" : "PASS (adapter rejects) vector index", i);
            }
        }
    }

    /// @notice Pure comparison: two replay outcomes are deterministic iff both succeeded, or both
    /// reverted with byte-identical revert data. Split out and separately unit-tested (see
    /// `AdapterAdmissionSuite.t.sol`) so the detector itself is proven to catch a real mismatch,
    /// not just proven to pass on well-behaved adapters.
    function isDeterministic(bool ok1, bytes memory data1, bool ok2, bytes memory data2)
        public
        pure
        returns (bool)
    {
        if (ok1 != ok2) return false;
        return keccak256(data1) == keccak256(data2);
    }

    function evaluateOnce(AdapterRegistry registry, address adapter, address subject, uint256 amount)
        internal
        returns (bool ok, bytes memory data)
    {
        try registry.evaluate(adapter, subject, amount) returns (bool) {
            ok = true;
            data = "";
        } catch (bytes memory reason) {
            ok = false;
            data = reason;
        }
    }

    function loadVectors(string memory path) public view returns (Vector[] memory vectors) {
        string memory json = vm.readFile(path);
        address[] memory subjects = vm.parseJsonAddressArray(json, ".subjects");
        uint256[] memory amounts = vm.parseJsonUintArray(json, ".amounts");
        require(
            subjects.length == amounts.length, "AdapterAdmissionSuite: subjects/amounts length mismatch in vectors file"
        );
        vectors = new Vector[](subjects.length);
        for (uint256 i = 0; i < subjects.length; i++) {
            vectors[i] = Vector({subject: subjects[i], amount: amounts[i]});
        }
    }

    function writeReport(string memory path, address adapter, VectorResult[] memory results) internal {
        string memory arr = "[";
        for (uint256 i = 0; i < results.length; i++) {
            VectorResult memory r = results[i];
            string memory obj = string.concat(
                "{",
                "\"subject\":\"",
                vm.toString(r.subject),
                "\",",
                "\"amount\":\"",
                vm.toString(r.amount),
                "\",",
                "\"succeededFirst\":",
                r.succeededFirst ? "true" : "false",
                ",",
                "\"succeededSecond\":",
                r.succeededSecond ? "true" : "false",
                ",",
                "\"revertReasonHashFirst\":\"",
                vm.toString(r.revertReasonHashFirst),
                "\",",
                "\"revertReasonHashSecond\":\"",
                vm.toString(r.revertReasonHashSecond),
                "\",",
                "\"deterministic\":",
                r.deterministic ? "true" : "false",
                "}"
            );
            arr = string.concat(arr, obj, i + 1 < results.length ? "," : "");
        }
        arr = string.concat(arr, "]");

        string memory report = string.concat("{\"adapter\":\"", vm.toString(adapter), "\",\"vectors\":", arr, "}");
        vm.writeFile(path, report);
    }
}
