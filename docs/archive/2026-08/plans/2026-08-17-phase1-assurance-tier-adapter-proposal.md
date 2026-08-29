# Phase I third reference adapter (assurance tier) — go/no-go proposal

**Status:** proposal only. Nothing here is authorized. Same incremental-extension pattern as the
reputation-floor adapter (`docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md`), which
this proposal is deliberately kept consistent with.

## What this is

Completes the trio of reference adapters the original Phase I plan named: "start with three that
exercise real integrity-core state: a spend/velocity cap, a reputation floor..., and an
assurance-tier check (reads `isZkBoosted`)." The first two are built. This adds the third: a
requirement that the bound account hold a live, on-chain-verified ZK attestation
(`ReputationRegistry.isZkBoosted`) before any execution proceeds.

**No new external dependency.** `isZkBoosted(address agent) external view returns (bool)` lives
on the exact same `ReputationRegistry` contract the reputation-floor adapter already reads —
confirmed directly in `contracts/src/oracle/ReputationRegistry.sol`. The kernel's existing
`reputationRegistry` immutable is reused as-is; nothing new to wire in, verify, or trust.

## Mechanism

A third conjunctive `preCheck` condition, same pattern as the reputation floor (a precondition
gate, not a conserved quantity — ZK-boost state can't change mid-call in a way `postCheck` would
need to re-verify): revert unless `reputationRegistry.isZkBoosted(boundAccount) == true`.

**Deliberately made unconditional, not toggleable**, for consistency with the two checks already
built (both are always-on, no opt-out flag) — introducing a configuration toggle here would be a
different kind of change (a new class of "what if disabled" surface) than "add the third named
adapter," and isn't asked for. If a future need for optional/configurable adapters emerges,
that's separate scope with its own proposal.

## Scope: in

- One new `preCheck` read + revert: `isZkBoosted(boundAccount)` must be `true`.
- No new constructor params beyond nothing — reuses the existing `reputationRegistry` immutable.
- Tests: (a) boosted account with in-budget, above-floor call succeeds (all three conditions
  hold); (b) non-boosted account reverts even when budget and reputation both pass; (c) a boost
  that has expired (`block.timestamp` past `zkBoostExpiry`, per `isZkBoosted`'s own logic) is
  treated as not-boosted — a real time-based boundary case, not just a static true/false; (d) the
  three checks remain independent — confirm a boosted-but-over-budget call still reverts on
  budget, and a boosted-but-below-floor call still reverts on reputation.
- Mutation-test sanity check on the new condition, same discipline as the first two.
- `preCheck` gas re-measured against the Table 4 budget — now three cross-contract-adjacent
  checks instead of two; this is exactly the kind of change the regression test exists to catch,
  and it's plausible this pushes closer to or over 40k, which would itself be a real finding.

## Scope: out

- No change to the budget or reputation checks.
- No `submitZkAttestation` testing beyond what's needed to make `isZkBoosted` return `true` in
  a test (i.e., directly manipulating `zkBoostExpiry` via the same test-oracle pattern already
  used for `updateScore`, not exercising the real Noir/Barretenberg proof pipeline — that's
  already covered elsewhere, per `PRODUCTION_GAPS.md` §26, and out of scope for a kernel-level
  test).
- No deployment, no toggle/configurability, no fourth adapter.

## Real risk worth naming explicitly

If the gas re-measurement shows `preCheck` pushing near or over the 40k Table 4 budget, that's a
genuine design pressure point for the eventual real kernel (which the plan already flags: "a cold
cross-contract SLOAD for effectiveScore() is ~2.6k on its own... reputation should be
cached/snapshotted per epoch rather than read live on every call"). This proposal does not
attempt to solve that now — if the measurement crosses the budget, the honest outcome is
reporting it as a finding, not silently accepting a broken budget assertion or quietly loosening
the test's threshold.

## Decision needed

1. **Authorize as scoped above.**
2. **Authorize with changes.**
3. **Not yet.**
