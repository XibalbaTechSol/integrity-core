// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {IAnchorPolicy} from "../core/IAnchorPolicy.sol";

/// @title StateAnchor
/// @notice Anchors Merkle roots of the off-chain Trust Vault.
/// @dev Frozen bytecode per SPEC.md §5.3. Behavior changes only through
/// IAnchorPolicy. Existing storage declarations MUST remain ordered.
/// Tree convention: leaves keccak256(abi.encodePacked(leafData)); parents use
/// sorted-pair keccak256(a < b ? (a,b) : (b,a)).
contract StateAnchor is AccessControl {
    bytes32 public constant ANCHOR_ROLE = keccak256("ANCHOR_ROLE");

    bytes32 public latestRoot;
    uint256 public latestEpoch;
    uint256 public latestTimestamp;

    mapping(bytes32 => bool) public isAnchoredRoot;
    mapping(uint256 => bytes32) public rootAtEpoch;

    /// @notice Policy hook for anchoring. Mainnet deployments MUST set this before
    /// admitting production anchors; zero retains the disclosed development posture.
    IAnchorPolicy public anchorPolicy;

    event RootAnchored(uint256 indexed epoch, bytes32 indexed root, uint256 timestamp);
    event AnchorPolicyUpdated(address indexed oldPolicy, address indexed newPolicy);

    error EmptyRoot();
    error AnchorPolicyDenied();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(ANCHOR_ROLE, admin);
    }

    /// @notice Anchors a root for the next monotonic epoch.
    function anchorRoot(bytes32 root) external onlyRole(ANCHOR_ROLE) returns (uint256 epoch) {
        if (root == bytes32(0)) revert EmptyRoot();

        IAnchorPolicy policy = anchorPolicy;
        if (address(policy) != address(0)) {
            if (!policy.checkAnchor(msg.sender, root, latestEpoch + 1)) {
                revert AnchorPolicyDenied();
            }
        }

        epoch = ++latestEpoch;
        rootAtEpoch[epoch] = root;
        isAnchoredRoot[root] = true;
        latestRoot = root;
        latestTimestamp = block.timestamp;
        emit RootAnchored(epoch, root, block.timestamp);
    }

    /// @notice Replaces the anchoring policy. Governance custody is governed by SPEC §5.4.
    function setAnchorPolicy(IAnchorPolicy policy) external onlyRole(DEFAULT_ADMIN_ROLE) {
        emit AnchorPolicyUpdated(address(anchorPolicy), address(policy));
        anchorPolicy = policy;
    }

    function verifyLeaf(bytes32 root, bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        if (!isAnchoredRoot[root]) return false;
        return MerkleProof.verify(proof, root, leaf);
    }

    function verifyLeafAtLatest(bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        return MerkleProof.verify(proof, latestRoot, leaf);
    }
}
