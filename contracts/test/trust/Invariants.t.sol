// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {GateAllowModule, GateTarget} from "./ExecuteGating.t.sol";

/// @dev Drives the REAL ITK and StakeVault with bounded actions. The handler holds the
/// MINTER / AIS_REGISTRY / DISPUTER / admin roles; a fixed set of agents acts through
/// vm.prank so `lockForAction` (msg.sender == agent) succeeds.
contract TrustHandler is Test {
    ITK public immutable itk;
    StakeVault public immutable vault;

    address[] public agents;
    uint256[] internal _openDisputes;

    uint256 public lastTotalMinted;
    uint256 public calls;

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
        lastTotalMinted = itk.totalMinted();
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

    /// @dev Probes the cap: an over-cap mint must revert and leave totalMinted unchanged.
    function mintOverCap(uint256 extra) external {
        uint256 headroom = itk.MAX_SUPPLY() - itk.totalMinted();
        extra = bound(extra, 1, 1_000_000 ether);
        uint256 before = itk.totalMinted();
        try itk.mint(address(this), headroom + extra) {
            revert("over-cap mint succeeded");
        } catch {}
        assertEq(itk.totalMinted(), before);
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

    function doUnstake(uint256 seed, uint256 amount) external {
        address a = _agent(seed);
        amount = bound(amount, 0, vault.availableOf(a));
        if (amount == 0) return;
        vm.prank(a);
        vault.unstake(amount);
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
        amount = bound(amount, 0, vault.availableOf(a));
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

contract InvariantsTest is Test {
    ITK itk;
    StakeVault vault;
    TrustHandler handler;

    uint256 internal _prevTotalMinted;

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

    /// Invariant 1: totalMinted never decreases (burns do not reopen headroom) and is capped.
    function invariant_totalMintedMonotonicAndCapped() public {
        uint256 t = itk.totalMinted();
        assertGe(t, _prevTotalMinted, "totalMinted decreased");
        assertLe(t, itk.MAX_SUPPLY(), "totalMinted exceeds MAX_SUPPLY");
        assertEq(t, handler.lastTotalMinted(), "totalMinted drifted from ghost");
        _prevTotalMinted = t;
    }

    /// Invariant 2: per-agent stake bookkeeping, and availableOf never reverts.
    function invariant_stakeBookkeeping() public view {
        uint256 n = handler.agentCount();
        for (uint256 i; i < n; i++) {
            address a = handler.agents(i);
            StakeVault.Stake memory s = vault.stakeOf(a);
            assertLe(s.locked + vault.disputeLockedOf(a), s.amount, "locked + disputeLockedOf > amount");
            assertEq(vault.availableOf(a), s.amount - s.locked - vault.disputeLockedOf(a));
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

/// Invariant 3: a frozen SovereignAgent cannot execute through EITHER overload.
contract FrozenAgentInvariantTest is Test {
    SovereignAgent agent;
    ITK itk;
    StakeVault vault;
    PolicyRegistry registry;
    GateTarget tgt;

    address admin = makeAddr("admin");
    address controller = makeAddr("controller");

    bytes32 constant GRAPH_DOMAIN = keccak256("graph-domain");
    bytes32 constant PLAIN_DOMAIN = keccak256("plain-domain");
    bytes32 constant FROM = bytes32(uint256(1));
    bytes32 constant REL = bytes32(uint256(2));
    bytes32 constant TO = bytes32(uint256(3));
    bytes32 constant OTHER_TO = bytes32(uint256(4));
    uint16 constant RISK = 1000;

    bytes32 leafB;

    function setUp() public {
        agent = new SovereignAgent("did:integrity:inv", controller, address(0), address(0));
        tgt = new GateTarget();
        GateAllowModule module = new GateAllowModule(2000);

        vm.startPrank(admin);
        itk = new ITK(admin, 0);
        vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), admin);
        registry = new PolicyRegistry(admin);
        registry.setModule(PLAIN_DOMAIN, address(module));
        itk.mint(address(agent), 10_000 ether);
        vm.stopPrank();

        bytes32 leafA = registry.leafOf(FROM, REL, TO, GateTarget.ping.selector, RISK);
        leafB = registry.leafOf(FROM, REL, OTHER_TO, GateTarget.ping.selector, RISK);
        bytes32 root =
            leafA < leafB ? keccak256(abi.encodePacked(leafA, leafB)) : keccak256(abi.encodePacked(leafB, leafA));
        vm.prank(admin);
        registry.setGraphRoot(GRAPH_DOMAIN, root);
        vm.deal(address(agent), 100 ether);

        vm.startPrank(controller);
        agent.execute(address(itk), 0, abi.encodeCall(itk.approve, (address(vault), type(uint256).max)));
        agent.execute(address(vault), 0, abi.encodeCall(vault.stake, (1000 ether)));
        agent.setStakeVault(address(vault));
        agent.setPolicyRegistry(address(registry));
        vm.stopPrank();
    }

    /// Any score < threshold latches the freeze; both overloads then revert Frozen.
    function testFuzz_frozenAgentCannotExecute(uint32 threshold, uint32 score, uint256 value) public {
        threshold = uint32(bound(threshold, 1, type(uint32).max));
        score = uint32(bound(score, 0, threshold - 1));
        value = bound(value, 0, 10 ether);

        vm.startPrank(admin);
        vault.setFreezeThreshold(threshold);
        vault.onCheckpoint(address(agent), score);
        vm.stopPrank();
        assertTrue(vault.stakeOf(address(agent)).frozen);

        bytes memory d = abi.encodeCall(GateTarget.ping, ());
        bytes32[] memory p = new bytes32[](1);
        p[0] = leafB;

        // plain overload (plain domain)
        vm.prank(controller);
        agent.setDomainId(PLAIN_DOMAIN);
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agent.execute(address(tgt), value, d);

        // edge overload (graph domain)
        vm.prank(controller);
        agent.setDomainId(GRAPH_DOMAIN);
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agent.execute(address(tgt), value, d, FROM, REL, TO, RISK, p);

        // latch survives a healthy later checkpoint; only admin unfreeze clears it
        vm.prank(admin);
        vault.onCheckpoint(address(agent), type(uint32).max);
        assertTrue(vault.stakeOf(address(agent)).frozen);
        vm.prank(controller);
        vm.expectRevert(SovereignAgent.Frozen.selector);
        agent.execute(address(tgt), value, d, FROM, REL, TO, RISK, p);

        vm.prank(admin);
        vault.unfreeze(address(agent));
        vm.prank(controller);
        agent.execute(address(tgt), 0, d, FROM, REL, TO, RISK, p);
        assertEq(tgt.pings(), 1);
    }
}
