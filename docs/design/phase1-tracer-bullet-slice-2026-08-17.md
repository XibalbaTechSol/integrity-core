# Phase I tracer-bullet slice — what it proves, precisely

Companion to `docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md` (the authorized scope) and
`docs/design/phase1-slice-dependency-inventory-2026-08-17.md` (the dependency research). This
note states the actual guarantee, in the same register as the whitepaper's own Proposition 1 —
no broader, no narrower.

## What exists

`contracts/src/kernel/IntegrityAccountV1Experimental.sol` and
`IntegrityKernelV1Experimental.sol`. **Not deployed anywhere** — Foundry-test-only. Not
upgradeable, not a proxy, not referenced by `Deploy.s.sol` or any deployment script. 12 passing
tests in `contracts/test/IntegrityAccountV1Experimental.t.sol`; full repo suite green at 221/221
(up from 209 before this slice).

## The guarantee, precisely

**Proposition (slice-scoped).** For an `IntegrityAccountV1Experimental` instance with kernel `K`
bound at construction and budgets `(b_op, b_cum)`: for every sequence of calls to `execute()`
with mode `(CALLTYPE_SINGLE, EXECTYPE_DEFAULT)`, accepted by the account's own
`onlyEntryPointOrSelf` gate, the account's native-token balance decrease from any single call
never exceeds `b_op`, and the cumulative decrease across all such calls never exceeds `b_cum`.
Verified by `test_overPerOpBudgetCallRevertsBeforeAnyStateChange` and
`test_overCumulativeBudgetCallRevertsEvenWhenEachCallIsIndividuallyInBudget`.

**What makes this hold, verified rather than assumed:**
- The hook fires on every reachable execution path — verified by proving the other three
  ERC-7579 dispatch combinations are rejected before reaching the base class's execution logic
  (`test_batchExecutionModeIsRejected`, `test_delegatecallExecutionModeIsRejected`,
  `test_tryExecTypeIsRejectedEvenWithSingleCalltype`), and that no second execution path can ever
  be opened (`test_moduleInstallIsUnconditionallyDisabled`,
  `test_moduleUninstallIsUnconditionallyDisabled` — the latter tried against the real, already-
  installed kernel specifically, not a hypothetical module).
- The hook cannot be bypassed or spoofed by a caller other than the bound account
  (`test_preCheckAndPostCheckRejectCallersOtherThanTheBoundAccount`), and cannot be invoked out
  of sequence (`test_postCheckCannotBeCalledDirectlyWithoutAPrecedingPreCheck`).
- The accounting cannot be defeated by reentrancy — proven with a genuine self-call reentrant
  execution (not a mocked shortcut), and separately confirmed by mutation testing: removing the
  `armed` guard makes the same test fail differently, demonstrating the guard performs real work
  rather than being decorative (see the commit history for the mutation-test transcript).
- `preCheck` measured under the whitepaper's own Table 4 budget (`<=40k` total) — a live
  regression test, not a one-off measurement (`test_preCheckGasIsWithinPaperTable4Budget`).

## What this does NOT prove — read this list as seriously as the guarantee above

- **Not general value conservation.** Only native ETH is tracked. Any ERC-20/ERC-721/other
  asset movement inside the wrapped call is completely unconstrained by this kernel.
- **Not calldata-content-aware.** The kernel never inspects what the wrapped call actually does
  beyond the resulting native-balance delta — a call that moves zero ETH but does anything else
  (approves a token, calls an arbitrary contract, self-destructs a target) is unconstrained.
- **Not complete mediation in the whitepaper's full sense.** Condition (iii) — module
  install/removal must itself be a constrained transition — is satisfied only by making
  install/removal *unreachable entirely*, not by gating it through the kernel. This is a
  materially weaker property: an account that could never evolve its policy is trivially "safe"
  from policy-removal attacks, but it is also not a general-purpose account design. The full
  Phase I plan's module-governance item (timelocked, multi-party removal) remains unbuilt.
- **Not audited.** No external review has occurred. This slice's own completion does not clear
  the Devil's Advocate review's stated gate to Phase II ("audit + machine-checked invariance").
- **Not proof that `IntegrityAccount`/`IntegrityKernel` (the real Phase I names) exist.** This is
  an experimental, disclosed-scope artifact validating specific architectural choices (atomic
  immutable kernel binding, mode restriction, hook-frame reentrancy guarding, snapshot-based
  conserved-quantity checking) — not a partial implementation of the production contracts.

## Verification summary

| Property | Test | Verified how |
|---|---|---|
| In-budget call succeeds | `test_inBudgetCallSucceedsAndCommits` | Real hook flow, real balance assertion |
| Over-per-op-budget reverts, no state change | `test_overPerOpBudgetCallRevertsBeforeAnyStateChange` | Balance unchanged + `armed` cleared after revert |
| Over-cumulative-budget reverts at the real boundary | `test_overCumulativeBudgetCallRevertsEvenWhenEachCallIsIndividuallyInBudget` | Exact-boundary case (succeeds) vs. one-wei-over (fails) |
| Batch/delegatecall/try modes rejected | 3 tests | Real `ERC7579Utils.encodeMode` values, real revert assertions |
| Module mutation permanently disabled | 2 tests | Attempted against a real, already-installed kernel |
| Hook cannot be spoofed or called out of sequence | 2 tests | Direct calls to `preCheck`/`postCheck` from non-account callers and without pairing |
| Reentrancy guard does real work | 1 test + mutation check | Genuine self-call reentrancy; guard removal changes the failure mode |
| `preCheck` gas within Table 4 budget | `test_preCheckGasIsWithinPaperTable4Budget` | Live `gasleft()` diff, regression-tested |
