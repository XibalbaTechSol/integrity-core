// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title IAnchorPolicy
/// @notice Swappable check invoked by `StateAnchor.anchorRoot` before a root is written.
/// @dev SPEC.md §5.3. A missing policy (address(0) on the host) is the testnet skip path.
///      Once set, a false return or revert MUST fail closed (root is not written).
interface IAnchorPolicy {
    /// @param caller The `msg.sender` of `anchorRoot` (ANCHOR_ROLE holder).
    /// @param root Merkle root proposed for the next epoch.
    /// @param nextEpoch Epoch that would be assigned (`latestEpoch + 1`).
    /// @return allowed True iff the host may proceed to write the root.
    function check(address caller, bytes32 root, uint256 nextEpoch) external view returns (bool);
}
