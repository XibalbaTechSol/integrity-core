# Declared multi-asset value conservation — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Follow-up scoping for Option A
of `docs/plans/2026-08-24-phase1-value-conservation-scope-proposal.md` (authorized decision:
generalize the kernel's native-ETH-only conserved quantity to a small *declared* asset list,
explicitly not attempting undeclared-asset/calldata-content awareness, which stays out of scope
regardless). Written against `contracts/src/kernel/IntegrityKernel.sol` and
`IntegrityAccount.sol` as they exist post-promotion (`PRODUCTION_GAPS.md` §40) — read in full
before drafting this, not assumed from prior summaries.

## What exists today, precisely

`IntegrityKernel.preCheck` snapshots exactly one quantity — `boundAccount.balance` (native ETH,
a free EVM opcode, not an external call) — and returns it as `hookData`. `postCheck` re-reads the
same balance, computes `spent`, and reverts on a per-operation or cumulative budget breach. One
asset, two immutable budgets (`perOpBudgetWei`, `cumulativeBudgetWei`), one running counter
(`cumulativeSpentWei`). `preCheck` also does the reputation-floor and assurance-tier checks
(cached, epoch-snapshotted) — those are irrelevant to this change except as the thing sharing
`preCheck`'s gas budget.

## Dependency inventory — the real constraint this proposal exists to name

**Value conservation is a hard invariant, not soft context, and that fact forecloses the
mitigation the reputation checks used.** `spec/integrity-protocol-v3.2.md` §4.7.1 is explicit:
"Hard invariants (value conservation, meter depletion, replay domain) never enter grace — they
are fail-closed in every state." Reputation and assurance-tier crossed Table 4's `<=40k` `preCheck`
ceiling and were rescued by epoch-snapshotting — caching a value and accepting staleness up to
`epochLengthSeconds`. **That exact rescue is unavailable here.** A cached ERC-20 balance is not
"possibly a little stale" the way cached reputation is — it is a wrong measurement of the actual
conserved quantity the whole mechanism exists to bound, and caching it would silently void
equation (12) rather than merely widen a window on a soft precondition. Any additional declared
asset must be read **live**, in both `preCheck` (before-snapshot) and `postCheck` (after-read,
same as native ETH today).

**Consequence for gas:** each declared ERC-20 adds one external `balanceOf` staticcall in
`preCheck` (a cold cross-contract call plus the token's own SLOAD — the design doc's own prior
measurement of a comparable cross-contract read, `effectiveScore()`, was "~2.6k on its own," before
this slice's Solidity/ABI overhead) and a second in `postCheck`. `preCheck` is already at 33,321
gas with zero headroom rescued twice already (once by moving from live to cached reputation
reads, which this change cannot repeat). **Realistic expectation, stated before any code exists
so this proposal can't retroactively rationalize a bad number: one additional declared ERC-20
token plausibly pushes `preCheck` back over the 40k Table 4 ceiling on its own.** This must be
measured, not assumed, and is this slice's own named risk — see "Real risk" below.

**Scope bound following directly from the above:** this slice targets exactly **one** additional
declared asset (a single ERC-20 token address, fixed at construction — almost certainly `$ITK`
given it's the protocol's own token and the concrete motivating case from the parent proposal),
not a general N-asset list. If gas allows headroom after measuring, a follow-up slice can consider
more; committing to more before measuring one would repeat the exact mistake the three-reference-
adapter slice made (stacking checks before measuring, discovering the crossing only after all
three landed).

## What this slice does NOT attempt

- **Not ERC-721 or any non-fungible asset.** `balanceOf` semantics differ (count vs. amount) and
  "spent" has no natural meaning for a token that isn't fungible — a real design question, not an
  oversight, deferred entirely.
- **Not a runtime-mutable asset list.** The declared token address is immutable, set at
  construction, matching every other kernel parameter's own atomic-binding philosophy (no
  governance path to add/remove a tracked asset post-deploy — that would need its own timelocked
  mechanism, out of scope here).
- **Not calldata-content awareness or undeclared-asset protection** — explicitly and permanently
  out of scope per the parent proposal's Option A framing, not something this slice was ever
  meant to close.
- **Not a solution if gas doesn't fit.** If measurement shows `preCheck` exceeds Table 4 with one
  added token and no further mitigation is available (see below), the honest outcome is
  **not-yet**, not silently raising the ceiling or moving the check to a place that weakens the
  guarantee.

## Design

- New immutable constructor params: `trackedToken` (address, may be `address(0)` to mean "no
  additional token tracked," preserving today's behavior when unset — needed so existing
  deployments/tests that don't want this feature aren't forced to supply a real token),
  `tokenPerOpBudget`, `tokenCumulativeBudget`.
- `preCheck`: when `trackedToken != address(0)`, add one `IERC20(trackedToken).balanceOf(boundAccount)`
  read to the existing native-balance snapshot; both values returned in `hookData`
  (`abi.encode(nativeBefore, tokenBefore)` — a shape change from today's single-value encode,
  so every existing caller of `hookData` decoding must be updated together, not left mismatched).
- `postCheck`: decode both, compute `spent` for each asset independently, check each against its
  own per-op/cumulative budget (conjunctive — either alone can revert), maintain a second
  cumulative counter (`tokenCumulativeSpent`) alongside the existing `cumulativeSpentWei`.
- No change to the reputation/assurance-tier logic or their caching — orthogonal, already correct.

## Process discipline (matching the original tracer-bullet proposal's own rules)

1. **Gas checkpoint before committing to the full slice.** Land the `preCheck` balance-read
   addition alone first, with a live gas regression test, before writing the `postCheck`
   accounting logic — if `preCheck` alone crosses 40k, that's the go/no-go moment, not something
   discovered after the whole feature is built (the assurance-tier adapter's own history is the
   cautionary example: three checks were built, then measured, then found over budget).
2. **Strict red→green TDD**, one failing Foundry test at a time, same as every prior kernel slice.
3. **Mutation-tested guards** on both the per-op and cumulative token checks, same discipline as
   the native-ETH budget's own tests.
4. **A dedicated Devil's Advocate review before landing**, matching every governance-affecting or
   accounting-affecting kernel slice so far (module governance, reputation snapshotting, all six
   2026-08-19 gap closures). Named risk areas to hand the review: (a) `hookData` shape change and
   whether any caller could be tricked into supplying/accepting a mismatched encoding; (b) a
   token whose `balanceOf` reverts or is nonstandard (fee-on-transfer, rebasing) — this kernel
   cannot assume ERC-20 correctness any more than `IntegrityAccount` assumes a well-behaved
   `newKernel`; (c) reentrancy interaction between the token check and the existing `armed` guard
   with a token whose `balanceOf` itself makes an external call (some proxy/rebasing tokens do).

## Acceptance criteria

- Real Foundry tests proving: in-budget native+token call succeeds; over-per-op-budget on either
  asset alone reverts (both directions — over on token but not native, and vice versa); over-
  cumulative on either asset reverts at its own exact boundary; both budgets independently
  enforced (an above-native-budget, at-token-budget call still bound by whichever check applies).
- `preCheck` gas measured live as a regression test, immediately after the balance-read addition,
  before any further accounting logic is written — this is the checkpoint named above, not an
  afterthought.
- A short update to `IntegrityKernel`'s own guarantee-statement NatSpec (the contract-level doc
  comment already states precisely what it does and does not cover — this must be extended, not
  left to imply broader coverage than what's tested) and to
  `docs/design/phase1-tracer-bullet-slice-2026-08-17.md`'s "What this does NOT prove" section.
- `PRODUCTION_GAPS.md` updated with a dated entry, same as every other kernel slice.

## Real risk, stated before any code exists

- **This may simply not fit the gas budget**, per the dependency-inventory section above — a real
  possibility, not a formality, because the one mitigation available to reputation/assurance
  (caching) is foreclosed here by the hard-invariant requirement. If it doesn't fit, this
  proposal's honest resolution is to report that finding and stop, the same way the
  three-reference-adapter slice reported (not silently absorbed) its own over-budget crossing.
- **Nonstandard ERC-20 behavior** (tokens that revert on zero-value transfers, rebase, or charge
  a transfer fee) could make "spent" not equal the amount the wrapped call's calldata requested —
  this kernel would still correctly bound the *observed* balance delta (which is what equation
  (12) actually requires), but that's worth stating plainly rather than assumed obvious.
- **`hookData` shape change is a breaking change** to the encode/decode contract between
  `preCheck` and `postCheck` — low risk since both live in this one kernel and no other contract
  currently decodes `hookData` from it, but must be verified, not assumed, before landing (grep
  for every caller).

## Decision needed

1. **Authorize as scoped above** — one additional declared ERC-20, gas-checkpointed before full
   implementation, Devil's Advocate review before landing.
2. **Authorize with changes** — different scope (e.g. skip the gas checkpoint gate, or widen to
   N tokens immediately).
3. **Not yet** — the gas risk named above is real enough to warrant deciding after a throwaway
   gas-only spike (implement just the `preCheck` balance read, measure, discard or keep) rather
   than committing to the full slice up front.

This document does not authorize itself.

## Outcome (2026-08-24)

**Authorized as scoped ("full scoped slice at once") and built.** All acceptance criteria met
except one, which resolved negatively for real: the gas checkpoint. `preCheck` with `trackedToken`
enabled measures ~41,056 gas against a genuinely cold token-balance read — over Table 4's `<=40k`
ceiling by ~1k gas, exactly the risk this proposal's dependency-inventory section named before any
code existed. Per this proposal's own commitment ("if it doesn't fit... report that finding and
stop"), the finding is reported, not worked around: `test_preCheckGasExceedsPaperTable4BudgetWithTrackedTokenLiveRead`
documents it directly, the kernel's NatSpec states the crossing rather than implying compliance,
and no mitigation was attempted within this slice. Full write-up, including a real methodology
correction found mid-implementation (an initial ~25,829 gas measurement was a same-transaction
warm-storage artifact, corrected before being trusted): `PRODUCTION_GAPS.md` §41. Full repo suite:
321/321, zero regressions.

**Decision (2026-08-24): accepted as a disclosed, permanent Phase I boundary** (option (a) of
§41's three named options). No mitigation attempted, no revert — `IntegrityKernel` keeps
`trackedToken` exactly as built and measured. The kernel is still un-deployed, so no live UserOp
is affected; the crossing is a bundler-economics cost under real ERC-4337 gas limits, not an
on-chain correctness or safety failure. Full reasoning: `PRODUCTION_GAPS.md` §41's own "Decision"
paragraph. Workstream 2 is now closed — the parent scope decision
(`docs/plans/2026-08-24-phase1-value-conservation-scope-proposal.md`) is fully resolved.
