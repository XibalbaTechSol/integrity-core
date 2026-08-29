// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";

/// @title DomainRegistry
/// @notice Registers namespaces ("domains", e.g. `healthcare.integrity`) that agents
/// register under, and decides who is allowed to create an agent in a given domain.
/// @dev Domains exist so verticals (like the HIPAA "Integrity Health" stack) can require agents to
/// belong to a vetted namespace before they're eligible for domain-specific gating
/// (see health/EHRGate.sol, which only trusts a CoveredEntityRegistry entry that in turn
/// only makes sense for agents joined to a healthcare-flavoured domain). Domain
/// membership is intentionally *not* the same thing as reputation/staking — a domain
/// answers "is this agent claiming to operate in the right vertical", reputation answers
/// "has this agent behaved well".
contract DomainRegistry is AccessControl {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    enum JoinMode {
        Open, // anyone may register an agent under this domain
        Permissioned // only addresses the domain owner has approved may join
    }

    struct Domain {
        address owner;
        JoinMode mode;
        bool exists;
        uint256 memberCount;
    }

    /// @dev keyed by keccak256(bytes(domainName)) rather than the string itself — string
    /// keys in a mapping cost an extra hash anyway, so hashing once at the call boundary
    /// and reusing the bytes32 everywhere (events, approvals, membership) is both cheaper
    /// and gives every consumer a fixed-width identifier to index on.
    mapping(bytes32 => Domain) public domains;
    mapping(bytes32 => mapping(address => bool)) public approvedJoiners;
    mapping(bytes32 => mapping(address => bool)) public isMember;

    event DomainRegistered(bytes32 indexed domainId, string name, address indexed owner, JoinMode mode);
    event JoinerApproved(bytes32 indexed domainId, address indexed joiner);
    event JoinerRevoked(bytes32 indexed domainId, address indexed joiner);
    event MemberJoined(bytes32 indexed domainId, address indexed member);
    event DomainModeChanged(bytes32 indexed domainId, JoinMode newMode);

    error DomainAlreadyExists();
    error DomainDoesNotExist();
    error NotDomainOwner();
    error JoinNotApproved();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    function domainId(string memory name) public pure returns (bytes32) {
        return keccak256(bytes(name));
    }

    /// @notice Registers a new domain. Anyone can claim an unclaimed domain name and
    /// become its owner — first-come-first-served, same trust model as ENS second-level
    /// names. Governance/admin can still intervene via REGISTRAR_ROLE for disputes.
    function registerDomain(string calldata name, JoinMode mode) external returns (bytes32 id) {
        id = domainId(name);
        if (domains[id].exists) revert DomainAlreadyExists();
        domains[id] = Domain({owner: msg.sender, mode: mode, exists: true, memberCount: 0});
        emit DomainRegistered(id, name, msg.sender, mode);
    }

    function setJoinMode(bytes32 id, JoinMode mode) external {
        Domain storage d = domains[id];
        if (!d.exists) revert DomainDoesNotExist();
        if (msg.sender != d.owner && !hasRole(REGISTRAR_ROLE, msg.sender)) revert NotDomainOwner();
        d.mode = mode;
        emit DomainModeChanged(id, mode);
    }

    function approveJoiner(bytes32 id, address joiner) external {
        Domain storage d = domains[id];
        if (!d.exists) revert DomainDoesNotExist();
        if (msg.sender != d.owner && !hasRole(REGISTRAR_ROLE, msg.sender)) revert NotDomainOwner();
        approvedJoiners[id][joiner] = true;
        emit JoinerApproved(id, joiner);
    }

    function revokeJoiner(bytes32 id, address joiner) external {
        Domain storage d = domains[id];
        if (!d.exists) revert DomainDoesNotExist();
        if (msg.sender != d.owner && !hasRole(REGISTRAR_ROLE, msg.sender)) revert NotDomainOwner();
        approvedJoiners[id][joiner] = false;
        emit JoinerRevoked(id, joiner);
    }

    /// @notice Returns whether `caller` is currently allowed to register a new agent
    /// under domain `id`. Called by AgentFactory before it deploys a SovereignAgent.
    function canJoin(bytes32 id, address caller) public view returns (bool) {
        Domain storage d = domains[id];
        if (!d.exists) return false;
        if (d.mode == JoinMode.Open) return true;
        return approvedJoiners[id][caller];
    }

    /// @notice Records that `member` has joined domain `id`, on behalf of `approvedAs`.
    /// Restricted to REGISTRAR_ROLE, granted to AgentFactory at deploy time.
    /// @dev `approvedAs` and `member` are deliberately separate parameters: permission
    /// checks (`canJoin`/`approvedJoiners`) are naturally granted to the *controller*
    /// EOA that requested agent creation (that's the address a domain owner can vet
    /// ahead of time), while the actual domain *member* recorded here is the freshly
    /// deployed SovereignAgent contract address (that's the address downstream
    /// consumers like EHRGate check against, since access-control calls arrive with
    /// the agent contract as `msg.sender`). Conflating the two would force domain
    /// owners to pre-approve a CREATE address before it exists, which isn't possible.
    function recordJoin(bytes32 id, address approvedAs, address member) external onlyRole(REGISTRAR_ROLE) {
        Domain storage d = domains[id];
        if (!d.exists) revert DomainDoesNotExist();
        if (!canJoin(id, approvedAs)) revert JoinNotApproved();
        if (!isMember[id][member]) {
            isMember[id][member] = true;
            d.memberCount += 1;
            emit MemberJoined(id, member);
        }
    }
}
