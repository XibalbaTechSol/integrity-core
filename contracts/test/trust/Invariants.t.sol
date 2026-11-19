// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";

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
