// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IAdapter
/// @notice The minimal shared interface every `AdapterRegistry`-registered adapter implements --
/// whitepaper §6's "transducer" concept (`ILicenceHook.sol`'s own doc comment covers the same
/// architectural choice in more depth; this is the generalized, registry-facing counterpart).
/// @dev Decided here, per `docs/plans/2026-08-25-phase3-adapter-registry-tracer-bullet-proposal.md`'s
/// own open question: typed parameters `(address subject, uint256 amount)`, not opaque
/// `bytes calldata` -- cheaper, clearer, and sufficient for both seed adapters
/// (`SpendBudgetAdapter`, `ReputationFloorAdapter`). A future adapter needing richer context is
/// real, separately-scoped follow-on work, not something this interface tries to anticipate.
/// Revert-to-reject, no bool/status return -- matches every existing check in this codebase's own
/// style (`ILicenceHook`, `IntegrityKernel`'s hook functions).
/// @dev Whether this interface and `ILicenceHook` should eventually merge is an explicitly open
/// question (see the design note above) -- NOT resolved by this interface's existence. Kept
/// deliberately separate for this slice.
interface IAdapter {
    /// @param subject The address this check evaluates against (an account, a consumer -- whoever
    /// the calling context resolves as the relevant party; `AdapterRegistry.evaluate` passes this
    /// through unchanged from its own caller, never substituting `msg.sender`).
    /// @param amount A single numeric parameter, meaning defined by the adapter itself (a spend
    /// amount for `SpendBudgetAdapter`, ignored by `ReputationFloorAdapter`). MUST revert to
    /// reject (whitepaper R2's totality obligation) -- returning normally means "allow."
    function check(address subject, uint256 amount) external;
}
