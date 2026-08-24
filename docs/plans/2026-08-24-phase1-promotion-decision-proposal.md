# Phase I promotion decision — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Written as workstream 1 of
completing whitepaper Phase I (`spec/integrity-protocol-v3.2.md` §10.3, Table 8), following the
2026-08-24 audit that found Phase I's remaining blockers are deployment, external audit, and
machine-checked invariance — plus this naming decision, which gates the other three (you can't
sensibly audit or deploy a contract you might still rename).

## The question

`contracts/src/kernel/IntegrityAccountV1Experimental.sol` and `IntegrityKernelV1Experimental.sol`
are, per their own design doc (`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`), explicitly
**not** "proof that `IntegrityAccount`/`IntegrityKernel` (the real Phase I names) exist" — "an
experimental, disclosed-scope artifact validating specific architectural choices... not a partial
implementation of the production contracts." That framing was correct when written (2026-08-17,
one adapter deep). It is 314 tests, six governance hardening slices, and a ZK-circuit binding
later, and the artifact has grown into something closer to the real thing than the original
"tracer bullet" name implies. Does it graduate, or get rebuilt?

## Option A: promote in place (rename, keep the code)

`IntegrityAccountV1Experimental` → `IntegrityAccount`, `IntegrityKernelV1Experimental` →
`IntegrityKernel`. Drop "Experimental" from both file names, contract names, and NatSpec
cross-references. No logic change.

**What this costs:**
- Two contract files, low internal reference count (6 and 5 NatSpec/comment mentions
  respectively — verified by grep, not estimated). A clean `sed`-style rename plus a NatSpec
  reread, not a rewrite.
- `contracts/test/IntegrityAccountV1Experimental.t.sol` → renamed, 146 occurrences of the old
  name (type references, constructor calls) — mechanical, but worth a real compile+test pass
  after, not just a search-replace-and-trust.
- No error/event selector changes — verified: "Experimental" appears only in contract names and
  comments, never in an `error`/`event` identifier, so this is not an ABI-shape change.
- Historical docs (`HANDOFF.md`, `CLAUDE_HANDOFF_2026-08-19.md`, `PRODUCTION_GAPS.md`'s dated
  entries, every `docs/plans/2026-08-1[78]-phase1-*.md` proposal) **must not** be retroactively
  rewritten — they are dated logs of what was true when written, and this repo's own convention
  (see `PRODUCTION_GAPS.md`'s repeated "the record briefly said otherwise" corrections) treats
  silently rewriting history as worse than leaving it stale. Current-state docs only (README.md,
  CLAUDE.md, a fresh PRODUCTION_GAPS.md entry) get updated forward from this decision.

**What this buys:**
- Keeps 314 tests, six rounds of Devil's Advocate review, and the disclosed-limitation record
  intact and attached to the contract that will actually go to audit — a rebuild would either
  discard that evidence or have to re-derive it against new code, at real risk of silently
  reintroducing an already-closed gap (e.g. the reentrancy guard, the epoch/timelock invariant).
- The existing code is already scoped honestly narrower than the whitepaper's full Phase I ideal
  (single conserved asset, not calldata-aware, single-signer day-to-day authority) — promoting it
  doesn't change what it proves, only what it's called. The "not general value conservation" /
  "not calldata-aware" limitations from the 2026-08-24 audit stay exactly as true after a rename
  as before.

**What this does NOT resolve, rename or not:** deployment, external audit, machine-checked
invariance, and the still-open value-conservation-scope decision (workstream 2) are all
untouched by this choice either way.

## Option B: rebuild fresh under the production names

Treat the experimental contracts as reference-only; write `IntegrityAccount`/`IntegrityKernel`
from scratch, informed by but not literally descended from the tested code.

**What this costs:**
- Every one of the 314 tests, six Devil's Advocate reviews, and disclosed-limitation findings
  (the gas-budget crossing and its epoch-snapshotting fix, the two reentrancy windows, the
  broken-kernel-brick class, the guardian-quorum/rotation/rescue mechanisms) would need to be
  either ported deliberately or independently rediscovered. Rediscovery is the real risk: this
  repo's own history (§21 of `PRODUCTION_GAPS.md`) has multiple entries where a control existed
  in source, was removed or diverged, and nothing caught it until a live measurement. A rebuild
  is exactly the kind of divergence-prone path this repo's conventions warn against.
- No technical justification currently on record for a rebuild — nothing in the 2026-08-24 audit
  or the design doc names a defect in the experimental contracts' *architecture* (as opposed to
  its explicitly disclosed scope limits) that would require starting over.

**What this buys:** a clean-room chance to fold in the still-deferred general-value-conservation
question (workstream 2) or a broader constraint grammar from day one, if that's judged to need a
different account/kernel shape than the current single-conserved-quantity design supports. There
is no current evidence that it does — but this option exists for the record in case workstream 2
surfaces one.

## Recommendation

**Option A — promote in place.** The blast radius is small and mechanical (verified above, not
assumed), the alternative discards real, hard-won test/review evidence for no named technical
reason, and this repo's own standing discipline is to correct and extend code in place rather
than silently re-derive it. Nothing about "Experimental" in the current name reflects an actual
scope gap that a rebuild would close — the real gaps (deployment, audit, formal verification,
value-conservation scope) are orthogonal to what the contract is called.

## Decision needed

1. **Authorize Option A** — rename in place, current-state docs only, mechanical + verified
   compile/test pass.
2. **Authorize Option B** — rebuild fresh; needs its own scoping proposal before any code.
3. **Not yet** — revisit after workstream 2 (general value-conservation scope) is decided, in
   case that decision changes what "the real Phase I contracts" need to look like.

This document does not authorize itself.

## Outcome (2026-08-24)

**Option A authorized and implemented.** `IntegrityAccountV1Experimental.sol` →
`IntegrityAccount.sol`, `IntegrityKernelV1Experimental.sol` → `IntegrityKernel.sol`,
`IntegrityAccountV1Experimental.t.sol` → `IntegrityAccount.t.sol`; rename only, verified zero
logic change. `forge build` clean; full repo suite re-verified at 314/314, zero regressions.
Full write-up: `PRODUCTION_GAPS.md` §40.
