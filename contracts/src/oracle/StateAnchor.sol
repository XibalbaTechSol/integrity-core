// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {IAnchorPolicy} from "../core/IAnchorPolicy.sol";

/// @title StateAnchor
/// @notice Anchors Merkle roots of the off-chain "Trust Vault" (the state integrity-oracle
/// recomputes for this agent). Bytecode is frozen after deploy; behavior changes only by
/// swapping `IAnchorPolicy` at the `anchorRoot` chokepoint (SPEC.md §5.3).
/// @dev Sorted-pair Merkle proofs: a different parent could be built from the same leaf set
/// by permuting left/right at each level; with sorted pairs there is exactly one valid parent
/// hash for a given set of two children, so the root is a true function of the *set* of leaves,
/// not their arrangement.
contract StateAnchor is AccessControl {
    bytes32 public constant ANCHOR_ROLE = keccak256("ANCHOR_ROLE");

    bytes32 public latestRoot;
    uint256 public latestEpoch;
    uint256 public latestTimestamp;

    /// @dev Every root we have ever anchored remains individually verifiable — a proof
    /// generated against last week's root must still verify today. Only `latestRoot`
    /// advances "what's current"; `isAnchoredRoot` never un-anchors an old root.
    mapping(bytes32 => bool) public isAnchoredRoot;
    mapping(uint256 => bytes32) public rootAtEpoch;

    /// @notice Swappable anchor policy. address(0) skips the check (testnet default).
    IAnchorPolicy public anchorPolicy;

    event RootAnchored(uint256 indexed epoch, bytes32 indexed root, uint256 timestamp);
    event AnchorPolicySet(address indexed policy);

    error EmptyRoot();
    error PolicyDenied();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ANCHOR_ROLE, admin);
    }

    function setAnchorPolicy(address policy_) external onlyRole(DEFAULT_ADMIN_ROLE) {
        anchorPolicy = IAnchorPolicy(policy_);
        emit AnchorPolicySet(policy_);
    }

    /// @notice Anchors a new Merkle root for the next epoch. Called by integrity-oracle's
    /// signer (or, cross-chain, indirectly via CCIPReputationBridge) each time it
    /// recomputes the Trust Vault.
    function anchorRoot(bytes32 root) external onlyRole(ANCHOR_ROLE) returns (uint256 epoch) {
        if (root == bytes32(0)) revert EmptyRoot();
        if (address(anchorPolicy) != address(0)) {
            if (!anchorPolicy.check(msg.sender, root, latestEpoch + 1)) revert PolicyDenied();
        }
        epoch = ++latestEpoch;
        rootAtEpoch[epoch] = root;
        isAnchoredRoot[root] = true;
        latestRoot = root;
        latestTimestamp = block.timestamp;
        emit RootAnchored(epoch, root, block.timestamp);
    }

    /// @notice Verifies that `leaf` is included under `root`, and that `root` is one
    /// that this contract has actually anchored (so a well-formed proof of an unanchored
    /// tree cannot be passed off as live).
    function verifyLeaf(bytes32 root, bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        if (!isAnchoredRoot[root]) return false;
        return MerkleProof.verify(proof, root, leaf);
    }

    /// @notice Convenience wrapper that verifies against the current `latestRoot`.
    function verifyLeafAtLatest(bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        return MerkleProof.verify(proof, latestRoot, leaf);
    }
}
