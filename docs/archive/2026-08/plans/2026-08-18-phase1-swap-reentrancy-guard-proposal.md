# Phase I kernel-swap reentrancy guard (scoping only)

**Status:** Implemented and landed (2026-08-18), Shape B as recommended. 88/88 file tests, 297/297
full repo suite. A real imprecision in the account's own long-standing NatSpec claim ("hostile
kernel reenters `execute()`") was found and corrected during implementation — the actually-
reachable path is the unguarded `fallback()`, not the `onlyEntryPointOrSelf`-gated `execute()`.
Full writeup: `PRODUCTION_GAPS.md` §34, `docs/design/phase1-tracer-bullet-slice-2026-08-17.md`'s
seventh update. Foundry-test-only — not committed, not deployed. Written after reading
`IntegrityAccountV1Experimental.sol` (current `e53da44`
state) and OpenZeppelin's vendored
`node_modules/@openzeppelin/contracts/account/extensions/draft-AccountERC7579Hooked.sol` directly
— this proposal's feasibility claim rests on that source, not on the account's own doc-comment
description of it.

## Why this slice

The account's own NatSpec discloses two reentrancy windows during `executeKernelSwap`, both
inherited from how the OZ base class's `withHook` modifier interacts with `_installModule`/
`_uninstallModule`, neither closed by any prior slice:

1. **Install half.** `_hook` is written to point at `newKernel` *before* `newKernel.onInstall()`
   runs (inside `_installModule`'s body, which the `withHook` modifier wraps). A hostile
   `onInstall` that reenters `execute()` would be mediated only by its own (attacker-controlled)
   `preCheck`/`postCheck` — self-mediation, not independent mediation, inside the same atomic
   swap transaction.
2. **Uninstall half.** `_hook` is cleared to `address(0)` *before* the old kernel's
   `onUninstall()` runs. A reentrant `execute()` from a compromised old kernel's `onUninstall`
   is mediated by nothing at all — `withHook`'s `hook_ != address(0)` check simply skips both
   `preCheck` and `postCheck`.

## Confirmed against the actual OZ source, not assumed

`withHook`'s modifier body:

```solidity
modifier withHook() {
    address hook_ = hook();          // captured BEFORE the wrapped function body runs
    bytes memory hookData;
    if (hook_ != address(0)) hookData = IERC7579Hook(hook_).preCheck(msg.sender, msg.value, msg.data);
    _;                                // wrapped function body runs here
    if (hook_ != address(0)) IERC7579Hook(hook_).postCheck(hookData);
}
```

`_installModule`/`_uninstallModule` are both `internal virtual override withHook` — the `_hook`
storage write happens *inside* the wrapped body (`_;`), after `hook_` has already been captured
for this call's own pre/post check, but before `_hook`'s new value is visible to anything called
*from inside* that body (i.e., the `onInstall`/`onUninstall` lifecycle callback, which fires from
within `super._installModule`/`super._uninstallModule`, itself called after the local `_hook =
module` assignment). This confirms the account's own disclosure precisely: the new/old kernel's
lifecycle callback sees the *post-swap* `_hook` value, not the value that was true when the
callback's own enclosing call started.

## Two remediation shapes considered

**Shape A — reorder or locally reimplement `_installModule`/`_uninstallModule`.** Move the
`_hook` write after the lifecycle callback, or copy the base functions locally with reordered
statements. **Rejected as the recommended approach for this proposal.** This diverges from
OpenZeppelin's own audited base contract on a security-critical path, for behavior this codebase
doesn't own and doesn't need to fully rewrite — the actual attacker-reachable harm is a reentrant
`execute()` call, not the storage-ordering pattern itself. Forking a vendored security contract
is expensive to justify, expensive to keep in sync with future OZ patches, and broader than the
problem requires.

**Shape B — a local reentrancy guard scoped to the swap's execute-call surface.** Recommended.
Add a `bool swapInProgress` flag, set `true` immediately before the uninstall/install call pair in
`executeKernelSwap` and `false` immediately after (or via a scoped modifier). Add a single check
at the top of `_execute` (already overridden locally for the CALLTYPE/EXECTYPE restriction, so
this is one more line in an already-overridden function, not a new override): `if (swapInProgress)
revert ReentrantDuringSwap();`. This directly closes both disclosed windows' actual attacker
capability — a reentrant `execute()` call during either lifecycle callback — without touching or
depending on OZ's internal `_hook`-then-callback ordering at all. The guard is orthogonal to
whatever `_hook` happens to point at mid-swap; it simply makes any nested `execute()` attempt
revert unconditionally for the duration of the swap.

## What Shape B does not close — must be disclosed, not silently implied as complete

- Does **not** close reentrancy into `approveKernelSwap`, `proposeKernelSwap`, or
  `cancelKernelSwap` during the swap window — only `_execute` gets the guard in this sketch. A
  reentrant call to one of the governance functions themselves (as opposed to `execute()`) is a
  separate question the real proposal must explicitly analyze: is it reachable at all from inside
  `onInstall`/`onUninstall` (both are plain external calls from within `executeKernelSwap`, so in
  principle yes), and if reachable, is it actually harmful, or already inert for unrelated reasons
  (e.g. `proposeKernelSwap` would revert `SwapAlreadyPending` since `pendingKernelSwap` is only
  deleted at the *start* of `executeKernelSwap`, before either callback fires — verify this
  ordering explicitly in the real proposal rather than assuming it).
- Does **not** change the underlying `_hook`-visible-before-callback ordering — a *non-reentrant*
  hostile action inside `onInstall`/`onUninstall` (e.g. reading `_hook` and behaving differently
  based on its already-updated value, without calling back into `execute()`) is unaffected. The
  account's own doc comment's specific concern — a reentrant `execute()` mediated by the wrong or
  no kernel — is what this closes, not every possible consequence of the ordering.
- Does **not** address the broken-kernel brick scenario (item 4) — unrelated failure mode
  (a kernel that always reverts, not one that reenters).

## Scope: in (for the real proposal, once authorized)

- `swapInProgress` guard (or equivalent), set/cleared around the uninstall/install pair inside
  `executeKernelSwap`, checked in `_execute`.
- Explicit analysis (not just testing) of whether reentrancy into
  `proposeKernelSwap`/`cancelKernelSwap`/`approveKernelSwap` during the guarded window is
  reachable and, if reachable, whether it needs the same guard or is already inert — state the
  conclusion either way in the proposal, don't leave it implicit.
- Foundry tests, following this codebase's existing pattern for the account's `armed` guard
  (`test_reentrancyDuringInstallAndUninstallObservesFreshApprovalsAndEmptyPending` is the closest
  precedent — a `ReentrancyObserverKernel`/`HostileReentrantKernel` fixture playing both the
  new-kernel and old-kernel role): a hostile `onInstall` that attempts to reenter `execute()`
  reverts `ReentrantDuringSwap` rather than succeeding self-mediated; a hostile `onUninstall` that
  attempts to reenter `execute()` reverts the same way rather than succeeding unmediated. Both
  mutation-tested (temporarily remove the guard, confirm the same reentrant call succeeds
  instead, restore).
- Gas re-measurement of `executeKernelSwap` (a `SSTORE`+`SLOAD` pair added to an already-measured
  function — expect a small, real, recorded delta, not "unchanged").

## Scope: out

- Reordering or reimplementing OZ's `_installModule`/`_uninstallModule` (Shape A, rejected above).
- Any change to `IntegrityKernelV1Experimental.sol`.
- Guardian mechanisms (items 1, 2, 4) — independent of this proposal, though a Devil's Advocate
  review of this slice should re-confirm the guardian-approval-visibility finding from §31
  (`test_reentrancyDuringInstallAndUninstallObservesFreshApprovalsAndEmptyPending`) still holds
  once this guard exists, since the guard changes what a reentrant call can even attempt.

## Decision needed

1. **Authorize Shape B as scoped above** — the smallest of the six items, independent of the
   others, no dependency chain.
2. **Authorize Shape A instead** — fork/reorder the OZ base functions (not recommended, larger
   and riskier for the same closed surface).
3. **Not yet** — stay at proposal stage.
