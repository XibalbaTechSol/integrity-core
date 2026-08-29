// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IAgentAuthorityResolver
/// @notice Profile-agnostic read surface for "is this address a registered agent, what is
/// its current AIS, and what StateAnchor backs its memory" — SPEC.md §3.4 Enclosed
/// Enterprise Profile requires this to not assume a full 6-contract clone set.
/// @dev Implementations MUST support both the sovereign-profile clone-set
/// (`XibalbaAgentRegistry.resolveAgent`) and an enterprise, anchor-only profile without
/// requiring callers to know which profile a given agent used at registration.
interface IAgentAuthorityResolver {
    /// @return True if `agent` is registered under either profile.
    function isAuthorityRegistered(address agent) external view returns (bool);

    /// @notice Current Agent Integrity Score for `agent`, resolved from whichever profile
    /// it registered under.
    /// @dev MUST revert (not return 0) if `agent` is not registered — callers must not be
    /// able to confuse "unregistered" with "registered, score 0".
    function getAis(address agent) external view returns (uint256);

    /// @notice The `StateAnchor` backing `agent`'s memory, for either profile.
    /// @dev MUST revert if `agent` is not registered.
    function getStateAnchor(address agent) external view returns (address);
}
