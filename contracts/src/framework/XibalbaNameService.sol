// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {AgentRegistry} from "./AgentRegistry.sol";

/// @title XibalbaNameService (XNS)
/// @notice Maps human-readable handles (e.g. "hermes.integrity") to a registered agent's
/// `SovereignAgent` contract address, so agents don't have to be addressed only by their
/// raw address or DID string. Per the root README's "Vision & long-term roadmap" table
/// and docs/wiki/concepts/xns.md, this was `[PLANNED]` — no contract existed anywhere in
/// this rewrite's `contracts/src/` until now.
/// @dev **Deliberately NOT a port of the legacy prototype's `XibalbaNameService.sol`.**
/// That contract restricted `register()` to an admin-only `REGISTRAR_ROLE`, i.e. a
/// privileged party registered handles ON BEHALF OF agents — the exact "nothing is
/// registered on behalf of the agent by a privileged factory" violation this whole
/// rewrite's self-sovereign thesis (see root README) was built to eliminate. This
/// version instead follows `DomainRegistry.registerDomain`'s already-established pattern
/// in this codebase: self-service, first-come-first-served, no privileged party in the
/// critical path. `REGISTRAR_ROLE` here is reserved for dispute intervention only
/// (`revokeByRegistrar`), mirroring `DomainRegistry`'s own REGISTRAR_ROLE scope — not a
/// normal-path registration mechanism.
contract XibalbaNameService is AccessControl {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    /// @dev Immutable: the canonical `AgentRegistry` (registration v3) singleton this deployment of
    /// XNS checks handle-registration eligibility against. A handle can only ever be
    /// claimed by an address `isRegisteredAgent` — i.e. a real `SovereignAgent` contract
    /// that completed the full self-sovereign registration flow (§6.1/§6.2 of
    /// docs/INTERFACE_CONTRACT.md) — not an arbitrary EOA or contract squatting names
    /// unrelated to any real agent.
    AgentRegistry public immutable agentRegistry;

    struct HandleRecord {
        address sovereignAgent;
        uint256 registeredAt;
        bool exists;
    }

    /// @dev keyed by keccak256(bytes(handle)), same rationale as DomainRegistry.domainId:
    /// a fixed-width identifier is cheaper to index on and reused across events/mappings
    /// rather than a string key.
    mapping(bytes32 => HandleRecord) private _byHandle;
    /// @dev handleId => original string, so `primaryHandle(address)` can return a
    /// human-readable name rather than a hash back out to callers.
    mapping(bytes32 => string) private _handleName;
    /// @notice sovereignAgent => its current primary handle's id (bytes32(0) if none).
    mapping(address => bytes32) public primaryHandleOf;

    event HandleRegistered(bytes32 indexed handleId, string handle, address indexed sovereignAgent);
    event HandleRevoked(bytes32 indexed handleId, string handle, address indexed sovereignAgent);
    event PrimaryHandleChanged(address indexed sovereignAgent, bytes32 indexed handleId);

    error EmptyHandle();
    error NotRegisteredAgent();
    error HandleAlreadyRegistered();
    error HandleNotFound();
    error NotHandleOwner();

    constructor(address admin, address agentRegistry_) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        agentRegistry = AgentRegistry(agentRegistry_);
    }

    function handleId(string memory handle) public pure returns (bytes32) {
        return keccak256(bytes(handle));
    }

    /// @notice Self-service handle registration. `msg.sender` must itself be a
    /// registered agent's `SovereignAgent` address (verified live against
    /// `AgentRegistry` (a bound actor), not merely asserted) — matching how every other
    /// agent-facing contract in this codebase (`ComplianceGate`, `EHRGate`) treats the
    /// calling `SovereignAgent` contract as the acting agent's identity. First unclaimed
    /// handle wins, same trust model as `DomainRegistry.registerDomain`/ENS
    /// second-level names. An agent's first registered handle becomes its primary
    /// automatically; use `setPrimaryHandle` to change that later.
    function register(string calldata handle) external returns (bytes32 id) {
        if (bytes(handle).length == 0) revert EmptyHandle();
        if (!agentRegistry.isRegisteredAgent(msg.sender)) revert NotRegisteredAgent();

        id = handleId(handle);
        if (_byHandle[id].exists) revert HandleAlreadyRegistered();

        _byHandle[id] = HandleRecord({sovereignAgent: msg.sender, registeredAt: block.timestamp, exists: true});
        _handleName[id] = handle;
        emit HandleRegistered(id, handle, msg.sender);

        if (primaryHandleOf[msg.sender] == bytes32(0)) {
            primaryHandleOf[msg.sender] = id;
            emit PrimaryHandleChanged(msg.sender, id);
        }
    }

    /// @notice Lets an agent with multiple handles choose which one `primaryHandle`
    /// returns for it. Self-service — no registrar involved.
    function setPrimaryHandle(string calldata handle) external {
        bytes32 id = handleId(handle);
        HandleRecord storage rec = _byHandle[id];
        if (!rec.exists) revert HandleNotFound();
        if (rec.sovereignAgent != msg.sender) revert NotHandleOwner();
        primaryHandleOf[msg.sender] = id;
        emit PrimaryHandleChanged(msg.sender, id);
    }

    /// @notice Voluntary self-release of a handle the caller itself owns (e.g. to free
    /// it up, or before an agent decommissions).
    function release(string calldata handle) external {
        bytes32 id = handleId(handle);
        HandleRecord storage rec = _byHandle[id];
        if (!rec.exists) revert HandleNotFound();
        if (rec.sovereignAgent != msg.sender) revert NotHandleOwner();
        _revoke(id, handle, rec.sovereignAgent);
    }

    /// @notice Dispute-intervention path (e.g. a name used for impersonation, or a
    /// compromised agent) — mirrors `DomainRegistry`'s REGISTRAR_ROLE scope exactly:
    /// reserved for governance intervention, not a normal-path registration mechanism.
    /// Granted to nothing by default; a deploy script must explicitly grant it if this
    /// capability is wanted, same as every other REGISTRAR_ROLE in this codebase.
    function revokeByRegistrar(string calldata handle) external onlyRole(REGISTRAR_ROLE) {
        bytes32 id = handleId(handle);
        HandleRecord storage rec = _byHandle[id];
        if (!rec.exists) revert HandleNotFound();
        _revoke(id, handle, rec.sovereignAgent);
    }

    function _revoke(bytes32 id, string calldata handle, address owner) private {
        delete _byHandle[id];
        delete _handleName[id];
        if (primaryHandleOf[owner] == id) {
            delete primaryHandleOf[owner];
        }
        emit HandleRevoked(id, handle, owner);
    }

    /// @notice Resolves a handle to the agent's `SovereignAgent` address. Reverts on an
    /// unregistered/revoked handle rather than returning `address(0)` — callers that
    /// want a non-reverting existence check should use `handleExists` first.
    function resolve(string calldata handle) external view returns (address sovereignAgent) {
        HandleRecord storage rec = _byHandle[handleId(handle)];
        if (!rec.exists) revert HandleNotFound();
        return rec.sovereignAgent;
    }

    function handleExists(string calldata handle) external view returns (bool) {
        return _byHandle[handleId(handle)].exists;
    }

    /// @notice Returns the human-readable primary handle for an agent, or "" if it has
    /// none registered.
    function primaryHandle(address sovereignAgent) external view returns (string memory) {
        return _handleName[primaryHandleOf[sovereignAgent]];
    }
}
