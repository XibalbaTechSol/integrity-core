# Phase I tracer-bullet slice — what it proves, precisely

Companion to `docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md` (the authorized scope) and
`docs/design/phase1-slice-dependency-inventory-2026-08-17.md` (the dependency research). This
note states the actual guarantee, in the same register as the whitepaper's own Proposition 1 —
no broader, no narrower.

**Update (2026-08-17, same day): extended with a second reference adapter**, per
`docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md` (separately authorized). The kernel
now enforces two conjunctive conditions, not one — see the updated guarantee statement below.

**Second update (2026-08-17, same day): extended with a third reference adapter (assurance
tier)**, per `docs/plans/2026-08-17-phase1-assurance-tier-adapter-proposal.md`, completing the
trio the original Phase I plan named. **This also produced a real, disclosed finding, not a
silently-resolved one**: with all three checks live, `preCheck` measures ~40,129 gas — over the
whitepaper's own Table 4 budget (`<=40k`). This is exactly the pressure point the Phase I plan
already anticipated before this slice existed ("reputation should be cached/snapshotted per
epoch rather than read live on every call") — confirmed live, not hypothetical. Per this session's
own standing commitment, the test asserting this was renamed to document the finding honestly
(`test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks`) rather than having its
threshold quietly raised to make it pass silently. See §"Known limitation" below.

## What exists

`contracts/src/kernel/IntegrityAccountV1Experimental.sol` and
`IntegrityKernelV1Experimental.sol`. **Not deployed anywhere** — Foundry-test-only. Not
upgradeable, not a proxy, not referenced by `Deploy.s.sol` or any deployment script. 17 passing
tests in `contracts/test/IntegrityAccountV1Experimental.t.sol`; full repo suite green at 226/226
(up from 209 before this slice, +12 for the first adapter, +3 for the reputation floor, +2 for
the assurance tier — a net +2 after also removing one redundant test the assurance-tier work made
unnecessary).

## The guarantee, precisely

**Proposition (slice-scoped).** For an `IntegrityAccountV1Experimental` instance with kernel `K`
bound at construction, budgets `(b_op, b_cum)`, a reputation registry `R`, a floor `s_min`, and an
assurance requirement: for every sequence of calls to `execute()` with mode `(CALLTYPE_SINGLE,
EXECTYPE_DEFAULT)`, accepted by the account's own `onlyEntryPointOrSelf` gate —
**(1)** the account's native-token balance decrease from any single call never exceeds `b_op`,
and the cumulative decrease across all such calls never exceeds `b_cum` (verified by
`test_overPerOpBudgetCallRevertsBeforeAnyStateChange` and
`test_overCumulativeBudgetCallRevertsEvenWhenEachCallIsIndividuallyInBudget`);
**(2)** no call proceeds at all while `R.effectiveScore(account) < s_min` (verified by
`test_belowFloorCallRevertsEvenThoughItWouldBeWithinBudget` and
`test_scoreExactlyAtTheFloorSucceeds`); **and (3)** no call proceeds at all while
`R.isZkBoosted(account)` is false (verified by
`test_nonBoostedAccountRevertsEvenWhenBudgetAndReputationBothPass` and
`test_expiredBoostIsTreatedAsNotBoosted`, the latter confirming this is a genuine
`block.timestamp`-based boundary, not a static flag). All three conditions are conjunctive and
mutually independent — `test_aboveFloorButOverBudgetCallStillRevertsOnBudget` confirms an
account passing reputation AND assurance is still bound by the budget check; none of the three
short-circuits any other.

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
- `preCheck` gas is a live regression test, not a one-off measurement, across all three checks'
  addition: 27,131 (budget only) → 35,505 (+ reputation) → ~40,129 (+ assurance tier) — the last
  crossing the whitepaper's Table 4 budget for real. See "Known limitation" below; this is
  disclosed, not hidden.
- The reputation floor is a real gate, not decoration — same mutation-testing discipline as the
  `armed` guard: removing the check makes `test_belowFloorCallRevertsEvenThoughItWouldBeWithinBudget`
  fail (the call wrongly succeeds), confirmed and reverted before landing.
- The assurance-tier check is a real gate, not decoration — same mutation-testing discipline:
  removing it makes both `test_nonBoostedAccountRevertsEvenWhenBudgetAndReputationBothPass` and
  `test_expiredBoostIsTreatedAsNotBoosted` wrongly pass, confirmed and reverted before landing.

## Known limitation: `preCheck` exceeds the Table 4 gas budget with all three checks live

Measured directly, not estimated: ~40,129 gas with the budget, reputation-floor, and
assurance-tier checks all live — over the whitepaper's own `<=40k` `preCheck` ceiling
(`test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks`, which asserts the cost is
both genuinely over 40k *and* hasn't regressed past a documented 42k ceiling — a two-sided
assertion specifically so this finding stays visible rather than silently resolving itself or
silently getting worse). This is not a surprise: the Phase I plan named the cause before this
slice was built — "a cold cross-contract SLOAD for `effectiveScore()` is ~2.6k on its own...
reputation should be cached/snapshotted per epoch rather than read live on every call." Each
adapter this slice added makes an independent, uncached cross-contract-adjacent read to
`ReputationRegistry`; the real fix is the per-epoch snapshotting the plan already anticipated,
which is out of scope for a reference-adapter slice and would need its own proposal. Per this
session's standing commitment (stated in the assurance-tier proposal before this was even
measured): the response to crossing budget is reporting it, not quietly raising the number.

## What this does NOT prove — read this list as seriously as the guarantee above

- **Not general value conservation.** Only native ETH is tracked. Any ERC-20/ERC-721/other
  asset movement inside the wrapped call is completely unconstrained by this kernel.
- **Does not reason about how `effectiveScore`/`isZkBoosted` were computed, or whether the
  oracle/attestation pipeline behind them is honest.** Both adapters trust `ReputationRegistry`
  exactly as far as that contract's own oracle-signer and `submitZkAttestation` trust model goes
  — no more, no less. Neither touches, and both are fully independent of, the still-deferred AIS
  floor/shadow-gate decision (`PRODUCTION_GAPS.md` §27).
- **Does not meet the whitepaper's own Table 4 `preCheck` gas budget** with all three checks
  live — see "Known limitation" above. A real, measured, disclosed finding, not resolved by this
  slice.
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
| `preCheck` gas (documents the over-budget finding) | `test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks` | Live `gasleft()` diff, two-sided regression bound (>=40k and <42k) |
| Below-floor call reverts even if in-budget | `test_belowFloorCallRevertsEvenThoughItWouldBeWithinBudget` | Real `ReputationRegistry` clone, real pushed score, boost-adjusted math |
| Score exactly at the floor succeeds | `test_scoreExactlyAtTheFloorSucceeds` | Boundary case, matching the budget check's own boundary discipline |
| All three checks are mutually independent | `test_aboveFloorButOverBudgetCallStillRevertsOnBudget` | Above-floor, boosted account still bound by the budget check |
| Reputation floor does real work | mutation check | Removing the check makes the below-floor test wrongly pass |
| Non-boosted account reverts even when budget+reputation pass | `test_nonBoostedAccountRevertsEvenWhenBudgetAndReputationBothPass` | `stdStorage`-set `zkBoostExpiry`, real `isZkBoosted` read |
| Expired boost treated as not-boosted | `test_expiredBoostIsTreatedAsNotBoosted` | Real `block.timestamp`-based boundary, not a static flag |
| Assurance-tier check does real work | mutation check | Removing the check makes both assurance-tier tests wrongly pass |
