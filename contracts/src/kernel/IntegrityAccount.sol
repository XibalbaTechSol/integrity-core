// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccountERC7579Hooked} from "@openzeppelin/contracts/account/extensions/draft-AccountERC7579Hooked.sol";
import {AccountERC7579} from "@openzeppelin/contracts/account/extensions/draft-AccountERC7579.sol";
import {SignerECDSA} from "@openzeppelin/contracts/utils/cryptography/signers/SignerECDSA.sol";
import {MODULE_TYPE_HOOK, IERC7579Module} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";
import {ERC7579Utils, Mode, CallType, ExecType} from "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";

/// @dev Minimal marker interface for the epoch-length deployment-invariant probe (see
/// `_checkEpochCompatibility` below). Deliberately NOT a requirement every hook module must
/// implement -- only `IntegrityKernel` (and any future kernel that opts into the
/// same epoch-snapshotting pattern) implements this; a `newKernel` that doesn't is not rejected,
/// just not checked. See the account's own `moduleActionTimelockSeconds` doc comment for the
/// full disclosed fail-open caveat this implies.
interface IEpochSnapshotting {
    function epochLengthSeconds() external view returns (uint256);
}

/// @title IntegrityAccount
/// @notice Phase I tracer-bullet slice (docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md),
/// extended with a timelocked, atomic kernel-swap governance mechanism
/// (docs/plans/2026-08-17-phase1-module-governance-proposal.md). **This reverses a previously
/// committed claim** -- the tracer-bullet slice and its two adapter extensions all stated module
/// mutation is "permanently unreachable by construction"; that is no longer true. See the
/// proposal doc for the reversal stated plainly.
/// @dev NOT the full Phase I `IntegrityAccount` the plan describes, and NOT a general-purpose
/// ERC-4337/ERC-7579 account. Deliberately narrow, by construction rather than by policy:
///
///  - Non-upgradeable. No proxy, no upgrade path, immutable kernel binding set once at
///    construction via a direct internal `_installModule` call (never the external,
///    `onlyEntryPointOrSelf`-gated `installModule`).
///  - Exactly one hook module, always. There is never a legitimate reason for this account to
///    hold zero or two hook modules, so governance is modelled as a single atomic **swap**
///    (`proposeKernelSwap`/`executeKernelSwap`/`cancelKernelSwap` below), not generic
///    install/uninstall. An earlier draft of this mechanism exposed independent install and
///    uninstall actions; that was deleted before landing because in a one-hook-slot account its
///    only reachable outcome -- uninstall with nothing queued to replace it -- is exactly the
///    "the agent can simply uninstall its own supervisor" failure the whitepaper names as fatal
///    to complete mediation. Swap-only removes that state entirely: there is no `executeKernelSwap`
///    call that leaves the account with zero installed hook, because both halves happen in one
///    transaction.
///  - The swap is gated by a mandatory timelock -- reachable, but only after a declared delay,
///    never immediately. **This is explicitly single-signer-timelocked, NOT the plan's full
///    "timelocked + multi-party" requirement** -- this account has exactly one ECDSA signer
///    (`SignerECDSA`), so a compromised signing key can still eventually force a kernel swap,
///    just not instantly. The delay is the entire value this mechanism adds over the tracer-
///    bullet slice's original "permanently unreachable" design: it turns an instant, silent
///    policy change into an observable, time-bounded window. It does NOT provide the
///    independent-quorum property real multi-party governance would. See the proposal doc for
///    why a genuinely multi-party version is separate, larger scope (this account's whole
///    authority model is single-signer).
///  - **The swap is asymmetrically mediated, verified rather than assumed** (see
///    `test_executeKernelSwapUninstallHalfIsMediatedByOldKernel` and
///    `test_executeKernelSwapInstallHalfIsUnmediated`): `_uninstallModule` and `_installModule`
///    are each independently wrapped by the base class's own `withHook` modifier, which captures
///    the currently-installed hook address at the START of each call. The uninstall call still
///    sees the old kernel installed, so the old kernel's `preCheck`/`postCheck` DO fire around
///    it -- REMOVAL of the old kernel is genuinely content-gated (reputation floor + assurance
///    tier; budget is unaffected either way, since a swap moves zero native value). The
///    immediately following install call sees the hook slot already cleared (`address(0)`), so
///    it fires no hook at all -- INSTALLATION of the new kernel is gated only by
///    `proposeKernelSwap`'s superficial `isModuleType` probe and elapsed time, never by any
///    check with security content. Whatever guarantee this account had before a swap is only as
///    strong as whatever the newly-installed kernel chooses to assert going forward -- this is
///    why this mechanism should NOT be read as fully satisfying the whitepaper's condition (iii)
///    for the installation half, only for removal.
///  - **Reentrancy window during the swap itself, on both halves -- the reentrant-CALL half is
///    now closed, extended (docs/plans/2026-08-18-phase1-swap-reentrancy-guard-proposal.md).**
///    `AccountERC7579Hooked`'s `_installModule`/`_uninstallModule` update `_hook` storage BEFORE
///    calling the module's own `onInstall`/`onUninstall` lifecycle hook, so the new kernel's
///    `onInstall` runs with `_hook` already pointing at itself, and the old kernel's `onUninstall`
///    runs with `_hook` already cleared. This claim was previously stated in terms of a hostile
///    kernel reentering `execute()` -- imprecise: `execute()` is `onlyEntryPointOrSelf`-gated, so
///    a kernel contract (whose caller identity is its own address, neither `self` nor the entry
///    point) could never reach it directly. The ACTUALLY reachable path is `fallback()`, which has
///    NO access restriction and routes through the same `withHook`-wrapped `_fallback`. `swapInProgress`
///    now makes both `_execute` and `_fallback` revert unconditionally (`ReentrantDuringSwap`) for
///    the swap's duration, regardless of what `_hook` points at mid-swap -- proven, not assumed,
///    by `test_reentrantFallbackDuringInstallIsRejected`/`test_reentrantFallbackDuringUninstallIsRejected`,
///    which confirm the revert reason genuinely changes (not just that some revert occurs) between
///    guarded and unguarded behavior. **Does NOT reorder or reimplement OZ's own
///    `_installModule`/`_uninstallModule`** (deliberately -- forking a vendored security contract
///    was rejected in favor of blocking the actual attacker-reachable harm). A non-reentrant
///    observation of `_hook`'s transient value during a swap (e.g. reading state without calling
///    back in) is unaffected and was never the risk this closes -- see
///    `test_reentrancyDuringInstallAndUninstallObservesFreshApprovalsAndEmptyPending`.
///  - **Recovery lockout is broader than "requalify and retry" -- funds are no longer actually
///    irrecoverable, extended (docs/plans/2026-08-18-phase1-broken-kernel-rescue-proposal.md).**
///    An account below the outgoing kernel's reputation floor or without its assurance tier cannot
///    execute a swap at all -- but that case is at least recoverable (regain reputation, retry). A
///    SEPARATE and more severe case remains: if the currently-installed kernel's `preCheck`
///    reverts unconditionally, every future `execute()` reverts forever, AND the rescue swap's own
///    uninstall half must call that same broken `preCheck` first -- so there is still no way to
///    swap AWAY FROM a bricked kernel; the account itself never gets repaired. **What changed:**
///    this is now provably NOT the same as funds being irrecoverable. A true kernel-swap rescue
///    was investigated and found ARCHITECTURALLY IMPOSSIBLE at this layer -- `AccountERC7579Hooked`'s
///    `_hook` storage is `private`, and both its only mutation paths are unconditionally
///    `withHook`-wrapped, so no override point can clear it without asking the broken kernel's
///    permission first; only forking the base contract could bypass this, explicitly rejected
///    (see the reentrancy-guard proposal's own Shape A rejection, at much smaller scale). Instead,
///    `proposeGuardianRescueSweep`/`approveGuardianRescueSweep`/`executeGuardianRescueSweep` give
///    guardians (UNANIMOUS, plus an independently configurable `rescueTimelockSeconds`) a raw
///    value transfer that never touches `_hook`/`execute()`/`withHook` at all, sidestepping the
///    wall entirely rather than defeating it. Proven, not assumed, against the exact bricked
///    scenario a normal rescue swap cannot save:
///    `test_guardianRescueSweep_RecoversFundsFromAPermanentlyBrickedAccount`. **This is a
///    materially larger guardian power than any other in this contract, by deliberate user
///    decision:** because no on-chain check can distinguish "genuinely, permanently broken" from
///    "reverted on some past calls," this cannot be scoped to only-when-bricked -- it is a general
///    guardian-unanimous power to drain the account's native balance to an address of the
///    guardians' choosing, reachable at any time, the same tradeoff real-world social-recovery
///    wallets accept for their own backup-key quorums. The `isModuleType` probe in
///    `proposeKernelSwap` narrows how a non-conforming address gets in but cannot verify
///    `preCheck`/`postCheck` correctness -- that remains fundamentally unenforceable at the type
///    level, which is exactly why the sweep exists as a parallel, kernel-independent path rather
///    than trying to make the swap path itself unbrickable.
///  - `execute()` accepts ONLY `(CALLTYPE_SINGLE, EXECTYPE_DEFAULT)`. Batch, delegatecall, and
///    try-execution modes are rejected before reaching the base class's dispatch logic.
///  - This slice never exercises the ERC-4337 EntryPoint/UserOp/prefund path. `execute()` and
///    the governance functions below are reachable only via `onlyEntryPointOrSelf`'s "self"
///    branch in this slice's own test suite.
///  - **Guardian quorum gates `executeKernelSwap`, extended
///    (docs/plans/2026-08-18-phase1-multiparty-kernel-governance-proposal.md).** This is a
///    SECOND reversal of the "hook fires on every reachable state-changing path" guarantee,
///    alongside the swap's own install/uninstall mediation asymmetry already documented above:
///    `approveKernelSwap` is a new state-changing entry point that is deliberately
///    guardian-callable DIRECTLY, never routed through `execute()`/`_execute`/`withHook` --
///    gating a guardian's approval behind the account's own hook would be circular, since
///    guardians exist precisely to act when the account/kernel may itself be compromised or
///    non-conformant. `proposeKernelSwap` and `cancelKernelSwap` remain signer-only, unchanged
///    -- only `executeKernelSwap` additionally requires `guardianThreshold` independent guardian
///    approvals, scoped to the current `kernelSwapNonce` so a stale approval from a cancelled or
///    already-executed proposal can never count toward a later one. This closes unilateral swap
///    EXECUTION (a compromised signer alone can no longer force a swap through), NOT unilateral
///    swap DENIAL (a compromised signer can still park an unwanted proposal in the single
///    pending-swap slot indefinitely, since only the signer may cancel) -- see the proposal
///    doc's "What this does NOT prove" for why guardian-cancel was deliberately rejected. Also
///    NOT closed: the two reentrancy windows and the broken-kernel brick scenario already
///    disclosed above (orthogonal to who authorizes a swap), and the account's own day-to-day
///    `execute()` authority remains single-signer by design -- only the swap path gained a
///    second, independent authority axis. A guardian quorum also strictly lengthens real-world
///    elapsed time between propose and execute, making the timelock-vs-`epochLengthSeconds`
///    collision documented on `moduleActionTimelockSeconds` above materially more likely in
///    practice, not just in theory -- recoverable via the permissionless
///    `refreshReputationSnapshot()`, but easy to mistake for a reputation problem.
///  - **Guardian emergency action closes unilateral swap DENIAL, extended
///    (docs/plans/2026-08-18-phase1-guardian-swap-denial-proposal.md).** `approveKernelSwap`
///    above closed unilateral swap execution but explicitly left denial open: only the signer
///    could `proposeKernelSwap`/`cancelKernelSwap`, so an unresponsive signer left guardians with
///    nothing to act on, and an uncooperative signer could park a bad proposal forever.
///    `guardianProposeAction`/`approveGuardianAction`/`executeGuardianAction` add a THIRD
///    unmediated, signer-independent entry point (alongside `approveKernelSwap`'s own, per the
///    guardian-quorum paragraph above) that lets guardians force-cancel a stuck proposal or
///    force-propose a brand-new one with zero signer involvement -- but only at UNANIMOUS (N-of-N,
///    not `guardianThreshold`) approval, deliberately the highest bar in this contract, since this
///    is the one path where the signer's cooperation is not required at all. A force-propose
///    enacted this way bumps `kernelSwapNonce` exactly as a signer-originated
///    `proposeKernelSwap` does, so it is indistinguishable from one to every downstream check
///    (`approveKernelSwap`, `executeKernelSwap`'s quorum gate, the timelock). This does NOT close
///    guardian collusion/compromise at unanimity (same caveat as the M-of-N execution quorum,
///    just a higher bar), and does NOT address the broken-kernel brick scenario below (a
///    force-proposed swap's uninstall half still calls the outgoing kernel's `preCheck`, so a
///    kernel that reverts unconditionally there remains unrescuable by this mechanism alone).
///  - **Guardian-set rotation, extended
///    (docs/plans/2026-08-18-phase1-guardian-rotation-proposal.md).** The guardian set is no
///    longer permanently fixed at construction -- `proposeGuardianRotation`/
///    `approveGuardianRotation`/`executeGuardianRotation` let the CURRENT guardians add or remove
///    one guardian at a time, gated by UNANIMOUS approval (same bar as the emergency action
///    above), since changing who the guardians ARE is at least as sensitive as an emergency
///    action once they exist. `guardianThreshold` itself is NEVER rotatable -- immutable forever,
///    by deliberate user decision, closing off "guardians vote the bar down toward 1 and become
///    unstoppable" as an attack surface, the same reasoning `moduleActionTimelockSeconds`'s own
///    immutability already uses. A removal that would drop the guardian count below the immutable
///    threshold is rejected outright. Rotation is blocked while a kernel swap or guardian action
///    is pending, and neither of those may be proposed while a rotation is pending -- enforced
///    symmetrically in all three propose functions, so at most one guardian-relevant governance
///    process is ever in flight, which is what makes it safe to block rather than needing to
///    invalidate stale approvals on removal (the class of bug `kernelSwapNonce` already solved
///    once for proposal replay). This does NOT make the guardian mechanism resistant to key
///    compromise at unanimity threshold -- an attacker controlling every current guardian key can
///    rotate itself into a permanent, self-perpetuating set the same way any legitimate unanimous
///    quorum could; rotation changes WHO is trusted, it cannot make the underlying trust model
///    stronger than "the guardian keys are genuinely independent," the same caveat every guardian
///    mechanism in this contract already carries.
///
/// See `IntegrityKernel` for exactly what guarantee the installed hook provides --
/// this account only guarantees that the hook fires on every reachable state-changing path
/// EXCEPT `approveKernelSwap` (and, for the swap's uninstall half, that the outgoing kernel's
/// hook fires on the governance path too), not what the hook itself checks.
contract IntegrityAccount is AccountERC7579Hooked, SignerECDSA {
    using ERC7579Utils for Mode;

    error ModuleMutationDisabled();
    error UnsupportedExecutionMode(CallType callType, ExecType execType);
    error NoSwapPending();
    error SwapAlreadyPending();
    error SwapMismatch(address proposed, address executed);
    error TimelockNotElapsed(uint256 readyAt, uint256 currentTime);
    error ZeroKernel();
    error ZeroTimelock();
    error NewKernelNotAHookModule(address newKernel);
    error ZeroGuardian();
    error DuplicateGuardian(address guardian);
    error InvalidGuardianThreshold(uint256 threshold, uint256 guardianCount);
    error NotAGuardian(address caller);
    error GuardianNonceMismatch(uint256 expected, uint256 provided);
    error GuardianAlreadyApproved(address guardian, uint256 nonce);
    error InsufficientGuardianApprovals(uint256 approvals, uint256 threshold);
    error GuardianActionAlreadyPending();
    error NoGuardianActionPending();
    error GuardianActionNonceMismatch(uint256 expected, uint256 provided);
    error GuardianActionAlreadyApproved(address guardian, uint256 nonce);
    error InsufficientGuardianActionApprovals(uint256 approvals, uint256 required);
    error GuardianRotationInProgress();
    error GuardianRotationAlreadyPending();
    error NoGuardianRotationPending();
    error GuardianRotationNonceMismatch(uint256 expected, uint256 provided);
    error GuardianRotationAlreadyApproved(address guardian, uint256 nonce);
    error InsufficientGuardianRotationApprovals(uint256 approvals, uint256 required);
    error GuardianNotFound(address guardian);
    error GuardianRemovalWouldBreakThreshold(uint256 remainingGuardians, uint256 threshold);
    error ReentrantDuringSwap();
    error ZeroRescueRecipient();
    error RescueSweepAlreadyPending();
    error NoRescueSweepPending();
    error RescueSweepNonceMismatch(uint256 expected, uint256 provided);
    error RescueSweepAlreadyApproved(address guardian, uint256 nonce);
    error InsufficientRescueSweepApprovals(uint256 approvals, uint256 required);
    error RescueTimelockNotElapsed(uint256 readyAt, uint256 currentTime);
    error RescueSweepAmountExceedsBalance(uint256 requested, uint256 available);
    error RescueTransferFailed();
    error EpochTooShortForTimelock(uint256 kernelEpochLengthSeconds, uint256 moduleActionTimelockSeconds);

    /// @dev Delay between proposing and executing a kernel swap. Immutable -- the delay itself
    /// cannot be shortened or lengthened after deployment, closing off "govern the governance"
    /// as an attack surface.
    ///
    /// **Deployment invariant with `IntegrityKernel.epochLengthSeconds`, if the
    /// bound kernel uses reputation epoch-snapshotting** (see that contract's own doc comment):
    /// this value should be `<= epochLengthSeconds` on the currently-installed kernel. If the
    /// timelock outlives the epoch, `executeKernelSwap`'s uninstall half (mediated by the
    /// outgoing kernel's `preCheck`) can revert `SnapshotStale` on a fully-vested swap for a
    /// reason unrelated to reputation, and a freshly-installed replacement kernel can be
    /// stale-on-arrival, immediately rejecting the account's first post-swap `execute()` call.
    /// Neither is destructive, but both are easy to mistake for a reputation problem.
    ///
    /// **As of 2026-08-19, this is a code-level check, not only a deploy-time discipline --
    /// with one disclosed, deliberate gap.** The constructor and every path that can install a
    /// new kernel (`proposeKernelSwap`, `guardianProposeAction`'s force-propose branch) probe
    /// `newKernel.epochLengthSeconds()` (via `IEpochSnapshotting`, see above) and revert
    /// `EpochTooShortForTimelock` if it's shorter than this value. **The gap:** not every hook
    /// module implements `epochLengthSeconds()` at all -- a future, non-snapshotting kernel
    /// (e.g. budget-only, no reputation check) legitimately wouldn't. The probe is a `try`/
    /// `catch`: if the call reverts or the target has no such function, the check is SKIPPED
    /// for that kernel, not failed closed -- deliberately, so this invariant doesn't become a
    /// permanent tax on every future kernel this account can ever hold. This means a kernel
    /// that reverts on that specific call for an unrelated, transient reason would also silently
    /// skip the check; Solidity's `try`/`catch` cannot distinguish "doesn't implement this" from
    /// "implements it but is currently reverting." Only closes the case where the epoch value is
    /// checkable at all -- see `docs/plans/2026-08-18-phase1-epoch-timelock-invariant-proposal.md`
    /// for the two-options discussion and why Option B (this one) was chosen over requiring every
    /// kernel to implement the selector.
    uint256 public immutable moduleActionTimelockSeconds;

    struct PendingKernelSwap {
        address newKernel;
        uint256 readyAt;
    }

    /// @dev Single pending-swap slot, deliberately -- this account only ever has one hook
    /// module, so there is never a legitimate reason for two swaps to be in flight at once. A
    /// second `proposeKernelSwap` call while one is already pending must be rejected, not
    /// silently overwrite the first.
    PendingKernelSwap public pendingKernelSwap;

    /// @dev Closes the reentrant-`execute()` half of the two disclosed reentrancy windows during
    /// a kernel swap (docs/plans/2026-08-18-phase1-swap-reentrancy-guard-proposal.md) -- see
    /// `executeKernelSwap` and `_execute` below. Deliberately does NOT reorder or reimplement
    /// OZ's `_installModule`/`_uninstallModule` (that would fork a vendored security contract for
    /// behavior this codebase doesn't own); instead it makes the actual attacker-reachable harm --
    /// a reentrant `execute()` call mediated by whichever kernel `_hook` happens to point at
    /// mid-swap, either the attacker's own new kernel or nothing at all -- unconditionally revert
    /// for the swap's duration, regardless of what `_hook` points at.
    bool public swapInProgress;

    /// @dev Guardian set is set at construction and may change over time only via
    /// `proposeGuardianRotation`/`approveGuardianRotation`/`executeGuardianRotation` below (added
    /// 2026-08-18 -- this comment previously said the set was fixed forever, which stopped being
    /// true once rotation landed). `_isGuardian` avoids an array scan per `approveKernelSwap`
    /// call; `_guardians` itself is kept so the current set can be inspected off-chain and so
    /// rotation can compute `_guardians.length` for the removal-threshold check and unanimity
    /// requirements -- it is never iterated in a normal (non-rotation) call path.
    address[] private _guardians;
    mapping(address guardian => bool) private _isGuardian;

    /// @dev M-of-N threshold gating `executeKernelSwap` only -- `proposeKernelSwap` and
    /// `cancelKernelSwap` remain signer-only. Immutable: this slice has no guardian-set or
    /// threshold rotation mechanism.
    uint256 public immutable guardianThreshold;

    /// @dev Bumped once per `proposeKernelSwap` call. Scopes guardian approvals to exactly the
    /// proposal that was current when they were cast, so an approval can never be replayed
    /// against a later, different proposal (including a cancel-and-repropose of the SAME
    /// `newKernel` address) -- there is deliberately no separate clear-on-cancel or
    /// clear-on-execute bookkeeping; a new nonce alone makes prior approvals irrelevant.
    uint256 public kernelSwapNonce;

    mapping(uint256 nonce => mapping(address guardian => bool)) private _kernelSwapApprovals;
    mapping(uint256 nonce => uint256) public kernelSwapApprovalCount;

    event KernelSwapApproved(uint256 indexed nonce, address indexed guardian, address newKernel);

    /// @dev Emergency guardian-originated action, reachable WITHOUT any signer involvement --
    /// see docs/plans/2026-08-18-phase1-guardian-swap-denial-proposal.md. Closes the two denial
    /// gaps `approveKernelSwap` deliberately left open: a signer who never proposes anything at
    /// all (guardians previously had nothing to act on), and a signer who proposes then refuses
    /// to cancel (only the signer could cancel). Requires UNANIMOUS guardian approval --
    /// deliberately stricter than `guardianThreshold`, since this is the one path that lets
    /// guardians act entirely without the signer.
    struct GuardianAction {
        bool active;
        bool isCancel;
        address newKernel;
    }

    /// @dev Single pending-action slot, mirroring `pendingKernelSwap`'s own single-slot
    /// discipline -- there is never a legitimate reason for two guardian emergency actions to be
    /// in flight at once.
    GuardianAction public pendingGuardianAction;

    /// @dev Separate from `kernelSwapNonce` during the approval-gathering phase (a guardian
    /// action's target may not correspond to any real current swap nonce, e.g. when nothing is
    /// pending yet). Once a force-propose action is executed, it bumps `kernelSwapNonce` exactly
    /// as `proposeKernelSwap` does, so downstream `approveKernelSwap`/`executeKernelSwap` treat a
    /// guardian-originated proposal identically to a signer-originated one -- no separate
    /// execution-approval bookkeeping needed for the guardian path.
    uint256 public guardianActionNonce;

    mapping(uint256 nonce => mapping(address guardian => bool)) private _guardianActionApprovals;
    mapping(uint256 nonce => uint256) public guardianActionApprovalCount;

    event GuardianActionProposed(uint256 indexed nonce, bool isCancel, address newKernel);
    event GuardianActionApproved(uint256 indexed nonce, address indexed guardian);
    event GuardianActionExecuted(uint256 indexed nonce, bool isCancel, address newKernel);

    /// @dev Guardian-set rotation -- see docs/plans/2026-08-18-phase1-guardian-rotation-proposal.md.
    /// `guardianThreshold` itself is NEVER rotatable (stays immutable forever, same reasoning as
    /// `moduleActionTimelockSeconds`'s own immutability -- letting the required-approval COUNT
    /// change would let a subset of guardians vote the bar down toward "1" and become
    /// unstoppable). Only WHO counts as a guardian can change, one address at a time (add XOR
    /// remove), gated by UNANIMOUS approval from the CURRENT guardian set -- the same bar as the
    /// emergency guardian action, since changing who the guardians ARE is at least as sensitive as
    /// using an emergency path once they're established.
    struct GuardianRotation {
        bool active;
        bool isAddition;
        address guardian;
    }

    /// @dev Single pending-rotation slot, same discipline as `pendingKernelSwap`/
    /// `pendingGuardianAction`. A rotation may not be proposed while a kernel swap or guardian
    /// action is pending, and neither of those may be proposed while a rotation is pending --
    /// enforced in all three propose functions, so at most ONE guardian-relevant governance
    /// process is ever in flight at a time. This is what makes it safe to keep Trap 2 simple
    /// (block rotation during a pending swap) rather than needing to invalidate stale approvals on
    /// removal -- by construction, a swap can never start or be in flight while a rotation is.
    GuardianRotation public pendingGuardianRotation;

    uint256 public guardianRotationNonce;
    mapping(uint256 nonce => mapping(address guardian => bool)) private _guardianRotationApprovals;
    mapping(uint256 nonce => uint256) public guardianRotationApprovalCount;

    event GuardianRotationProposed(uint256 indexed nonce, bool isAddition, address guardian);
    event GuardianRotationApproved(uint256 indexed nonce, address indexed guardian);
    event GuardianRotationExecuted(uint256 indexed nonce, bool isAddition, address guardian);

    /// @dev Funds-recovery sweep for a permanently bricked kernel
    /// (docs/plans/2026-08-18-phase1-broken-kernel-rescue-proposal.md) -- see that mechanism's
    /// own doc comments below for why this exists and what it deliberately does NOT attempt.
    struct PendingRescueSweep {
        bool active;
        address payable to;
        uint256 amount;
        bool sweepFullBalance;
        uint256 readyAt;
    }

    PendingRescueSweep public pendingRescueSweep;
    uint256 public rescueSweepNonce;
    mapping(uint256 nonce => mapping(address guardian => bool)) private _rescueSweepApprovals;
    mapping(uint256 nonce => uint256) public rescueSweepApprovalCount;

    /// @dev Deliberately INDEPENDENT of `moduleActionTimelockSeconds` and, unlike it, deliberately
    /// permitted to be ZERO -- a user decision (2026-08-18), not a default: different deployments
    /// (e.g. different market verticals) may have genuinely different risk tolerances for how long
    /// a bricked account's funds should sit unrecoverable before a guardian-unanimous sweep can
    /// fire. Zero means instant-once-unanimous for a deployment that prioritizes recovery speed;
    /// a nonzero value gives an observable warning window before the single most powerful action
    /// in this contract executes, at literally no operational cost -- an already-bricked account
    /// has no normal activity a delay could interfere with.
    uint256 public immutable rescueTimelockSeconds;

    event GuardianRescueSweepProposed(
        uint256 indexed nonce, address indexed to, uint256 amount, bool sweepFullBalance, uint256 readyAt
    );
    event GuardianRescueSweepApproved(uint256 indexed nonce, address indexed guardian);
    event GuardianRescueSweepExecuted(uint256 indexed nonce, address indexed to, uint256 amountSent);

    constructor(
        address signerAddr,
        address kernel,
        uint256 moduleActionTimelockSeconds_,
        address[] memory guardians_,
        uint256 guardianThreshold_,
        uint256 rescueTimelockSeconds_
    ) SignerECDSA(signerAddr) {
        // A zero timelock would make executeKernelSwap immediately callable in the same
        // transaction as proposeKernelSwap, silently voiding this mechanism's entire value
        // proposition over the tracer-bullet slice's original "permanently unreachable" design --
        // this is exactly the class of parameter IntegrityKernel's own constructor
        // already rejects for its analogous immutables (ZeroBudget, ZeroMinEffectiveScore).
        if (moduleActionTimelockSeconds_ == 0) revert ZeroTimelock();
        moduleActionTimelockSeconds = moduleActionTimelockSeconds_;

        // rescueTimelockSeconds_ deliberately has NO zero check -- see its own doc comment.
        rescueTimelockSeconds = rescueTimelockSeconds_;

        // threshold >= 1 and <= guardians_.length together already exclude both the empty-set
        // and the zero-threshold case -- no separate check needed for either.
        if (guardianThreshold_ == 0 || guardianThreshold_ > guardians_.length) {
            revert InvalidGuardianThreshold(guardianThreshold_, guardians_.length);
        }
        for (uint256 i = 0; i < guardians_.length; i++) {
            address guardian = guardians_[i];
            if (guardian == address(0)) revert ZeroGuardian();
            if (_isGuardian[guardian]) revert DuplicateGuardian(guardian);
            _isGuardian[guardian] = true;
            _guardians.push(guardian);
        }
        guardianThreshold = guardianThreshold_;

        _checkEpochCompatibility(kernel);
        _installModule(MODULE_TYPE_HOOK, kernel, "");
    }

    /// @dev Probes `newKernel.epochLengthSeconds()` (if implemented -- see `IEpochSnapshotting`
    /// and `moduleActionTimelockSeconds`'s own doc comment for the full disclosed fail-open
    /// case) and reverts `EpochTooShortForTimelock` if the kernel's epoch is shorter than this
    /// account's timelock. Called from the constructor (genesis kernel) and every path that can
    /// queue a kernel swap (`proposeKernelSwap`, `guardianProposeAction`'s force-propose branch)
    /// -- a constructor-only check would leave every subsequently swapped-in kernel unchecked,
    /// which defeats the point given `executeKernelSwap` exists specifically to install a
    /// different kernel later.
    function _checkEpochCompatibility(address newKernel) private view {
        try IEpochSnapshotting(newKernel).epochLengthSeconds() returns (uint256 kernelEpochLengthSeconds) {
            if (kernelEpochLengthSeconds < moduleActionTimelockSeconds) {
                revert EpochTooShortForTimelock(kernelEpochLengthSeconds, moduleActionTimelockSeconds);
            }
        } catch {
            // newKernel doesn't implement epochLengthSeconds() at all (or reverted) -- the
            // invariant doesn't apply to it. Deliberate fail-open; see this function's own doc
            // comment and moduleActionTimelockSeconds's.
        }
    }

    /// @notice Returns the immutable guardian set.
    function guardians() external view returns (address[] memory) {
        return _guardians;
    }

    /// @notice A guardian's independent approval of the currently pending kernel swap.
    /// `expectedNonce` must match `kernelSwapNonce` exactly -- this is what prevents an approval
    /// cast against one proposal from silently counting toward a different one (including a
    /// cancel-and-repropose of the same `newKernel` address under a new nonce). Does NOT itself
    /// mutate `_hook`; only raises `executeKernelSwap`'s approval count for this nonce.
    /// @dev Deliberately NOT routed through `execute()`/`withHook` -- see the contract-level doc
    /// comment's guardian-quorum paragraph for why gating a guardian behind the account's own
    /// hook would be circular.
    function approveKernelSwap(uint256 expectedNonce, address newKernel) external {
        if (!_isGuardian[msg.sender]) revert NotAGuardian(msg.sender);
        if (pendingKernelSwap.readyAt == 0) revert NoSwapPending();
        if (expectedNonce != kernelSwapNonce) revert GuardianNonceMismatch(kernelSwapNonce, expectedNonce);
        if (pendingKernelSwap.newKernel != newKernel) revert SwapMismatch(pendingKernelSwap.newKernel, newKernel);
        if (_kernelSwapApprovals[kernelSwapNonce][msg.sender]) revert GuardianAlreadyApproved(msg.sender, kernelSwapNonce);

        _kernelSwapApprovals[kernelSwapNonce][msg.sender] = true;
        kernelSwapApprovalCount[kernelSwapNonce] += 1;
        emit KernelSwapApproved(kernelSwapNonce, msg.sender, newKernel);
    }

    /// @notice A guardian starts gathering unanimous consent for an emergency action: either
    /// force-cancelling the currently pending swap (`isCancel == true`, `newKernel` ignored), or
    /// force-proposing a new kernel swap with no signer involvement at all (`isCancel == false`).
    /// Only one guardian action may be pending at a time -- mirrors `pendingKernelSwap`'s own
    /// single-slot discipline. A force-propose while a swap is already pending must be resolved
    /// via a force-cancel action first (a separate, also-unanimous action) rather than atomically
    /// overriding it here -- keeps each guardian action's blast radius to exactly one state
    /// transition.
    /// @dev The same `isModuleType` probe and `_checkEpochCompatibility` check `proposeKernelSwap`
    /// uses are applied here too, so a non-conforming or epoch-incompatible `newKernel` fails
    /// fast at proposal time rather than after gathering unanimous approval for nothing.
    function guardianProposeAction(bool isCancel, address newKernel) external {
        if (!_isGuardian[msg.sender]) revert NotAGuardian(msg.sender);
        if (pendingGuardianAction.active) revert GuardianActionAlreadyPending();
        if (pendingGuardianRotation.active) revert GuardianRotationInProgress();
        if (!isCancel) {
            if (newKernel == address(0)) revert ZeroKernel();
            if (!IERC7579Module(newKernel).isModuleType(MODULE_TYPE_HOOK)) {
                revert NewKernelNotAHookModule(newKernel);
            }
            _checkEpochCompatibility(newKernel);
        }
        guardianActionNonce += 1;
        pendingGuardianAction = GuardianAction({active: true, isCancel: isCancel, newKernel: newKernel});
        emit GuardianActionProposed(guardianActionNonce, isCancel, newKernel);
    }

    /// @notice A guardian's independent approval of the currently pending guardian action.
    /// `expectedNonce` must match `guardianActionNonce` exactly, same replay protection
    /// `approveKernelSwap` applies to `kernelSwapNonce`.
    function approveGuardianAction(uint256 expectedNonce) external {
        if (!_isGuardian[msg.sender]) revert NotAGuardian(msg.sender);
        if (!pendingGuardianAction.active) revert NoGuardianActionPending();
        if (expectedNonce != guardianActionNonce) revert GuardianActionNonceMismatch(guardianActionNonce, expectedNonce);
        if (_guardianActionApprovals[guardianActionNonce][msg.sender]) {
            revert GuardianActionAlreadyApproved(msg.sender, guardianActionNonce);
        }
        _guardianActionApprovals[guardianActionNonce][msg.sender] = true;
        guardianActionApprovalCount[guardianActionNonce] += 1;
        emit GuardianActionApproved(guardianActionNonce, msg.sender);
    }

    /// @notice Clears a pending guardian action WITHOUT enacting it. Permissionless -- purely
    /// clears state, never advances anything, so there is no manipulation surface, matching
    /// `executeGuardianAction`'s own reasoning.
    /// @dev This is a genuine liveness fix, not a convenience: `executeGuardianAction` reverts if
    /// the world has moved on since the action was proposed (e.g. the signer independently
    /// cancelled the very swap guardians were unanimously force-cancelling, or proposed a
    /// different swap while a force-propose was in flight) -- and because a Solidity revert undoes
    /// every state change made earlier in the SAME call, including `delete pendingGuardianAction`,
    /// there was previously no way to clear a pending action once it could no longer execute. That
    /// permanently blocks every future `guardianProposeAction`/`proposeGuardianRotation` call
    /// (both check `pendingGuardianAction.active`; `proposeKernelSwap` does not and is unaffected
    /// -- the signer's own path was never gated on guardian-action state) from an entirely
    /// ordinary race, not an attack -- discovered while testing the rotation mechanism's
    /// cross-mechanism lock, fixed here rather than left disclosed-but-broken. Guardians must
    /// re-propose (and re-gather unanimous approval) after cancelling; this function itself does
    /// not require any approval, since clearing a stuck slot can never itself be harmful.
    function cancelPendingGuardianAction() external {
        if (!pendingGuardianAction.active) revert NoGuardianActionPending();
        delete pendingGuardianAction;
    }

    /// @notice Clears a pending guardian rotation WITHOUT enacting it -- e.g. guardians change
    /// their mind, or want to restart with different parameters. Permissionless, same reasoning
    /// as `cancelPendingGuardianAction`. Not required for liveness the way that function is
    /// (`executeGuardianRotation`'s own preconditions are unreachable in practice due to the
    /// cross-mechanism lock -- see that function's doc comment), added for parity and usability.
    function cancelPendingGuardianRotation() external {
        if (!pendingGuardianRotation.active) revert NoGuardianRotationPending();
        delete pendingGuardianRotation;
    }

    /// @notice Enacts the pending guardian action once every guardian (not merely
    /// `guardianThreshold`) has approved it. Permissionless -- like `refreshReputationSnapshot`,
    /// there is no manipulation surface over WHAT gets enacted once unanimity is genuinely
    /// reached, only a gas cost anyone may pay. A force-cancel clears `pendingKernelSwap` exactly
    /// as `cancelKernelSwap` does; a force-propose creates a brand-new proposal exactly as
    /// `proposeKernelSwap` does, including bumping `kernelSwapNonce`, so the guardian-originated
    /// proposal is indistinguishable from a signer-originated one to every downstream check.
    function executeGuardianAction() external {
        GuardianAction memory action = pendingGuardianAction;
        if (!action.active) revert NoGuardianActionPending();
        uint256 approvals = guardianActionApprovalCount[guardianActionNonce];
        uint256 required = _guardians.length;
        if (approvals < required) revert InsufficientGuardianActionApprovals(approvals, required);

        delete pendingGuardianAction;

        if (action.isCancel) {
            if (pendingKernelSwap.readyAt == 0) revert NoSwapPending();
            delete pendingKernelSwap;
        } else {
            if (pendingKernelSwap.readyAt != 0) revert SwapAlreadyPending();
            kernelSwapNonce += 1;
            pendingKernelSwap =
                PendingKernelSwap({newKernel: action.newKernel, readyAt: block.timestamp + moduleActionTimelockSeconds});
        }
        emit GuardianActionExecuted(guardianActionNonce, action.isCancel, action.newKernel);
    }

    /// @notice A guardian proposes adding a new guardian or removing an existing one -- one
    /// change at a time, never both in a single rotation, matching this contract's own
    /// single-pending-slot discipline elsewhere. `guardianThreshold` itself is never touched by
    /// rotation; a removal that would drop the guardian count below the immutable threshold is
    /// rejected outright rather than silently making quorum permanently unreachable.
    /// @dev Blocked while a kernel swap or guardian action is pending -- see the
    /// `GuardianRotation` struct's own doc comment for why this keeps Trap 2 (stale approvals on
    /// removal) a non-issue by construction rather than something to special-case.
    function proposeGuardianRotation(bool isAddition, address guardian) external {
        if (!_isGuardian[msg.sender]) revert NotAGuardian(msg.sender);
        if (pendingGuardianRotation.active) revert GuardianRotationAlreadyPending();
        if (pendingKernelSwap.readyAt != 0) revert SwapAlreadyPending();
        if (pendingGuardianAction.active) revert GuardianActionAlreadyPending();
        if (isAddition) {
            if (guardian == address(0)) revert ZeroGuardian();
            if (_isGuardian[guardian]) revert DuplicateGuardian(guardian);
        } else {
            if (!_isGuardian[guardian]) revert GuardianNotFound(guardian);
            if (_guardians.length - 1 < guardianThreshold) {
                revert GuardianRemovalWouldBreakThreshold(_guardians.length - 1, guardianThreshold);
            }
        }
        guardianRotationNonce += 1;
        pendingGuardianRotation = GuardianRotation({active: true, isAddition: isAddition, guardian: guardian});
        emit GuardianRotationProposed(guardianRotationNonce, isAddition, guardian);
    }

    /// @notice A guardian's independent approval of the currently pending rotation.
    /// `expectedNonce` must match `guardianRotationNonce` exactly, same replay protection every
    /// other nonce-scoped approval mapping in this contract applies.
    function approveGuardianRotation(uint256 expectedNonce) external {
        if (!_isGuardian[msg.sender]) revert NotAGuardian(msg.sender);
        if (!pendingGuardianRotation.active) revert NoGuardianRotationPending();
        if (expectedNonce != guardianRotationNonce) {
            revert GuardianRotationNonceMismatch(guardianRotationNonce, expectedNonce);
        }
        if (_guardianRotationApprovals[guardianRotationNonce][msg.sender]) {
            revert GuardianRotationAlreadyApproved(msg.sender, guardianRotationNonce);
        }
        _guardianRotationApprovals[guardianRotationNonce][msg.sender] = true;
        guardianRotationApprovalCount[guardianRotationNonce] += 1;
        emit GuardianRotationApproved(guardianRotationNonce, msg.sender);
    }

    /// @notice Enacts the pending rotation once every CURRENT guardian has approved it
    /// (unanimous -- same bar as the emergency guardian action). Permissionless, same reasoning
    /// as `executeGuardianAction`/`refreshReputationSnapshot`. Re-checks that no kernel swap or
    /// guardian action is pending even though the propose-time check already makes this
    /// unreachable by construction (defense in depth, matching this codebase's standing style).
    function executeGuardianRotation() external {
        GuardianRotation memory rotation = pendingGuardianRotation;
        if (!rotation.active) revert NoGuardianRotationPending();
        uint256 approvals = guardianRotationApprovalCount[guardianRotationNonce];
        uint256 required = _guardians.length;
        if (approvals < required) revert InsufficientGuardianRotationApprovals(approvals, required);
        if (pendingKernelSwap.readyAt != 0) revert SwapAlreadyPending();
        if (pendingGuardianAction.active) revert GuardianActionAlreadyPending();

        delete pendingGuardianRotation;

        if (rotation.isAddition) {
            _isGuardian[rotation.guardian] = true;
            _guardians.push(rotation.guardian);
        } else {
            _isGuardian[rotation.guardian] = false;
            uint256 len = _guardians.length;
            for (uint256 i = 0; i < len; i++) {
                if (_guardians[i] == rotation.guardian) {
                    _guardians[i] = _guardians[len - 1];
                    _guardians.pop();
                    break;
                }
            }
        }
        emit GuardianRotationExecuted(guardianRotationNonce, rotation.isAddition, rotation.guardian);
    }

    /// @notice A guardian proposes an emergency funds-recovery sweep of the account's native
    /// balance to `to`, gated by UNANIMOUS approval and `rescueTimelockSeconds`.
    /// @dev **Why this exists, and why it is a sweep rather than a kernel-swap rescue.** The
    /// broken-kernel brick scenario disclosed since §29 (a `preCheck` that reverts unconditionally
    /// permanently blocks `execute()` AND the normal rescue swap's own uninstall half, which must
    /// call that same broken `preCheck` first) was investigated for a true fix and found
    /// ARCHITECTURALLY IMPOSSIBLE at this layer, not merely difficult: `AccountERC7579Hooked`'s
    /// `_hook` storage slot is `private` to that base contract, and both of its only mutation
    /// paths (`_installModule`/`_uninstallModule`) are unconditionally wrapped by the `withHook`
    /// modifier in their own function bodies -- there is no override point that reaches `_hook`
    /// without triggering `preCheck` on whatever is currently installed. Bypassing this would
    /// require forking and reimplementing `AccountERC7579Hooked` itself, the same class of
    /// undertaking Shape A rejected at much smaller scale for the reentrancy guard
    /// (docs/plans/2026-08-18-phase1-swap-reentrancy-guard-proposal.md) -- explicitly not pursued
    /// here either, per user decision. This sweep sidesteps the wall entirely rather than trying
    /// to defeat it: it never touches `_hook`, `_installModule`, `_uninstallModule`, `execute()`,
    /// or `withHook` at all -- a raw low-level value transfer, gated only by this function's own
    /// guardian-unanimous/timelock checks. The account itself remains permanently unable to
    /// `execute()` after this -- this recovers FUNDS, it does not repair the account.
    /// @dev **A materially larger power than any other guardian mechanism in this contract, by
    /// deliberate user decision, not an oversight.** Every other guardian-gated action here
    /// affects governance (who is in charge, which kernel is installed) -- this is the first that
    /// directly moves value. Because a smart contract cannot verify on-chain whether the
    /// currently-installed kernel is genuinely, permanently broken (only that it reverted on some
    /// past calls), this cannot be scoped to "only when actually bricked" -- it is, and must be
    /// disclosed as, a general guardian-unanimous power to drain the account's native balance to
    /// an address of the guardians' choosing, reachable at any time, not only during a genuine
    /// emergency. Accepted explicitly by the user (2026-08-18) as the same tradeoff real-world
    /// social-recovery wallets make: a backup-key quorum that can always move funds, gated by the
    /// strongest approval bar this contract has (unanimous, matching the other emergency paths).
    function proposeGuardianRescueSweep(address payable to, uint256 amount, bool sweepFullBalance) external {
        if (!_isGuardian[msg.sender]) revert NotAGuardian(msg.sender);
        if (pendingRescueSweep.active) revert RescueSweepAlreadyPending();
        if (to == address(0)) revert ZeroRescueRecipient();
        rescueSweepNonce += 1;
        uint256 readyAt = block.timestamp + rescueTimelockSeconds;
        pendingRescueSweep = PendingRescueSweep({
            active: true,
            to: to,
            amount: amount,
            sweepFullBalance: sweepFullBalance,
            readyAt: readyAt
        });
        emit GuardianRescueSweepProposed(rescueSweepNonce, to, amount, sweepFullBalance, readyAt);
    }

    /// @notice A guardian's independent approval of the currently pending rescue sweep.
    function approveGuardianRescueSweep(uint256 expectedNonce) external {
        if (!_isGuardian[msg.sender]) revert NotAGuardian(msg.sender);
        if (!pendingRescueSweep.active) revert NoRescueSweepPending();
        if (expectedNonce != rescueSweepNonce) revert RescueSweepNonceMismatch(rescueSweepNonce, expectedNonce);
        if (_rescueSweepApprovals[rescueSweepNonce][msg.sender]) {
            revert RescueSweepAlreadyApproved(msg.sender, rescueSweepNonce);
        }
        _rescueSweepApprovals[rescueSweepNonce][msg.sender] = true;
        rescueSweepApprovalCount[rescueSweepNonce] += 1;
        emit GuardianRescueSweepApproved(rescueSweepNonce, msg.sender);
    }

    /// @notice Clears a pending rescue sweep without enacting it. Permissionless, same liveness
    /// reasoning as `cancelPendingGuardianAction` (docs/plans/2026-08-18-phase1-guardian-swap-denial-proposal.md's
    /// own liveness finding) -- without an unconditional way to clear a stuck pending sweep, a
    /// proposal targeting a `to` address guardians later reconsider would have no way to be
    /// abandoned and re-proposed.
    function cancelPendingGuardianRescueSweep() external {
        if (!pendingRescueSweep.active) revert NoRescueSweepPending();
        delete pendingRescueSweep;
    }

    /// @notice Enacts the pending rescue sweep once every guardian has approved it and
    /// `rescueTimelockSeconds` has elapsed. Permissionless, same reasoning as every other
    /// `execute*` function in this contract -- no manipulation surface once unanimity and the
    /// timelock are genuinely satisfied.
    /// @dev A raw low-level `.call` -- never routed through `execute()`/`_execute`/`withHook`,
    /// which is the entire point (see `proposeGuardianRescueSweep`'s doc comment).
    function executeGuardianRescueSweep() external {
        PendingRescueSweep memory sweep = pendingRescueSweep;
        if (!sweep.active) revert NoRescueSweepPending();
        uint256 approvals = rescueSweepApprovalCount[rescueSweepNonce];
        uint256 required = _guardians.length;
        if (approvals < required) revert InsufficientRescueSweepApprovals(approvals, required);
        if (block.timestamp < sweep.readyAt) revert RescueTimelockNotElapsed(sweep.readyAt, block.timestamp);

        delete pendingRescueSweep;

        uint256 amountToSend = sweep.sweepFullBalance ? address(this).balance : sweep.amount;
        if (!sweep.sweepFullBalance && amountToSend > address(this).balance) {
            revert RescueSweepAmountExceedsBalance(amountToSend, address(this).balance);
        }
        (bool success,) = sweep.to.call{value: amountToSend}("");
        if (!success) revert RescueTransferFailed();
        emit GuardianRescueSweepExecuted(rescueSweepNonce, sweep.to, amountToSend);
    }

    /// @notice Starts the timelock for a future swap of the currently installed kernel for
    /// `newKernel`. `onlyEntryPointOrSelf` -- same access control as `execute()` and the base
    /// class's own module functions, not a separate, weaker check.
    /// @dev Probes `newKernel.isModuleType(MODULE_TYPE_HOOK)` before committing to the timelock,
    /// so an address that doesn't even superficially conform to the hook-module interface (wrong
    /// address, EOA, unrelated contract) fails fast at proposal time rather than reverting the
    /// whole swap only after the delay has already elapsed. This is a real but partial
    /// mitigation: it cannot and does not verify that `newKernel`'s `preCheck`/`postCheck` are
    /// correct or non-hostile -- that remains fundamentally unenforceable at the type level, and
    /// a `newKernel` that passes this probe but reverts unconditionally in `preCheck` still
    /// permanently bricks the account's ability to `execute()` OR to swap away again (the rescue
    /// swap's own uninstall half must call the broken kernel's `preCheck` first). See the
    /// proposal doc's "What this does NOT prove" section -- this is a real, disclosed,
    /// unresolved risk for this experimental slice, not something this probe closes.
    function proposeKernelSwap(address newKernel) external onlyEntryPointOrSelf {
        if (newKernel == address(0)) revert ZeroKernel();
        if (pendingKernelSwap.readyAt != 0) revert SwapAlreadyPending();
        if (pendingGuardianRotation.active) revert GuardianRotationInProgress();
        if (!IERC7579Module(newKernel).isModuleType(MODULE_TYPE_HOOK)) {
            revert NewKernelNotAHookModule(newKernel);
        }
        _checkEpochCompatibility(newKernel);
        // Bumped BEFORE this proposal becomes current, so any approval a guardian casts against
        // it always targets a freshly-zeroed approval count -- no prior proposal's leftover
        // approvals (there are none stored under this new nonce) can carry over.
        kernelSwapNonce += 1;
        pendingKernelSwap =
            PendingKernelSwap({newKernel: newKernel, readyAt: block.timestamp + moduleActionTimelockSeconds});
    }

    /// @notice Aborts a pending swap before it's executed. `onlyEntryPointOrSelf` -- the same
    /// authority that can propose can also cancel; there is no separate, more restrictive
    /// cancellation path in this single-signer design.
    function cancelKernelSwap() external onlyEntryPointOrSelf {
        if (pendingKernelSwap.readyAt == 0) revert NoSwapPending();
        delete pendingKernelSwap;
    }

    /// @notice Executes a previously proposed kernel swap once its timelock has elapsed.
    /// `newKernel` must match the proposal exactly -- executing with a different address than
    /// what was proposed and observed is rejected, not silently substituted. Atomically
    /// uninstalls the current kernel and installs `newKernel` in the same call, so there is no
    /// intermediate state with zero hook modules installed. See the contract-level doc comment
    /// for exactly which half of this call the old kernel mediates.
    /// @dev Callable by the entry point, the account itself, OR any single guardian --
    /// deliberately NOT `onlyEntryPointOrSelf` alone, per
    /// docs/plans/2026-08-18-phase1-guardian-swap-denial-proposal.md. A guardian-force-proposed
    /// swap (see `executeGuardianAction`) would otherwise be permanently unfinishable if the
    /// signer that the whole mechanism exists to work around never calls this function --
    /// widening WHO may submit this call does not weaken WHAT is required for it to succeed: the
    /// four preconditions below (pending exists, address match, timelock elapsed, quorum met)
    /// are unchanged and still independently gate every caller, guardian or not. A single
    /// guardian submitting this call is not a second, lower-bar approval path -- by the time any
    /// caller can reach past these checks, `kernelSwapApprovalCount` has already independently
    /// reached `guardianThreshold` (or the swap was force-proposed at full unanimity), so this
    /// only changes who may act as the transaction submitter for an already-fully-authorized
    /// swap, not what authorizes it.
    function executeKernelSwap(address newKernel) external {
        if (msg.sender != address(this) && msg.sender != address(entryPoint()) && !_isGuardian[msg.sender]) {
            revert AccountUnauthorized(msg.sender);
        }
        PendingKernelSwap memory pending = pendingKernelSwap;
        if (pending.readyAt == 0) revert NoSwapPending();
        if (pending.newKernel != newKernel) revert SwapMismatch(pending.newKernel, newKernel);
        if (block.timestamp < pending.readyAt) revert TimelockNotElapsed(pending.readyAt, block.timestamp);
        uint256 approvals = kernelSwapApprovalCount[kernelSwapNonce];
        if (approvals < guardianThreshold) revert InsufficientGuardianApprovals(approvals, guardianThreshold);

        delete pendingKernelSwap;
        address oldKernel = hook();
        // Reentrancy guard around exactly the window where `_hook` is transiently either the
        // outgoing kernel (mid-uninstall) or the incoming one (mid-install) -- see
        // `swapInProgress`'s own doc comment and `_execute` below.
        swapInProgress = true;
        _uninstallModule(MODULE_TYPE_HOOK, oldKernel, "");
        _installModule(MODULE_TYPE_HOOK, newKernel, "");
        swapInProgress = false;
    }

    /// @dev The base class's own `installModule`/`uninstallModule` (immediate, `onlyEntryPointOrSelf`
    /// only) are disabled unconditionally -- module mutation is reachable ONLY through the
    /// timelocked swap pair above, never as a single-call shortcut.
    function installModule(uint256, address, bytes calldata) public pure override {
        revert ModuleMutationDisabled();
    }

    /// @dev See {installModule}.
    function uninstallModule(uint256, address, bytes calldata) public pure override {
        revert ModuleMutationDisabled();
    }

    /// @dev Rejects every execution mode except (CALLTYPE_SINGLE, EXECTYPE_DEFAULT) before
    /// delegating to the base class, which otherwise supports batch and delegatecall too. Also
    /// rejects ANY call while `swapInProgress` -- defense in depth for a genuinely self-originated
    /// reentrant `execute()` call (the same `self`-reentrancy shape
    /// `test_reentrantExecuteDuringAnInFlightCallIsRejected` already exercises via the kernel's
    /// own `armed` guard, now doubly covered here). NOTE: `execute()` itself is
    /// `onlyEntryPointOrSelf`-gated by the base class, so a hostile kernel's `onInstall`/
    /// `onUninstall` callback -- whose caller identity from the account's perspective is the
    /// KERNEL's own address, neither `self` nor the entry point -- could never reach this function
    /// directly in the first place. See `_fallback` below for the actually-reachable reentrant
    /// path an external, non-privileged caller (including a hostile kernel mid-callback) has.
    function _execute(Mode mode, bytes calldata executionCalldata) internal override returns (bytes[] memory) {
        if (swapInProgress) revert ReentrantDuringSwap();
        (CallType callType, ExecType execType,,) = mode.decodeMode();
        bool allowed = callType == ERC7579Utils.CALLTYPE_SINGLE && execType == ERC7579Utils.EXECTYPE_DEFAULT;
        if (!allowed) revert UnsupportedExecutionMode(callType, execType);
        return super._execute(mode, executionCalldata);
    }

    /// @dev `AccountERC7579`'s public `fallback(bytes calldata) external payable` has NO access
    /// restriction (unlike `execute()`, which is `onlyEntryPointOrSelf`) -- ANY caller, including
    /// a hostile kernel's `onInstall`/`onUninstall` callback mid-swap, can trigger it, and
    /// `AccountERC7579Hooked._fallback` wraps it in the same `withHook` modifier `_execute` uses.
    /// This IS the actually-reachable half of the two disclosed reentrancy windows the account's
    /// own doc comment describes as "a hostile `newKernel.onInstall` that reenters `execute()`" --
    /// the real bypass is through this unguarded fallback path, not the gated `execute()` function
    /// itself. Closed the same way: unconditionally reverts while `swapInProgress`, regardless of
    /// what `_hook` points at mid-swap.
    function _fallback() internal override returns (bytes memory) {
        if (swapInProgress) revert ReentrantDuringSwap();
        return super._fallback();
    }

    /// @dev AccountERC7579 and SignerECDSA both define this (AccountERC7579's own version
    /// deliberately disables raw signatures in favour of the ERC-7579 validator-module pattern
    /// -- see its own doc comment). This slice has no validator module (module mutation is fully
    /// disabled, see {installModule}), so it explicitly resolves the diamond in favour of the
    /// real ECDSA check.
    function _rawSignatureValidation(bytes32 hash, bytes calldata signature)
        internal
        view
        override(AccountERC7579, SignerECDSA)
        returns (bool)
    {
        return SignerECDSA._rawSignatureValidation(hash, signature);
    }
}
