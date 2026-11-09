// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/// @title ActionAnchor
/// @notice Per-agent Merkle-root anchor for the Integrity Protocol v2 trust layer. Each agent
/// anchors roots of its own action log under its own address; the caller IS the namespace, so
/// no role gate is needed. Unlike `StateAnchor` (one global root), every agent has an
/// independent epoch counter and latest root.
/// @dev Sorted-pair Merkle proofs (OZ `MerkleProof.verify`), as in `StateAnchor`: the root is a
/// function of the leaf set, not of leaf arrangement.
contract ActionAnchor {
    mapping(address agent => bytes32) public latestRoot;
    mapping(address agent => uint256) public epoch;

    event RootAnchored(address indexed agent, uint256 epoch, bytes32 root);

    error EmptyRoot();

    /// @notice Anchors `root` as the caller's latest root and advances the caller's epoch.
    /// @return newEpoch The caller's epoch after this anchor.
    function anchorRoot(bytes32 root) external returns (uint256 newEpoch) {
        if (root == bytes32(0)) revert EmptyRoot();
        newEpoch = ++epoch[msg.sender];
        latestRoot[msg.sender] = root;
        emit RootAnchored(msg.sender, newEpoch, root);
    }

    /// @notice Verifies `leaf` is included under `agent`'s latest anchored root.
    /// @dev Only the latest root counts. An agent with no anchor verifies nothing, since
    /// `latestRoot` is zero and `MerkleProof.verify` cannot match a zero root for a real leaf.
    function verifyLeaf(address agent, bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        bytes32 root = latestRoot[agent];
        if (root == bytes32(0)) return false;
        return MerkleProof.verify(proof, root, leaf);
    }
}
