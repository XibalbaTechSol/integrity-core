// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccountERC7579Hooked} from "@openzeppelin/contracts/account/extensions/draft-AccountERC7579Hooked.sol";
import {AccountERC7579} from "@openzeppelin/contracts/account/extensions/draft-AccountERC7579.sol";
import {SignerECDSA} from "@openzeppelin/contracts/utils/cryptography/signers/SignerECDSA.sol";
import {MODULE_TYPE_HOOK, IERC7579Module} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";
import {ERC7579Utils, Mode, CallType, ExecType} from "@openzeppelin/contracts/account/utils/draft-ERC7579Utils.sol";

/// @title IntegrityAccountV1Experimental
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
///  - **Reentrancy window during the swap itself, on both halves.** `AccountERC7579Hooked`'s
///    `_installModule`/`_uninstallModule` update `_hook` storage BEFORE calling the module's own
///    `onInstall`/`onUninstall` lifecycle hook. So the new kernel's `onInstall` runs with `_hook`
///    already pointing at itself -- a hostile `newKernel.onInstall` that reenters `execute()`
///    would be mediated entirely by its own (attacker-controlled) `preCheck`/`postCheck`, inside
///    the same atomic swap transaction, before any external observer has a chance to react to the
///    new kernel appearing. Symmetrically, the OLD kernel's `onUninstall` runs with `_hook`
///    already cleared to `address(0)` -- if the outgoing kernel was itself already compromised, a
///    reentrant `execute()` from its `onUninstall` is mediated by nothing at all. Neither window
///    is closed by this slice; both are real, disclosed, unresolved risk surface.
///  - **Recovery lockout is broader than "requalify and retry."** An account below the outgoing
///    kernel's reputation floor or without its assurance tier cannot execute a swap at all -- but
///    that case is at least recoverable (regain reputation, retry). A SEPARATE and more severe
///    case has no recovery path whatsoever: if the currently-installed kernel's `preCheck` reverts
///    unconditionally (buggy, or maliciously crafted to look conformant at proposal time but
///    brick on the next call), every future `execute()` reverts forever, AND the rescue swap's own
///    uninstall half must call that same broken `preCheck` first -- so there is no way to swap
///    away from a bricked kernel either. Funds become stuck, not stolen, but irrecoverable. The
///    `isModuleType` probe in `proposeKernelSwap` narrows how a non-conforming address gets in but
///    cannot verify `preCheck`/`postCheck` correctness -- that remains fundamentally unenforceable
///    at the type level. See the proposal doc for why the rejected "bypass the outgoing kernel"
///    alternative was reconsidered but still not adopted for this slice.
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
///
/// See `IntegrityKernelV1Experimental` for exactly what guarantee the installed hook provides --
/// this account only guarantees that the hook fires on every reachable state-changing path
/// EXCEPT `approveKernelSwap` (and, for the swap's uninstall half, that the outgoing kernel's
/// hook fires on the governance path too), not what the hook itself checks.
contract IntegrityAccountV1Experimental is AccountERC7579Hooked, SignerECDSA {
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

    /// @dev Delay between proposing and executing a kernel swap. Immutable -- the delay itself
    /// cannot be shortened or lengthened after deployment, closing off "govern the governance"
    /// as an attack surface.
    ///
    /// **Deployment invariant with `IntegrityKernelV1Experimental.epochLengthSeconds`, if the
    /// bound kernel uses reputation epoch-snapshotting** (see that contract's own doc comment):
    /// this value should be `<= epochLengthSeconds` on the currently-installed kernel. If the
    /// timelock outlives the epoch, `executeKernelSwap`'s uninstall half (mediated by the
    /// outgoing kernel's `preCheck`) can revert `SnapshotStale` on a fully-vested swap for a
    /// reason unrelated to reputation, and a freshly-installed replacement kernel can be
    /// stale-on-arrival, immediately rejecting the account's first post-swap `execute()` call.
    /// Neither is destructive, but both are easy to mistake for a reputation problem. Nothing in
    /// either contract enforces this ordering across the two -- they are constructed
    /// independently and neither knows the other's parameters, so it is a deploy-time discipline,
    /// not a code-level guarantee. Found by an independent adversarial review, not caught at
    /// design time.
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

    /// @dev Guardian set is fixed forever at construction -- no add/remove/rotate path exists in
    /// this slice (see the proposal doc's "Scope: out"). `_isGuardian` avoids an array scan per
    /// `approveKernelSwap` call; `_guardians` itself is kept only so the set can be inspected
    /// off-chain, it is never iterated on-chain.
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

    constructor(
        address signerAddr,
        address kernel,
        uint256 moduleActionTimelockSeconds_,
        address[] memory guardians_,
        uint256 guardianThreshold_
    ) SignerECDSA(signerAddr) {
        // A zero timelock would make executeKernelSwap immediately callable in the same
        // transaction as proposeKernelSwap, silently voiding this mechanism's entire value
        // proposition over the tracer-bullet slice's original "permanently unreachable" design --
        // this is exactly the class of parameter IntegrityKernelV1Experimental's own constructor
        // already rejects for its analogous immutables (ZeroBudget, ZeroMinEffectiveScore).
        if (moduleActionTimelockSeconds_ == 0) revert ZeroTimelock();
        moduleActionTimelockSeconds = moduleActionTimelockSeconds_;

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

        _installModule(MODULE_TYPE_HOOK, kernel, "");
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
        if (!IERC7579Module(newKernel).isModuleType(MODULE_TYPE_HOOK)) {
            revert NewKernelNotAHookModule(newKernel);
        }
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
    function executeKernelSwap(address newKernel) external onlyEntryPointOrSelf {
        PendingKernelSwap memory pending = pendingKernelSwap;
        if (pending.readyAt == 0) revert NoSwapPending();
        if (pending.newKernel != newKernel) revert SwapMismatch(pending.newKernel, newKernel);
        if (block.timestamp < pending.readyAt) revert TimelockNotElapsed(pending.readyAt, block.timestamp);
        uint256 approvals = kernelSwapApprovalCount[kernelSwapNonce];
        if (approvals < guardianThreshold) revert InsufficientGuardianApprovals(approvals, guardianThreshold);

        delete pendingKernelSwap;
        address oldKernel = hook();
        _uninstallModule(MODULE_TYPE_HOOK, oldKernel, "");
        _installModule(MODULE_TYPE_HOOK, newKernel, "");
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
    /// delegating to the base class, which otherwise supports batch and delegatecall too.
    function _execute(Mode mode, bytes calldata executionCalldata) internal override returns (bytes[] memory) {
        (CallType callType, ExecType execType,,) = mode.decodeMode();
        bool allowed = callType == ERC7579Utils.CALLTYPE_SINGLE && execType == ERC7579Utils.EXECTYPE_DEFAULT;
        if (!allowed) revert UnsupportedExecutionMode(callType, execType);
        return super._execute(mode, executionCalldata);
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
