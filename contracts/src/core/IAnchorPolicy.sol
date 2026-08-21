// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IAnchorPolicy
/// @notice Swappable policy hook for StateAnchor.anchorRoot (SPEC.md §5.3).
/// @dev StateAnchor is frozen bytecode. This interface is the only post-deploy
/// behavior-change surface. A policy that returns false or reverts denies anchoring.
interface IAnchorPolicy {
    /// @notice Called before StateAnchor writes a root.
    /// @param caller The ANCHOR_ROLE holder requesting the anchor.
    /// @param root The proposed Merkle root.
    /// @param epoch The epoch that would be assigned on success.
    /// @return allowed Whether the root may be anchored.
    function checkAnchor(address caller, bytes32 root, uint256 epoch) external view returns (bool allowed);
}
