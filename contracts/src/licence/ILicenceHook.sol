// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title ILicenceHook
/// @notice Minimal, bespoke precondition hook for `LicenceAccount.consume()`/`consumeWithIntent()`
/// -- whitepaper §5.3's "the same [kernel] mechanism serves both [agent accounts and licence
/// accounts]" claim, scoped down to what this slice actually proves.
/// @dev Deliberately NOT `IERC7579Hook` and NOT the whitepaper §6 permissionless adapter-registry
/// interface. `IntegrityKernel`/`IntegrityAccount` are ERC-4337 + ERC-7579; `LicenceAccount` is
/// ERC-6551 -- the earlier Phase II proposal
/// (`docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`) explicitly declined
/// combining both standards in one contract as its own, later, separately-scoped undertaking. This
/// interface is that later slice, kept intentionally narrow:
/// - **One hook per licence account, immutable at construction** -- not swappable/composable like
///   `IntegrityAccount`'s timelocked kernel-swap governance, and not a registry of many adapters
///   like whitepaper §6. `address(0)` disables it entirely, matching `IntegrityKernel.trackedToken`'s
///   own "zero disables, no separate flag" convention.
/// - **A single `preConsume` call, no `postConsume`.** `IntegrityKernel`'s `postCheck` exists to
///   verify a balance DELTA across the wrapped call (spend budget) -- `LicenceAccount.consume()`'s
///   royalty/volume-cap outcome is already fully determined by its own inputs before the hook runs,
///   so there is no analogous post-condition to check. If a future hook needs one, that is real,
///   separately-scoped follow-on work, not implied by this interface.
/// - **Revert-to-reject, no bool/hookData return.** Matches this account's own existing style
///   (`NotAuthorized`, `VolumeCapExceeded`, etc. -- custom errors, not status codes).
/// - **No declared gas bound and no metered-call enforcement.** Whitepaper §6.2's obligation R2
///   ("every adapter declares a worst-case gas bound, enforced by metered call") is NOT
///   implemented here -- a misbehaving or unbounded hook can make `consume()` arbitrarily
///   expensive or revert unconditionally. Disclosed, not mitigated, in this slice.
/// - **Additive only, by construction, not by an enforced rule.** This interface has no
///   `postCheck` counterpart to catch a hook that "relaxes" a check (whitepaper R4) -- a hook
///   simply cannot loosen `LicenceAccount`'s own volume-cap/royalty/expiry logic because it runs
///   as an independent precondition ANDed with them, not a replacement for them. `_consume()`
///   still enforces its own checks unconditionally.
interface ILicenceHook {
    /// @param account The `LicenceAccount` this hook is installed on (`address(this)` from the
    /// caller's perspective) -- passed explicitly so ONE hook deployment can safely serve
    /// multiple licence accounts without relying on `msg.sender` alone for context.
    /// @param consumer The address attempting to consume (`owner()` for `consume()`, the
    /// recovered EIP-712 signer for `consumeWithIntent()` -- NOT necessarily `msg.sender`, since
    /// `consumeWithIntent()` deliberately allows open relaying).
    /// @param units The requested consumption amount, pre-check (before `consumedUnits` is
    /// incremented).
    /// @param royaltyPaid The royalty amount this call will pay, pre-check (before it is
    /// transferred).
    /// @dev MUST revert (with a typed reason, whitepaper R2's totality obligation) to reject.
    /// Returning normally means "allow." Called AFTER `LicenceAccount`'s own volume-cap, royalty,
    /// and expiry checks already passed -- a hook adds a condition, it never substitutes for one.
    function preConsume(address account, address consumer, uint256 units, uint256 royaltyPaid) external;
}
