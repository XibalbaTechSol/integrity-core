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

**Third update (2026-08-17, same day): module mutation is now reachable, reversing a claim this
doc previously made.** Per `docs/plans/2026-08-17-phase1-module-governance-proposal.md` (which
states the reversal plainly — read it before trusting any "unreachable" language elsewhere in
this doc that hasn't been updated), the account now exposes a timelocked, atomic kernel-swap path
(`proposeKernelSwap`/`executeKernelSwap`/`cancelKernelSwap`). `installModule`/`uninstallModule`
themselves still always revert — the new path reaches the same underlying internals through a
different, constrained route. This is **single-signer-timelocked, not the plan's full
"timelocked + multi-party"** requirement. The guarantee statement and "What this does NOT prove"
section below are updated accordingly; anywhere else in the repo that still says "module mutation
is permanently unreachable" for this slice is now stale and should be corrected against this
update, not trusted as current.

## What exists

`contracts/src/kernel/IntegrityAccountV1Experimental.sol` and
`IntegrityKernelV1Experimental.sol`. **Not deployed anywhere** — Foundry-test-only. Not
upgradeable, not a proxy, not referenced by `Deploy.s.sol` or any deployment script. 41 passing
tests in `contracts/test/IntegrityAccountV1Experimental.t.sol` (up from 17: +10 for the
module-governance kernel-swap mechanism, +4 from that mechanism's own Devil's Advocate review, +6
for reputation epoch-snapshotting, +4 from ITS Devil's Advocate review — see
`docs/plans/2026-08-17-phase1-module-governance-proposal.md` and
`docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md`'s respective "Devil's Advocate
review and response" sections); full repo suite green at 250/250 (up from 209 before this slice
began: +12 for the first adapter, +3 for the reputation floor, +2 for the assurance tier net of
one removed redundant test, +10 for module governance, +4 for its review's fixes, +6 for
epoch-snapshotting, +4 for its review's fixes).

## The guarantee, precisely

**Proposition (slice-scoped).** For an `IntegrityAccountV1Experimental` instance with kernel `K`
bound at construction, budgets `(b_op, b_cum)`, a reputation registry `R`, a floor `s_min`, and an
assurance requirement: for every sequence of calls to `execute()` with mode `(CALLTYPE_SINGLE,
EXECTYPE_DEFAULT)`, accepted by the account's own `onlyEntryPointOrSelf` gate —
**(1)** the account's native-token balance decrease from any single call never exceeds `b_op`,
and the cumulative decrease across all such calls never exceeds `b_cum` (verified by
`test_overPerOpBudgetCallRevertsBeforeAnyStateChange` and
`test_overCumulativeBudgetCallRevertsEvenWhenEachCallIsIndividuallyInBudget`);
**(2)** no call proceeds at all while a CACHED snapshot of `R.effectiveScore(account) < s_min`
(verified by `test_belowFloorCallRevertsEvenThoughItWouldBeWithinBudget` and
`test_scoreExactlyAtTheFloorSucceeds` — as of the epoch-snapshotting update below, both now
include an explicit `refreshReputationSnapshot()` call so they exercise current, not stale,
state); **and (3)** no call proceeds at all while a CACHED `R.isZkBoosted(account)` is false
(verified by `test_nonBoostedAccountRevertsEvenWhenBudgetAndReputationBothPass` and
`test_expiredBoostIsTreatedAsNotBoosted`, the latter confirming this is a genuine
`block.timestamp`-based boundary, not a static flag). **The snapshot itself is at most
`epochLengthSeconds` old, or the call reverts (`SnapshotStale`) rather than using stale data** —
see "RESOLVED" below for what this cache-instead-of-live-read change actually trades away. All
three conditions are conjunctive and mutually independent — `test_aboveFloorButOverBudgetCallStillRevertsOnBudget`
confirms an account passing reputation AND assurance is still bound by the budget check; none of
the three short-circuits any other.

**What makes this hold, verified rather than assumed:**
- The hook fires on every reachable execution path — verified by proving the other three
  ERC-7579 dispatch combinations are rejected before reaching the base class's execution logic
  (`test_batchExecutionModeIsRejected`, `test_delegatecallExecutionModeIsRejected`,
  `test_tryExecTypeIsRejectedEvenWithSingleCalltype`), and that no second execution path can ever
  be opened via a direct call (`test_moduleInstallIsUnconditionallyDisabled`,
  `test_moduleUninstallIsUnconditionallyDisabled` — the latter tried against the real, already-
  installed kernel specifically, not a hypothetical module). The direct `installModule`/
  `uninstallModule` functions remain disabled unconditionally; module mutation is reachable only
  through the separate, timelocked kernel-swap path (see "Not complete mediation" below) — a
  deliberate reversal of this doc's original claim that mutation was unreachable entirely.
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

## RESOLVED: `preCheck` now measures under the Table 4 gas budget

**Update (2026-08-17, same day): resolved, not just disclosed.** The Table 4 finding below was
real and stood for several hours of this same session before being closed for real by
`docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md`: `IntegrityKernelV1Experimental`
now caches `effectiveScore`/`isZkBoosted` locally (`refreshReputationSnapshot()`, permissionless)
instead of reading them live, and `preCheck` reads the cache. Measured directly, not estimated:
**33,321 gas** in the steady state (post-refresh, within-epoch) — under the whitepaper's `<=40k`
ceiling for real (`test_preCheckGasIsUnderPaperTable4BudgetWithCachedReputation`, which supersedes
the old over-budget test below).

**This is a genuine trade, not a free resolution — read this as seriously as the win above.**
`preCheck` fails closed (`SnapshotStale`) if the cache is older than an immutable
`epochLengthSeconds` (capped at 7 days, `MAX_EPOCH_LENGTH_SECONDS`) — so for up to
`epochLengthSeconds`, reputation is not "possibly a little stale," it is **completely
unenforced**; only the budget check still bounds damage during that window. The design also
introduces a new liveness dependency the live-read design never had: `execute()` can now revert
purely because nobody called `refreshReputationSnapshot()` in time, for ANY call, not only
governance actions. And it creates a genuine, disclosed interaction with the kernel-swap
mechanism above: if `moduleActionTimelockSeconds` exceeds `epochLengthSeconds` (true of this
slice's own test values — 3 days vs. 1 day), a fully-vested swap can revert `SnapshotStale` for a
reason unrelated to reputation, and a freshly-installed kernel can be stale-on-arrival, rejecting
the account's first post-swap call. Both contracts' NatSpec now state
`epochLengthSeconds >= moduleActionTimelockSeconds` as an explicit deployment invariant neither
contract enforces on its own. Full detail, including a Devil's Advocate review's findings and
code-level fixes (a constant-drift hole that a hollow test had been silently not catching, a
missing event, an unbounded epoch length): the proposal doc's "Devil's Advocate review and
response" section.

### Original finding (superseded above, kept for the record)

Measured directly, not estimated: ~40,129 gas with the budget, reputation-floor, and
assurance-tier checks all live — over the whitepaper's own `<=40k` `preCheck` ceiling
(previously `test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks`, since replaced).
This was not a surprise: the Phase I plan named the cause before this slice was built — "a cold
cross-contract SLOAD for `effectiveScore()` is ~2.6k on its own... reputation should be
cached/snapshotted per epoch rather than read live on every call." Each adapter this slice added
made an independent, uncached cross-contract-adjacent read to `ReputationRegistry`; the fix was
exactly the per-epoch snapshotting the plan anticipated. Per this session's standing commitment
(stated in the assurance-tier proposal before this was even measured): the response to crossing
budget was reporting it first, not quietly raising the number — and then, once scoped as its own
piece of work, actually closing it.

## What this does NOT prove — read this list as seriously as the guarantee above

- **Not general value conservation.** Only native ETH is tracked. Any ERC-20/ERC-721/other
  asset movement inside the wrapped call is completely unconstrained by this kernel.
- **Does not reason about how `effectiveScore`/`isZkBoosted` were computed, or whether the
  oracle/attestation pipeline behind them is honest.** Both adapters trust `ReputationRegistry`
  exactly as far as that contract's own oracle-signer and `submitZkAttestation` trust model goes
  — no more, no less. Neither touches, and both are fully independent of, the still-deferred AIS
  floor/shadow-gate decision (`PRODUCTION_GAPS.md` §27).
- **Now meets the whitepaper's own Table 4 `preCheck` gas budget (33,321 measured), but only by
  trading it for a real, disclosed staleness/liveness dependency** — see "RESOLVED" above.
  Reputation and assurance-tier checks are no longer live; they can lag real registry state by up
  to `epochLengthSeconds`, during which only the budget check still bounds behavior, and
  `execute()` can revert purely because nobody refreshed the cache in time. Read the "RESOLVED"
  section's tradeoffs, not just its headline number.
- **Not calldata-content-aware.** The kernel never inspects what the wrapped call actually does
  beyond the resulting native-balance delta — a call that moves zero ETH but does anything else
  (approves a token, calls an arbitrary contract, self-destructs a target) is unconstrained.
- **Closer to, but still short of, complete mediation in the whitepaper's full sense.**
  Condition (iii) — module install/removal must itself be a constrained transition — is now
  satisfied by a timelocked, atomic kernel-swap path (`proposeKernelSwap`/`executeKernelSwap`/
  `cancelKernelSwap`, per `docs/plans/2026-08-17-phase1-module-governance-proposal.md`), not by
  making mutation unreachable. This is still a materially weaker property than the plan's full
  "timelocked + multi-party" requirement: this account has exactly one ECDSA signer, so a
  compromised signing key can still eventually force a kernel swap, just not instantly, and not
  silently (the timelock window is observable). The swap is asymmetrically mediated — verified,
  not assumed, by `test_executeKernelSwapUninstallHalfIsMediatedByOldKernel` and
  `test_executeKernelSwapInstallHalfIsUnmediated` — removal of the outgoing kernel is genuinely
  content-gated (reputation floor + assurance tier), while installation of the new kernel is
  gated only by a superficial `isModuleType` interface probe and elapsed time, never by a check
  with security content. Two distinct lockout classes follow from this, not one: an account below
  the outgoing kernel's floor/tier is temporarily locked out but can requalify and retry; a
  SEPARATE, more severe class has no recovery path at all — a kernel that passes the interface
  probe but reverts unconditionally in `preCheck` bricks `execute()` permanently AND blocks every
  rescue swap too (the rescue's own uninstall half must call the broken kernel's `preCheck`
  first). This second class was found by a Devil's Advocate review and is now a permanent
  regression fixture, not just a documented claim:
  `test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath`. A genuinely multi-party
  version of this mechanism remains unbuilt and is separate, larger scope. Full review findings
  and code-level response: `docs/plans/2026-08-17-phase1-module-governance-proposal.md`.
  **Fourth update (2026-08-18/19): the multi-party gap just named is now closed for swap
  *execution*, not for the hook-mediation guarantee itself — a second reversal, not a silent
  one.** Per `docs/plans/2026-08-18-phase1-multiparty-kernel-governance-proposal.md`,
  `executeKernelSwap` now additionally requires `guardianThreshold`-of-`N` independent guardian
  approvals (an immutable set fixed at construction, no rotation) before it will proceed — a
  compromised signer can still *propose* and start the timelock, but can no longer *execute*
  alone. This closes exactly the gap the third update above named ("a compromised signing key can
  still eventually force a kernel swap"), not the account's day-to-day `execute()` authority,
  which remains single-signer by design. It does NOT close unilateral swap *denial* (the signer
  can still park an unwanted proposal forever by never cancelling) — see the proposal doc's "What
  this does NOT prove" for the full disclosure list, including the newly-introduced
  quorum-vs-epoch-staleness interaction (guardian approval-gathering takes real elapsed time,
  which can itself exhaust the outgoing kernel's `epochLengthSeconds` even from a snapshot fresh
  at the moment gathering began — regression-tested by
  `test_quorumGatheringCanStaleTheSnapshotBetweenApprovals`). **This slice ALSO breaks the "hook
  fires on every reachable execution path" claim above a second time, the same way the swap's own
  install/uninstall asymmetry broke it once already**: the new `approveKernelSwap` entry point is
  guardian-callable directly, deliberately NOT routed through `execute()`/`withHook` (gating a
  guardian's approval behind the account's own hook would be circular — the guardian exists
  precisely to act when the account may be compromised or non-conformant). Proven empirically, not
  just asserted, by `test_approveKernelSwapIsNotMediatedByTheInstalledHook`, which installs a
  kernel that reverts unconditionally in `preCheck` and shows guardian approvals still succeed.
  So as of this update there are two permanent, disclosed exceptions to "the hook mediates
  everything": the swap's install half (unmediated by either kernel) and `approveKernelSwap`
  (unmediated by any hook at all). 14 new Foundry tests for this extension (9 scope-enumerated
  guardian-quorum tests, 4 constructor edge cases, 1 proving what a reentrant call during
  `onInstall`/`onUninstall` observes of quorum state — full findings and mutation-testing detail:
  `PRODUCTION_GAPS.md` §31). File suite: 41 → 55 (up from 17 before the module-governance
  extension). Full repo suite: 264/264 (up from 250). Foundry-test-only, not deployed, same as
  every prior slice.
  **Fifth update (2026-08-18): the denial gap the fourth update named ("the signer can still park
  an unwanted proposal forever by never cancelling") is now closed, both forms of it, not just the
  narrower one.** Per `docs/plans/2026-08-18-phase1-guardian-swap-denial-proposal.md` (Option B,
  user-selected after the tradeoff was explained in plain terms), a new
  `guardianProposeAction`/`approveGuardianAction`/`executeGuardianAction` triple lets guardians act
  with ZERO signer involvement at all — closing both the narrow case (signer proposes, refuses to
  cancel) and the wider one the fourth update didn't fully name (signer never proposes anything at
  all, e.g. a lost key, leaving guardians nothing to act on even at full consensus). Gated by
  UNANIMOUS approval (all of `_guardians`, not `guardianThreshold`) — deliberately the highest bar
  in the contract, since this is the only path that requires no signer cooperation whatsoever. A
  real gap was found and fixed during implementation, not assumed away: a guardian-force-proposed
  swap still has to clear the pre-existing `executeKernelSwap`, which was signer-only
  (`onlyEntryPointOrSelf`) — an absent signer could never call it, stalling the rescue at the last
  step regardless of guardian consensus. Fixed, with explicit user sign-off on the tradeoff:
  `executeKernelSwap` now additionally accepts any single guardian as caller, without changing any
  of its four existing preconditions (proven, not assumed, by
  `test_executeKernelSwapCallableByGuardian_StillEnforcesExecutionQuorum` and
  `test_executeKernelSwapRevertsForUnrelatedCaller_EvenAtFullQuorum`). **This slice adds a THIRD
  permanent, disclosed exception to "the hook mediates everything"** — `guardianProposeAction`/
  `approveGuardianAction`/`executeGuardianAction` are guardian-callable directly, never routed
  through `execute()`/`withHook`, same reasoning as `approveKernelSwap`'s own exception above. Does
  NOT close guardian collusion/compromise at unanimity, guardian-set rotation (tracked separately,
  `docs/plans/2026-08-18-phase1-guardian-rotation-proposal.md` — losing even one guardian now
  raises TWO bars toward impossible, not one), or the broken-kernel brick scenario (a
  force-proposed swap's uninstall half still calls the outgoing kernel's `preCheck`; see
  `docs/plans/2026-08-18-phase1-broken-kernel-rescue-proposal.md`). Full findings, gas
  measurements, and the mutation-testing pass on all three new/changed guards: `PRODUCTION_GAPS.md`
  §32. File suite: 55 → 71 tests. Full repo suite: 280/280 (up from 264). Foundry-test-only, not
  deployed, same as every prior slice.
  **Sixth update (2026-08-18): guardian-set rotation, closing the gap the fifth update named.**
  Per `docs/plans/2026-08-18-phase1-guardian-rotation-proposal.md`,
  `proposeGuardianRotation`/`approveGuardianRotation`/`executeGuardianRotation` let the CURRENT
  guardians add or remove one guardian at a time (never both at once), gated by UNANIMOUS
  approval. Two decisions, explained in plain language before being asked: `guardianThreshold`
  itself is never rotatable (immutable forever, closing off "vote the bar down" as an attack
  surface); rotation requires unanimity, not the ordinary `guardianThreshold`. At most one
  guardian-relevant governance process may be in flight at a time — rotation is blocked while a
  kernel swap or guardian action is pending, and neither of those may be proposed while a rotation
  is pending, enforced symmetrically and proven in both directions. **A real, previously-
  undiscovered liveness bug in the fifth update's own mechanism was found while writing this
  slice's tests and fixed, not left broken:** `executeGuardianAction` deleted its pending-action
  state and only afterward checked whether the action could proceed, but a Solidity revert undoes
  every state change made earlier in the same call — so a legitimate signer action (e.g.
  cancelling a swap guardians were separately, unanimously already agreeing to force-cancel) could
  leave `pendingGuardianAction` permanently stuck, blocking every future
  `guardianProposeAction`/`proposeGuardianRotation` call from an entirely ordinary race, not an
  attack. Fixed with two small permissionless functions, `cancelPendingGuardianAction()` (the
  actual fix) and `cancelPendingGuardianRotation()` (added for parity). The exact bug scenario is
  now a permanent regression fixture, not just a documented claim. Mutation-tested three new
  guards, all caught. Full findings and gas measurements: `PRODUCTION_GAPS.md` §33. File suite:
  71 → 86 tests. Full repo suite: 295/295 (up from 280). Foundry-test-only, not deployed, same as
  every prior slice.
  **Seventh update (2026-08-18): the reentrant-call half of the "reentrancy window during the
  swap" risk named in this doc's own earlier update is now closed, and a real imprecision in how
  that risk was described is corrected, not silently carried forward.** Per
  `docs/plans/2026-08-18-phase1-swap-reentrancy-guard-proposal.md`, a new `swapInProgress` flag
  makes both `_execute` and a newly-added `_fallback` override revert unconditionally
  (`ReentrantDuringSwap`) for the duration of `executeKernelSwap`'s uninstall/install pair. The
  correction: this doc and the account's own NatSpec previously described the risk as "a hostile
  `newKernel.onInstall` that reenters `execute()`" -- imprecise, since `execute()` is
  `onlyEntryPointOrSelf`-gated and a kernel's callback caller-identity is its own address, never
  `self` or the entry point, so it could never reach `execute()` directly. The actually-reachable
  path is `fallback()`, which carries no access restriction at all. Honestly disclosed rather than
  overstated: in this account's CURRENT configuration (no fallback-handler module ever installed),
  a reentrant fallback call fails closed either way -- the guard's effect is proven by the revert
  REASON changing (`ReentrantDuringSwap` vs. `ERC7579MissingFallbackHandler`), which shows a
  hostile kernel's own `preCheck` genuinely runs, self-mediated, before the unguarded call
  eventually fails for an unrelated reason -- so this is real, forward-looking hardening for the
  moment this account (or a descendant) ever legitimately installs a fallback handler, not a fix
  for damage reachable today. Deliberately does NOT reorder or reimplement OZ's own
  `_installModule`/`_uninstallModule` (the proposal's rejected, more expensive Shape A). Mutation-
  tested: removing the `_fallback` guard changes the observed revert selector, caught by both new
  tests, restored after confirming detection. Full findings: `PRODUCTION_GAPS.md` §34. File suite:
  86 → 88 tests. Full repo suite: 297/297 (up from 295). Foundry-test-only, not deployed, same as
  every prior slice.
  **Eighth update (2026-08-18): a true kernel-swap rescue for the broken-kernel brick scenario is
  ARCHITECTURALLY IMPOSSIBLE at this layer -- investigated and disclosed before writing any code,
  not discovered partway through.** `AccountERC7579Hooked`'s `_hook` storage is `private`, and its
  only two mutation paths (`_installModule`/`_uninstallModule`) are unconditionally `withHook`-
  wrapped in their own bodies -- no subclass override point can clear `_hook` without asking
  whatever is currently installed for permission first. A true rescue would require forking
  `AccountERC7579Hooked` itself, the same class of undertaking the seventh update's Shape A
  explicitly rejected at much smaller scale -- not pursued here either, per user decision after
  the wall was explained plainly. **Built instead, with the user's fully-informed sign-off:** a
  guardian-unanimous emergency funds-recovery SWEEP (`proposeGuardianRescueSweep`/
  `approveGuardianRescueSweep`/`executeGuardianRescueSweep`), a raw value transfer that never
  touches `_hook`/`execute()`/`withHook` at all -- sidesteps the wall rather than defeating it. The
  account itself is never repaired; this recovers funds, proven against the exact scenario the
  normal rescue-swap machinery cannot save
  (`test_guardianRescueSweep_RecoversFundsFromAPermanentlyBrickedAccount`, which installs a real
  always-reverting kernel, confirms the normal rescue path still fails, then confirms the sweep
  succeeds and the account remains bricked afterward). Two real decisions the user made explicitly
  after plain-language explanation, not defaulted: (1) a separate, independently configurable
  `rescueTimelockSeconds`, deliberately allowed to be ZERO -- unlike every other timelock in this
  contract -- because different deployments may have different risk tolerances and a delay costs
  nothing operationally once an account is already bricked; (2) the sweep's severity was surfaced
  explicitly before authorization -- since no on-chain check can distinguish "permanently broken"
  from "reverted recently," this is a general guardian-unanimous power to drain the account's
  ENTIRE balance at ANY time, not only during genuine emergencies, the first guardian mechanism in
  this contract to directly move value rather than only govern. Mutation-tested three guards
  (unanimity, timelock, exceeds-balance), all caught and restored. Full findings and gas
  measurements: `PRODUCTION_GAPS.md` §35. File suite: 88 → 101 tests. Full repo suite: 310/310 (up
  from 297). Foundry-test-only, not deployed, same as every prior slice.
  **Ninth update (2026-08-19): the epoch/timelock deployment invariant both this account and the
  kernel documented but neither enforced is now code-level, Option B (fail-open for kernels with
  no epoch concept).** `_checkEpochCompatibility` (`try`/`catch` probe of `newKernel.
  epochLengthSeconds()`) is called from the constructor and both kernel-swap-proposal paths
  (`proposeKernelSwap`, `guardianProposeAction`'s force-propose branch), reverting
  `EpochTooShortForTimelock` when the kernel implements the selector and its epoch is shorter
  than `moduleActionTimelockSeconds` -- silently skipped, not failed closed, for a kernel that
  doesn't implement it at all (the user's explicit choice between two real options, matching the
  proposal's own recommendation). **A significant mid-implementation discovery:** the entire
  101-test suite's shared fixture had deliberately used the exact invariant-violating pair
  (3-day timelock, 1-day epoch) this feature rejects, since several tests used that mismatch to
  demonstrate the pre-existing bug motivating this proposal -- fixed by raising the shared epoch
  constant to match the timelock (compliant pair) and auditing every dependent test's now-
  redundant `refreshReputationSnapshot()` calls and comments, verified empirically (removed and
  re-added, not just hand-reasoned) rather than assumed safe. Zero existing test behavior
  weakened; all 101 pass unchanged. New: `NonSnapshottingKernel` fixture + 4 tests (genesis
  revert, propose revert via both paths, and a full fail-open round trip proven end-to-end, not
  just at the constructor). Mutation-tested (neutralized the comparison, all three revert tests
  failed distinctly, restored). Full findings: `PRODUCTION_GAPS.md` §37. File suite: 101 → 105
  tests. Full repo suite: 310/310 → 314/314. Foundry-test-only, not deployed. **This closes the
  sixth and final of the six items scoped for this slice's continuation** -- item 7 (external
  audit) remains a gate, not buildable work.
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
| Direct `installModule`/`uninstallModule` remain unconditionally disabled | `test_moduleInstallIsUnconditionallyDisabled`, `test_moduleUninstallIsUnconditionallyDisabled` | Attempted against a real, already-installed kernel |
| Kernel swap succeeds after the timelock and leaves the account functional | `test_kernelSwapSucceedsAfterTimelockElapsesAndInstallsTheNewKernel` | Real `hook()` readback + a genuine post-swap `execute()` |
| Swap rejects: no pending swap, already pending, parameter mismatch, premature execution | 4 tests | Real revert-selector assertions against each error |
| Cancel fully clears the pending slot, not just marks it cancelled | `test_cancelKernelSwapThenReproposeSucceeds` | Re-propose immediately after cancel succeeds and lands |
| Timelock does real work | mutation check | Removing `block.timestamp < readyAt` makes the premature-execution test wrongly pass (instant swap) |
| Swap's uninstall half is genuinely mediated by the outgoing kernel | `test_executeKernelSwapUninstallHalfIsMediatedByOldKernel` | Real reputation drop after propose, before execute, blocks the swap |
| Swap's install half is genuinely unmediated (nothing to mediate against, not a bypass) | `test_executeKernelSwapInstallHalfIsUnmediated` | New kernel with an unreachable floor still installs; only the next real `execute()` correctly rejects |
| Zero timelock is rejected at construction | `test_constructorRevertsOnZeroTimelock` | Mutation-tested: removing the check makes it instead fail with the kernel's `Unauthorized` further downstream |
| Non-conforming `newKernel` is rejected at propose time, not after the delay | `test_proposeKernelSwapRevertsOnNonConformingKernel` | Mutation-tested against a real contract whose `isModuleType` returns `false` |
| Only self/EntryPoint can propose, cancel, or execute a swap | `test_governanceFunctionsRevertForNonSelfNonEntryPointCaller` | Real revert-selector assertions against a stranger address for all three functions |
| A `preCheck`-reverting kernel permanently bricks `execute()` and blocks every rescue swap | `test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath` | Real adversarial fixture kernel; asserts both the brick and the failed rescue attempt |
| `preCheck` gas is under the Table 4 budget with cached reputation | `test_preCheckGasIsUnderPaperTable4BudgetWithCachedReputation` | Live `gasleft()` diff, two-sided regression bound (>30k and <40k) |
| Stale snapshot reverts even when real reputation would pass | `test_staleSnapshotRevertsEvenWhenRealReputationWouldPass` | Mutation-tested: removing the staleness check makes it wrongly pass |
| A real reputation change is invisible until refreshed (within-epoch) | `test_withinEpochPreCheckDoesNotReflectARealReputationChangeUntilRefreshed` | Real registry mutation, no refresh, call still succeeds on stale data |
| A boost that expires mid-epoch stays stale-permissive on BOTH the tier flag and the boosted score | `test_withinEpochBoostExpiryIsNotReflectedUntilRefreshed` | Real `zkBoostExpiry` mutation past its deadline, cache still reports boosted |
| Refresh is genuinely permissionless and restores operation after staleness | `test_refreshBySomeoneOtherThanTheAccountRestoresOperationAfterStaleness` | A stranger address calls refresh; subsequent execute() succeeds |
| Refresh emits an observable event | `test_refreshReputationSnapshotEmitsEvent` | `vm.expectEmit` against real emitted values |
| Zero and over-long epoch lengths are rejected at construction | `test_constructorRevertsOnZeroEpochLength`, `test_constructorRevertsOnEpochLengthTooLong` | Both mutation-tested |
| Local boost-math constants are verified against the real registry at deploy time, not just asserted in a test | `test_constructorRevertsWhenBoostConstantsMismatchTheRegistry` | Real fixture registry with different constants; mutation-tested |
| Cached score/boost genuinely match a live read | `test_refreshedSnapshotMatchesALiveEffectiveScoreRead` | Differential test against `reputation.effectiveScore`/`isZkBoosted` directly |
