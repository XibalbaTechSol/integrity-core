// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IAgentAuthorityResolver
/// @notice Read surface for "is this address a registered agent, and what is its current AIS".
/// @dev Registration v3: "registered" means bound as an actor in `AgentRegistry`
/// (`isRegisteredAgent`), and AIS is the latest `AISRegistry` checkpoint score.
interface IAgentAuthorityResolver {
    /// @return True if `agent` is bound as an actor of an `AgentRegistry` record.
    function isAuthorityRegistered(address agent) external view returns (bool);

    /// @notice Current Agent Integrity Score for `agent`, in BASIS POINTS (0..10000), the
    /// `AISRegistry` scale. A registered agent with no checkpoint yet reads 0.
    /// @dev MUST revert (not return 0) if `agent` is not registered — callers must not be
    /// able to confuse "unregistered" with "registered, score 0".
    function getAis(address agent) external view returns (uint256);
}
