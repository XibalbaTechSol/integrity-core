// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IAccount} from "./IAccount.sol";
import {IExecutionPolicy} from "./IExecutionPolicy.sol";

/// @dev Minimal views of the v2 trust layer, ABI-compatible with `StakeVault` /
/// `PolicyRegistry` / `DiscountRewardModule` (declared here so SovereignAgent does not
/// import their implementations).
interface IAgentStakeVault {
    struct Stake {
        uint256 amount;
        uint256 locked;
        bool frozen;
    }

    function stakeOf(address agent) external view returns (Stake memory);
    function lockForAction(address agent, uint256 req) external;
}

interface IAgentPolicyRegistry {
    function graphRootOf(bytes32 domainId) external view returns (bytes32);
    function domainFloor(bytes32 domainId) external view returns (uint16);
    function checkCompliance(address agent, bytes32 domainId, address target, bytes calldata data)
        external
        view
        returns (bool allowed, uint16 riskWeightBps);
    function checkGraphEdge(
        bytes32 domainId,
        bytes32 fromNode,
        bytes32 relation,
        bytes32 toNode,
        bytes4 targetSelector,
        uint16 riskWeightBps,
        bytes32[] calldata proof
    ) external view returns (bool);
}

interface IAgentRewardDiscount {
    function trustDiscountBps(address agent) external view returns (uint256);
}

/// @title SovereignAgent
/// @notice The per-agent on-chain account for a single AI ("Sovereign") agent.
/// @dev One instance is deployed per agent by `AgentFactory`. It is intentionally a thin
/// account: identity + a cached reputation score + a generic `execute`. Everything
/// heavier (staking, slashing, cross-chain sync, HIPAA gating) lives in the shared
/// oracle/framework/health contracts and simply *reads* this contract's controller/DID,
/// rather than being folded into it — that keeps a compromise of one agent's logic from
/// being able to reach into protocol-wide state it has no business touching.
///
/// SPEC.md §5.3: `execute` MUST consult `IExecutionPolicy` when a policy is installed.
/// address(0) is the disclosed testnet skip path so existing agents keep working.
contract SovereignAgent is AccessControl, IAccount {
    /// @dev Granted to the integrity-oracle backend's signer so it can push AIS cache
    /// updates. Deliberately *not* the same key as DEFAULT_ADMIN_ROLE (the controller):
    /// the oracle should never be able to rotate control of the agent or execute calls
    /// on its behalf, only report a score.
    bytes32 public constant ORACLE_ROLE = keccak256("ORACLE_ROLE");

    /// @dev Off-chain DID string this account is bound to, e.g.
    /// `did:integrity:9f1c...`. Set once at construction; the AgentFactory is
    /// responsible for ensuring DID uniqueness registry-wide (see AgentFactory.sol).
    string private _agentDID;

    /// @notice Cached Agent Integrity Score last reported by the oracle. This is a cache
    /// of `ReputationRegistry`'s value for cheap on-chain reads (e.g. by other
    /// contracts gating access on "this agent's score"); ReputationRegistry remains the
    /// canonical, cross-agent source of truth.
    uint256 public ais;

    /// @notice Monotonic nonce, bumped on every `execute`. Lets off-chain indexers
    /// (integrity-oracle, integrity-dashboard) correlate on-chain actions with the
    /// BCC commitments (`nonce` field, §4.2) an agent submitted off-chain.
    uint256 public executionNonce;

    /// @notice The factory that deployed this agent (informational / for indexers).
    address public immutable factory;

    /// @notice Swappable execution policy. address(0) skips the check (testnet default).
    IExecutionPolicy public executionPolicy;

    /// @notice v2 trust layer. Each module is optional: address(0) skips its gate step so an
    /// agent with nothing wired behaves exactly as before. Wired post-deploy by the controller
    /// (not via the constructor, since every agent self-deploys with the same ctor ABI).
    IAgentStakeVault public stakeVault;
    IAgentPolicyRegistry public policyRegistry;
    IAgentRewardDiscount public rewardDiscountModule;
    /// @notice Policy domain this agent is evaluated under.
    bytes32 public domainId;

    event StakeVaultSet(address indexed stakeVault);
    event PolicyRegistrySet(address indexed policyRegistry);
    event RewardDiscountModuleSet(address indexed rewardDiscountModule);
    event DomainIdSet(bytes32 indexed domainId);

    event AISUpdated(uint256 oldScore, uint256 newScore);
    event ControllerRotated(address indexed oldController, address indexed newController);
    event AgentExecuted(address indexed target, uint256 value, bytes data, uint256 nonce);
    event ExecutionPolicySet(address indexed policy);

    error NotController();
    error PolicyDenied();
    error Frozen();
    error EdgeNotProven();
    error EdgeClaimRequired();

    modifier onlyController() {
        if (!hasRole(DEFAULT_ADMIN_ROLE, msg.sender)) revert NotController();
        _;
    }

    constructor(string memory did_, address controller_, address oracle_, address factory_) {
        require(controller_ != address(0), "SovereignAgent: zero controller");
        _agentDID = did_;
        factory = factory_;

        _grantRole(DEFAULT_ADMIN_ROLE, controller_);
        if (oracle_ != address(0)) {
            _grantRole(ORACLE_ROLE, oracle_);
        }
        // Baseline score before the oracle has ever reported one. 0 rather than an
        // arbitrary "starting reputation" — a nonzero default would let a freshly
        // created, never-scored agent masquerade as one with an established track
        // record in any downstream threshold check (e.g. health/EHRGate.sol).
        ais = 0;
    }

    /// @inheritdoc IAccount
    function agentDID() external view returns (string memory) {
        return _agentDID;
    }

    /// @notice Install or clear the execution policy. Only the controller may do this.
    function setExecutionPolicy(address policy_) external onlyController {
        executionPolicy = IExecutionPolicy(policy_);
        emit ExecutionPolicySet(policy_);
    }

    function setStakeVault(address vault_) external onlyController {
        stakeVault = IAgentStakeVault(vault_);
        emit StakeVaultSet(vault_);
    }

    function setPolicyRegistry(address registry_) external onlyController {
        policyRegistry = IAgentPolicyRegistry(registry_);
        emit PolicyRegistrySet(registry_);
    }

    function setRewardDiscountModule(address module_) external onlyController {
        rewardDiscountModule = IAgentRewardDiscount(module_);
        emit RewardDiscountModuleSet(module_);
    }

    function setDomainId(bytes32 domainId_) external onlyController {
        domainId = domainId_;
        emit DomainIdSet(domainId_);
    }

    /// @inheritdoc IAccount
    /// @dev Arbitrary external call gated to the controller only. Bubbles up the revert
    /// reason from the callee verbatim (via the assembly block) so failures are
    /// debuggable from the controller's perspective instead of collapsing to a generic
    /// "call failed". Policy is evaluated *before* the nonce bump so a denial does not
    /// consume a BCC-correlated nonce.
    function execute(address target, uint256 value, bytes calldata data)
        external
        onlyController
        returns (bytes memory)
    {
        if (address(executionPolicy) != address(0)) {
            if (!executionPolicy.check(address(this), target, value, data)) revert PolicyDenied();
        }
        _checkFrozen();
        uint16 riskWeightBps;
        if (address(policyRegistry) != address(0)) {
            // A graph-governed domain must be driven through the edge-claim overload; the plain
            // path may never skip the proof.
            if (policyRegistry.graphRootOf(domainId) != bytes32(0)) revert EdgeClaimRequired();
            bool ok;
            (ok, riskWeightBps) = policyRegistry.checkCompliance(address(this), domainId, target, data);
            if (!ok) revert PolicyDenied();
        }
        _lockStake(value, riskWeightBps);
        return _dispatch(target, value, data);
    }

    /// @notice Edge-claim overload: same gate as `execute(target,value,data)` but the call is
    /// proven against the domain's committed action graph, bound to `bytes4(data)`.
    function execute(
        address target,
        uint256 value,
        bytes calldata data,
        bytes32 fromNode,
        bytes32 relation,
        bytes32 toNode,
        uint16 riskWeightBps,
        bytes32[] calldata proof
    ) external onlyController returns (bytes memory) {
        if (address(executionPolicy) != address(0)) {
            if (!executionPolicy.check(address(this), target, value, data)) revert PolicyDenied();
        }
        _checkFrozen();
        // An edge claim needs a registry to verify against; with none wired it cannot be proven.
        if (address(policyRegistry) == address(0)) revert EdgeNotProven();
        if (!policyRegistry.checkGraphEdge(
                domainId, fromNode, relation, toNode, bytes4(data), riskWeightBps, proof
            )) revert EdgeNotProven();
        _lockStake(value, riskWeightBps);
        return _dispatch(target, value, data);
    }

    function _checkFrozen() internal view {
        if (address(stakeVault) != address(0) && stakeVault.stakeOf(address(this)).frozen) revert Frozen();
    }

    /// @dev required = floor + value * riskWeightBps / 10000, then scaled by (10000 - discount)
    /// / 10000. Basis-point multiplication only; no subtraction of stake-sized values.
    function _lockStake(uint256 value, uint16 riskWeightBps) internal {
        if (address(stakeVault) == address(0)) return;
        uint256 floor = address(policyRegistry) == address(0) ? 0 : policyRegistry.domainFloor(domainId);
        uint256 required = floor + (value * riskWeightBps) / 10000;
        uint256 discountBps =
            address(rewardDiscountModule) == address(0) ? 0 : rewardDiscountModule.trustDiscountBps(address(this));
        if (discountBps > 10000) discountBps = 10000;
        stakeVault.lockForAction(address(this), (required * (10000 - discountBps)) / 10000);
    }

    function _dispatch(address target, uint256 value, bytes calldata data) internal returns (bytes memory) {
        uint256 nonce = ++executionNonce;
        (bool success, bytes memory result) = target.call{value: value}(data);
        if (!success) {
            assembly {
                revert(add(result, 32), mload(result))
            }
        }
        emit AgentExecuted(target, value, data, nonce);
        return result;
    }

    /// @inheritdoc IAccount
    function updateAIS(uint256 newScore) external onlyRole(ORACLE_ROLE) {
        uint256 old = ais;
        ais = newScore;
        emit AISUpdated(old, newScore);
    }

    /// @notice Rotates control of the agent to a new address.
    /// @dev Only the *current* controller may do this (a single AccessControl role,
    /// not an NFT-ownership check as older prototypes used) — collapsing "who can act
    /// as this agent" into one role avoids the two-sources-of-truth bug where an NFT
    /// transfer and a role grant could disagree about who is actually in control.
    function rotateController(address newController) external onlyController {
        require(newController != address(0), "SovereignAgent: zero controller");
        _revokeRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(DEFAULT_ADMIN_ROLE, newController);
        emit ControllerRotated(msg.sender, newController);
    }

    /// @notice Lets the account receive native value (e.g. refunds from `execute` calls).
    receive() external payable {}
}
