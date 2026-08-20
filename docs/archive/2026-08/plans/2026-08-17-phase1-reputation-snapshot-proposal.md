# Phase I reputation epoch-snapshotting — go/no-go proposal

**Status:** proposal only. Nothing here is authorized yet.

## What this is

Closes the real, disclosed finding from the third reference adapter: with all three `preCheck`
conditions live (budget, reputation floor, assurance tier), gas measures ~40,129 — over the
whitepaper's own Table 4 budget (`<=40k`). The Phase I plan named the cause before this slice
existed: *"a cold cross-contract SLOAD for `effectiveScore()` is ~2.6k on its own... reputation
should be cached/snapshotted per epoch rather than read live on every call."* This proposal builds
exactly that.

**This is a genuine fix, not another disclosed-and-accepted finding.** The first four pieces of
this slice each ended with "measured, documented, not resolved." This one is scoped specifically
to resolve the gas number for real — full-suite gas measurement is what closes or reopens it, not
prediction.

## Real research done before drafting this

Read `ReputationRegistry.sol` in full (not assumed) to answer the question that actually
determines the design: does `baseScore`/`zkBoostExpiry` change in a way that makes a naive
cache dangerous?

- **`baseScore` has no monotonicity guarantee at all.** `updateScore` (`ORACLE_ROLE`) can move it
  up or down, at any time, no bound. A cached score genuinely needs a refresh cadence — there is
  no shortcut that avoids re-reading it periodically.
- **`zkBoostExpiry` is set to `block.timestamp + reportingPeriod` on every successful
  `submitZkAttestation`**, with no explicit revocation path. In the common case this only ever
  moves forward (later expiry), which raised an idea worth naming and then rejecting: cache the
  *raw* `zkBoostExpiry` timestamp instead of a boolean, and re-derive `isZkBoosted` locally via
  `block.timestamp <= cachedExpiry` forever, no staleness window needed at all, since a stale-low
  cached expiry is merely a false rejection (availability issue), never a false grant (security
  issue). **Rejected**, because `reportingPeriod` itself is admin-mutable
  (`setReportingPeriod`, `DEFAULT_ADMIN_ROLE`) — an admin who shortens `reportingPeriod` and the
  agent then resubmits could produce a new real expiry *earlier* than a previously cached one,
  which flips the direction: a stale-high cached expiry could then grant assurance-tier status
  the real, current registry state no longer would. Narrow (requires an admin action, not
  attacker-controlled), but real, and it defeats the "raw expiry needs no refresh" claim. Both
  values get the same uniform snapshot-and-refresh treatment instead — simpler, one staleness
  story to reason about and test, not two.

## Mechanism

`IntegrityKernelV1Experimental` gains a cached snapshot and an epoch-length parameter:

```solidity
uint256 public immutable epochLengthSeconds;
uint256 public snapshotScore;
bool public snapshotIsZkBoosted;
uint256 public snapshotTakenAt;
```

**`refreshReputationSnapshot()` — permissionless, callable by anyone.** Reads
`reputationRegistry.scores(boundAccount)` **once** (the public struct getter — `baseScore`,
`lastUpdate`, `zkBoostExpiry` in a single external call), then derives both `snapshotScore`
(applying `ZK_BOOST_BPS`/`BPS_DENOMINATOR` locally, same math `effectiveScore` uses) and
`snapshotIsZkBoosted` from that one read, and sets `snapshotTakenAt = block.timestamp`. This is
actually *cheaper* than today's `preCheck` (one external call instead of two — `effectiveScore`
and `isZkBoosted` each currently cost their own call).

No access control: the function only ever pulls real data from the registry — there is no
caller-supplied value to manipulate, so anyone paying the gas to keep the account's snapshot
fresh (the agent itself, a keeper bot, a concerned third party) can, exactly like a Chainlink
Automation upkeep pattern. This decouples "who benefits from freshness" from "who has to pay for
it."

**`preCheck` reads the cache, and reverts (fail-closed) if it's stale**, rather than silently
using arbitrarily old data or (the rejected alternative below) auto-refreshing inline:

```solidity
if (block.timestamp > snapshotTakenAt + epochLengthSeconds) {
    revert SnapshotStale(snapshotTakenAt, block.timestamp, epochLengthSeconds);
}
if (snapshotScore < minEffectiveScore) revert ReputationBelowFloor(snapshotScore, minEffectiveScore);
if (!snapshotIsZkBoosted) revert AssuranceTierNotMet(boundAccount);
```

**Constructor takes the initial snapshot atomically** (calls the same internal refresh logic once
during deployment), so the first `preCheck` never has to special-case an empty snapshot — and
validates `epochLengthSeconds_ != 0` (`ZeroEpochLength()`), same input-validation discipline as
every other immutable this kernel already guards.

## Design alternative considered and rejected: auto-refresh inside `preCheck`

Instead of reverting on staleness and requiring a separate `refreshReputationSnapshot()` call,
`preCheck` could detect a stale snapshot and transparently refresh it inline, then proceed —
no separate transaction ever required, no liveness risk.

**Rejected as the primary design**, because it doesn't actually resolve the Table 4 finding this
proposal exists to close: the call that happens to land right after an epoch boundary would still
pay the full cross-contract read cost *inside* `preCheck`, still exceeding 40k on that call. It
would lower the *average* gas cost across many calls without ever making the *worst case*
conform to the whitepaper's stated ceiling — which is a softer, less honest claim than "resolved."

The explicit-refresh design's own new liveness risk is judged acceptable specifically because it's
mild relative to what it replaces: refresh is permissionless (not gated behind the account's
single signer, unlike the kernel-swap mechanism's analogous risk), costless to set up a keeper
against (a fixed, known `epochLengthSeconds` any operator can schedule around), and recoverable by
literally anyone, not just the account's own controller. This is a real, disclosed tradeoff —
trading a documented, mild, universally-recoverable liveness risk for an actual, verified,
worst-case gas number under budget — not a free resolution.

## Scope: in

- `refreshReputationSnapshot()`, `snapshotScore`/`snapshotIsZkBoosted`/`snapshotTakenAt` state,
  `epochLengthSeconds` immutable, `SnapshotStale`/`ZeroEpochLength` errors.
- `preCheck` reads the cache instead of live cross-contract calls; reverts fail-closed on
  staleness.
- Constructor takes the initial snapshot atomically; rejects a zero epoch length.
- Tests: staleness genuinely blocks calls that would otherwise pass (mutation-tested); the cache
  genuinely does NOT reflect a real reputation change until refreshed (proving it's a real cache,
  not accidentally still reading live state); refresh is callable by a stranger, not just the
  account; refresh after staleness restores normal operation, picking up real current state
  (including a real current *failure*, e.g. now-below-floor, not just clearing the stale flag);
  the initial constructor-time snapshot lets the very first `preCheck` succeed with zero prior
  refresh calls.
- Re-measure `preCheck` gas for the steady-state (post-refresh, within-epoch) path and update the
  existing over-budget regression test — this closes `PRODUCTION_GAPS.md`'s disclosed finding if
  the number lands under 40k, or documents an updated finding honestly if it doesn't. Measured,
  not assumed, either way.
- Separately measure `refreshReputationSnapshot()`'s own gas cost as its own regression test, so
  the "amortized, not eliminated" cost is visible, not hidden by only reporting the cheap path.

## Scope: out

- No change to `budget`/reputation-floor/assurance-tier threshold *values* — same checks, cached
  differently.
- No off-chain keeper infrastructure (scheduling `refreshReputationSnapshot()` calls) — this
  proposal only builds the on-chain mechanism a keeper would call.
- No change to `ReputationRegistry` itself (the `reportingPeriod`-mutability edge case above is
  named, not fixed — fixing it would mean constraining `setReportingPeriod`, a change to a
  different, already-deployed-pattern contract, out of scope here).
- No deployment. Foundry-test-only, same as the rest of this slice.

## Real risk worth naming explicitly

**The staleness window is a real, accepted gap, not a rounding error.** For up to
`epochLengthSeconds`, `preCheck` can pass using a snapshot that no longer matches the registry's
real current state — a real-time reputation drop below the floor, or a boost expiring, is not
caught until the next refresh. This is the direct, necessary cost of resolving the gas finding;
the proposal's job is to make the window's size an explicit, tunable parameter and prove (via a
dedicated test) that the gap is real and bounded, not to pretend it doesn't exist. Choosing
`epochLengthSeconds` is a real tradeoff (shorter = tighter security window but more refresh
overhead in practice; longer = cheaper in practice but a wider real-time drift) that this proposal
does not resolve — the tests will use a placeholder value and this should be revisited with a real
number before anything resembling production use.

## Devil's Advocate review and response (2026-08-17, same day)

A focused adversarial review (independent subagent, given the full diff, `ReputationRegistry.sol`,
the paired account's kernel-swap mechanism, the test suite, and this doc) ran before finalizing.
Confirmed empirically first: `preCheck` measures 33,321 gas in the steady state (down from
~40,129) — the fix genuinely works, not just in theory. Full findings below; summarized with what
changed in response.

**Top-line verdict: add code-level mitigations before treating this as closed** (two items),
**accept-and-document** the rest.

**Fixed in code:**
- **The constants-match test verified nothing about this kernel.** `ZK_BOOST_BPS`/
  `BPS_DENOMINATOR` are `private` on the kernel — the original test compared the REAL registry's
  values against two hardcoded literals in the test file, never touching the kernel at all. A
  future `ReputationRegistry` redeployment with different constants (plausible — the boost
  multiplier is a spec value, not fixed forever) would silently produce wrong cached scores
  forever, undetected. Fixed: the constructor now reads the real
  `reputationRegistry.ZK_BOOST_BPS()`/`BPS_DENOMINATOR()` once and reverts
  `BoostConstantsMismatch` on any divergence — verified at deploy time, not asserted in a test
  that can't reach the value it claims to check. Regression test:
  `test_constructorRevertsWhenBoostConstantsMismatchTheRegistry`, mutation-tested. Also added a
  genuine differential test, `test_refreshedSnapshotMatchesALiveEffectiveScoreRead`, asserting the
  cached value equals a live `effectiveScore()`/`isZkBoosted()` read at the same moment — this is
  what actually catches a rounding/boundary/order-of-operations divergence, which reading the
  registry source line-by-line (done during review) confirmed does NOT currently exist, but which
  nothing in the original test suite would have caught if it had.
- **`epochLengthSeconds` had no upper bound.** A deployment could set an unreasonably long epoch
  and truthfully claim "epoch-snapshotted reputation" while meaning, in practice, "never
  re-checked." Fixed: `MAX_EPOCH_LENGTH_SECONDS = 7 days`, enforced in the constructor
  (`EpochLengthTooLong`), mutation-tested.
- **No event emitted anywhere.** The entire safety story for the staleness window depends on
  someone (an off-chain keeper, the operator) noticing the snapshot is aging and refreshing it —
  but there was no cheap on-chain signal to react to. Fixed: `ReputationSnapshotRefreshed(score,
  zkBoosted, takenAt)`, emitted on every refresh (including the constructor's atomic initial
  snapshot), tested via `test_refreshReputationSnapshotEmitsEvent`.

**Disclosed more precisely, not code-fixed — real design tradeoffs, not oversights:**
- **Within an epoch, reputation is not "possibly a little stale" — it is completely unenforced.**
  The only thing bounding damage during the window is the budget check. Both the kernel's own doc
  comment and this doc are corrected to state this plainly rather than the softer "up to
  `epochLengthSeconds` old" framing used before review.
- **A compounding case the original tests didn't cover**, found by review: a boost that expires
  mid-epoch (real registry state) leaves BOTH `snapshotIsZkBoosted` AND the boosted (1.15x)
  `snapshotScore` stale-permissive simultaneously, not just one flag. Made into its own test,
  `test_withinEpochBoostExpiryIsNotReflectedUntilRefreshed`, rather than left as an inference from
  the score-staleness test alone.
- **A real, previously-undocumented interaction with kernel-swap governance.** If
  `moduleActionTimelockSeconds` (the account's swap timelock) exceeds `epochLengthSeconds` (this
  kernel's freshness window) — true of this test suite's own placeholder values (3 days vs. 1
  day) — a fully-vested swap's uninstall half can revert `SnapshotStale` for a reason unrelated to
  reputation, AND a freshly-installed replacement kernel can be stale-on-arrival, immediately
  rejecting the account's first post-swap `execute()` call. The test suite already patched around
  this with explicit refresh calls before landing this proposal, but review correctly flagged that
  framing it as merely "an extra step to remember" undersold it — a successfully-executed swap can
  silently hand the account a kernel that rejects its very first real call. This is now stated as
  an explicit **deployment invariant** (`epochLengthSeconds >= moduleActionTimelockSeconds`) in
  both contracts' NatSpec, not left implicit in test comments only. Neither contract enforces this
  across the other (they're constructed independently) — this is a deploy-time discipline, not a
  code-level guarantee, and is recorded here as a real, open gap.
- **Permissionless refresh's "no manipulation surface" claim was slightly too strong.** A caller
  can't manipulate WHAT gets cached (always real registry data), but CAN influence WHEN it gets
  pulled in — an adversary could force an early refresh that locks in a real-but-temporary
  reputation dip sooner than the operator wanted. This makes the kernel stricter, not exploited,
  but it's denial-by-accurate-data worth naming rather than the stronger original claim.
- **The rejected auto-refresh-inside-`preCheck` alternative's gas cost was asserted, not
  measured.** Review correctly flagged this as a lower evidentiary bar than the rest of this
  proposal holds itself to. The reasoning for rejecting it (the worst-case boundary call would
  still likely exceed budget, and it doesn't fully resolve the finding either way) stands, but the
  proposal should not have implied that number was confirmed by a test — it wasn't, and still
  isn't; the fail-closed design was chosen on structural grounds (bounding the worst case for
  real), not because the alternative was measured and found wanting.

**Test suite after these fixes:** `contracts/test/IntegrityAccountV1Experimental.t.sol` at 41
tests (up from the pre-review 37, +4 for the review-driven fixes and their regressions). Full
repo suite: 250/250 (up from 246 pre-review).

## Decision

Shipped after the review above and its code-level fixes, per this session's governance-review
discipline for security-relevant kernel changes. `epochLengthSeconds >= moduleActionTimelockSeconds`
remains an operator-enforced deployment invariant, not a code-level guarantee — flagged for
whoever eventually writes a real deployment script for this account/kernel pair.
