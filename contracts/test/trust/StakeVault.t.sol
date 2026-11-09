// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";

contract StakeVaultTest is Test {
    ITK itk;
    StakeVault vault;

    address admin = makeAddr("admin");
    address registry = makeAddr("registry");
    address disputer = makeAddr("disputer");
    address agent = makeAddr("agent");
    address stranger = makeAddr("stranger");

    uint256 constant STAKE = 1000 ether;

    function setUp() public {
        vm.startPrank(admin);
        itk = new ITK(admin, 0);
        vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), registry);
        vault.grantRole(vault.DISPUTER_ROLE(), disputer);
        itk.mint(agent, 10_000 ether);
        vault.setFreezeThreshold(500);
        vm.stopPrank();

        vm.prank(agent);
        itk.approve(address(vault), type(uint256).max);
    }

    function _stake(uint256 amt) internal {
        vm.prank(agent);
        vault.stake(amt);
    }

    function test_stake_increasesAmount() public {
        _stake(STAKE);
        assertEq(vault.stakeOf(agent).amount, STAKE);
        assertEq(itk.balanceOf(address(vault)), STAKE);
    }

    function test_unstake_revertsIfExceedsUnlocked() public {
        _stake(STAKE);
        vm.prank(agent);
        vault.lockForAction(agent, 600 ether);
        vm.prank(agent);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        vault.unstake(500 ether);
        vm.prank(agent);
        vault.unstake(400 ether);
        assertEq(vault.stakeOf(agent).amount, 600 ether);
    }

    function test_lockForAction_incrementsLocked() public {
        _stake(STAKE);
        vm.prank(agent);
        vault.lockForAction(agent, 300 ether);
        assertEq(vault.stakeOf(agent).locked, 300 ether);
    }

    function test_lockForAction_revertsBelowRequired() public {
        _stake(STAKE);
        vm.prank(agent);
        vault.lockForAction(agent, 800 ether);
        vm.prank(agent);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        vault.lockForAction(agent, 300 ether);
    }

    function test_lockForAction_revertsWhenCallerIsNotAgent() public {
        _stake(STAKE);
        vm.prank(stranger);
        vm.expectRevert(StakeVault.NotAgent.selector);
        vault.lockForAction(agent, 1 ether);
    }

    function test_releaseLock_decrementsByMin() public {
        _stake(STAKE);
        vm.prank(agent);
        vault.lockForAction(agent, 300 ether);
        vm.prank(registry);
        vault.releaseLock(agent, 100 ether);
        assertEq(vault.stakeOf(agent).locked, 200 ether);
        vm.prank(registry);
        vault.releaseLock(agent, 999 ether); // more than locked: clamps, no underflow
        assertEq(vault.stakeOf(agent).locked, 0);
    }

    function test_releaseLock_revertsForNonAisRegistry() public {
        _stake(STAKE);
        vm.prank(agent);
        vault.lockForAction(agent, 300 ether);
        vm.prank(stranger);
        vm.expectRevert();
        vault.releaseLock(agent, 1 ether);
        vm.prank(agent);
        vm.expectRevert();
        vault.releaseLock(agent, 1 ether);
    }

    function test_onCheckpoint_freezesBelowThreshold() public {
        vm.prank(registry);
        vault.onCheckpoint(agent, 499);
        assertTrue(vault.stakeOf(agent).frozen);
    }

    function test_onCheckpoint_noFreezeAtOrAbove() public {
        vm.prank(registry);
        vault.onCheckpoint(agent, 500);
        assertFalse(vault.stakeOf(agent).frozen);
        vm.prank(registry);
        vault.onCheckpoint(agent, 900);
        assertFalse(vault.stakeOf(agent).frozen);
    }

    function test_onCheckpoint_doesNotUnfreezeOnLaterGoodScore() public {
        vm.prank(registry);
        vault.onCheckpoint(agent, 100);
        assertTrue(vault.stakeOf(agent).frozen);
        vm.prank(registry);
        vault.onCheckpoint(agent, 1000);
        assertTrue(vault.stakeOf(agent).frozen);
    }

    function test_onCheckpoint_revertsForNonAisRegistryCaller() public {
        vm.prank(stranger);
        vm.expectRevert();
        vault.onCheckpoint(agent, 0);
    }

    function test_unfreeze_onlyAdmin() public {
        vm.prank(registry);
        vault.onCheckpoint(agent, 0);
        vm.prank(stranger);
        vm.expectRevert();
        vault.unfreeze(agent);
        vm.prank(registry);
        vm.expectRevert();
        vault.unfreeze(agent);
        vm.prank(admin);
        vault.unfreeze(agent);
        assertFalse(vault.stakeOf(agent).frozen);
    }

    function test_setFreezeThreshold_onlyAdmin() public {
        vm.prank(stranger);
        vm.expectRevert();
        vault.setFreezeThreshold(1);
        vm.prank(admin);
        vault.setFreezeThreshold(700);
        assertEq(vault.freezeThreshold(), 700);
    }

    function test_raiseDispute_locksThenResolveBurns() public {
        _stake(STAKE);
        uint256 supplyBefore = itk.totalSupply();
        vm.prank(disputer);
        uint256 id = vault.raiseDispute(agent, 400 ether, "bad");
        // Disputed amount cannot be withdrawn
        vm.prank(agent);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        vault.unstake(700 ether);

        vm.warp(block.timestamp + 3 days);
        vm.prank(admin);
        vault.resolveDispute(id, true);

        assertEq(vault.stakeOf(agent).amount, 600 ether);
        assertEq(itk.totalSupply(), supplyBefore - 400 ether);
        assertEq(itk.balanceOf(address(vault)), 600 ether);
        // Cannot resolve twice
        vm.prank(admin);
        vm.expectRevert(StakeVault.DisputeAlreadyResolved.selector);
        vault.resolveDispute(id, true);
    }

    function test_resolveDispute_notSlashedReleasesLock() public {
        _stake(STAKE);
        vm.prank(disputer);
        uint256 id = vault.raiseDispute(agent, 400 ether, "bad");
        vm.warp(block.timestamp + 3 days);
        vm.prank(admin);
        vault.resolveDispute(id, false);
        assertEq(vault.stakeOf(agent).amount, STAKE);
        vm.prank(agent);
        vault.unstake(STAKE);
    }

    function test_resolveDispute_revertsBeforeWindow() public {
        _stake(STAKE);
        vm.prank(disputer);
        uint256 id = vault.raiseDispute(agent, 400 ether, "bad");
        vm.warp(block.timestamp + 3 days - 1);
        vm.prank(admin);
        vm.expectRevert(StakeVault.ChallengeWindowNotElapsed.selector);
        vault.resolveDispute(id, true);
    }

    function test_raiseDispute_onlyDisputer() public {
        _stake(STAKE);
        vm.prank(stranger);
        vm.expectRevert();
        vault.raiseDispute(agent, 1 ether, "x");
    }

    /// A registry releaseLock must not be able to erase a dispute's hold.
    function test_releaseLock_cannotReleaseDisputeLock() public {
        _stake(STAKE);
        vm.prank(disputer);
        uint256 id = vault.raiseDispute(agent, 400 ether, "bad");
        vm.prank(registry);
        vault.releaseLock(agent, 400 ether);
        vm.prank(agent);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        vault.unstake(700 ether);
        vm.warp(block.timestamp + 3 days);
        vm.prank(admin);
        vault.resolveDispute(id, true);
        assertEq(vault.stakeOf(agent).amount, 600 ether);
    }

    function test_lockedNeverExceedsAmount_singleCase() public {
        _stake(STAKE);
        vm.prank(agent);
        vault.lockForAction(agent, 500 ether);
        vm.prank(registry);
        vault.onCheckpoint(agent, 0);
        vm.prank(disputer);
        uint256 id = vault.raiseDispute(agent, 500 ether, "bad");
        StakeVault.Stake memory s = vault.stakeOf(agent);
        assertLe(s.locked, s.amount);
        // No headroom left for another lock or dispute
        vm.prank(agent);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        vault.lockForAction(agent, 1);
        vm.warp(block.timestamp + 3 days);
        vm.prank(admin);
        vault.resolveDispute(id, true);
        s = vault.stakeOf(agent);
        assertEq(s.amount, 500 ether);
        assertEq(s.locked, 500 ether);
        assertLe(s.locked, s.amount);
    }

    function testFuzz_lockedNeverExceedsAmount(uint96 a, uint96 b, uint96 c) public {
        uint256 amt = bound(a, 1, 10_000 ether);
        _stake(amt);
        vm.prank(agent);
        try vault.lockForAction(agent, bound(b, 1, 20_000 ether)) {} catch {}
        vm.prank(registry);
        vault.releaseLock(agent, bound(c, 0, 20_000 ether));
        StakeVault.Stake memory s = vault.stakeOf(agent);
        assertLe(s.locked, s.amount);
    }
}
