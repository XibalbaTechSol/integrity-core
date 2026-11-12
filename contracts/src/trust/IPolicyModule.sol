// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IPolicyModule
/// @notice Pluggable per-domain (or per-agent) compliance check consulted by `PolicyRegistry`.
interface IPolicyModule {
    /// @param agent    The agent attempting the call.
    /// @param domainId The policy domain the agent operates in.
    /// @param target   The contract being called.
    /// @param data     The raw calldata of the call.
    /// @return allowed        Whether the call is compliant.
    /// @return riskWeightBps  Risk weight of the call, in basis points.
    function checkCompliance(address agent, bytes32 domainId, address target, bytes calldata data)
        external
        view
        returns (bool allowed, uint16 riskWeightBps);
}
