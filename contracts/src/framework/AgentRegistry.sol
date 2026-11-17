// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {SignatureChecker} from "@openzeppelin/contracts/utils/cryptography/SignatureChecker.sol";
import {SovereignAgent} from "../core/SovereignAgent.sol";
import {DomainRegistry} from "./DomainRegistry.sol";
import {IEd25519Verifier} from "./IEd25519Verifier.sol";

interface IAgentRegistryTrustConfig {
    function policyRegistry() external view returns (address);
}

interface IAgentRegistryPolicy {
    function moduleOf(bytes32 domainId) external view returns (address);
    function graphRootOf(bytes32 domainId) external view returns (bytes32);
}

/// @title AgentRegistry
/// @notice The on-chain record that an agent exists (agent registration v3, Part 3). One record per
/// Ed25519 key, keyed by its fingerprint `sha256(pubkey)` — the same 32 bytes as the suffix of the
/// agent's `did:integrity:` DID. A record optionally binds an *actor*: the agent's gated
/// `SovereignAgent`, the only kind of account that can be confined to its policy (Part 4).
/// @dev Invariants (see test/framework/AgentRegistryInvariants.t.sol):
///  - first write wins: a fingerprint's `registeredAt`/`pubkey` never change once set;
///  - `retiredAt` never returns to 0;
///  - `agentOf[a] == fp` iff `records[fp].actor == a` (one actor <-> one agent);
///  - an actor is only ever bound to the fingerprint that first bound it.
/// The attester (the Oracle) can only enable the FIRST write of a fingerprint; it has no power over
/// an existing record. Everything after registration is guardian-only.
contract AgentRegistry is AccessControl, EIP712 {
    /// @notice Signs proof kind 1 (`RegisterAgent` attestations). Governance-managed.
    bytes32 public constant ATTESTER_ROLE = keccak256("ATTESTER_ROLE");

    uint8 public constant PROOF_ATTESTATION = 1;
    uint8 public constant PROOF_ED25519 = 2;

    bytes32 public constant REGISTER_AGENT_TYPEHASH = keccak256(
        "RegisterAgent(bytes32 pubkey,address guardian,address actor,bytes32 domainId,bytes32 uriHash,uint256 deadline)"
    );
    bytes32 public constant BIND_ACTOR_TYPEHASH =
        keccak256("BindActor(bytes32 fingerprint,address actor,uint256 deadline)");

    struct AgentRecord {
        bytes32 pubkey; // raw Ed25519 public key; sha256(pubkey) == fingerprint
        address guardian; // controls this record
        address actor; // optional gated account (a SovereignAgent); 0 = existence only
        bytes32 domainId; // required when actor != 0
        string uri; // optional metadata (DID document / profile)
        uint64 registeredAt;
        uint64 retiredAt; // 0 = active
        uint8 proofKind; // 1 = oracle attestation, 2 = ed25519
    }

    DomainRegistry public immutable domainRegistry;
    /// @notice Runtime codehash of the canonical `SovereignAgent` build bound as actor. Learned by
    /// deploying one reference instance in the constructor (same technique as the old factory):
    /// `SovereignAgent.factory` is its only immutable, so every agent constructed with
    /// `factory_ == address(this)` shares this hash, and nothing can leave the pin unwired.
    bytes32 public immutable agentCodehash;

    /// @notice Governance-set source of the trust singletons (moves here from XibalbaAgentRegistry).
    address public trustConfig;
    /// @notice Proof kind 2 verifier. Zero = kind 2 disabled.
    IEd25519Verifier public ed25519Verifier;

    mapping(bytes32 fingerprint => AgentRecord) private _records;
    /// @notice The fingerprint an actor is currently bound to (0 = none).
    mapping(address actor => bytes32 fingerprint) public agentOf;
    /// @notice The fingerprint that first bound an actor. An actor can never serve another agent,
    /// even after `clearActor`, so a SovereignAgent's on-chain history belongs to one identity.
    mapping(address actor => bytes32 fingerprint) public actorClaimedBy;
    mapping(bytes32 fingerprint => address) public pendingGuardian;

    event AgentRegistered(
        bytes32 indexed fingerprint, address indexed guardian, address indexed actor, bytes32 domainId, uint8 proofKind
    );
    event ActorBound(bytes32 indexed fingerprint, address indexed actor);
    event ActorCleared(bytes32 indexed fingerprint, address indexed actor);
    event GuardianProposed(bytes32 indexed fingerprint, address indexed next);
    event GuardianChanged(bytes32 indexed fingerprint, address indexed previous, address indexed next);
    event DomainChanged(bytes32 indexed fingerprint, bytes32 domainId);
    event UriChanged(bytes32 indexed fingerprint, string uri);
    event AgentRetired(bytes32 indexed fingerprint);
    event AttesterAdded(address indexed attester);
    event AttesterRemoved(address indexed attester);
    event Ed25519VerifierSet(address indexed verifier);
    event TrustConfigSet(address indexed trustConfig);

    error DeadlineExpired();
    error ZeroPubkey();
    error ZeroGuardian();
    error AlreadyRegistered(bytes32 fingerprint);
    error NotRegistered(bytes32 fingerprint);
    error InvalidProof();
    error ProofKindDisabled();
    error UnknownProofKind(uint8 kind);
    error DomainJoinNotAllowed(bytes32 domainId);
    error NotGatedAccount(address actor);
    error ActorConsentMissing(address actor);
    error ActorAlreadyBound(address actor);
    error ActorRequiresDomain();
    error DomainHasNoPolicy(bytes32 domainId);
    error NotGuardian();
    error NotPendingGuardian();
    error Retired(bytes32 fingerprint);
    error NoActor();
    error InvalidDid();

    constructor(address admin, address domainRegistry_) EIP712("IntegrityAgentRegistry", "1") {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        domainRegistry = DomainRegistry(domainRegistry_);
        // Reference instance: controlled by this registry, which exposes no way to drive it.
        agentCodehash =
            address(new SovereignAgent("did:integrity:reference", address(this), address(this))).codehash;
    }

    // ── Governance ───────────────────────────────────────────────────────────

    function addAttester(address a) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _grantRole(ATTESTER_ROLE, a);
        emit AttesterAdded(a);
    }

    function removeAttester(address a) external onlyRole(DEFAULT_ADMIN_ROLE) {
        _revokeRole(ATTESTER_ROLE, a);
        emit AttesterRemoved(a);
    }

    function setEd25519Verifier(address v) external onlyRole(DEFAULT_ADMIN_ROLE) {
        ed25519Verifier = IEd25519Verifier(v);
        emit Ed25519VerifierSet(v);
    }

    function setTrustConfig(address cfg) external onlyRole(DEFAULT_ADMIN_ROLE) {
        trustConfig = cfg;
        emit TrustConfigSet(cfg);
    }

    // ── Registration ─────────────────────────────────────────────────────────

    /// @notice The EIP-712 digest the agent signs with its Ed25519 key (and the attester co-signs).
    function registerDigest(
        bytes32 pubkey,
        address guardian,
        address actor,
        bytes32 domainId,
        string calldata uri,
        uint256 deadline
    ) public view returns (bytes32) {
        return _hashTypedDataV4(
            keccak256(
                abi.encode(
                    REGISTER_AGENT_TYPEHASH, pubkey, guardian, actor, domainId, keccak256(bytes(uri)), deadline
                )
            )
        );
    }

    /// @notice The EIP-712 digest an actor signs (via EIP-1271) to consent to being bound.
    function bindActorDigest(bytes32 fingerprint, address actor, uint256 deadline) public view returns (bytes32) {
        return _hashTypedDataV4(keccak256(abi.encode(BIND_ACTOR_TYPEHASH, fingerprint, actor, deadline)));
    }

    /// @notice Writes the record for `pubkey`. Anyone may submit; no fee or bond.
    /// @param actorConsent Ignored when `actor == 0` or `msg.sender == actor`; otherwise an EIP-1271
    /// signature by `actor` over `bindActorDigest(fingerprint, actor, deadline)`.
    function register(
        bytes32 pubkey,
        address guardian,
        address actor,
        bytes32 domainId,
        string calldata uri,
        uint256 deadline,
        uint8 proofKind,
        bytes calldata proof,
        bytes calldata actorConsent
    ) external returns (bytes32 fingerprint) {
        if (block.timestamp > deadline) revert DeadlineExpired();
        if (pubkey == bytes32(0)) revert ZeroPubkey();
        if (guardian == address(0)) revert ZeroGuardian();
        fingerprint = sha256(abi.encodePacked(pubkey));
        if (_records[fingerprint].registeredAt != 0) revert AlreadyRegistered(fingerprint);

        _verifyProof(pubkey, registerDigest(pubkey, guardian, actor, domainId, uri, deadline), proofKind, proof);

        if (domainId != bytes32(0) && !domainRegistry.canJoin(domainId, guardian)) {
            revert DomainJoinNotAllowed(domainId);
        }

        AgentRecord storage r = _records[fingerprint];
        r.pubkey = pubkey;
        r.guardian = guardian;
        r.domainId = domainId;
        r.uri = uri;
        r.registeredAt = uint64(block.timestamp);
        r.proofKind = proofKind;

        if (actor != address(0)) {
            _bindActor(fingerprint, r, actor, deadline, actorConsent);
        }
        emit AgentRegistered(fingerprint, guardian, actor, domainId, proofKind);
    }

    // ── Guardian-only ────────────────────────────────────────────────────────

    function setActor(bytes32 fingerprint, address newActor, uint256 deadline, bytes calldata consent) external {
        AgentRecord storage r = _guarded(fingerprint);
        if (block.timestamp > deadline) revert DeadlineExpired();
        if (r.actor != address(0)) _clearActor(fingerprint, r);
        _bindActor(fingerprint, r, newActor, deadline, consent);
    }

    function clearActor(bytes32 fingerprint) external {
        AgentRecord storage r = _guarded(fingerprint);
        if (r.actor == address(0)) revert NoActor();
        _clearActor(fingerprint, r);
    }

    function setUri(bytes32 fingerprint, string calldata uri) external {
        AgentRecord storage r = _guarded(fingerprint);
        r.uri = uri;
        emit UriChanged(fingerprint, uri);
    }

    function setDomain(bytes32 fingerprint, bytes32 domainId) external {
        AgentRecord storage r = _guarded(fingerprint);
        if (domainId != bytes32(0) && !domainRegistry.canJoin(domainId, r.guardian)) {
            revert DomainJoinNotAllowed(domainId);
        }
        if (r.actor != address(0)) {
            _requirePolicy(domainId);
            domainRegistry.recordJoin(domainId, r.guardian, r.actor);
        }
        r.domainId = domainId;
        emit DomainChanged(fingerprint, domainId);
    }

    /// @notice Step 1 of a guardian transfer. A record can never be re-created, so a one-step
    /// transfer to a wrong address would strand it permanently; the next guardian must accept.
    function proposeGuardian(bytes32 fingerprint, address next) external {
        _guarded(fingerprint);
        if (next == address(0)) revert ZeroGuardian();
        pendingGuardian[fingerprint] = next;
        emit GuardianProposed(fingerprint, next);
    }

    function acceptGuardian(bytes32 fingerprint) external {
        AgentRecord storage r = _records[fingerprint];
        if (r.registeredAt == 0) revert NotRegistered(fingerprint);
        if (r.retiredAt != 0) revert Retired(fingerprint);
        if (msg.sender != pendingGuardian[fingerprint] || msg.sender == address(0)) revert NotPendingGuardian();
        address previous = r.guardian;
        r.guardian = msg.sender;
        delete pendingGuardian[fingerprint];
        emit GuardianChanged(fingerprint, previous, msg.sender);
    }

    /// @notice Irreversible. The record and its actor binding are kept, marked inactive.
    function retire(bytes32 fingerprint) external {
        AgentRecord storage r = _guarded(fingerprint);
        r.retiredAt = uint64(block.timestamp);
        delete pendingGuardian[fingerprint];
        emit AgentRetired(fingerprint);
    }

    // ── Reads ────────────────────────────────────────────────────────────────

    function isRegisteredAgent(address actor) external view returns (bool) {
        bytes32 fp = agentOf[actor];
        return fp != bytes32(0) && _records[fp].retiredAt == 0;
    }

    function resolve(bytes32 fingerprint) public view returns (AgentRecord memory) {
        return _records[fingerprint];
    }

    function resolveAgent(address actor) external view returns (AgentRecord memory) {
        return _records[agentOf[actor]];
    }

    /// @notice Resolves `did:integrity:<64 lowercase hex>` (the hex is the fingerprint).
    function resolveDID(string calldata did) external view returns (AgentRecord memory) {
        return _records[fingerprintOfDID(did)];
    }

    function fingerprintOfDID(string calldata did) public pure returns (bytes32 fp) {
        bytes calldata b = bytes(did);
        bytes memory prefix = "did:integrity:";
        if (b.length != prefix.length + 64) revert InvalidDid();
        for (uint256 i = 0; i < prefix.length; i++) {
            if (b[i] != prefix[i]) revert InvalidDid();
        }
        uint256 v;
        for (uint256 i = prefix.length; i < b.length; i++) {
            uint8 c = uint8(b[i]);
            uint8 n;
            if (c >= 48 && c <= 57) n = c - 48;
            else if (c >= 97 && c <= 102) n = c - 87;
            else revert InvalidDid();
            v = (v << 4) | n;
        }
        fp = bytes32(v);
    }

    /// @notice True when `a` runs the canonical SovereignAgent build bound to this registry.
    function isGatedAccount(address a) public view returns (bool) {
        return a.code.length != 0 && a.codehash == agentCodehash;
    }

    // ── Internal ─────────────────────────────────────────────────────────────

    function _verifyProof(bytes32 pubkey, bytes32 digest, uint8 proofKind, bytes calldata proof) internal view {
        if (proofKind == PROOF_ATTESTATION) {
            (address signer, ECDSA.RecoverError err,) = ECDSA.tryRecover(digest, proof);
            if (err != ECDSA.RecoverError.NoError || !hasRole(ATTESTER_ROLE, signer)) revert InvalidProof();
        } else if (proofKind == PROOF_ED25519) {
            IEd25519Verifier v = ed25519Verifier;
            if (address(v) == address(0)) revert ProofKindDisabled();
            if (!v.verify(pubkey, digest, proof)) revert InvalidProof();
        } else {
            revert UnknownProofKind(proofKind);
        }
    }

    function _guarded(bytes32 fingerprint) internal view returns (AgentRecord storage r) {
        r = _records[fingerprint];
        if (r.registeredAt == 0) revert NotRegistered(fingerprint);
        if (msg.sender != r.guardian) revert NotGuardian();
        if (r.retiredAt != 0) revert Retired(fingerprint);
    }

    function _bindActor(
        bytes32 fingerprint,
        AgentRecord storage r,
        address actor,
        uint256 deadline,
        bytes calldata consent
    ) internal {
        // Codehash first: until it passes, `actor` is untrusted code and is never called.
        if (!isGatedAccount(actor)) revert NotGatedAccount(actor);
        if (agentOf[actor] != bytes32(0)) revert ActorAlreadyBound(actor);
        bytes32 claimedBy = actorClaimedBy[actor];
        if (claimedBy != bytes32(0) && claimedBy != fingerprint) revert ActorAlreadyBound(actor);
        if (
            msg.sender != actor
                && !SignatureChecker.isValidSignatureNow(actor, bindActorDigest(fingerprint, actor, deadline), consent)
        ) revert ActorConsentMissing(actor);
        if (r.domainId == bytes32(0)) revert ActorRequiresDomain();
        _requirePolicy(r.domainId);

        r.actor = actor;
        agentOf[actor] = fingerprint;
        actorClaimedBy[actor] = fingerprint;
        domainRegistry.recordJoin(r.domainId, r.guardian, actor);
        emit ActorBound(fingerprint, actor);
    }

    function _clearActor(bytes32 fingerprint, AgentRecord storage r) internal {
        address actor = r.actor;
        delete agentOf[actor];
        r.actor = address(0);
        emit ActorCleared(fingerprint, actor);
    }

    /// @dev Fails closed: an actor with no policy would be an agent with no map.
    function _requirePolicy(bytes32 domainId) internal view {
        if (domainId == bytes32(0)) revert ActorRequiresDomain();
        address cfg = trustConfig;
        if (cfg == address(0)) revert DomainHasNoPolicy(domainId);
        address pr = IAgentRegistryTrustConfig(cfg).policyRegistry();
        if (pr == address(0)) revert DomainHasNoPolicy(domainId);
        if (
            IAgentRegistryPolicy(pr).moduleOf(domainId) == address(0)
                && IAgentRegistryPolicy(pr).graphRootOf(domainId) == bytes32(0)
        ) revert DomainHasNoPolicy(domainId);
    }
}
