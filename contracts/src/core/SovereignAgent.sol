// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IAccount} from "./IAccount.sol";
import {IExecutionPolicy} from "./IExecutionPolicy.sol";
import {XibalbaAgentRegistry} from "../framework/XibalbaAgentRegistry.sol";

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
    function domainFloor(bytes32 domainId) external view returns (uint256);
    function checkCompliance(address agent, bytes32 domainId, address target, bytes calldata data)
        external
        view
        returns (bool allowed, uint16 riskWeightBps);
    function checkGraphEdge(
        bytes32 domainId,
        bytes32 fromNode,
        bytes32 relation,
        bytes32 toNode,
        address target,
        bytes4 targetSelector,
        uint16 riskWeightBps,
        bytes32[] calldata proof
    ) external view returns (bool);
}

interface IAgentRewardDiscount {
    function trustDiscountBps(address agent) external view returns (uint256);
}

/// @dev The deploying factory, read only for its `registry()` pointer. The factory binds this
/// agent to itself at registration (`AgentPrimitivesFactory` reverts `FactoryMismatch` unless
/// `sa.factory() == address(this)`), so for a registered agent `factory.registry()` is provably
/// the real governance-owned registry — the root of the unspoofable pin.
interface IFactoryLike {
    function registry() external view returns (address);
}

/// @dev The governance-owned pins the gate resolves at call time.
interface ITrustConfigLike {
    function stakeVault() external view returns (address);
    function policyRegistry() external view returns (address);
    function rewardDiscountModule() external view returns (address);
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

    /// @notice v2 trust layer: the stake vault, policy registry, reward-discount module, and the
    /// domain this agent is evaluated under are NOT stored here and NOT controller-settable. They
    /// are PINNED to a governance-owned source and resolved at call time via
    /// `factory.registry().trustConfig()` (modules) and `registry.resolveAgent()` (domain). This
    /// is the redesign that closes the Critical: a self-deployed agent is its own controller, so
    /// any gate reference it could set, it could also swap for a benign fake to escape the freeze.
    /// See `_resolveGate`.

    event AISUpdated(uint256 oldScore, uint256 newScore);
    event ControllerRotated(address indexed oldController, address indexed newController);
    event AgentExecuted(address indexed target, uint256 value, bytes data, uint256 nonce);
    event ExecutionPolicySet(address indexed policy);

    error NotController();
    error PolicyDenied();
    error Frozen();
    error EdgeNotProven();
    error EdgeClaimRequired();
    /// @dev A wiring target must be a contract (or zero to clear). Mirrors `AISRegistry`'s guard.
    error NotAContract(address target);

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
    /// @dev `policy_` must be a contract (or zero to clear); a codeless policy would make every
    /// later `execute` revert on the view call it cannot absorb. Mirrors `AISRegistry`'s guard.
    function setExecutionPolicy(address policy_) external onlyController {
        if (policy_ != address(0) && policy_.code.length == 0) revert NotAContract(policy_);
        executionPolicy = IExecutionPolicy(policy_);
        emit ExecutionPolicySet(policy_);
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
        (address sv, address pr, address rd, bytes32 dom) = _resolveGate();
        _checkFrozen(sv);
        uint16 riskWeightBps;
        if (pr != address(0)) {
            // A graph-governed domain must be driven through the edge-claim overload; the plain
            // path may never skip the proof.
            if (IAgentPolicyRegistry(pr).graphRootOf(dom) != bytes32(0)) revert EdgeClaimRequired();
            bool ok;
            (ok, riskWeightBps) = IAgentPolicyRegistry(pr).checkCompliance(address(this), dom, target, data);
            if (!ok) revert PolicyDenied();
        }
        _lockStake(sv, pr, rd, dom, value, riskWeightBps);
        return _dispatch(target, value, data);
    }

    /// @notice Edge-claim overload: same gate as `execute(target,value,data)` but the call is
    /// proven against the domain's committed action graph, bound to the specific `target` contract
    /// and `bytes4(data)` selector (so one proof no longer authorizes the same selector on any
    /// target).
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
        (address sv, address pr, address rd, bytes32 dom) = _resolveGate();
        _checkFrozen(sv);
        // An edge claim needs a registry to verify against; with none pinned it cannot be proven.
        if (pr == address(0)) revert EdgeNotProven();
        if (
            !IAgentPolicyRegistry(pr).checkGraphEdge(
                dom, fromNode, relation, toNode, target, bytes4(data), riskWeightBps, proof
            )
        ) revert EdgeNotProven();
        _lockStake(sv, pr, rd, dom, value, riskWeightBps);
        return _dispatch(target, value, data);
    }

    function _checkFrozen(address sv) internal view {
        if (sv != address(0) && IAgentStakeVault(sv).stakeOf(address(this)).frozen) revert Frozen();
    }

    /// @dev required = floor + value * riskWeightBps / 10000, then scaled by (10000 - discount)
    /// / 10000. Basis-point multiplication only; no subtraction of stake-sized values.
    function _lockStake(address sv, address pr, address rd, bytes32 dom, uint256 value, uint16 riskWeightBps)
        internal
    {
        if (sv == address(0)) return;
        uint256 floor = pr == address(0) ? 0 : IAgentPolicyRegistry(pr).domainFloor(dom);
        uint256 required = floor + (value * riskWeightBps) / 10000;
        uint256 discountBps = rd == address(0) ? 0 : IAgentRewardDiscount(rd).trustDiscountBps(address(this));
        if (discountBps > 10000) discountBps = 10000;
        IAgentStakeVault(sv).lockForAction(address(this), (required * (10000 - discountBps)) / 10000);
    }

    /// @notice Resolves the PINNED gate references at call time. Returns the stake vault, policy
    /// registry, reward-discount module, and this agent's policy domain — all zero/empty whenever
    /// the gate must be inert.
    /// @dev The gate is inert (returns all zeros) when ANY of the following holds, which is what
    /// preserves "an unwired/unregistered agent behaves exactly as before" and keeps the
    /// registration onboarding sequence (which routes `execute` BEFORE the agent is registered)
    /// working:
    ///   - `factory == 0` or factory is codeless (a never-registered test/standalone agent);
    ///   - `factory.registry()` reverts or is zero/codeless;
    ///   - the agent is NOT yet registered (`isRegisteredAgent == false`) — critically, this guard
    ///     is applied to the WHOLE gate, not just the domain: once governance sets a global
    ///     `trustConfig` with a live `policyRegistry`, a pre-registration `execute` would resolve
    ///     `domainId == 0`, and `checkCompliance` for an unconfigured domain reverts
    ///     `NoModuleConfigured`, bricking onboarding — so an unregistered agent is fully inert;
    ///   - `registry.trustConfig()` is zero/codeless (governance has not wired the trust layer).
    /// Each pin is additionally treated as inert if it is codeless (a misconfigured EOA pin), since
    /// a `try/catch` cannot absorb the caller-side `extcodesize` check on an external call.
    /// Every external read is wrapped so a hostile/broken registry can never brick `execute`; the
    /// pin SOURCE is governance-owned, so "inert on failure" is safe here (it cannot be forced by
    /// the agent to escape an active gate — an active gate means a live, non-reverting config).
    function _resolveGate()
        internal
        view
        returns (address stakeVault_, address policyRegistry_, address rewardDiscountModule_, bytes32 domainId_)
    {
        address f = factory;
        if (f == address(0) || f.code.length == 0) return (address(0), address(0), address(0), bytes32(0));

        address r;
        try IFactoryLike(f).registry() returns (address r_) {
            r = r_;
        } catch {
            return (address(0), address(0), address(0), bytes32(0));
        }
        if (r == address(0) || r.code.length == 0) return (address(0), address(0), address(0), bytes32(0));

        // Registration guard: the whole gate is inert until the agent is registered.
        try XibalbaAgentRegistry(r).isRegisteredAgent(address(this)) returns (bool ok) {
            if (!ok) return (address(0), address(0), address(0), bytes32(0));
        } catch {
            return (address(0), address(0), address(0), bytes32(0));
        }

        // Domain is sourced from the registry record (NOT self-set). `resolveAgent` reverts for an
        // unregistered agent, but the guard above already returned; still wrapped defensively.
        try XibalbaAgentRegistry(r).resolveAgent(address(this)) returns (
            XibalbaAgentRegistry.AgentRecord memory rec
        ) {
            domainId_ = rec.domainId;
        } catch {
            return (address(0), address(0), address(0), bytes32(0));
        }

        address cfg;
        try XibalbaAgentRegistry(r).trustConfig() returns (address c) {
            cfg = c;
        } catch {
            return (address(0), address(0), address(0), bytes32(0));
        }
        if (cfg == address(0) || cfg.code.length == 0) return (address(0), address(0), address(0), domainId_);

        try ITrustConfigLike(cfg).stakeVault() returns (address v) {
            if (v.code.length != 0) stakeVault_ = v;
        } catch {}
        try ITrustConfigLike(cfg).policyRegistry() returns (address p) {
            if (p.code.length != 0) policyRegistry_ = p;
        } catch {}
        try ITrustConfigLike(cfg).rewardDiscountModule() returns (address d) {
            if (d.code.length != 0) rewardDiscountModule_ = d;
        } catch {}
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
