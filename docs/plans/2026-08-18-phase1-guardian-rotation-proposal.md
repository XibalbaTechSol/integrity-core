# Phase I guardian-set rotation (scoping only)

**Status:** Implemented and landed (2026-08-18). Threshold locked forever, unanimous rotation
approval — both decisions explained in plain language and confirmed by the user before
implementation. 86/86 file tests, 295/295 full repo suite. A real liveness bug in the
prerequisite emergency-path mechanism (item 1) was found while testing this slice's
cross-mechanism lock and fixed. Full writeup: `PRODUCTION_GAPS.md` §33,
`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`'s sixth update. Foundry-test-only — not
committed, not deployed. Depended on the guardian emergency-path proposal
(`docs/plans/2026-08-18-phase1-guardian-swap-denial-proposal.md`), which had already landed — see
"Sequencing" below (historical, now satisfied).

## Related, deferred: initial guardian selection at registration time

Not part of this contract-level proposal, noted here so it isn't lost. This experimental account
is not yet wired into real agent registration (`integrity-sdk/registration.py` doesn't reference
it today). When that wiring happens, `integrity-cli` and `integrity-dashboard` should give an
org/person-registering-an-agent an **active guardian-selection workflow** at registration time —
not a silent default. The user's own reasoning (2026-08-18): a sensible default for an
org/person-owned agent is the human operator's own separate backup key as ONE guardian among
several genuinely independent others (not the operator as the *sole* guardian, which would
collapse the guardian mechanism's independence property — see the swap-denial proposal's related
discussion). This is SDK/CLI/dashboard registration-flow scope, not on-chain contract scope — the
account contract already accepts any guardian list; this is about how that list gets chosen and
presented to a human at setup time.

## Why this slice

`IntegrityAccountV1Experimental`'s guardian set and `guardianThreshold` are both `immutable`,
fixed forever at construction (§31). Disclosed there as accepted, not solved: "an unreachable or
permanently-departed guardian permanently raises the effective bar toward 'impossible,' never
toward 'insecure.'" A guardian who loses their key, or a company/entity acting as guardian that
dissolves, doesn't make the account less safe — it makes the account's swap-execution path
progressively harder to ever legitimately use, up to and including impossible if enough guardians
become unreachable to make quorum unreachable regardless of who holds the signer key.

## The blocker that makes this harder than it looks

Two real traps, both already caught before any code exists (surfaced during scoping, not after
an incident):

**Trap 1 — mutable threshold reopens governance-of-governance.** `moduleActionTimelockSeconds`
is immutable specifically "to close off 'govern the governance' as an attack surface" (the
account's own NatSpec, verbatim). `guardianThreshold` was made immutable for the same reason.
Any rotation mechanism that lets `guardianThreshold` itself change reopens exactly that surface —
an attacker who can lower the threshold has partially defeated the quorum requirement without
ever forging a guardian signature. This proposal must state plainly whether rotation keeps
`guardianThreshold` as a fixed absolute number (removal below that number bricks execution
permanently, a real and disclosed cost) or lets it move (reopening the surface it was built to
close) — there is no third option that avoids naming this tension.

**Trap 2 — stale approvals don't decrement on removal.** `kernelSwapApprovalCount[nonce]` is a
running tally keyed only by nonce, not by which guardians are currently valid. Removing a
guardian who already approved the *currently pending* swap does not retroactively decrement that
count — their stale approval keeps counting toward `guardianThreshold` even after they're no
longer a guardian. This is the exact bug class `kernelSwapNonce` already solved once for
proposal-to-proposal replay; guardian rotation reopens it at the individual-approval level unless
the mechanism explicitly accounts for it. Two live options, not yet chosen: (a) any rotation event
also invalidates the currently pending swap's approval count (forces re-approval from the current
set — simple, but means a rotation always resets in-flight swap progress, a real operational
cost to name), or (b) rotation is blocked entirely while a swap is pending (simpler still, but
means a malicious signer could stall rotation itself by keeping a swap perpetually pending —
which is exactly the denial pattern item 1's proposal is designed to close, so these two
proposals interact and should probably be read together before either is authorized standalone).

## Sequencing dependency, stated explicitly

Trap 2's option (b) above is only survivable if item 1 (guardian emergency path) already exists —
otherwise a signer can block guardian rotation indefinitely the same way it can currently deny a
swap, and there would be no guardian-side recourse to break that stall either. **Recommend
authorizing and landing item 1 before this proposal is finalized**, not merely before it's
implemented — the design of rotation's interaction with a pending swap genuinely depends on
whether guardians already have an emergency path.

## Mechanism sketch (for discussion, not final)

- Add/remove functions, guardian-quorum-gated (not signer-gated — a signer should not unilaterally
  be able to add a guardian loyal to itself, which would silently defeat the entire quorum
  property). Candidate shape: `proposeGuardianRotation(address[] toAdd, address[] toRemove)` /
  `approveGuardianRotation(uint256 expectedRotationNonce)` / `executeGuardianRotation(...)`,
  mirroring the kernel-swap propose/approve/execute pattern already established and tested in
  this codebase, rather than inventing a new shape.
- A dedicated `rotationNonce`, separate from `kernelSwapNonce` — rotation and kernel-swap
  approvals must never be conflatable, or a guardian's rotation-approval could be misread as a
  swap-approval or vice versa.
- Threshold-after-removal validation: reject any removal that would drop `guardians().length`
  below the current `guardianThreshold` (matching the constructor's existing
  `InvalidGuardianThreshold` check, applied again at rotation time) — unless the same rotation
  transaction also lowers the threshold, which reopens Trap 1 and must be an explicit, disclosed
  choice if allowed at all, not a silent side effect.
- A timelock on rotation itself, likely reusing `moduleActionTimelockSeconds` or a dedicated
  immutable of its own — an instant rotation would let a compromised quorum silently replace
  itself with attacker-controlled guardians in one transaction, no observable window at all.

## What this does NOT prove (to be inherited into the real proposal)

- Does not make the guardian mechanism itself resistant to key compromise at the moment of
  rotation — if attacker-controlled addresses already hold `guardianThreshold` valid approvals
  (via key compromise, not code failure), they can rotate themselves into a permanent set the
  same way any legitimate quorum could. Rotation changes *who* the trusted parties are; it cannot
  make the trust model itself stronger than "the M keys are independent," the same caveat §31
  already names for execution.
- Does not resolve Trap 1's tension by itself — whichever choice this proposal makes
  (fixed-threshold or threshold-can-move) is a real, disclosed policy decision the user must
  affirmatively pick, not a default this scoping pass should silently assume.

## Scope: in (for the real proposal, once authorized and item 1 has landed)

- Resolve Trap 1 (threshold mutability) and Trap 2 (stale-approval decrement on removal) as
  explicit, named decisions.
- Propose/approve/execute rotation mechanism, guardian-quorum-gated, timelocked, nonce-scoped
  independently from `kernelSwapNonce`.
- Foundry tests: removal below threshold reverts (or, if threshold-lowering is allowed, the
  combined-change path is tested explicitly); a guardian's approval on a pending swap is provably
  invalidated (or the rotation is provably blocked) once that guardian is removed mid-swap;
  rotation timelock cannot be bypassed; a rotated-out guardian cannot approve anything post-removal
  even with a pre-removal-signed transaction that lands post-removal (ordering/front-running
  check).
- Mutation testing + Devil's Advocate review, same discipline as §31.

## Scope: out

- Changing `guardianThreshold`'s immutability outside of an explicit, disclosed rotation-combined-
  with-threshold-change path, if that path is even authorized.
- Any interaction with the account signer's own key (`SignerECDSA`) — rotation here means the
  guardian set only, never the account's primary signing key.

## Decision needed

1. **Authorize item 1 (guardian emergency path) first**, since this proposal's Trap 2 resolution
   likely depends on it.
2. **Authorize scoping to proceed to a full rotation proposal** once item 1's shape is settled.
3. **Not yet** — stay at this sketch stage.
