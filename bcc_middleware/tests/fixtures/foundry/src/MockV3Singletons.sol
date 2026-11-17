// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal stand-ins for the v3 trust singletons bcc_middleware talks to:
/// `AgentRegistry`, `TrustConfig`, `StakeVault`, `AISRegistry` and `ActionAnchor`. TEST FIXTURES
/// ONLY. Every function the middleware calls keeps the real contract's exact signature and return
/// shape, because the middleware calls them through the canonical ABIs synced into
/// `integrity_sdk/abis/` (a mock with a different selector or tuple shape fails the suite). Role
/// gates are reduced to plain allowlists, and staking needs no ERC-20.

/// @dev Same record shape as `contracts/src/framework/AgentRegistry.sol`.
contract MockAgentRegistry {
    struct AgentRecord {
        bytes32 pubkey;
        address guardian;
        address actor;
        bytes32 domainId;
        string uri;
        uint64 registeredAt;
        uint64 retiredAt;
        uint8 proofKind;
    }

    error InvalidDid();

    address public trustConfig;
    mapping(bytes32 => AgentRecord) internal _records;
    mapping(address => bytes32) public agentOf;

    function setTrustConfig(address cfg) external {
        trustConfig = cfg;
    }

    /// @notice Registers (or overwrites) the record for `did`, bound to `actor` (zero = no actor).
    function setRecord(string calldata did, address actor, bool retired) external {
        bytes32 fp = fingerprintOfDID(did);
        AgentRecord storage r = _records[fp];
        if (r.actor != address(0)) delete agentOf[r.actor];
        r.pubkey = fp;
        r.guardian = msg.sender;
        r.actor = actor;
        r.domainId = actor == address(0) ? bytes32(0) : keccak256("general.integrity");
        r.registeredAt = uint64(block.timestamp);
        r.retiredAt = retired ? uint64(block.timestamp) : 0;
        r.proofKind = 1;
        if (actor != address(0)) agentOf[actor] = fp;
    }

    function isRegisteredAgent(address actor) external view returns (bool) {
        bytes32 fp = agentOf[actor];
        return fp != bytes32(0) && _records[fp].retiredAt == 0;
    }

    function resolveDID(string calldata did) external view returns (AgentRecord memory) {
        return _records[fingerprintOfDID(did)];
    }

    /// @dev Copied from the real registry so a malformed DID reverts here exactly as it does there.
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
}

contract MockTrustConfig {
    address public stakeVault;

    function setStakeVault(address v) external {
        stakeVault = v;
    }
}

/// @dev Keeps the real vault's split between `stakeOf().locked` (per-action locks) and
/// `disputeLockedOf` (open-dispute holds) as SEPARATE storage, so a test can tell them apart.
contract MockStakeVault {
    struct Stake {
        uint256 amount;
        uint256 locked;
        bool frozen;
    }

    error ZeroAmount();
    error InsufficientAvailableStake();
    error NotDisputer();

    mapping(address => Stake) internal _stakes;
    mapping(address => uint256) public disputeLockedOf;
    mapping(address => bool) public isDisputer;
    uint256 public nextDisputeId;

    event DisputeRaised(uint256 indexed disputeId, address indexed agent, uint256 amount, string reason);

    function grantDisputer(address a) external {
        isDisputer[a] = true;
    }

    function seedStake(address agent, uint256 amount) external {
        _stakes[agent].amount += amount;
    }

    /// @notice Sets the per-action lock (`stakeOf().locked`) without touching dispute holds.
    function setActionLock(address agent, uint256 amount) external {
        _stakes[agent].locked = amount;
    }

    function stakeOf(address agent) external view returns (Stake memory) {
        return _stakes[agent];
    }

    function availableOf(address agent) public view returns (uint256) {
        Stake storage s = _stakes[agent];
        return s.amount - s.locked - disputeLockedOf[agent];
    }

    function raiseDispute(address agent, uint256 amount, string calldata reason) external returns (uint256 disputeId) {
        if (!isDisputer[msg.sender]) revert NotDisputer();
        if (amount == 0) revert ZeroAmount();
        if (availableOf(agent) < amount) revert InsufficientAvailableStake();
        disputeLockedOf[agent] += amount;
        disputeId = nextDisputeId++;
        emit DisputeRaised(disputeId, agent, amount, reason);
    }
}

contract MockAISRegistry {
    struct Checkpoint {
        uint32 score;
        uint64 windowEnd;
        bytes32 evidenceRoot;
    }

    uint32 public constant MAX_SCORE = 10000;

    error ScoreOutOfRange();
    error NotRegisteredAgent(address agent);
    error NotScorer();

    MockAgentRegistry public agentRegistry;
    mapping(address => Checkpoint) public latest;
    mapping(address => uint256) public lastReleasable;
    mapping(address => bool) public isScorer;
    uint256 public checkpointCount;

    event CheckpointPosted(address indexed agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot);

    constructor(MockAgentRegistry registry) {
        agentRegistry = registry;
    }

    function grantScorer(address a) external {
        isScorer[a] = true;
    }

    function postCheckpoint(address agent, uint32 score, uint64 windowEnd, bytes32 evidenceRoot, uint256 releasable)
        external
    {
        if (!isScorer[msg.sender]) revert NotScorer();
        if (score > MAX_SCORE) revert ScoreOutOfRange();
        if (!agentRegistry.isRegisteredAgent(agent)) revert NotRegisteredAgent(agent);
        latest[agent] = Checkpoint({score: score, windowEnd: windowEnd, evidenceRoot: evidenceRoot});
        lastReleasable[agent] = releasable;
        checkpointCount++;
        emit CheckpointPosted(agent, score, windowEnd, evidenceRoot);
    }
}

/// @dev Same storage, event and sorted-pair proof rule as `contracts/src/trust/ActionAnchor.sol`,
/// with the OpenZeppelin `MerkleProof.verify` loop inlined (this fixture project has no libs).
contract MockActionAnchor {
    mapping(address => bytes32) public latestRoot;
    mapping(address => uint256) public epoch;

    event RootAnchored(address indexed agent, uint256 epoch, bytes32 root);

    error EmptyRoot();

    function anchorRoot(bytes32 root) external returns (uint256 newEpoch) {
        if (root == bytes32(0)) revert EmptyRoot();
        newEpoch = ++epoch[msg.sender];
        latestRoot[msg.sender] = root;
        emit RootAnchored(msg.sender, newEpoch, root);
    }

    function verifyLeaf(address agent, bytes32 leaf, bytes32[] calldata proof) external view returns (bool) {
        bytes32 root = latestRoot[agent];
        if (root == bytes32(0)) return false;
        bytes32 h = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 p = proof[i];
            h = h < p ? keccak256(abi.encodePacked(h, p)) : keccak256(abi.encodePacked(p, h));
        }
        return h == root;
    }
}
