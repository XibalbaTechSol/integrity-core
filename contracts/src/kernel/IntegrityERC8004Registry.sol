// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {ERC721URIStorage} from "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {XibalbaAgentRegistry} from "../framework/XibalbaAgentRegistry.sol";

/// @title IntegrityERC8004Registry
/// @notice ERC-8004 conformant Identity Registry for the Integrity Protocol.
///
// Design principles:
///
//  1. ONE TOKEN PER AGENT — tokenId = uint256(keccak256(bytes(did))), the same hash
///     XibalbaAgentRegistry already uses for its primary key. Deterministic, derivable
///     off-chain without a lookup.
///
//  2. SOULBOUND — standard ERC-721 transfers are permanently disabled. Ownership
///     mirrors agent controller rotation only (not market-transferable).
///
//  3. SOURCE OF TRUTH IS XibalbaAgentRegistry — this contract stores the agentURI
///     and on-chain metadata only. All identity resolution delegates to the underlying
///     registry. No duplicate identity store.
///
//  4. ERC-8004 CONFORMANT — isERC8004Conformant() returns true. The agentURI MUST
///     resolve to a document matching ERC-8004 registration file schema:
///     { "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1", ... }
///
//  5. MINTER ROLE — only a privileged minter (AgentPrimitivesFactory at deploy time)
///     can call mintSovereign / mintEnterprise.
///
//  6. ENTERPRISE AGENTS — enterprise agents (ERC-4337 accounts, no DID string today)
///     get tokenId = uint256(keccak256(abi.encodePacked(agentAddress))).
///
// References:
//   ERC-8004: ethereum/ERCs@503591a6e80e6e1affdd6403341e25269141f046/ERCS/erc-8004.md
//   Integrity SPEC.md §3.3  — AgentId = IntegrityDid | ERC8004TokenId
//   INTERFACE_CONTRACT.md §6.1a — ERC-8004 boundary, isERC8004Conformant()
//   CROSS_PLATFORM_MANAGEMENT.md §3.6 — cross-platform ERC-8004 strategy
contract IntegrityERC8004Registry is ERC721URIStorage, AccessControl {

    // ── Roles ──────────────────────────────────────────────────────────────────

    bytes32 public constant MINTER_ROLE   = keccak256("MINTER_ROLE");
    bytes32 public constant METADATA_ROLE = keccak256("METADATA_ROLE");

    // ── State ──────────────────────────────────────────────────────────────────

    XibalbaAgentRegistry public immutable sourceRegistry;

    /// @dev tokenId → metadataKey → value  (ERC-8004 §4.2 on-chain metadata)
    mapping(uint256 => mapping(string => bytes)) private _metadata;

    /// @dev tokenId → owner address (sovereign agent contract or enterprise account).
    ///      Kept separately because ERC-721's _owners mapping is private.
    mapping(uint256 => address) private _agentOwner;

    // ── Reserved metadata key ──────────────────────────────────────────────────

    string private constant _KEY_AGENT_WALLET = "agentWallet";

    // ── Events (ERC-8004 required) ─────────────────────────────────────────────

    /// @notice Emitted when an agent is registered and a token minted.
    event AgentRegistered(uint256 indexed agentId, address indexed owner, string agentURI);

    /// @notice Emitted when on-chain metadata is set (ERC-8004 §4.2).
    event MetadataSet(
        uint256 indexed agentId,
        string  indexed indexedMetadataKey,
        string          metadataKey,
        bytes           metadataValue
    );

    // ── Errors ─────────────────────────────────────────────────────────────────

    error Soulbound();
    error ReservedKey(string key);
    error AlreadyMinted(uint256 tokenId);
    error NotTokenOwner();

    // ── Constructor ────────────────────────────────────────────────────────────

    constructor(address registry_, address admin_)
        ERC721("Integrity Agent Identity", "IAID")
    {
        require(registry_ != address(0), "zero registry");
        require(admin_    != address(0), "zero admin");
        sourceRegistry = XibalbaAgentRegistry(registry_);
        _grantRole(DEFAULT_ADMIN_ROLE, admin_);
    }

    // ── ERC-8004 capability claim ──────────────────────────────────────────────

    /// @notice Returns true — this contract IS ERC-8004 conformant.
    /// @dev Contrast with IntegrityIdentityReadV1 which returns false.
    function isERC8004Conformant() external pure returns (bool) {
        return true;
    }

    // ── Minting ────────────────────────────────────────────────────────────────

    /// @notice Mint an ERC-8004 identity token for a sovereign agent.
    /// @dev Should be called by AgentPrimitivesFactory after registerPrimitives.
    ///      tokenId = uint256(keccak256(bytes(did))).
    /// @param did        Canonical DID string, e.g. "did:integrity:<fingerprint>"
    /// @param owner      The SovereignAgent contract address (becomes token owner)
    /// @param agentURI_  URI of the ERC-8004 registration file
    function mintSovereign(
        string  calldata did,
        address          owner,
        string  calldata agentURI_
    ) external onlyRole(MINTER_ROLE) {
        uint256 tokenId = _tokenIdForDID(did);
        if (_ownerOf(tokenId) != address(0)) revert AlreadyMinted(tokenId);

        _mint(owner, tokenId);
        _setTokenURI(tokenId, agentURI_);
        _agentOwner[tokenId] = owner;

        emit AgentRegistered(tokenId, owner, agentURI_);
    }

    /// @notice Mint an ERC-8004 identity token for an enterprise agent.
    /// @dev tokenId = uint256(keccak256(abi.encodePacked(agent))).
    /// @param agent      The ERC-4337 account address
    /// @param agentURI_  URI of the ERC-8004 registration file
    function mintEnterprise(
        address          agent,
        string  calldata agentURI_
    ) external onlyRole(MINTER_ROLE) {
        uint256 tokenId = _tokenIdForAddress(agent);
        if (_ownerOf(tokenId) != address(0)) revert AlreadyMinted(tokenId);

        _mint(agent, tokenId);
        _setTokenURI(tokenId, agentURI_);
        _agentOwner[tokenId] = agent;

        emit AgentRegistered(tokenId, agent, agentURI_);
    }

    // ── agentURI update ────────────────────────────────────────────────────────

    /// @notice Update the agentURI (e.g. after re-pinning to IPFS with updated endpoints).
    /// @dev Only the token owner (routed through SovereignAgent.execute) or METADATA_ROLE.
    function setAgentURI(uint256 tokenId, string calldata agentURI_) external {
        if (_ownerOf(tokenId) == address(0)) revert ERC721NonexistentToken(tokenId);
        if (msg.sender != _agentOwner[tokenId] && !hasRole(METADATA_ROLE, msg.sender)) {
            revert NotTokenOwner();
        }
        _setTokenURI(tokenId, agentURI_);
    }

    // ── ERC-8004 on-chain metadata ─────────────────────────────────────────────

    /// @notice Read on-chain metadata for an agent (ERC-8004 §4.2).
    function getMetadata(uint256 agentId, string calldata metadataKey)
        external view returns (bytes memory)
    {
        return _metadata[agentId][metadataKey];
    }

    /// @notice Write on-chain metadata for an agent (ERC-8004 §4.2).
    /// @dev "agentWallet" is reserved — use setMetadata with that key after minting
    ///      via a separate privileged path if needed. Only owner or METADATA_ROLE.
    function setMetadata(
        uint256        agentId,
        string calldata metadataKey,
        bytes  calldata metadataValue
    ) external {
        if (keccak256(bytes(metadataKey)) == keccak256(bytes(_KEY_AGENT_WALLET))) {
            revert ReservedKey(metadataKey);
        }
        if (_ownerOf(agentId) == address(0)) revert ERC721NonexistentToken(agentId);
        if (msg.sender != _agentOwner[agentId] && !hasRole(METADATA_ROLE, msg.sender)) {
            revert NotTokenOwner();
        }
        _metadata[agentId][metadataKey] = metadataValue;
        emit MetadataSet(agentId, metadataKey, metadataKey, metadataValue);
    }

    // ── tokenId derivation (public for off-chain use) ──────────────────────────

    /// @notice Off-chain helper: derive the tokenId for a sovereign agent from its DID.
    function tokenIdForDID(string calldata did) external pure returns (uint256) {
        return _tokenIdForDID(did);
    }

    /// @notice Off-chain helper: derive the tokenId for an enterprise agent from its address.
    function tokenIdForAddress(address agent) external pure returns (uint256) {
        return _tokenIdForAddress(agent);
    }

    // ── Soulbound: block all post-mint transfers ───────────────────────────────

    /// @dev ERC-721 internal transfer hook. Mint (from == address(0)) is allowed;
    ///      any other transfer (including burn) reverts with Soulbound().
    function _update(address to, uint256 tokenId, address auth)
        internal override returns (address)
    {
        address from = _ownerOf(tokenId);
        if (from != address(0)) revert Soulbound();
        return super._update(to, tokenId, auth);
    }

    // ── ERC-165 ────────────────────────────────────────────────────────────────

    function supportsInterface(bytes4 interfaceId)
        public view override(ERC721URIStorage, AccessControl)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }

    // ── Internal ───────────────────────────────────────────────────────────────

    function _tokenIdForDID(string memory did) internal pure returns (uint256) {
        return uint256(keccak256(bytes(did)));
    }

    function _tokenIdForAddress(address agent) internal pure returns (uint256) {
        return uint256(keccak256(abi.encodePacked(agent)));
    }
}
