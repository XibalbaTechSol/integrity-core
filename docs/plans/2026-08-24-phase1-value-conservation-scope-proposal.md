# Phase I value-conservation scope — go/no-go proposal

**Status:** proposal only. Nothing in this document is authorized. Workstream 2 of completing
whitepaper Phase I (`spec/integrity-protocol-v3.2.md` §10.3, Table 8), following workstream 1's
promotion of `IntegrityAccount`/`IntegrityKernel` (`PRODUCTION_GAPS.md` §40).

## The question

`docs/design/phase1-tracer-bullet-slice-2026-08-17.md` discloses, and the 2026-08-24 audit
restated: **"Not general value conservation. Only native ETH is tracked. Any ERC-20/ERC-721/
other asset movement inside the wrapped call is completely unconstrained by this kernel."** The
whitepaper's own §4.4 names value conservation as one of three primitives "the kernel supplies... so
that adapter authors do not re-derive them":

$$\sum_{j \in P} \Delta b(j) + \varphi = 0 \tag{12}$$

stated generally over a participant set and balances $b(j)$ — not restricted to native ETH by the
formalism, only by this implementation. This is also the paper's own headline safety claim
(Proposition 1: "the reachable state set of an enclosed agent is contained in an operator-declared
admissible set, for *every* input"). As built today, that containment holds only for ETH — an
agent holding `$ITK` (the protocol's own ERC-20, used throughout markets/treasury flows —
verified: `contracts/src/kernel/*.sol` has zero `IERC20`/`ERC20` references) or any other token
has zero kernel-enforced protection on that balance. Does Phase I need to close this before it's
honestly "the kernel," or is single-asset scope acceptable with generalization deferred?

## What's actually being asked to generalize, precisely

Two distinct things get conflated under "not general value conservation," and they have very
different costs:

1. **Balance-delta conservation over a *declared* set of assets.** Exactly what's built today for
   native ETH — budget in, budget out, checked via a before/after balance read — extended to also
   track a fixed list of ERC-20 (and optionally ERC-721 ownership) addresses the deploying account
   declares at construction. Mechanically the same pattern as the existing per-op/cumulative
   budget, just N assets instead of one.
2. **Calldata-content awareness / arbitrary-asset conservation.** Knowing that a call approved a
   token, invoked an arbitrary contract, or moved an *undeclared* asset, without the account
   having named that asset in advance. This is a fundamentally different problem — it requires
   either simulating/decoding arbitrary calldata against arbitrary token contracts (unbounded gas,
   unbounded complexity, exactly what the whitepaper's own R2 gas-boundedness requirement for
   adapters rules out) or a general semantic model of "what is value" for arbitrary contracts,
   which doesn't exist. The design doc's own tracer-bullet review is explicit on this point: value
   conservation "is invalid until each asset profile defines a closed accounting universe" — i.e.
   the primitive only ever applies to a *declared*, finite set, never to arbitrary unknown assets.

**Item 2 is not a Phase I gap to close — it's out of scope by the whitepaper's own definition of
what value conservation (12) means.** Table 2's own worked example (royalty licensing) conserves
one declared token; §7.5 state channels conserve one declared quantity $Q$. Nowhere does the paper
propose a mechanism for asset-agnostic protection against arbitrary undeclared calls — that's
squarely `integrity-dsl` / adapter-registry territory (§7.5.2, Phase III "permissionless adapter
publication"), where a domain expert declares the accounting universe for their specific mandate.
The "not calldata-content-aware" limitation the 2026-08-24 audit also named is this same category,
correctly scoped as a *disclosed limitation of a hook design*, not a missing deliverable — general
calldata semantics is a research-grade problem, not a Phase I engineering task.

So the real, tractable question is only **item 1**: should Phase I's reference kernel generalize
its one conserved quantity (native ETH) to a small declared set (ETH + N ERC-20 addresses,
each with their own per-op/cumulative budget), the same way `preCheck`'s reputation and assurance
checks already generalize from "one hardcoded condition" to "N conjunctive conditions"?

## Option A: generalize now, before Phase I is called complete

Extend `IntegrityKernel`'s conserved-quantity check from a single native-ETH budget to a declared
list of `(token address, per-op budget, cumulative budget)` tuples, native ETH being one entry
(`address(0)`) among them. Mechanically: `postCheck` reads `balanceOf` before/after for each
declared ERC-20 in the list (plus the existing native-balance delta), same conjunctive-revert
pattern the trio of reference adapters already established.

**Cost:** real Solidity work, not a rename — new state (the declared asset list), new tests
(per-asset budget boundaries, multi-asset conjunctive reverts, the interaction between a
native-ETH budget and an ERC-20 budget checked in the same `postCheck`), a fresh gas measurement
against Table 4's budget (more `balanceOf` calls = more gas — the existing 33,321 gas headroom
under the 40k ceiling may not survive one added token, let alone several, without its own
snapshot/caching treatment the way reputation needed). Genuinely comparable in size to the
reputation-floor or assurance-tier adapter slices already built (each ran ~1 day, several
Foundry tests, one Devil's Advocate review) — not a small change, but a bounded and
precedented one.

**Benefit:** closes the actual gap between "the kernel" and Proposition 1's own stated guarantee
for any agent holding more than native ETH — which in this protocol's own ecosystem is the
common case ($ITK is the protocol's own token). Makes the audit workstream (workstream 5) face a
kernel that matches its own headline claim, rather than one an auditor immediately flags as
under-scoped relative to the paper it implements.

## Option B: defer — declare native-ETH-only in scope for Phase I, generalize later

Leave the kernel as-is; document the single-asset scope as a permanent, disclosed Phase I
boundary (not a to-do) — the same way `PRODUCTION_GAPS.md` §19 already treats the 7 legacy
non-compliant agents as "a permanent, structural fact... not a to-do" rather than open work.
Multi-asset conservation becomes explicit Phase II/III scope, likely delivered as one of the
first adapters through the (not-yet-built) adapter registry rather than as a kernel primitive.

**Cost:** the gap stated above stays real and disclosed — an auditor reviewing "the kernel" against
the whitepaper's own §4.4 will find value conservation is asset-scoped to exactly one asset, which
is a legitimate, nameable finding even if accepted by design.

**Benefit:** keeps Phase I's remaining engineering surface smaller heading into the harder,
harder-to-scope workstreams (formal verification, external audit) — those two are already large
unknowns; adding a new contract feature now grows what has to be verified and audited, not just
what has to be built.

## Recommendation

**Option A, scoped narrowly** — generalize to a small *declared* list (ETH + a handful of
ERC-20 addresses fixed at construction, not runtime-mutable, matching the existing
atomic-kernel-binding philosophy), explicitly **not** attempting item 2 (calldata-content
awareness / undeclared-asset protection), which stays out of scope for Phase I regardless of this
decision. Reasoning: this is the one piece of "not general value conservation" that is both
(a) named directly by the whitepaper's own core safety primitive and (b) tractable with the exact
architecture already built and tested — declining it would mean shipping a kernel whose headline
guarantee provably doesn't cover this protocol's own native token, for a well-scoped, precedented
amount of work. Item 2 should be recorded as a permanent, disclosed boundary either way (Option A
does not and cannot close it).

## Decision needed

1. **Authorize Option A** — generalize to a declared multi-asset list; needs its own scoped
   go/no-go proposal (asset-list size limit, gas-budget re-measurement plan, whether to reuse or
   extend the epoch-snapshotting pattern) before any Solidity, matching this repo's standing
   discipline for kernel changes.
2. **Authorize Option B** — declare native-ETH-only permanent Phase I scope; write the
   disclosure into `PRODUCTION_GAPS.md`/README now, move directly to workstream 3.
3. **Not yet** — revisit after workstream 5 (external audit) scopes its own findings; an auditor
   may independently flag this and settle the question with less speculation than is possible here.

This document does not authorize itself.

## Outcome (2026-08-24)

**Option A authorized, scoped in a follow-up proposal
(`docs/plans/2026-08-24-phase1-declared-asset-conservation-proposal.md`), and built.** A single
declared ERC-20 (`trackedToken`) generalizes the kernel's conserved quantity from native-ETH-only
to a two-asset declared set. The follow-up's own gas checkpoint returned a real, negative result —
`preCheck` measures over the whitepaper's Table 4 ceiling with the token check enabled (~41,056
gas cold, vs. the ~40k ceiling) — reported rather than absorbed, per that doc's own process
discipline. **Decision: accepted as a disclosed, permanent Phase I boundary**, not mitigated or
reverted. Full write-up: `PRODUCTION_GAPS.md` §41. Item 2 from this document (calldata-content
awareness / undeclared-asset protection) remains out of scope for Phase I as originally reasoned —
unaffected by any of the above. Workstream 2 is closed.
