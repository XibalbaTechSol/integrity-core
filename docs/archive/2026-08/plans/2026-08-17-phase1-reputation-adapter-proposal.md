# Phase I second reference adapter (reputation floor) — go/no-go proposal

**Status:** proposal only. Nothing here is authorized. Follows the same process discipline as
`docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md` (the first, already-authorized-and-built
slice) — this is an incremental extension of that slice, not a new one from scratch.

## What this is

The full Phase I plan names three reference adapters (spend/velocity cap, reputation floor,
assurance tier) and is explicit that the paper's many-adapter model must "multiplex *inside* the
single kernel hook" — `AccountERC7579Hooked` only supports one installed hook module at all
(`ERC7579HookModuleAlreadyPresent`), confirmed when building the first slice. `IntegrityKernelV1Experimental`
today enforces exactly one conserved quantity (the native-value budget). This proposal adds a
**second, independent, conjunctive** check to the same kernel — real multiplexing, not a second
hook — using an already-real, already-deployed contract (`ReputationRegistry`), not inventing new
reputation infrastructure.

## What this is NOT

- **Not** a new AIS decision. `ReputationRegistry.effectiveScore(agent)` already exists, is
  already read by other contracts, and is completely independent of the still-deferred AIS
  floor/shadow-gate work (`PRODUCTION_GAPS.md` §27's decision to wait for more registered
  agents). This adapter reads the existing, real, oracle-pushed score — it does not touch
  `scoring-core`, does not pick floor values, does not flip any enforcement decision that's
  still explicitly on hold.
- **Not** deployed anywhere, same as the first slice.
- **Not** a change to the first slice's existing guarantees — the budget check stays exactly as
  built and tested; this adds a second, independently-testable condition alongside it.

## Mechanism

Verified directly from `contracts/src/oracle/ReputationRegistry.sol` before writing this
proposal (not assumed):

- `effectiveScore(address agent) public view returns (uint256)` — the oracle-pushed, pre-boost
  base score boosted by `ZK_BOOST_BPS`/`BPS_DENOMINATOR` while a ZK attestation is live. Same
  0–~1150 scale the oracle's `GET /v1/agent/{id}/ais` reports.
- `updateScore(address agent, uint256 baseScore) external onlyRole(ORACLE_ROLE)` — how a real
  score gets set. Not restricted to agents registered anywhere else; keyed by an arbitrary
  address, which is what makes it usable here.
- `initialize(admin, oracleSigner, zkVerifier, stateAnchor)` tolerates `address(0)` for
  `zkVerifier`/`stateAnchor` — confirmed by reading `effectiveScore`/`updateScore`'s bodies,
  neither touches those fields (only `submitZkAttestation`, not exercised by this adapter).
  Testable with a real, standalone `ReputationRegistry` instance, no other contracts needed.

The kernel gains one new immutable: `minEffectiveScore`. `reputationRegistry` is also immutable,
set at construction (same "pinned once, no rebind" posture as `boundAccount`/the budgets). The
**subject** whose score is checked is `boundAccount` itself, not a separate parameter — this
matches the real system's intended design (the plan: "`IntegrityAccount` must register itself as
`primitives.sovereignAgent`"), not a testing convenience that would diverge from production
shape.

`preCheck` gains one additional read-only check: revert unless
`ReputationRegistry(reputationRegistry).effectiveScore(boundAccount) >= minEffectiveScore`. This
is a **precondition gate, not a conserved quantity** — unlike the budget check, it needs no
before/after snapshot or `postCheck` involvement; a single read in `preCheck` is sufficient and
correct (reputation cannot change *during* the wrapped call in any way this kernel needs to
re-verify after the fact).

## Scope: in

- The one new `preCheck` read + revert described above.
- Constructor gains two new immutable params (`reputationRegistry`, `minEffectiveScore`) —
  additive to the existing three (`boundAccount`, `perOpBudgetWei`, `cumulativeBudgetWei`).
- Tests deploy a real, standalone `ReputationRegistry` (not a clone — direct `new` +
  `initialize`, confirmed viable above) and push real scores via `updateScore` as a test-local
  oracle-role account.
- Both checks (budget AND reputation) must hold conjunctively — an in-budget call from a
  below-floor account must still revert, and vice versa.

## Scope: out

- No change to `scoring-core`, no floor values chosen for the still-deferred AIS gate.
- No handling of `submitZkAttestation`/ZK boost mechanics beyond what `effectiveScore` already
  folds in automatically (this adapter just reads the number, doesn't reason about how it got
  there).
- No third adapter (assurance-tier/`isZkBoosted`) — separate scope if wanted later.
- No deployment, no registration of the experimental account as a real agent anywhere.
- No change to the first slice's module-mutation-disabled posture, execution-mode restriction,
  or reentrancy guard — all untouched.

## Acceptance criteria

- Real Foundry tests, passing, proving: (a) an in-budget call from an above-floor account
  succeeds (both checks pass); (b) an in-budget call from a below-floor account reverts, even
  though the budget check alone would have passed; (c) an above-floor call that's also
  over-budget still reverts on the budget check (order/independence of the two checks doesn't
  matter for correctness, but the test should confirm reputation passing doesn't somehow bypass
  the budget check); (d) a score exactly at the floor succeeds (boundary case, matching the
  first slice's exact-boundary testing discipline for the cumulative budget).
- `preCheck`'s gas, now with two checks instead of one, re-measured against the Table 4 budget
  (`<=40k`) — this is the real reason gas assertions exist as regression tests, not one-off
  numbers: this is exactly the kind of change that could push a prior measurement over budget.
- Full repo suite stays green.
- `PRODUCTION_GAPS.md`/`HANDOFF.md`/the design note updated the same as the first slice.

## Decision needed

1. **Authorize as scoped above.**
2. **Authorize with changes.**
3. **Not yet.**
