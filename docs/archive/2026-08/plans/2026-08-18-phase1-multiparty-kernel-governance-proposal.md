# Phase I multi-party kernel governance (guardian quorum) — go/no-go proposal

**Status:** authorized as scoped (option 1). Written after reading
`IntegrityAccountV1Experimental.sol`'s current single-signer-timelocked swap mechanism directly
(not from memory of prior handoffs) and `PRODUCTION_GAPS.md` §29's full account of what that
mechanism does and does not close.

## Why this slice, and why now

The tracer-bullet slice's kernel-swap governance (`docs/plans/2026-08-17-phase1-module-governance-proposal.md`)
shipped **single-signer-timelocked**, not the original Phase I plan's "timelocked + **multi-party**"
requirement (`CLAUDE_HANDOFF_2026-08-17.md` §8.1, item 4). The contract's own doc comment states
the gap plainly: "a compromised signing key can still eventually force a kernel swap, just not
instantly... It does NOT provide the independent-quorum property real multi-party governance
would." This proposal closes exactly that gap — nothing more.

Two other named Phase I items remain open (formal `ConstraintTypes.sol` grammar; independent
audit + machine-checked invariance). This proposal is scoped to governance only, matching the
"one slice at a time" discipline every prior extension used.

## What this is NOT

- **Not** a redesign of the account's day-to-day authority model. `execute()` remains gated by
  the account's single `SignerECDSA` exactly as today — the whitepaper's four-primitive model
  treats account authority and kernel governance as different concerns, and the existing account
  doc comment is explicit that making the *whole account* multi-sig is "separate, larger scope."
  This proposal adds a second, independent authority axis (a guardian quorum) that gates only the
  kernel-swap path, leaving everything else about the account unchanged.
- **Not** deployed anywhere. Foundry-test-only, same as every other Phase I slice so far.
- **Not** a fix for the two disclosed reentrancy windows or the broken-kernel brick scenario in
  `PRODUCTION_GAPS.md` §29 — those are orthogonal to *who* authorizes a swap and remain open,
  disclosed risk after this slice, exactly as before it.
- **Does not** touch `IntegrityKernelV1Experimental.sol`'s adapter logic (budget / reputation
  floor / assurance tier) or the reputation-snapshotting mechanism at all.

## The reversal, stated plainly

`docs/design/phase1-tracer-bullet-slice-2026-08-17.md` and this account's own doc comment both
state the hook fires "on every reachable state-changing path" (the module-governance slice
already amended this once, for the swap's two `_installModule`/`_uninstallModule` calls — see
that proposal's own reversal note). `approveKernelSwap` breaks this a second time: it is
deliberately guardian-callable *directly*, not routed through `execute()`/`_execute`/`withHook`,
because gating a guardian's approval behind the account's own reputation-floor/assurance-tier
hook would be circular (the guardian exists precisely to act when the account itself may be
compromised or non-conformant). That is the right design choice, but it means this slice adds a
second, permanent exception to the "hook mediates everything" guarantee, alongside the swap's
own uninstall/install asymmetry already on record. Both guarantee documents must be updated to
say so plainly, not left reading as if they still hold unconditionally.

## Mechanism

Add an immutable guardian set and threshold to `IntegrityAccountV1Experimental`, set once at
construction (non-upgradeable, matching the account's own philosophy — no guardian-set rotation
in this slice):

```solidity
address[] private _guardians;         // immutable-by-construction, no add/remove path
uint256 public immutable guardianThreshold;   // M-of-N, e.g. 2-of-3
```

- `proposeKernelSwap` stays exactly as today: `onlyEntryPointOrSelf` (the account's existing
  single signer starts the clock). Proposing is low-stakes — it mutates no state that affects
  `execute()` behavior until the swap actually executes, so gating it behind a quorum would only
  slow down the common case without closing a real risk.
- New: `approveKernelSwap(uint256 expectedNonce, address newKernel)`, callable only by an
  address in `_guardians`. Approvals are scoped by a `kernelSwapNonce` bumped once per
  `proposeKernelSwap` call — `mapping(uint256 nonce => mapping(address guardian => bool))` plus
  `mapping(uint256 nonce => uint256) approvalCount` — so a stale approval from a cancelled or
  already-executed proposal can never silently count toward a later one, and there is no
  clear-on-cancel/clear-on-execute bookkeeping to get wrong in three places. The guardian passes
  `expectedNonce` alongside `newKernel`; a mismatch reverts, so an approval can't land on a
  cancel-and-repropose of the same kernel address under a new nonce. Backed by
  `mapping(address => bool) _isGuardian` populated once in the constructor (not an array scan
  per call). Emits an event; does not itself mutate `_hook`.
  **This is a new state-changing entry point on the account that no hook mediates** — see
  "the reversal, stated plainly" below.
- `executeKernelSwap` gains a fourth precondition alongside the existing three (pending exists,
  `newKernel` matches, timelock elapsed): approval count for the pending swap must be `>=
  guardianThreshold`. Fails closed (`InsufficientGuardianApprovals`) otherwise — same discipline
  as every other guard in this codebase.
- `cancelKernelSwap` stays `onlyEntryPointOrSelf`-only, unchanged. A single party should be able
  to abort a proposal it regrets or that guardians are refusing to approve; requiring quorum to
  *stop* a swap would make a stuck multi-party negotiation the exploitable failure mode instead
  of the fixed one.

This is the same "propose low-stakes, gate the actually-consequential half" pattern the account
already uses for module mutation itself (propose is cheap and reversible; execute is where real
authority is required).

## What this closes, precisely

Before this slice: a single compromised signer key, waiting out the timelock, can force any
kernel swap alone — the disclosed gap.

After this slice: a single compromised signer key can still *propose* and *start the clock*, but
cannot execute without independently convincing `guardianThreshold` guardians (distinct keys, not
derived from or related to the account signer) to each submit their own on-chain approval. This
is the actual "independent-quorum property" the account's own doc comment names as missing.

## What this does NOT prove — read together with §29's existing disclosures

- **Not** protection against a compromised signer's day-to-day `execute()` calls — those remain
  single-signer-gated by design; this slice only hardens the swap path.
- **Not** protection against guardian collusion or guardian-key compromise at or above threshold
  — an M-of-N quorum is only as strong as the independence of the M keys, which this contract
  cannot verify or enforce; that is an operational/deployment discipline, not a code guarantee.
- **Does not** add a guardian-rotation mechanism. A guardian set fixed forever at construction is
  simple to reason about but has its own failure mode (an unreachable or permanently-departed
  guardian permanently raises the effective bar toward "impossible," never toward "insecure") —
  disclose this plainly rather than silently deferring it; a future slice would need a second,
  probably-also-guardian-gated rotation mechanism if this is adopted.
- **Does not** close the two reentrancy windows or the broken-kernel brick scenario already on
  record in `PRODUCTION_GAPS.md` §29. A malicious or buggy `newKernel` that passes the
  `isModuleType` probe can still brick the account after a fully-guardian-approved swap — quorum
  raises the bar for *who can propose a bad swap and get it through*, it does not make the swap
  itself safer once approved.
- **Does not** clear the Devil's Advocate review's own stated gate to Phase II (independent audit
  + machine-checked invariance). Same standing caveat as every prior slice.
- **Closes unilateral swap *execution*, not unilateral swap *denial*.** `proposeKernelSwap` and
  `cancelKernelSwap` both remain signer-only, and `SwapAlreadyPending` blocks a second proposal
  while one is pending. A compromised signer can no longer force a swap through alone, but it can
  still park an unwanted proposal in the single pending-swap slot indefinitely (never calling
  `executeKernelSwap`, never letting guardians act on anything), denying the account — including
  a legitimate rescue swap — for as long as the signer withholds a cancel. Letting guardians
  cancel at threshold would close this but reintroduces the stuck-negotiation failure mode this
  proposal deliberately rejects for `cancelKernelSwap` (see Mechanism). Disclosed and accepted,
  not solved, by this slice.
- **Quorum latency interacts with reputation epoch-staleness, a new failure mode this slice
  introduces rather than inherits.** The account doc comment already warns that
  `moduleActionTimelockSeconds > epochLengthSeconds` can make `executeKernelSwap`'s uninstall
  half revert `SnapshotStale` for a reason unrelated to reputation. A guardian quorum strictly
  lengthens real-world elapsed time between propose and execute (timelock, then M separate
  guardian transactions), making that collision materially more likely to occur in practice, not
  just in theory. Recoverable — anyone may permissionlessly call `refreshReputationSnapshot()` —
  but to whoever hits it, it looks like a reputation problem, not a staleness one. This slice adds
  a regression test for exactly this sequence (see Scope: in) rather than leaving it as a
  restated theoretical risk.

## Scope: in

- `_guardians` (immutable array) + `_isGuardian` mapping + `guardianThreshold` (immutable),
  constructor-validated: threshold must be `>= 1` and `<= _guardians.length`; reject duplicate
  guardian addresses; reject the zero address as a guardian.
- `kernelSwapNonce`, bumped once per `proposeKernelSwap`; nonce-scoped approval mapping +
  per-nonce approval count, as described in Mechanism.
- `approveKernelSwap(uint256 expectedNonce, address newKernel)` with nonce-mismatch and
  non-guardian rejection.
- `executeKernelSwap`'s new quorum precondition, read from the current nonce's approval count.
- Amend `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` and
  `IntegrityAccountV1Experimental.sol`'s own doc comment to disclose `approveKernelSwap` as an
  unmediated state-changing entry point, per "The reversal, stated plainly" above — same register
  the module-governance slice used for its own reversal, not a silent update.
- Foundry tests, strict red→green TDD, mutation-tested wherever a guard is security-relevant:
  below-threshold execute reverts; exact-threshold execute succeeds; a guardian approving twice
  under the same nonce does not double-count; a non-guardian approval reverts; a wrong-nonce
  approval reverts; an approval from a cancelled proposal's nonce cannot count toward a
  subsequent repropose of the same `newKernel`; the existing single-signer preconditions
  (timelock, address match, pending-exists) still independently gate execution alongside the new
  quorum check, not instead of it; **the quorum-vs-epoch-staleness sequence from "What this does
  NOT prove"** — assemble quorum after `epochLengthSeconds` has elapsed, confirm
  `executeKernelSwap` reverts `SnapshotStale`, call permissionless `refreshReputationSnapshot()`,
  confirm the same call then succeeds.
- Gas re-measurement of `proposeKernelSwap`/`approveKernelSwap`/`executeKernelSwap` (not
  `preCheck` — this slice doesn't touch the hot path the Table 4 budget governs) — recorded, not
  assumed.

## Scope: out

- Guardian rotation/replacement.
- Making the account's own `execute()` authority multi-party.
- Any change to `IntegrityKernelV1Experimental.sol`.
- Deployment, anywhere.
- Formal `ConstraintTypes.sol` grammar (separate named item).

## Process discipline

Same as every prior slice:

1. Strict red→green TDD — one failing Foundry test first, confirmed failing for the right
   reason, smallest implementation that passes, repeat.
2. Mutation-test every security-relevant guard (temporarily remove/weaken it, confirm the test
   suite actually catches the regression, then restore it) — this is what caught the reentrancy
   `armed`-guard finding and the timelock/probe gaps in prior slices; the discipline does not get
   relaxed because this slice feels smaller.
3. A dedicated adversarial pass before landing, same as the kernel-swap mechanism got
   (`PRODUCTION_GAPS.md` §29's six-area review) — at minimum: guardian-set/threshold
   constructor edge cases (threshold 0, threshold > length, duplicate guardians, empty guardian
   array with threshold 0 silently reducing to "no quorum required"), approval-replay across
   proposal cycles, and interaction with the existing reentrancy windows (does a reentrant call
   during `onInstall`/`onUninstall` see stale or fresh approval state?).
4. `PRODUCTION_GAPS.md` updated with the same register as §29's existing entries — including
   real findings that don't get fixed, not just the ones that do.

## Decision needed

1. **Authorize as scoped above** — build exactly this guardian-quorum extension, strict TDD,
   Foundry-only, no deployment.
2. **Authorize with changes** — e.g., gate `proposeKernelSwap` behind quorum too, or add
   guardian rotation now instead of deferring it.
3. **Not yet** — stay at proposal stage.
