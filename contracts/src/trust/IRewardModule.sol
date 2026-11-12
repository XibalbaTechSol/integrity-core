// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IRewardModule
/// @notice Pluggable per-domain positive-reward handler, invoked by `RewardRegistry` on a positive checkpoint.
interface IRewardModule {
    /// @param agent    The agent whose trust score checkpointed.
    /// @param oldScore The previous score.
    /// @param newScore The new score.
    /// @param domainId The domain the checkpoint belongs to.
    function onPositiveCheckpoint(address agent, uint32 oldScore, uint32 newScore, bytes32 domainId) external;
}
