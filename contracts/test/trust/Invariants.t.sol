// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {XibalbaAgentRegistry} from "../../src/framework/XibalbaAgentRegistry.sol";
import {GateAllowModule, GateTarget, FactoryStub} from "./ExecuteGating.t.sol";

/// @dev Drives the REAL ITK and StakeVault with bounded actions. The handler holds the
/// MINTER / AIS_REGISTRY / DISPUTER / admin roles; a fixed set of agents acts through
/// vm.prank so `lockForAction` (msg.sender == agent) succeeds.
contract TrustHandler is Test {
    ITK public immutable itk;
    StakeVault public immutable vault;

    address[] public agents;
    uint256[] internal _openDisputes;

    uint256 public constant HARD_CAP = 100_000_000 ether; // hardcoded: independent of itk.MAX_SUPPLY()

    uint256 public lastTotalMinted;
    uint256 public calls;
    /// @dev Ghost flags: set when a guard that must hold was observed broken mid-sequence.
    bool public totalMintedDecreased;
    bool public guardBypassed;

    constructor(ITK itk_, StakeVault vault_) {
        itk = itk_;
        vault = vault_;
        for (uint256 i; i < 4; i++) {
            address a = makeAddr(string(abi.encodePacked("inv-agent-", vm.toString(i))));
            agents.push(a);
            vm.prank(a);
            itk.approve(address(vault_), type(uint256).max);
        }
    }

    function agentCount() external view returns (uint256) {
        return agents.length;
    }

    function _agent(uint256 seed) internal view returns (address) {
        return agents[seed % agents.length];
    }

    function _sync() internal {
        uint256 t = itk.totalMinted();
        if (t < lastTotalMinted) totalMintedDecreased = true;
        lastTotalMinted = t;
        calls++;
    }

    // ---- ITK

    function mintTo(uint256 seed, uint256 amount) external {
        uint256 headroom = itk.MAX_SUPPLY() - itk.totalMinted();
        amount = bound(amount, 0, headroom < 1_000_000 ether ? headroom : 1_000_000 ether);
        if (amount == 0) return;
        itk.mint(_agent(seed), amount);
        _sync();
    }

    /// @dev Fills the supply to the hardcoded cap so the cap boundary is actually reached.
    function mintToCap(uint256 seed) external {
        uint256 t = itk.totalMinted();
        if (t >= HARD_CAP) return;
        itk.mint(_agent(seed), HARD_CAP - t);
        _sync();
    }

    /// @dev Probes the cap: any mint past the hardcoded cap must revert.
    function mintOverCap(uint256 extra) external {
        uint256 t = itk.totalMinted();
        extra = bound(extra, 1, 10 ether);
        try itk.mint(address(this), (HARD_CAP - t) + extra) {
            guardBypassed = true;
        } catch {}
        _sync();
    }

    /// @dev Burns free (unstaked) agent balance; must never reopen mint headroom.
    function burnFrom(uint256 seed, uint256 amount) external {
        address a = _agent(seed);
        amount = bound(amount, 0, itk.balanceOf(a));
        if (amount == 0) return;
        vm.prank(a);
        itk.burn(amount);
        _sync();
    }

    // ---- StakeVault

    function doStake(uint256 seed, uint256 amount) external {
        address a = _agent(seed);
        amount = bound(amount, 0, itk.balanceOf(a));
        if (amount == 0) return;
        vm.prank(a);
        vault.stake(amount);
        _sync();
    }

    // ---- guard attacks: smallest possible over-limit attempts; success = broken guard

    function attackLock(uint256 seed) external {
        address a = _agent(seed);
        uint256 over = vault.availableOf(a) + 1; // read BEFORE prank (prank covers only the next call)
        vm.prank(a);
        try vault.lockForAction(a, over) {
            guardBypassed = true;
        } catch {}
        _sync();
    }

    function attackUnstake(uint256 seed) external {
        address a = _agent(seed);
        uint256 over = vault.availableOf(a) + 1;
        vm.prank(a);
        try vault.requestUnstake(over) {
            guardBypassed = true;
        } catch {}
        _sync();
    }

    /// @dev Unbonding guard: a queued withdrawal must not pay out before its `releaseAt`,
    /// and never while the agent is frozen.
    function attackEarlyOrFrozenWithdraw(uint256 seed) external {
        address a = _agent(seed);
        (uint256 pending, uint256 releaseAt) = vault.unbondingOf(a);
        if (pending == 0) return;
        if (block.timestamp >= releaseAt && !vault.stakeOf(a).frozen) return; // legitimately payable
        vm.prank(a);
        try vault.withdraw() {
            guardBypassed = true;
        } catch {}
        _sync();
    }

    function attackDispute(uint256 seed) external {
        address a = _agent(seed);
        try vault.raiseDispute(a, vault.disputableOf(a) + 1, "attack") {
            guardBypassed = true;
        } catch {}
        _sync();
    }

    function doUnstake(uint256 seed, uint256 amount) external {
        address a = _agent(seed);
        if (vault.stakeOf(a).frozen) return; // A5: a frozen agent cannot withdraw stake
        amount = bound(amount, 0, vault.availableOf(a));
        if (amount == 0) return;
        vm.prank(a);
        vault.requestUnstake(amount);
        _sync();
    }

    function doWithdraw(uint256 seed) external {
        address a = _agent(seed);
        (uint256 pending, uint256 releaseAt) = vault.unbondingOf(a);
        if (pending == 0 || vault.stakeOf(a).frozen) return;
        if (block.timestamp < releaseAt) vm.warp(releaseAt);
        vm.prank(a);
        vault.withdraw();
        _sync();
    }

    function doCancelUnstake(uint256 seed) external {
        address a = _agent(seed);
        (uint256 pending,) = vault.unbondingOf(a);
        if (pending == 0) return;
        vm.prank(a);
        vault.cancelUnstake();
        _sync();
    }

    function doLock(uint256 seed, uint256 amount) external {
        address a = _agent(seed);
        amount = bound(amount, 0, vault.availableOf(a));
        vm.prank(a);
        vault.lockForAction(a, amount);
        _sync();
    }

    /// @dev Amount may exceed `locked` (the vault clamps); never touches dispute holds.
    function doRelease(uint256 seed, uint256 amount) external {
        amount = bound(amount, 0, type(uint128).max);
        vault.releaseLock(_agent(seed), amount);
        _sync();
    }

    function doRaiseDispute(uint256 seed, uint256 amount) external {
        address a = _agent(seed);
        // Bounded by disputableOf, not availableOf, so disputes also claw back queued withdrawals.
        amount = bound(amount, 0, vault.disputableOf(a));
        if (amount == 0) return;
        _openDisputes.push(vault.raiseDispute(a, amount, "inv"));
        _sync();
    }

    function doResolveDispute(uint256 idx, bool slash) external {
        if (_openDisputes.length == 0) return;
        idx = bound(idx, 0, _openDisputes.length - 1);
        uint256 id = _openDisputes[idx];
        _openDisputes[idx] = _openDisputes[_openDisputes.length - 1];
        _openDisputes.pop();
        (,, uint256 raisedAt,,,) = vault.disputes(id);
        if (block.timestamp < raisedAt + vault.disputeWindow()) {
            vm.warp(raisedAt + vault.disputeWindow());
        }
        vault.resolveDispute(id, slash);
        _sync();
    }

    function doCheckpoint(uint256 seed, uint32 score) external {
        vault.onCheckpoint(_agent(seed), score);
        _sync();
    }

    function doUnfreeze(uint256 seed) external {
        vault.unfreeze(_agent(seed));
        _sync();
    }

    function doSetThreshold(uint32 t) external {
        vault.setFreezeThreshold(t);
        _sync();
    }
}

/// forge-config: default.invariant.runs = 256
/// forge-config: default.invariant.depth = 500
/// forge-config: default.invariant.fail-on-revert = true
contract InvariantsTest is Test {
    ITK itk;
    StakeVault vault;
    TrustHandler handler;

    function setUp() public {
        itk = new ITK(address(this), 0);
        vault = new StakeVault(address(itk), address(this));
        handler = new TrustHandler(itk, vault);

        itk.grantRole(itk.MINTER_ROLE(), address(handler));
        vault.grantRole(vault.DEFAULT_ADMIN_ROLE(), address(handler));
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(handler));
        vault.grantRole(vault.DISPUTER_ROLE(), address(handler));

        targetContract(address(handler));
    }

    /// Invariant 1: totalMinted never decreased during the sequence (checked in the handler,
    /// where state persists) and is always within the hardcoded cap.
    function invariant_totalMintedMonotonicAndCapped() public view {
        assertFalse(handler.totalMintedDecreased(), "totalMinted decreased (burn reopened headroom)");
        assertLe(itk.totalMinted(), handler.HARD_CAP(), "totalMinted exceeds hardcoded cap");
        assertLe(itk.totalMinted(), itk.MAX_SUPPLY(), "totalMinted exceeds MAX_SUPPLY");
        assertEq(itk.totalMinted(), handler.lastTotalMinted(), "ghost drift");
    }

    /// Invariant 4: no over-limit lock / unstake / dispute / mint ever succeeded; run was not hollow.
    function invariant_guardsNeverBypassed() public view {
        assertFalse(handler.guardBypassed(), "a guard let an over-limit call succeed");
    }

    /// Guards against a hollow run: the handler must actually have done work.
    function afterInvariant() public view {
        assertGt(handler.calls(), 0, "handler made no successful calls");
    }

    /// Invariant 2: per-agent stake bookkeeping, and availableOf never reverts.
    function invariant_stakeBookkeeping() public view {
        uint256 n = handler.agentCount();
        for (uint256 i; i < n; i++) {
            address a = handler.agents(i);
            StakeVault.Stake memory s = vault.stakeOf(a);
            (uint256 unbonding,) = vault.unbondingOf(a);
            assertLe(
                s.locked + vault.disputeLockedOf(a) + unbonding, s.amount, "locked + disputeLockedOf + unbonding > amount"
            );
            assertEq(vault.availableOf(a), s.amount - s.locked - vault.disputeLockedOf(a) - unbonding);
            assertEq(vault.disputableOf(a), s.amount - s.locked - vault.disputeLockedOf(a));
        }
    }

    /// Solvency: vault ITK balance always equals recorded stake.
    function invariant_vaultSolvent() public view {
        uint256 sum;
        uint256 n = handler.agentCount();
        for (uint256 i; i < n; i++) {
            sum += vault.stakeOf(handler.agents(i)).amount;
        }
        assertEq(itk.balanceOf(address(vault)), sum, "vault balance != sum of stakes");
    }
}

/// Invariant 3: a frozen SovereignAgent cannot execute through EITHER overload, and under the
/// protocol-pinned model has no controller setter to escape through.
contract FrozenAgentGateTest is Test {
    SovereignAgent agentPlain;
    SovereignAgent agentGraph;
    ITK itk;
    StakeVault vault;
    PolicyRegistry policy;
    TrustConfig trustConfig;
    XibalbaAgentRegistry registry;
    FactoryStub factoryStub;
    GateTarget tgt;

    address admin = makeAddr("admin");
    address governance = makeAddr("governance");
    address controller = makeAddr("controller");
    address anchor = makeAddr("anchor");

    bytes32 constant GRAPH_DOMAIN = keccak256("graph-domain");
    bytes32 constant PLAIN_DOMAIN = keccak256("plain-domain");
    bytes32 constant FROM = bytes32(uint256(1));
    bytes32 constant REL = bytes32(uint256(2));
    bytes32 constant TO = bytes32(uint256(3));
    bytes32 constant OTHER_TO = bytes32(uint256(4));
    uint16 constant RISK = 1000;

    bytes32 leafB;

    function setUp() public {
        registry = new XibalbaAgentRegistry(admin);
        factoryStub = new FactoryStub(address(registry));
        agentPlain = new SovereignAgent("did:integrity:inv-plain", controller, address(0), address(factoryStub));
        agentGraph = new SovereignAgent("did:integrity:inv-graph", controller, address(0), address(factoryStub));
        tgt = new GateTarget();
        GateAllowModule module = new GateAllowModule(2000);

        vm.startPrank(admin);
        itk = new ITK(admin, 0);
        vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), admin);
        policy = new PolicyRegistry(admin);
        policy.setModule(PLAIN_DOMAIN, address(module));
        itk.mint(address(agentPlain), 10_000 ether);
        itk.mint(address(agentGraph), 10_000 ether);
        registry.grantRole(registry.REGISTRAR_ROLE(), admin);
        vm.stopPrank();

        trustConfig = new TrustConfig(governance);
        vm.startPrank(governance);
        trustConfig.setStakeVault(address(vault));
        trustConfig.setPolicyRegistry(address(policy));
        vm.stopPrank();

        bytes32 leafA = policy.leafOf(FROM, REL, TO, address(tgt), GateTarget.ping.selector, RISK);
        leafB = policy.leafOf(FROM, REL, OTHER_TO, address(tgt), GateTarget.ping.selector, RISK);
        bytes32 root =
            leafA < leafB ? keccak256(abi.encodePacked(leafA, leafB)) : keccak256(abi.encodePacked(leafB, leafA));
        vm.prank(admin);
        policy.setGraphRoot(GRAPH_DOMAIN, root);
        vm.deal(address(agentPlain), 100 ether);
        vm.deal(address(agentGraph), 100 ether);

        // Register both agents, stake while the gate is inert, then WIRE by pointing the registry
        // at the governance-owned TrustConfig.
        vm.startPrank(admin);
        registry.registerCore(
            registry.didHash("did:integrity:inv-plain"), address(agentPlain), anchor, controller, PLAIN_DOMAIN
        );
        registry.registerCore(
            registry.didHash("did:integrity:inv-graph"), address(agentGraph), anchor, controller, GRAPH_DOMAIN
        );
        vm.stopPrank();

        vm.startPrank(controller);
        agentPlain.execute(address(itk), 0, abi.encodeCall(itk.approve, (address(vault), type(uint256).max)));
        agentPlain.execute(address(vault), 0, abi.encodeCall(vault.stake, (1000 ether)));
        agentGraph.execute(address(itk), 0, abi.encodeCall(itk.approve, (address(vault), type(uint256).max)));
        agentGraph.execute(address(vault), 0, abi.encodeCall(vault.stake, (1000 ether)));
        vm.stopPrank();

        vm.prank(admin);
        registry.setTrustConfig(address(trustConfig));
    }

    /// Any score < threshold latches the freeze; both overloads then revert Frozen. The latch
    /// survives a healthy later checkpoint — only admin unfreeze clears it.
    function testFuzz_frozenAgentCannotExecute(uint32 threshold, uint32 score, uint256 value) public {
        threshold = uint32(bound(threshold, 1, type(uint32).max));
        score = uint32(bound(score, 0, threshold - 1));
        value = bound(value, 0, 10 ether);

        vm.startPrank(admin);
        vault.setFreezeThreshold(threshold);
        vault.onCheckpoint(address(agentPlain), score);
        vault.onCheckpoint(address(agentGraph), score);
        vm.stopPrank();
        assertTrue(vault.stakeOf(address(agentPlain)).frozen);
        assertTrue(vault.stakeOf(address(agentGraph)).frozen);

        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        bytes32[] memory p = new bytes32[](1);
        p[0] = leafB;

        // plain overload (plain-domain agent)
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agentPlain.execute(address(tgt), value, d);

        // edge overload (graph-domain agent)
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agentGraph.execute(address(tgt), value, d, FROM, REL, TO, RISK, p);

        // latch survives a healthy later checkpoint; only admin unfreeze clears it
        vm.prank(admin);
        vault.onCheckpoint(address(agentGraph), type(uint32).max);
        assertTrue(vault.stakeOf(address(agentGraph)).frozen);
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agentGraph.execute(address(tgt), value, d, FROM, REL, TO, RISK, p);

        vm.prank(admin);
        vault.unfreeze(address(agentGraph));
        vm.prank(controller);
        agentGraph.execute(address(tgt), 0, d, FROM, REL, TO, RISK, p);
        assertEq(tgt.pings(), 1);
    }
}
