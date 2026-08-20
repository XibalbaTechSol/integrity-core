# Phase I module governance (timelocked kernel swap) — proposal and reversal note

**Status:** built and tested under the standing goal ("implement all kernel features and validate
each one," set 2026-08-17 via session-scoped Stop hook + explicit user confirmation). Unlike the
three reference adapters, this proposal is written *alongside* the implementation rather than
strictly before it, because it reverses a previously committed claim — see "The reversal, stated
plainly" below. That reversal needed its own documented decision regardless of the standing
goal's authorization to keep building.

## What this is

The tracer-bullet slice and both adapter extensions (`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`)
all satisfy the whitepaper's complete-mediation condition (iii) — "module install/removal must
itself be a constrained transition, or the guarantee is void" — by making install/removal
**unreachable entirely**. That doc's own "What this does NOT prove" section already named this as
"a materially weaker property... an account that could never evolve its policy is trivially safe
from policy-removal attacks, but it is also not a general-purpose account design." This proposal
closes that gap with the smallest mechanism that makes module mutation *reachable* rather than
*unreachable*, while still keeping it constrained.

## The reversal, stated plainly

**Before this change**, `PRODUCTION_GAPS.md` §29, the design note, and `HANDOFF.md` all state:
module mutation is permanently unreachable by construction; `installModule`/`uninstallModule`
always revert; this is *why* the guarantee holds the way it does.

**After this change**, that is no longer true. `installModule`/`uninstallModule` still always
revert directly, but a new path — `proposeKernelSwap` → wait out a timelock →
`executeKernelSwap` — reaches the same underlying `_installModule`/`_uninstallModule` internals.
Module mutation is reachable, gated by time rather than by unreachability.

This is a real reversal, not an extension. It is disclosed here, in the contract's own top-level
NatSpec, and will be disclosed in every downstream doc this proposal updates
(`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`, `PRODUCTION_GAPS.md` §29,
`HANDOFF.md`) — none of them will be silently left asserting the old, now-false claim.

## Mechanism

Two design decisions, both made deliberately rather than defaulted into:

**1. Swap-only, not generic install/uninstall.** An earlier draft of this mechanism exposed
independent `proposeModuleAction`/`executeModuleAction` calls for install and uninstall
separately. That draft was deleted before landing: this account only ever holds exactly one hook
module, so there is never a legitimate reason to uninstall without a replacement queued, and the
only reachable outcome of allowing bare uninstall — a window with zero hook modules installed —
is precisely the "the agent can simply uninstall its own supervisor" failure the whitepaper names
as fatal. `proposeKernelSwap(newKernel)` / `executeKernelSwap(newKernel)` / `cancelKernelSwap()`
model the swap as one atomic unit: `executeKernelSwap` uninstalls the old kernel and installs the
new one in the same transaction, so there is no reachable intermediate state with zero hooks.

**2. Mediated, not bypassed — verified, not assumed.** The account's base class
(`AccountERC7579Hooked`) wraps `_installModule`/`_uninstallModule` in its own `withHook`
modifier, which calls `hook()` once at the start of each wrapped call to decide whether to fire
`preCheck`/`postCheck`. This was empirically verified (not assumed) by reading
`AccountERC7579Hooked.sol` directly and confirming with two new tests:

- `test_executeKernelSwapUninstallHalfIsMediatedByOldKernel` — the uninstall half still sees the
  OLD kernel installed at modifier-entry time, so the old kernel's `preCheck`/`postCheck` DO fire.
  An account below the old kernel's reputation floor cannot swap it out at all.
- `test_executeKernelSwapInstallHalfIsUnmediated` — the install half runs immediately after, by
  which point the hook slot has already been cleared to `address(0)` by the uninstall half, so
  `withHook` fires no hook at all for that half — not even the new kernel's own `preCheck`. Proven
  by installing a new kernel with an unreachably high reputation floor and confirming the swap
  still succeeds; only a subsequent real `execute()` call, now routed through the new kernel,
  correctly rejects.

A design alternative considered and rejected: making `executeKernelSwap` bypass the outgoing
kernel entirely (via an explicit `AccountERC7579._uninstallModule(...)` base-qualified call,
skipping `withHook`), on the reasoning that gating governance behind the very system it might need
to escape risks a lockout. Rejected because, with atomic swap already removing the "leaves the
account permanently unhooked" failure mode, the remaining lockout surface is narrow: a swap moves
zero native value, so only the reputation-floor and assurance-tier checks can block it, never the
budget check. A below-floor or non-boosted account being temporarily unable to replace its own
kernel — including replacing it with something more permissive — is a real, disclosed limitation,
but a materially smaller and more honest one than silently carving an unmediated path through a
guarantee this session has otherwise gone to some length to keep intact.

**Single-signer, not multi-party.** The timelock is the entire value this mechanism adds over
"permanently unreachable": it turns an instant, silent policy change into an observable,
time-bounded window. It does **not** provide the plan's full "timelocked + multi-party"
requirement — this account has exactly one ECDSA signer, so a compromised signing key can still
eventually force a kernel swap, just not instantly. A genuinely multi-party version is separate,
larger scope: this account's whole authority model (`SignerECDSA`, single key) would need to
change first.

## Scope: in

- `proposeKernelSwap(address newKernel)`, `executeKernelSwap(address newKernel)`,
  `cancelKernelSwap()`, `onlyEntryPointOrSelf`-gated, same as `execute()`.
- One pending-swap slot (`PendingKernelSwap{newKernel, readyAt}`), rejecting a second proposal
  while one is pending (`SwapAlreadyPending`) rather than silently overwriting it.
- `moduleActionTimelockSeconds` — immutable, set at construction, third constructor parameter.
- Tests (10 new, all in `contracts/test/IntegrityAccountV1Experimental.t.sol`): zero-kernel
  rejection, double-propose rejection, cancel-with-nothing-pending rejection,
  execute-with-nothing-pending rejection, parameter-mismatch rejection, premature-execution
  rejection, cancel-then-repropose-succeeds, a full successful swap (including a post-swap
  `execute()` proving the account remains functional), and the two mediation-asymmetry tests
  above.
- Mutation-tested the timelock check specifically (the mechanism's core security property):
  temporarily removed `block.timestamp < pending.readyAt`, confirmed
  `test_executeKernelSwapRevertsBeforeTimelockElapses` fails (swap goes through instantly),
  restored and verified byte-identical via `diff`.
- Full repo suite re-run clean: 236/236 (up from 226 — +10 for this change), replacing the stale
  17-tests/226-total figures the tracer-bullet doc previously quoted for this file.

## Scope: out

- Multi-party/quorum governance — separate, larger scope (see above).
- Any change to the budget, reputation-floor, or assurance-tier checks themselves.
- Deployment. This remains Foundry-test-only, same as every other Phase I slice artifact —
  deployment to Base Sepolia or any live network is explicitly excluded regardless of the
  standing goal.
- Caching/snapshotting `effectiveScore` to address the already-disclosed Table 4 gas overage —
  unrelated to this change, still open, still tracked in the tracer-bullet doc's "Known
  limitation" section.

## What this does NOT prove

- Does not make the account general-purpose or upgradeable — the kernel *type* the account will
  ever accept is unconstrained (any address can be proposed as `newKernel`; nothing here verifies
  the proposed address is a genuine, well-behaved `IERC7579Hook` implementation), so a
  maliciously-crafted `newKernel` is exactly as dangerous as it would be if `installModule` were
  simply re-enabled outright, just delayed by the timelock and observable during the window.
- Does not close the lockout surface named above — a below-floor or non-boosted account cannot
  replace its own kernel until it requalifies. Accepted, not solved.
- Does not audit or formally verify the swap's atomicity — "no reachable zero-hook state" is
  argued from reading `AccountERC7579Hooked`'s source and confirmed by tests exercising the
  documented behavior, not by an external audit or a machine-checked invariant.

## Devil's Advocate review and response (2026-08-17, same day)

A focused adversarial review (independent subagent, given the full diff, the OZ base source, the
test suite, and this doc) was run before landing, attacking six named areas: malicious
replacement-kernel installation, the unmediated install half, single-signer governance, recovery
lockout, kernel interface/code-hash validation, and the "complete mediation" claim. Full findings
are in the session transcript; summarized here with what changed in response.

**Top-line verdict: add code-level mitigations before shipping (not ship-as-is, not revert).**

**Fixed in code, not just documented:**
- **Zero timelock was accepted with no validation.** The constructor took
  `moduleActionTimelockSeconds_` with no floor check — a `0` value made `executeKernelSwap`
  immediately callable in the same transaction as `proposeKernelSwap`, silently voiding the
  entire mechanism's value proposition, confirmed by a disposable repro during review. Fixed:
  constructor now reverts `ZeroTimelock()` on a zero value, matching the same input-validation
  discipline `IntegrityKernelV1Experimental`'s own constructor already applies to its analogous
  immutables. Regression test: `test_constructorRevertsOnZeroTimelock`, mutation-tested.
- **No interface probe on the proposed kernel.** `proposeKernelSwap` accepted any non-zero
  address with zero validation, so a non-conforming address (wrong address, EOA, unrelated
  contract) would only fail *after* the timelock had already elapsed, at `executeKernelSwap`
  time. Fixed: `proposeKernelSwap` now probes `newKernel.isModuleType(MODULE_TYPE_HOOK)` and
  reverts `NewKernelNotAHookModule` immediately if it returns false. Regression test:
  `test_proposeKernelSwapRevertsOnNonConformingKernel`, mutation-tested. **This is a partial
  mitigation, explicitly not a full one** — see below.

**Disclosed more precisely (NatSpec + this doc), not code-fixed — genuinely unfixable at this
scope without re-architecting:**
- **A conforming-but-hostile kernel still bricks the account with no rescue path.** The
  `isModuleType` probe only catches non-conforming addresses. A kernel that passes the probe but
  reverts unconditionally in `preCheck` installs cleanly, then permanently blocks every future
  `execute()` — AND blocks every rescue swap too, because `executeKernelSwap`'s own uninstall
  half must call the broken kernel's `preCheck` first. This is *worse* than simply re-enabling
  `installModule` outright (a bad kernel there fails instantly and visibly; here it can fail
  catastrophically later, with no way back). No code fix exists for this within swap-only,
  mediated-uninstall design — it is the direct cost of the two decisions this proposal already
  made deliberately (swap-only, and mediated-not-bypassed). Made into a permanent regression
  fixture, not just prose: `test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath`.
  The contract's top-level NatSpec and this doc's "What this does NOT prove" section are both
  corrected to state this plainly — the earlier framing ("locked out... until it requalifies")
  was incomplete; that describes only the *recoverable* reputation-floor case, not this
  unrecoverable one.
- **Reentrancy window on both swap halves.** `AccountERC7579Hooked` sets `_hook` storage to the
  new address *before* calling that module's `onInstall`/`onUninstall` lifecycle hook. So a
  hostile new kernel's `onInstall` runs already self-mediated (any reentrant `execute()` would be
  checked by the attacker's own contract, inside the same atomic transaction, before external
  observability matters) — and symmetrically, if the *outgoing* kernel was already compromised,
  its `onUninstall` runs with no hook mediating it at all. Neither window is closed by this
  slice; both are now named explicitly in the contract's NatSpec rather than left implicit.
- **Removal-vs-installation asymmetry, stated precisely.** The original disclosure said the swap
  is "only partially mediated." The review's framing is more precise and is now the doc's
  framing: *removal* of the old kernel is genuinely content-gated (reputation floor + assurance
  tier — real security-relevant checks), while *installation* of the new kernel is gated only by
  the `isModuleType` probe and elapsed time, never by a check with security content. This is why
  the mechanism should be read as satisfying the whitepaper's condition (iii) for removal, not
  installation — not a uniform "constrained transition" claim.

**Reviewed and confirmed already correctly bounded, no change needed:**
- **Single-signer governance.** Confirmed against OZ's `Account.sol`: `onlyEntryPointOrSelf`
  admits only the canonical EntryPoint or `address(this)`; no validator modules are installable
  (fully disabled elsewhere in this contract), so the only real path is a UserOperation signed by
  the one `SignerECDSA` key. The "single-signer-timelocked, not multi-party" framing was already
  accurate. Gap found and closed: no test previously asserted a third party is rejected — added
  `test_governanceFunctionsRevertForNonSelfNonEntryPointCaller`.
- **Test-assertion gap.** `test_executeKernelSwapUninstallHalfIsMediatedByOldKernel` claimed in a
  comment that a reverted swap leaves the pending proposal untouched but never asserted it. Fixed
  — the test now asserts `pendingKernelSwap` explicitly.
- **Foundry double-`vm.warp` optimizer artifact.** The reviewer found and reproduced a case where
  a second `vm.warp` call within one test function can silently fail to advance
  `block.timestamp` under this repo's exact optimizer settings. `test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath`
  genuinely needs two sequential timelocked actions and therefore two `vm.warp` calls — rather
  than assume the landmine applies here, it was checked directly: the test asserts the *specific*
  custom-error selector (`AlwaysReverts`, not a generic revert or `TimelockNotElapsed`), which
  would only pass if `block.timestamp` genuinely advanced both times. It passes. Documented
  in-test rather than worked around, since the workaround (splitting into contrived, artificial
  test structure) would be worse than a verified-safe direct approach.

**Test suite after these fixes:** `contracts/test/IntegrityAccountV1Experimental.t.sol` at
31 tests (up from the pre-review 27, +4 for the review-driven fixes and their regressions). Full
repo suite: 240/240 (up from 236 pre-review).

## Decision

Authorized under the standing goal. Documented here, per this session's standing commitment to
disclose reversals plainly rather than let downstream docs drift out of sync with what the code
actually does. Shipped only after the Devil's Advocate review above and its code-level fixes,
per this session's own governance-review discipline for foundational security/identity-boundary
changes.
