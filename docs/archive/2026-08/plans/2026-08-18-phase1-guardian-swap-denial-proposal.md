# Phase I guardian emergency path — closes unilateral swap *denial* (scoping only)

**Status:** Implemented and landed (2026-08-18). Option B selected by the user, built, and
verified: 71/71 file tests, 280/280 full repo suite, three security-relevant guards
mutation-tested and confirmed caught. A real design gap (executeKernelSwap was signer-only,
which would have stalled a guardian-force-proposed rescue at the last step) was found during
implementation, explained to the user in plain terms, and fixed with their explicit sign-off.
Full writeup: `PRODUCTION_GAPS.md` §32,
`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`'s fifth update. Still Foundry-test-only —
not committed, not deployed. Written after reading `IntegrityAccountV1Experimental.sol` directly
(current `e53da44` state) and `PRODUCTION_GAPS.md` §31's own disclosure of this exact gap.

## Why this slice

§31 closed unilateral swap *execution*: a compromised signer alone can propose and start the
clock, but can no longer force `executeKernelSwap` through without independent guardian quorum.
It explicitly did not close unilateral swap *denial*, disclosed plainly in both the contract
NatSpec and §31:

> a compromised or uncooperative signer can park an unwanted proposal in the single pending-swap
> slot indefinitely (never cancelling, never letting guardians act on anything), denying the
> account — including a legitimate rescue swap — for as long as the signer withholds a cancel.

There is a second, more severe form of the same failure not previously named as sharply: the
signer doesn't even need to propose anything hostile. `proposeKernelSwap` is `onlyEntryPointOrSelf`
— **only the signer can start a swap at all.** If the signer key is lost, seized, or simply
unresponsive, guardians have zero recourse, even at full N-of-N consensus, because there is never
a pending swap for them to approve. This is the wider case; the "park a bad proposal forever"
case in §31 is the narrower one. Both share one root cause — every governance-initiating action
is signer-gated — and this proposal treats them as one mechanism, not two.

## What this is NOT

- **Not** a general escape hatch for account authority. `execute()` stays single-signer, exactly
  as every prior slice states. This only touches the swap-governance sub-system.
- **Not** the broken-kernel brick scenario (item 4 / §29). That is orthogonal: even a fully
  cooperative signer and fully willing guardians cannot rescue an account whose *currently
  installed* kernel reverts unconditionally in `preCheck`, because the swap's own uninstall half
  must call that broken `preCheck` first. This proposal assumes the installed kernel still
  functions; it only removes the signer as a single point of *authorization* failure. See the
  guardian-rescue proposal (item 4) for why that scenario needs this mechanism as a foundation,
  not a substitute.
- **Not** a guardian-rotation mechanism (item 2). Kept as a separate proposal deliberately —
  bundling rotation into the denial fix would conflate "who can act" with "who counts as an
  actor."

## The tension this proposal must not resolve silently

§31's own design record already rejected guardian-cancel once, specifically to avoid "making
swap denial itself a multi-party negotiation" — i.e., turning a fast unilateral cancel into a
slow multi-party one for the common, benign case (signer proposes, changes their mind, wants to
cancel *now*). Any mechanism that lets guardians act on the pending-swap slot must not weaken
that fast path for the cooperative-signer case. The two failure modes this proposal targets
(unresponsive signer, or signer actively withholding cancel) are both adversarial-signer
scenarios — the mechanism should only become reachable when the normal, faster, signer-only path
has already failed to move things forward, not compete with it.

## Mechanism sketch (for discussion, not final)

Two candidate shapes, both keeping `proposeKernelSwap`/`cancelKernelSwap` signer-only and
unchanged for the cooperative case:

**Option A — guardian force-cancel, high bar.** A new `guardianForceCancelKernelSwap()`,
callable only once **unanimous** guardian approval (N-of-N, deliberately higher than the
execution threshold `guardianThreshold`) has accumulated against the *current* pending swap.
Clears `pendingKernelSwap` exactly like `cancelKernelSwap` does. Addresses the narrow "bad
proposal parked forever" case. Does **not** address the wider "signer never proposes at all"
case, since there is nothing pending to force-cancel.

**Option B — guardian-originated propose, same high bar.** A new
`guardianProposeKernelSwap(address newKernel)`, reachable only at unanimous guardian approval
(collected the same way `approveKernelSwap` collects execution approvals, but against a
guardian-only proposal path, not the signer's), usable whether or not something is already
pending — if something is pending, it must first be superseded (a decision to make explicit in
the real proposal: does a guardian-propose require the guardian set to *also* force-cancel first,
one dependent action, or can it override a stuck pending swap atomically in one call?). Addresses
both cases in §31's disclosure, but is the larger of the two options: it duplicates the timelock
and nonce-scoping machinery `proposeKernelSwap` already has, under a second, guardian-authorized
entry point, and needs its own careful interaction analysis with `kernelSwapNonce` (does a
guardian-initiated proposal bump the same nonce counter the signer path uses, or a separate one —
mixing them risks a stale signer-side approval silently counting toward a guardian-originated
swap, or vice versa).

**Decided: Option B, unanimous threshold**, sharing `kernelSwapNonce` (bump-on-any-propose,
regardless of origin, keeps the existing "new nonce invalidates all prior approvals" invariant
simple and uniform rather than introducing a second counter to reason about). This closes both
failure modes with one mechanism, at the cost of being the larger build.

In plain terms: guardians get a way to both start a fresh lock-swap themselves (if the signer is
gone) and cancel a stuck one (if the signer is being uncooperative), but only when every single
guardian agrees — not a majority, all of them. That's a deliberately high bar, since this is the
one path in the whole system that lets someone other than the account's own signer make it change
its lock.

## Known trap carried into implementation, not resolved here

Any guardian-originated propose/cancel must go through the SAME nonce and approval-count
machinery the existing `approveKernelSwap` uses, or a stale approval could double-count across a
signer-initiated and guardian-initiated proposal for the same `newKernel` address. This is the
same class of bug `kernelSwapNonce` already solved once for the signer path — a guardian path
that reinvents its own bookkeeping instead of extending the existing nonce risks reopening it.

## Scope: in (for the real proposal, once authorized)

- Resolve Option A vs. Option B (recommend B, unanimous threshold) as an explicit decision, not
  left implicit.
- Guardian-originated propose/cancel semantics, fully specified: does it require unanimous
  consent or a separately configurable (likely stricter) threshold from `guardianThreshold`;
  interaction with an existing pending signer-proposed swap; nonce-sharing with the existing
  mechanism.
- Foundry tests: unresponsive-signer rescue (no pending swap, guardians alone bring a new kernel
  through), parked-bad-proposal rescue (signer proposes then goes dark, guardians override),
  interaction with an in-flight signer-side approval count (confirm no cross-contamination
  between a signer-initiated and guardian-initiated proposal under different nonces).
- Amend `IntegrityAccountV1Experimental.sol`'s NatSpec and
  `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` — this is a third reversal-in-progress
  of "hook mediates everything" bookkeeping if the new path is also unmediated (it must be, per
  §31's own reasoning for why `approveKernelSwap` is unmediated: gating an emergency guardian
  path behind the account's own hook would be circular).
- Mutation-testing and Devil's Advocate review, same discipline as §31.

## Scope: out

- Guardian-set rotation (item 2 — separate proposal, though this mechanism and rotation will need
  to be read together once both exist, since a rotation event could itself be gamed via a stuck
  swap negotiation).
- Broken-kernel rescue when the installed kernel itself is unconditionally reverting (item 4 —
  depends on this mechanism existing first, doesn't duplicate it).
- Any weakening of the signer's fast, unilateral, cooperative-case propose/cancel path.

## Decision needed

Option B is decided. Remaining: authorize implementation (strict TDD, Foundry-only, no
deployment, same discipline as every prior slice), or hold at this sketch stage a while longer.
