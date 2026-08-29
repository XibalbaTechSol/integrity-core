# Devil's Advocate review — governance state machine + EntryPoint integration gap

**Status:** proposal only, authorized to execute immediately per user direction (2026-08-24):
"scope the devil's advocate review on governance and EntryPoint and lets fix any phase 1
findings before moving to phase 2." Following the audit conclusion that formal Table 8
"independent audit" is out of scope for now (no external auditor; user is deliberately not
pursuing that gate at this stage) — this review is explicitly INTERNAL and does NOT substitute
for that gate. It exists to harden Phase I before Phase II work begins, which is its own,
legitimate reason to run it regardless of the external-audit question.

## Why these two areas, not a full re-review

`docs/plans/2026-08-24-phase1-formal-verification-proposal.md` deliberately deferred the
governance state machine out of the four Halmos properties' own scope ("a much larger state
space... deserves its own scoped verification slice"). `IntegrityAccount.sol`'s own NatSpec
discloses the EntryPoint gap directly: "This slice never exercises the ERC-4337 EntryPoint/
UserOp/prefund path... reachable only via `onlyEntryPointOrSelf`'s 'self' branch in this slice's
own test suite." Both are real, named, unclosed gaps — not invented for this review.

**What's NOT being re-reviewed:** the four already-machine-checked properties (native/token
budget containment, reputation/assurance gating, the `armed` reentrancy guard) and the
already-extensively-reviewed individual governance pieces as they were BUILT (kernel-swap
proposal/execution, guardian quorum, guardian emergency action, guardian rotation, rescue sweep
each already went through their own Devil's Advocate pass when added — `PRODUCTION_GAPS.md`
§29-37). Re-litigating those from scratch would be redundant, not thorough.

## Area 1: the governance state machine, reviewed as a FULLY ASSEMBLED whole

Every prior governance-mechanism review happened incrementally, as each piece landed — no single
review has looked at kernel-swap + guardian quorum + guardian emergency action + guardian
rotation + rescue sweep together, in their final, complete form, for CROSS-mechanism
interactions rather than each mechanism's own internal correctness. Concretely, hand the
reviewer:

- `contracts/src/kernel/IntegrityAccount.sol` in full (not a diff — the assembled whole).
- The five governance surfaces' state variables together: `pendingKernelSwap`/
  `kernelSwapNonce`/`kernelSwapApprovalCount`, `pendingGuardianAction`/`guardianActionNonce`/
  `guardianActionApprovalCount`, `pendingGuardianRotation`/`guardianRotationNonce`/
  `guardianRotationApprovalCount`, `pendingRescueSweep`/`rescueSweepNonce`/
  `rescueSweepApprovalCount`, `_guardians`/`_isGuardian`/`guardianThreshold`.
- Explicit prompt: find a sequence of calls across DIFFERENT governance mechanisms (not within
  one) that reaches a state the individual per-mechanism reviews wouldn't have caught -- e.g. a
  guardian rotation and a rescue sweep both claiming to be "the pending guardian-relevant
  process," a kernel-swap approval count surviving past where it should because a DIFFERENT
  mechanism's nonce bump doesn't invalidate it, or an ordering where two of the four "at most one
  in flight" guards each individually hold but the pair doesn't.
- Real, disclosed limits already on record, not to be re-discovered as if new: the broken-kernel
  brick class (unrescuable via kernel-swap, only via the separate rescue sweep), unilateral swap
  denial via never-cancelling a proposal (guardian force-cancel closes this, but confirm it still
  does after every subsequent addition), the two reentrancy windows in the swap halves.

## Area 2: the EntryPoint/ERC-4337 integration gap

Never exercised in this repo at all — every concrete test and every Halmos property calls
`execute()`/the governance functions via `vm.prank(address(account))`, standing in for what a
real `EntryPoint.handleOps()` call would produce. Real questions this leaves genuinely open, not
yet even framed as findings:

- Does `onlyEntryPointOrSelf` correctly distinguish a genuine `EntryPoint` call from a spoofed
  one in a REAL bundler flow, not just the `vm.prank` stand-in? (The OZ base `Account.sol`'s own
  `_checkEntryPointOrSelf`/`entryPoint()` — is this account's constructor wiring it to a real,
  correct `EntryPoint` address, or is `entryPoint()` left at some default/overridable value never
  actually checked?)
- `validateUserOp` (required by `IAccount`, inherited from the OZ base) — has ANYTHING checked
  this account's signature-validation path at all? `SignerECDSA` is mixed in, but is the
  validation logic itself exercised anywhere, by a concrete test, a Halmos property, or this
  review?
- Gas/prefund: real ERC-4337 flows involve a prefund step this slice's own NatSpec says is never
  exercised ("no prefund, no ERC-4337 UserOp gas-sponsorship path exercised" — tracer-bullet
  proposal's own original scope line). Does this matter for THIS deployment (self-funded,
  `vm.prank`-equivalent direct calls only) or would it break the moment someone tries to drive
  this account through a real bundler?
- The now-live Base Sepolia deployment (`PRODUCTION_GAPS.md` §44) makes this concrete, not
  hypothetical: is the deployed instance actually reachable via ERC-4337 infrastructure today, or
  only via a direct, self-authorized `execute()` call the way every test so far has used it?

## Process

Matching this repo's own established Devil's Advocate discipline (`PRODUCTION_GAPS.md` §29-37):
an independent subagent, given the full relevant source (not a diff), the real deployed addresses,
and this scoping doc's own two areas — not the rest of this session's conversation history, so it
isn't primed toward confirming what's already been decided. Findings get triaged: fixed in code
if genuinely fixable within Phase I's own scope, or explicitly disclosed as a permanent boundary
if not (matching the Table 4 gas crossing's own precedent) — never silently dropped.

## Decision needed

Already authorized by direct user instruction. Proceeding to dispatch the review now.

## Outcome (2026-08-24)

Review complete, six findings. Two real bugs (A1: a guardian-key-loss deadlock disabling three of
four guardian mechanisms; A2: force-cancel's missing target binding, a decoy-substitution
griefing vector) fixed and mutation-verified. One NatSpec overstatement corrected. Finding B1
(the EntryPoint address was never verified against anything) checked live against Base Sepolia
and resolved favorably -- real EntryPoint bytecode is genuinely there. Finding B2
(`validateUserOp` had zero test coverage) closed with four new, mutation-tested tests. Finding B3
sharpened the account's own NatSpec: the "self" branch every test uses has no production
equivalent at all -- on the live deployment, only a real EntryPoint/bundler flow can reach
`execute()` or the governance functions, not disclosed as such before this review. Full write-up:
`PRODUCTION_GAPS.md` §45. Full repo suite: 330/330 (up from 321), all six Halmos properties
re-verified unbounded after the fixes.

**What remains genuinely open:** the prefund/gas-sponsorship UserOp path is still unexercised, and
no real bundler has ever been driven against the live deployment. Also unchanged: this review does
NOT satisfy Table 8's "independent audit complete" gate -- by design, since no external auditor
was engaged. That distinction is preserved throughout, not blurred by having done real, useful
internal hardening work here.
