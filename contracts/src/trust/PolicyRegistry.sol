// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {IPolicyModule} from "./IPolicyModule.sol";

/// @title PolicyRegistry
/// @notice Pluggable policy gate: per-domain / per-agent compliance modules, plus a per-domain
/// Merkle commitment to the allowed action graph (edges bound to a target selector and risk weight).
contract PolicyRegistry is AccessControl {
    bytes32 public constant GRAPH_CURATOR_ROLE = keccak256("GRAPH_CURATOR_ROLE");

    mapping(bytes32 => IPolicyModule) public moduleOf;
    mapping(address => IPolicyModule) public agentOverrideOf;
    mapping(bytes32 => bytes32) public graphRootOf;
    mapping(bytes32 => uint256) public domainFloor;

    event ModuleSet(bytes32 indexed domainId, address indexed module);
    event AgentOverrideSet(address indexed agent, address indexed module);
    event GraphRootSet(bytes32 indexed domainId, bytes32 root);
    event DomainFloorSet(bytes32 indexed domainId, uint256 floorWei);

    error NoModuleConfigured();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(GRAPH_CURATOR_ROLE, admin);
    }

    function setModule(bytes32 domainId, address module) external onlyRole(DEFAULT_ADMIN_ROLE) {
        moduleOf[domainId] = IPolicyModule(module);
        emit ModuleSet(domainId, module);
    }

    function setAgentOverride(address agent, address module) external onlyRole(DEFAULT_ADMIN_ROLE) {
        agentOverrideOf[agent] = IPolicyModule(module);
        emit AgentOverrideSet(agent, module);
    }

    function setDomainFloor(bytes32 domainId, uint256 floorWei) external onlyRole(DEFAULT_ADMIN_ROLE) {
        domainFloor[domainId] = floorWei;
        emit DomainFloorSet(domainId, floorWei);
    }

    function setGraphRoot(bytes32 domainId, bytes32 root) external onlyRole(GRAPH_CURATOR_ROLE) {
        graphRootOf[domainId] = root;
        emit GraphRootSet(domainId, root);
    }

    /// @notice Consults the agent's override module if set, else the domain module.
    /// @dev Reverts `NoModuleConfigured` if neither exists.
    function checkCompliance(address agent, bytes32 domainId, address target, bytes calldata data)
        external
        view
        returns (bool allowed, uint16 riskWeightBps)
    {
        IPolicyModule module = agentOverrideOf[agent];
        if (address(module) == address(0)) module = moduleOf[domainId];
        if (address(module) == address(0)) revert NoModuleConfigured();
        return module.checkCompliance(agent, domainId, target, data);
    }

    /// @notice Canonical graph-edge leaf. Byte-for-byte contract with the Cortex (Python) side.
    /// @dev `abi.encode` of six fields (6 x 32 bytes = 192 bytes; `address`, `bytes4` and `uint16`
    /// are each padded to a full word). This 192-byte preimage is distinct from an internal Merkle
    /// node preimage (two concatenated 32-byte hashes = 64 bytes), so a leaf can never be confused
    /// with an internal node: no second-preimage ambiguity, which is why plain sorted-pair
    /// `MerkleProof.verify` is safe here.
    ///
    /// `target` binds the edge to the SPECIFIC callee contract (anti-bypass: one proof no longer
    /// authorizes the same selector against any target). `targetSelector` is kept separate from the
    /// full calldata deliberately — the Cortex tool-call-graph action space must be able to express
    /// "tool X with any args", so arguments are NOT hashed in.
    function leafOf(
        bytes32 fromNode,
        bytes32 relation,
        bytes32 toNode,
        address target,
        bytes4 targetSelector,
        uint16 riskWeightBps
    ) public pure returns (bytes32) {
        return keccak256(abi.encode(fromNode, relation, toNode, target, targetSelector, riskWeightBps));
    }

    /// @notice True iff the exact edge, including `target`, `targetSelector` and `riskWeightBps`, is
    /// committed under `graphRootOf[domainId]`. All fields are inside the leaf, so any mismatch
    /// yields a different leaf that is not in the tree.
    function checkGraphEdge(
        bytes32 domainId,
        bytes32 fromNode,
        bytes32 relation,
        bytes32 toNode,
        address target,
        bytes4 targetSelector,
        uint16 riskWeightBps,
        bytes32[] calldata proof
    ) external view returns (bool) {
        bytes32 leaf = leafOf(fromNode, relation, toNode, target, targetSelector, riskWeightBps);
        return MerkleProof.verifyCalldata(proof, graphRootOf[domainId], leaf);
    }
}
