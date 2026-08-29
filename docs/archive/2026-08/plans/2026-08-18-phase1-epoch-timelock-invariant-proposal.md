# Phase I epoch/timelock deployment invariant enforcement (scoping only)

**Status:** Implemented and landed (2026-08-19) — Option B, as recommended below, authorized by
the user after the two-option tradeoff was explained in plain language. Full writeup:
`PRODUCTION_GAPS.md` §37. `IntegrityAccountV1ExperimentalTest` suite: 101 → 105 tests. Full repo
suite: 310/310 → 314/314. Not committed, not deployed — same standing rule as every prior Phase I
slice. One significant discovery not anticipated below: the entire existing test suite's shared
fixture had deliberately used an invariant-violating account/kernel pair (to demonstrate the very
bug this proposal closes), which would have broken every single test once the constructor-time
check landed — resolved by making the shared fixture compliant and auditing every dependent
test, not by weakening the new check. This closes the sixth and final of the six items originally
scoped for this session's continuation of Phase I; only item 7 (external audit) remains, and it
is a gate, not buildable work. The rest of this document is preserved as written (the original
scoping) for the historical record.

## Why this slice

Both contracts' NatSpec independently state the same deployment invariant:
`epochLengthSeconds` (kernel) must be `>= moduleActionTimelockSeconds` (account), or a fully-
vested swap can revert `SnapshotStale` for a reason unrelated to reputation, and a freshly-
installed replacement kernel can be stale-on-arrival, rejecting the account's first post-swap
`execute()` call. Both contracts currently say, verbatim, that this is "a deploy-time discipline,
not a code-level guarantee." This is the smallest of the six items and the only one with no
guardian-authority dependency — independent of items 1/2/4's chain.

## The genesis-only trap — this proposal must not repeat it

A naive fix checks the invariant once, in the account's constructor, against the kernel passed in
at deploy time. **This is insufficient and must not be the shape of the real proposal.** The
account's constructor only ever sees the *genesis* kernel. The entire point of
`executeKernelSwap` is installing a *different* kernel later — a swapped-in kernel never passes
through the account's constructor, so a constructor-only check enforces the invariant exactly
once and leaves every subsequent kernel, including the one actually reached via the governance
path this repo has spent the most effort hardening (§29, §31), completely unchecked. The
constructor check is worth keeping (cheap, closes the genesis case), but it is not sufficient by
itself and the real proposal must say so rather than presenting it as complete.

## The real enforcement point, and its own fork to resolve

`proposeKernelSwap` already probes `newKernel.isModuleType(MODULE_TYPE_HOOK)` before committing to
the timelock — established precedent for "validate the incoming kernel before starting the
clock," and the natural place to add a second probe: call `newKernel.epochLengthSeconds()` (now
knowable to exist and be `public` on this codebase's own kernel implementation) and revert if it's
less than `moduleActionTimelockSeconds`.

This has a real fork the account's own constructor doesn't have to resolve, but `proposeKernelSwap`
does: **not every hook module has an `epochLengthSeconds()` function at all.** The `isModuleType`
probe only confirms ERC-7579 hook-module conformance, which says nothing about whether the
module uses epoch-snapshotting (this codebase's own `IntegrityKernelV1Experimental` does; a
future, simpler kernel — e.g. a budget-only adapter with no reputation check at all — legitimately
would not). Two options, both real, neither free:

**Option A — require the selector.** Any `newKernel` proposed for a swap must expose
`epochLengthSeconds()` (e.g. by requiring it implement a small marker interface,
`IEpochSnapshotting`, checked the same way `isModuleType` is checked). Simple, uniform, fully
closes the invariant for every kernel this mechanism can ever install. **Narrows what can ever be
swapped in** — a legitimate non-snapshotting kernel (budget-only, no reputation check) could never
be installed via `executeKernelSwap` again, even though nothing about such a kernel is unsafe.
This changes the account's own generality, not just this one check.

**Option B — try/catch probe, enforce only when present.** Attempt the
`epochLengthSeconds()` call inside a `try`/`catch`; if it reverts or the call target doesn't
implement the selector, skip the invariant check entirely for that `newKernel` (the invariant
simply doesn't apply to a kernel with no epoch concept). **Weaker** — a kernel that reverts on
that specific call for reasons unrelated to non-implementation (e.g. a transient revert condition)
would silently skip the check rather than fail closed, and there's no way to distinguish "doesn't
implement this" from "implements it but currently reverting" from inside a `try`/`catch` in
Solidity. Preserves full generality for non-snapshotting kernels.

**Recommendation for the real proposal to affirm or override:** Option B. The invariant exists to
protect deployments that specifically opt into epoch-snapshotting; it should not become a
generality tax on every future kernel this account can ever hold, especially given this account's
own stated design goal (a minimal, narrow, tracer-bullet slice, not a fixed final kernel set).
State the fail-open caveat plainly in the doc comment rather than letting it read as complete
type-level enforcement — this repo's own "no silent mocks" discipline applies to invariant checks
as much as to functional behavior.

## What this closes, and what it explicitly does not

Closes: the invariant becomes enforced at the one point where a new kernel with a genuinely
mismatched epoch could enter the account — `proposeKernelSwap` — in addition to the existing
genesis-only constructor path, for every kernel that opts into being checked (Option A) or that
implements the selector (Option B).

Does not close: this only prevents *installing* a mismatched pair going forward. It does nothing
for the account's own already-installed kernel — if the account was deployed before this check
existed, or the check is added to the account contract but the *existing* installed kernel already
violates the invariant, nothing retroactively fixes that; the only remedy remains a swap to a
compliant kernel, subject to the swap mechanism's own preconditions (including the very
`SnapshotStale` failure mode this invariant exists to prevent, if the swap-to-compliance itself
crosses a stale epoch — a real, disclosed bootstrapping edge case the proposal should name).

## Scope: in (for the real proposal, once authorized)

- Resolve Option A vs. Option B explicitly (recommend B).
- Constructor-time check for the genesis kernel (cheap, worth keeping even though insufficient
  alone).
- `proposeKernelSwap`-time check for every subsequent kernel, per the resolved option.
- Foundry tests: genesis kernel with `epochLengthSeconds < moduleActionTimelockSeconds` reverts at
  construction; a proposed swap to such a kernel reverts at `proposeKernelSwap`, not silently
  later at `SnapshotStale`; a proposed swap to a kernel with no `epochLengthSeconds()` at all
  succeeds under Option B (documenting the fail-open case as an explicit, asserted test outcome,
  not an accident); the existing `test_quorumGatheringCanStaleTheSnapshotBetweenApprovals`-style
  regression continues to pass unchanged (this proposal prevents *misconfigured* pairs, not the
  already-accepted, correctly-configured staleness window within a single epoch).
- Amend both contracts' NatSpec — the "deploy-time discipline, not a code-level guarantee" line
  becomes partially false once this lands and must be corrected precisely (still true for the
  Option-B fail-open case; no longer true for a kernel that does implement the selector).

## Scope: out

- Retroactive enforcement against an already-installed, already-violating kernel.
- Any change to `epochLengthSeconds`' own value or `MAX_EPOCH_LENGTH_SECONDS`.
- Guardian mechanisms (items 1/2/4) — fully independent of this proposal.

## Decision needed

1. **Authorize as scoped above (Option B recommended)** — independent, smallest, no dependency
   chain; could land before or after any of the guardian-authority items.
2. **Authorize with Option A instead** — accept the generality narrowing in exchange for a
   strictly stronger, fail-closed guarantee.
3. **Not yet** — stay at proposal stage.
