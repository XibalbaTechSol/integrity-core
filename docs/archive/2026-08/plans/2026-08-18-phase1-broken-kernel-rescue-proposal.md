# Phase I broken-kernel rescue path (scoping only)

**Status:** Implemented and landed (2026-08-18) — but NOT as originally scoped below. The
kernel-swap-bypass approach this document sketches was investigated during implementation and
found architecturally impossible (`AccountERC7579Hooked._hook` is `private`, and both its
mutation paths are unconditionally `withHook`-wrapped — no override point can reach it without
asking the broken kernel first). Disclosed to the user before writing code, not discovered
partway through. Built instead, with explicit user sign-off after the wall was explained: a
guardian-unanimous emergency FUNDS-RECOVERY SWEEP that never touches `_hook`/`execute()` at all —
recovers funds, does not repair the account. 101/101 file tests, 310/310 full repo suite. Full
writeup: `PRODUCTION_GAPS.md` §35, `docs/design/phase1-tracer-bullet-slice-2026-08-17.md`'s
eighth update. Foundry-test-only — not committed, not deployed. The rest of this document is
preserved as written (the original, superseded plan) for the historical record — see the writeup
above for what was actually built.

## Why this is the hardest of the six, and why it was previously called "genuinely unfixable"

`PRODUCTION_GAPS.md` §29 names this precisely: if the currently-installed kernel's `preCheck`
reverts unconditionally — buggy, or maliciously crafted to look conformant at proposal time but
brick on the next call — every future `execute()` reverts forever, **and the rescue swap's own
uninstall half must call that same broken `preCheck` first**, because `_uninstallModule` is
wrapped by `withHook`, which calls `preCheck` on the currently-installed hook before running the
uninstall body. There is no existing call path that removes a hook without first asking that same
hook's permission to proceed. §29's own verdict: "this remains fundamentally unenforceable at the
type level" — the `isModuleType` probe in `proposeKernelSwap` can reject non-conforming
addresses, but cannot verify `preCheck` correctness, which is unbounded, arbitrary contract logic.

## The actual tradeoff, named plainly rather than resolved

The only way to remove a kernel that refuses to be removed through the normal path is a rescue
path that **bypasses hook mediation entirely** for the uninstall half — i.e., a privileged call
that does not route through `withHook`'s `preCheck`/`postCheck` at all. This is not a bug to
engineer around; it is the necessary shape of any fix, and it directly weakens the account's own
central guarantee ("the hook fires on every reachable state-changing path except `X`" — this adds
a second, larger `X`). §31 already added one such exception (`approveKernelSwap`) and justified it
because gating a guardian's approval behind the account's own hook would be circular. The same
justification applies here, more sharply: gating a *rescue from a hook that is actively refusing
to cooperate* behind that same hook's cooperation is not just circular, it's definitionally
impossible.

**The real question for the eventual proposal is not "can this be built" — it clearly can, as an
unmediated guardian-only path — but "how high must the bar be to authorize bypassing the account's
own security mediation," given that the exact same mechanism, misused, is also the single most
powerful way to drain an account with an intentionally-installed-but-inconvenient kernel.**

## Mechanism sketch (for discussion, not final)

Builds directly on item 1's guardian emergency propose/execute path, with one addition: a
`forceRescueKernelSwap(address newKernel)` (or equivalent) that, once guardian-approved at the
**same or higher bar as the emergency propose path** (recommend: unanimous N-of-N, deliberately
the highest bar in the system — higher than both the normal execution threshold and the
emergency-propose threshold from item 1, since this is strictly the most dangerous capability
being added), performs the uninstall **without** calling the outgoing kernel's `preCheck`/
`postCheck` at all — a direct `_hook = address(0)` state change plus the outgoing kernel's
`onUninstall` lifecycle call (still invoked, since that's a module-interface obligation, not a
security check the module itself controls the outcome of), followed by the normal
`_installModule` for `newKernel`.

**A structural question the real proposal must resolve, not this sketch:** should
`forceRescueKernelSwap`'s `onUninstall` call to the broken kernel itself be attempted at all, or
skipped? Attempting it is the more "correct" ERC-7579 lifecycle behavior, but if the kernel
reverts unconditionally in *any* function, not just `preCheck`, then even `onUninstall` might
revert and reintroduce the same brick — the rescue path would need to either (a) not call
`onUninstall` at all for a force-rescue (a deeper interface-contract deviation, disclosed
explicitly), or (b) wrap the `onUninstall` call in a try/catch that proceeds regardless of
success (silently accepting a possibly-inconsistent state on the old kernel's side, which is
irrelevant anyway since it's being discarded). Recommend (b) for the real proposal — least
surprising, and the old kernel's internal state is moot once uninstalled.

## Why this depends on item 1, explicitly

A `forceRescueKernelSwap` gated purely by guardians (no signer involvement at all) is the natural
shape, since the whole point is rescuing an account whose kernel is broken regardless of what the
signer wants — but if guardians have no existing mechanism to originate an action without signer
cooperation (item 1's exact gap), this proposal would need to build that machinery from scratch
redundantly. Landing item 1 first means this proposal only needs to add "and this guardian path
may additionally skip hook mediation on the uninstall half, at a stricter threshold" as a
targeted extension, not a second parallel governance system.

## What this does NOT close, even once built

- Does not make `newKernel` any safer than the `isModuleType` probe already makes it — a
  force-rescue could just as easily install a second broken kernel, at which point the account is
  bricked again and the *only* remaining path is another force-rescue (whose bar the guardians
  must clear again). This is not a design flaw so much as an inherent limit: no on-chain mechanism
  can verify a hook module's `preCheck`/`postCheck` will never revert, since that's equivalent to
  solving the halting problem for arbitrary bytecode.
- Does not close the reentrancy windows from item 3 — if anything, a rescue path that skips
  `preCheck` mediation on the uninstall half removes one of the two existing reentrancy windows
  (there's no old-kernel `preCheck` call to reenter around) but the `onUninstall` lifecycle call
  itself is still a reentrancy surface the item-3 guard should be checked against once both exist.
- Introduces a second, disclosed reversal of "hook mediates every reachable path" — larger than
  §31's `approveKernelSwap` exception, since this one skips mediation on a path that would
  otherwise (in the non-broken case) be fully mediated. Both `IntegrityAccountV1Experimental.sol`'s
  NatSpec and `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` need a third disclosure
  paragraph, not a silent extension of the second.

## Scope: in (for the real proposal, once item 1 has landed and this is authorized)

- Resolve the try/catch-vs-skip question for the outgoing kernel's `onUninstall` call.
- `forceRescueKernelSwap`, gated at the highest threshold in the system (recommend unanimous
  N-of-N), independent of and likely without any timelock at all (a genuinely bricked account has
  no ongoing "normal operation" to protect by delaying rescue — the real proposal should state
  this explicitly rather than reflexively reusing `moduleActionTimelockSeconds`).
- Foundry tests: a kernel that reverts unconditionally in `preCheck` is confirmed to brick the
  account via the normal path first (regression-anchoring the problem this fixes, matching
  `test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath`'s existing pattern), then
  confirmed rescuable via the new path; a kernel that also reverts in `onUninstall` does not block
  the rescue (depends on the try/catch decision above); a rescue below the unanimous threshold
  reverts; the rescued account's new kernel is fully functional afterward (`execute()` succeeds
  through the replacement).
- Mutation testing + Devil's Advocate review — this is the highest-blast-radius item of the six
  and should get the most adversarial scrutiny, not less because it's "just" a rescue path.

## Scope: out

- Any weakening of the normal `executeKernelSwap` path's mediation — this is a separate,
  additional, higher-bar entry point, not a modification of the existing one.
- Solving "how do you know `newKernel` won't also be broken" in general — acknowledged as an
  inherent limit, not a solvable scope item.

## Decision needed

1. **Authorize item 1 first** — this proposal is not independently actionable.
2. **Authorize scoping to proceed to a full rescue proposal** once item 1's guardian-origination
   mechanism exists to build on.
3. **Not yet** — stay at this sketch stage, and accept §29's original "genuinely unfixable at this
   scope" framing as the operative decision for now.
