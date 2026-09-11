// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {AccessControlUpgradeable} from "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {IZkVerifier} from "./IZkVerifier.sol";
import {StateAnchor} from "./StateAnchor.sol";

/// @title ReputationRegistry
/// @notice Per-agent EIP-1167 clone: the on-chain ledger for one agent's Agent Integrity
/// Score (AIS, §4.3 of the interface contract). This contract does not *compute* the AIS
/// formula `(S_entropy*wE + S_grounding*wG + S_sacrifice*wS + S_compliance*wC) * ZK_boost`
/// — that weighted-sum computation is integrity-oracle's job, and stays the single place
/// it's computed (per the interface contract, every other package calls the oracle's
/// `/v1/agent/{id}/ais` HTTP endpoint rather than recompute it). What this contract owns
/// is the one component that *cannot* be trusted from an off-chain HTTP response alone:
/// the `ZK_boost` multiplier, which is only legitimate if a real Barretenberg proof
/// verified on-chain, against a leaf that is itself anchored in a Merkle root this chain
/// anchored. So the division of labour is: oracle pushes `baseScore` (the pre-boost
/// weighted sum) via `updateScore`; this contract independently earns the right to apply
/// the 1.15x multiplier by verifying a ZK proof itself, in `submitZkAttestation`.
/// @dev Was a directly-deployed singleton; now a per-agent clone (see
/// AgentPrimitivesFactory) so one agent's score storage never shares a slot with
/// another's, and `DEFAULT_ADMIN_ROLE` (config: which verifier/anchor this agent trusts)
/// belongs to that agent's own SovereignAgent contract rather than a shared protocol
/// admin — `ORACLE_ROLE` remains a separate, protocol-held signer so the oracle can keep
/// pushing scores without needing the agent's own permission on every update.
contract ReputationRegistry is Initializable, AccessControlUpgradeable {
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");
    bytes32 public constant BRIDGE_ROLE = keccak256("BRIDGE_ROLE");

    /// @dev ZK_boost = 1.15 per §4.3, expressed in basis points so Solidity integer
    /// arithmetic doesn't need a fixed-point library for a single constant multiplier.
    uint256 public constant ZK_BOOST_BPS = 11_500;
    uint256 public constant BPS_DENOMINATOR = 10_000;
    uint256 public constant BN254_SCALAR_FIELD =
        21888242871839275222246405745257275088548364400416034343698204186575808495617;
    uint256 public constant ZK_PUBLIC_INPUT_COUNT = 6;

    /// @notice How long a verified ZK proof's boost remains valid before it must be
    /// re-submitted. Mirrors "for the reporting period" in §4.3 — a proof verified once
    /// should not grant a permanent boost long after the period it attested to has
    /// passed, or the boost stops meaning "verified recently" and starts meaning
    /// "verified once, ever".
    /// @dev Deliberately NOT given an inline initializer here — inline field
    /// initializers compile into the constructor, which never runs for an EIP-1167
    /// clone. Set explicitly in `initialize` instead (see Slasher.disputeWindow for the
    /// same footgun, caught in that contract's own clone tests).
    uint256 public reportingPeriod;

    struct AgentScore {
        uint256 baseScore; // pre-boost weighted sum from integrity-oracle
        uint256 lastUpdate;
        uint256 zkBoostExpiry; // block.timestamp until which the ZK boost applies
    }

    mapping(address => AgentScore) public scores;
    mapping(bytes32 => bool) public usedAttestationLeaves;
    mapping(address => uint256) public lastZkNonce;
    /// @dev Oracle-authoritative fraction of reporting-window events with a verified proof,
    /// in basis points. It is explicitly configured by updateScoreWithCoverage; leaving it
    /// unset preserves the legacy read shape for already-deployed callers.
    mapping(address => uint256) public zkVerifiedEventRatioBps;
    mapping(address => bool) public coverageConfigured;

    IZkVerifier public zkVerifier;
    StateAnchor public stateAnchor;
    bytes32 public zkIdentityCommitment;

    event ScoreUpdated(address indexed agent, uint256 oldBaseScore, uint256 newBaseScore, address indexed updatedBy);
    event ZkAttestationVerified(address indexed agent, bytes32 indexed leaf, uint256 boostExpiry);
    event ZkIdentityCommitmentSet(bytes32 indexed commitment);
    event ZkEventCoverageUpdated(address indexed agent, uint256 verifiedEventRatioBps);
    event ZkConfigUpdated(address indexed verifier, address indexed anchor);
    event ReportingPeriodUpdated(uint256 newPeriod);

    error ZkNotConfigured();
    error InvalidProof();
    error LeafNotAnchored();
    error OnlyAgentCanSubmitOwnProof();
    error ZkIdentityNotConfigured();
    error ZkIdentityAlreadyConfigured();
    error InvalidZkIdentityCommitment();
    error InvalidPublicInputCount();
    error PublicInputMismatch();
    error ZkNonceNotIncreasing();
    error AttestationLeafAlreadyUsed();
    error InvalidEventCoverage();

    /// @dev Implementation contract itself is never initializable — only its clones are
    /// (standard OZ upgradeable-safety pattern: without this, someone could call
    /// `initialize` directly on the shared implementation and seize its admin role,
    /// though since this implementation is never delegatecalled into for its own storage
    /// that alone wouldn't be exploitable — but disabling it is free and removes the
    /// question entirely).
    constructor() {
        _disableInitializers();
    }

    /// @param admin Gets DEFAULT_ADMIN_ROLE — the agent's own SovereignAgent contract
    /// address, per the protocol's call-routing convention, so only that agent (acting
    /// through its own `execute`) can repoint its verifier/anchor.
    /// @param oracleSigner Gets ORACLE_ROLE — the protocol's oracle signer, kept
    /// separate from `admin` so the oracle can keep pushing scores independent of
    /// whatever the agent's own controller key is doing.
    function initialize(address admin, address oracleSigner, address _zkVerifier, address _stateAnchor)
        external
        initializer
    {
        __AccessControl_init();
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        if (oracleSigner != address(0)) {
            _grantRole(ORACLE_ROLE, oracleSigner);
        }
        zkVerifier = IZkVerifier(_zkVerifier);
        stateAnchor = StateAnchor(_stateAnchor);
        reportingPeriod = 7 days;
    }

    function setZkConfig(address _zkVerifier, address _stateAnchor) external onlyRole(DEFAULT_ADMIN_ROLE) {
        zkVerifier = IZkVerifier(_zkVerifier);
        stateAnchor = StateAnchor(_stateAnchor);
        emit ZkConfigUpdated(_zkVerifier, _stateAnchor);
    }

    function setReportingPeriod(uint256 newPeriod) external onlyRole(DEFAULT_ADMIN_ROLE) {
        reportingPeriod = newPeriod;
        emit ReportingPeriodUpdated(newPeriod);
    }

    /// @notice Pins the agent's long-lived Noir identity commitment once. The value is
    /// derived from the same agent-held secret used by the proving circuit. It cannot be
    /// rotated in place: changing ZK identity requires a new registry/version so an admin
    /// compromise cannot silently retarget already-issued proofs.
    function setZkIdentityCommitment(bytes32 commitment) external onlyRole(DEFAULT_ADMIN_ROLE) {
        if (commitment == bytes32(0)) revert InvalidZkIdentityCommitment();
        if (zkIdentityCommitment != bytes32(0)) revert ZkIdentityAlreadyConfigured();
        zkIdentityCommitment = commitment;
        emit ZkIdentityCommitmentSet(commitment);
    }

    /// @notice Oracle-pushed update of an agent's pre-boost weighted AIS. Does not
    /// touch `zkBoostExpiry` — a fresh score push should not silently extend or clear an
    /// independently-earned ZK boost.
    function updateScore(address agent, uint256 baseScore) external onlyRole(ORACLE_ROLE) {
        _setBaseScore(agent, baseScore, msg.sender);
    }

    /// @notice Pushes a pre-boost score together with the reporting-window fraction of
    /// events carrying an independently verified ZK proof. New oracle score syncs MUST use
    /// this method; the legacy updateScore remains only for compatibility with frozen
    /// integrations and intentionally does not configure coverage.
    /// @param verifiedEventRatioBps 0..10_000, where 10_000 means every event was proven.
    function updateScoreWithCoverage(address agent, uint256 baseScore, uint256 verifiedEventRatioBps)
        external
        onlyRole(ORACLE_ROLE)
    {
        if (verifiedEventRatioBps > BPS_DENOMINATOR) revert InvalidEventCoverage();
        _setBaseScore(agent, baseScore, msg.sender);
        zkVerifiedEventRatioBps[agent] = verifiedEventRatioBps;
        coverageConfigured[agent] = true;
        emit ZkEventCoverageUpdated(agent, verifiedEventRatioBps);
    }

    /// @notice Same as `updateScore`, but for scores arriving from a trusted cross-chain
    /// bridge (see CCIPReputationBridge) rather than the local oracle signer directly.
    /// Kept as a separate role/function (not just adding CCIPReputationBridge to
    /// ORACLE_ROLE) so a bridge compromise and an oracle-signer compromise are
    /// independently revocable.
    function updateScoreByBridge(address agent, uint256 baseScore) external onlyRole(BRIDGE_ROLE) {
        _setBaseScore(agent, baseScore, msg.sender);
    }

    function _setBaseScore(address agent, uint256 baseScore, address updatedBy) internal {
        uint256 old = scores[agent].baseScore;
        scores[agent].baseScore = baseScore;
        scores[agent].lastUpdate = block.timestamp;
        emit ScoreUpdated(agent, old, baseScore, updatedBy);
    }

    /// @notice Verifies a Noir/Barretenberg ZK proof that the given `leaf` (an
    /// off-chain-committed fact about this agent's behavior, e.g. a hashed intent
    /// payload from a BCC commitment, §4.2) is both (a) part of a Merkle tree this chain
    /// has anchored via StateAnchor, and (b) attested to by a valid ZK proof over
    /// `publicInputs`. The six logical inputs are checked here as
    /// `[identity, nonce, intentCommitment, chainId, verifyingContract, bccLeafField]`;
    /// the proof is therefore useful only for this agent, this registry deployment, and
    /// this exact anchored BCC leaf. Only the agent itself may submit its own attestation — otherwise
    /// anyone could grab a valid (proof, publicInputs, leaf, merkleProof) tuple observed
    /// on-chain or off-chain and replay it to boost a *different* agent's score, since
    /// none of those values are, by themselves, bound to a caller.
    /// @param agent The agent this attestation is for. Must equal msg.sender.
    /// @param proof The UltraPlonk/Honk proof bytes from `bb prove`.
    /// @param publicInputs The circuit's six logical public inputs, in circuit ABI order.
    /// @param root The StateAnchor root the leaf is claimed to belong to.
    /// @param leaf The keccak256 leaf value (§4.4 leaf-hashing convention).
    /// @param merkleProof Sibling hashes proving `leaf` is included under `root`.
    function submitZkAttestation(
        address agent,
        bytes calldata proof,
        bytes32[] calldata publicInputs,
        bytes32 root,
        bytes32 leaf,
        bytes32[] calldata merkleProof
    ) external {
        if (agent != msg.sender) revert OnlyAgentCanSubmitOwnProof();
        if (address(zkVerifier) == address(0) || address(stateAnchor) == address(0)) revert ZkNotConfigured();
        if (zkIdentityCommitment == bytes32(0)) revert ZkIdentityNotConfigured();
        if (publicInputs.length != ZK_PUBLIC_INPUT_COUNT) revert InvalidPublicInputCount();
        if (usedAttestationLeaves[leaf]) revert AttestationLeafAlreadyUsed();

        uint256 nonce = uint256(publicInputs[1]);
        if (nonce == 0 || nonce <= lastZkNonce[agent]) revert ZkNonceNotIncreasing();
        if (
            publicInputs[0] != zkIdentityCommitment || uint256(publicInputs[3]) != block.chainid
                || uint256(publicInputs[4]) != uint256(uint160(address(this)))
                || uint256(publicInputs[5]) != uint256(leaf) % BN254_SCALAR_FIELD
        ) revert PublicInputMismatch();

        if (!stateAnchor.verifyLeaf(root, leaf, merkleProof)) revert LeafNotAnchored();
        if (!zkVerifier.verify(proof, publicInputs)) revert InvalidProof();

        usedAttestationLeaves[leaf] = true;
        lastZkNonce[agent] = nonce;
        uint256 expiry = block.timestamp + reportingPeriod;
        scores[agent].zkBoostExpiry = expiry;
        emit ZkAttestationVerified(agent, leaf, expiry);
    }

    /// @notice The score other packages should actually use for threshold checks: the
    /// oracle-reported base score, boosted by ZK_boost only while a verified attestation
    /// is still within its reporting period.
    function effectiveScore(address agent) public view returns (uint256) {
        AgentScore storage s = scores[agent];
        if (block.timestamp <= s.zkBoostExpiry) {
            if (!coverageConfigured[agent]) return (s.baseScore * ZK_BOOST_BPS) / BPS_DENOMINATOR;
            uint256 boostBps =
                BPS_DENOMINATOR + ((ZK_BOOST_BPS - BPS_DENOMINATOR) * zkVerifiedEventRatioBps[agent]) / BPS_DENOMINATOR;
            return (s.baseScore * boostBps) / BPS_DENOMINATOR;
        }
        return s.baseScore;
    }

    function isZkBoosted(address agent) external view returns (bool) {
        if (block.timestamp > scores[agent].zkBoostExpiry) return false;
        return !coverageConfigured[agent] || zkVerifiedEventRatioBps[agent] > 0;
    }

    function getAgent(address agent)
        external
        view
        returns (uint256 baseScore, uint256 effective, bool zkBoosted, uint256 lastUpdate)
    {
        AgentScore storage s = scores[agent];
        return (s.baseScore, effectiveScore(agent), block.timestamp <= s.zkBoostExpiry, s.lastUpdate);
    }
}
