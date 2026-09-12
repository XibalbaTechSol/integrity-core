// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {XibalbaAgentRegistry} from "../framework/XibalbaAgentRegistry.sol";

interface IIntegrityAgentProfileURI {
    function profileURI() external view returns (string memory);
}

interface IIntegrityIdentitySubject {
    function agentDID() external view returns (string memory);
    function hasRole(bytes32 role, address account) external view returns (bool);
}

/// @title IntegrityIdentityReadV1
/// @notice Read-only identity discovery facade over XibalbaAgentRegistry.
/// @dev This facade is informed by the ERC-8004 draft but is deliberately NOT an ERC-8004
/// Identity Registry or ERC-721 implementation. It defines no token ids, ownership, transfers,
/// approvals, wallet proofs, metadata writes, reputation feedback, events, or ERC-165 support.
/// The returned profile URI is agent-controlled, unbounded, and unverified by this contract.
contract IntegrityIdentityReadV1 {
    bytes32 public constant INTERFACE_PROFILE = keccak256("xibalba.integrity.identity-read.v1");
    string public constant ERC8004_DRAFT_REFERENCE =
        "ethereum/ERCs@503591a6e80e6e1affdd6403341e25269141f046/ERCS/erc-8004.md";
    /// @dev sha256 of ERCS/erc-8004.md at the exact commit above (24470 bytes), so the pinned
    /// revision is independently checkable on-chain, not only in docs. Verified 2026-09-12: fetched
    /// via `gh api repos/ethereum/ERCs/contents/ERCS/erc-8004.md?ref=<commit>`, and `git
    /// hash-object` on the fetched bytes reproduced git blob 7653a80922c0bf0243669f30e7a2d4aabfe006aa,
    /// confirming this is the exact pinned-commit content, not a substituted or edited copy.
    bytes32 public constant ERC8004_DRAFT_CONTENT_SHA256 =
        0x249dc3d96ad7bbe4afd25cacd14be942eb87751abcf1608bab19a610f3c3f8a9;

    XibalbaAgentRegistry public immutable sourceRegistry;

    struct IdentityView {
        bytes32 didHash;
        address sovereignAgent;
        bytes32 domainId;
        uint256 registeredAt;
        XibalbaAgentRegistry.PrimitiveSet primitives;
    }

    error ZeroRegistry();
    error IdentityMappingMismatch(bytes32 requestedDIDHash, bytes32 reverseDIDHash);
    error DeclaredDIDUnavailable(address sovereignAgent);
    error DeclaredDIDMismatch(bytes32 registeredDIDHash, bytes32 declaredDIDHash);

    constructor(address registry_) {
        if (registry_ == address(0)) revert ZeroRegistry();
        sourceRegistry = XibalbaAgentRegistry(registry_);
    }

    /// @notice Explicit negative capability claim for integrations probing this facade.
    function isERC8004Conformant() external pure returns (bool) {
        return false;
    }

    function resolveDID(string calldata did) external view returns (IdentityView memory) {
        bytes32 didHash_ = sourceRegistry.didHash(did);
        return _toView(didHash_, sourceRegistry.resolveDID(did));
    }

    function resolveDIDHash(bytes32 didHash_) public view returns (IdentityView memory) {
        return _toView(didHash_, sourceRegistry.resolveDIDHash(didHash_));
    }

    function resolveAgent(address sovereignAgent) public view returns (IdentityView memory) {
        XibalbaAgentRegistry.AgentRecord memory record = sourceRegistry.resolveAgent(sovereignAgent);
        return _toView(sourceRegistry.didHashOf(sovereignAgent), record);
    }

    /// @notice Returns the live, agent-controlled profile pointer without interpreting it.
    function profileURI(bytes32 didHash_) external view returns (string memory) {
        IdentityView memory identity = resolveDIDHash(didHash_);
        return IIntegrityAgentProfileURI(identity.primitives.agentProfile).profileURI();
    }

    /// @notice Verify a claimed current controller against the subject account's live role state.
    /// @dev The registry's controller field is intentionally not exposed because it is only a
    /// registration-time snapshot and becomes stale after SovereignAgent.rotateController().
    function isController(address sovereignAgent, address candidate) external view returns (bool) {
        resolveAgent(sovereignAgent);
        return IIntegrityIdentitySubject(sovereignAgent).hasRole(bytes32(0), candidate);
    }

    function _toView(bytes32 requestedDIDHash, XibalbaAgentRegistry.AgentRecord memory record)
        internal
        view
        returns (IdentityView memory)
    {
        address sovereignAgent = record.primitives.sovereignAgent;
        bytes32 reverseDIDHash = sourceRegistry.didHashOf(sovereignAgent);
        if (reverseDIDHash != requestedDIDHash) {
            revert IdentityMappingMismatch(requestedDIDHash, reverseDIDHash);
        }

        string memory declaredDID;
        try IIntegrityIdentitySubject(sovereignAgent).agentDID() returns (string memory value) {
            declaredDID = value;
        } catch {
            revert DeclaredDIDUnavailable(sovereignAgent);
        }
        bytes32 declaredDIDHash = keccak256(bytes(declaredDID));
        if (declaredDIDHash != requestedDIDHash) {
            revert DeclaredDIDMismatch(requestedDIDHash, declaredDIDHash);
        }

        return IdentityView({
            didHash: requestedDIDHash,
            sovereignAgent: sovereignAgent,
            domainId: record.domainId,
            registeredAt: record.registeredAt,
            primitives: record.primitives
        });
    }
}
