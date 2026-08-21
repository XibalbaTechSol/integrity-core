// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IExecutionPolicy
/// @notice Swappable policy hook for SovereignAgent.execute (SPEC.md §5.3).
/// @dev A policy that returns false or reverts denies the requested execution.
interface IExecutionPolicy {
    /// @notice Called before SovereignAgent makes an external call.
    /// @param agent The SovereignAgent address.
    /// @param caller The controller requesting execution.
    /// @param target The proposed call target.
    /// @param value The proposed native-value transfer.
    /// @param data The proposed call data.
    /// @param nonce The execution nonce that would be consumed on success.
    /// @return allowed Whether the execution may proceed.
    function checkExecution(
        address agent,
        address caller,
        address target,
        uint256 value,
        bytes calldata data,
        uint256 nonce
    ) external view returns (bool allowed);
}
