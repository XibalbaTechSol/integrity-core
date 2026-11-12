// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";

/// @notice Unbonding delay (ruling R13): withdrawal is request -> wait -> withdraw, and funds in
/// the queue stay freezable and slashable. The threat is a mempool front-run of the freezing
/// `postCheckpoint`: with instant `unstake`, an agent that sees its bad checkpoint coming pulls
/// its free stake first, leaving nothing to slash.
contract StakeVaultUnbondingTest is Test {
    ITK itk;
    StakeVault vault;

    address admin = makeAddr("admin");
    address registry = makeAddr("registry");
    address disputer = makeAddr("disputer");
    address agent = makeAddr("agent");

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

        vm.startPrank(agent);
        itk.approve(address(vault), type(uint256).max);
        vault.stake(STAKE);
        vm.stopPrank();
    }

    function test_defaultDelayIsSevenDays() public view {
        assertEq(vault.unbondingDelay(), 7 days);
    }

    function test_requestUnstake_queuesWithoutTransfer() public {
        uint256 balBefore = itk.balanceOf(agent);
        vm.prank(agent);
        vault.requestUnstake(400 ether);

        (uint256 pending, uint256 releaseAt) = vault.unbondingOf(agent);
        assertEq(pending, 400 ether);
        assertEq(releaseAt, block.timestamp + 7 days);
        assertEq(itk.balanceOf(agent), balBefore, "no tokens move at request time");
        assertEq(vault.stakeOf(agent).amount, STAKE, "queued funds are still staked");
        assertEq(vault.availableOf(agent), 600 ether, "queued funds are not available");
    }

    function test_withdraw_revertsBeforeDelay_thenPays() public {
        vm.prank(agent);
        vault.requestUnstake(400 ether);

        vm.warp(block.timestamp + 7 days - 1);
        vm.prank(agent);
        vm.expectRevert(StakeVault.UnbondingNotElapsed.selector);
        vault.withdraw();

        vm.warp(block.timestamp + 1);
        uint256 balBefore = itk.balanceOf(agent);
        vm.prank(agent);
        vault.withdraw();
        assertEq(itk.balanceOf(agent), balBefore + 400 ether);
        assertEq(vault.stakeOf(agent).amount, 600 ether);
        (uint256 pending,) = vault.unbondingOf(agent);
        assertEq(pending, 0);
    }

    /// The front-run itself: the agent queues its whole stake just before the freezing
    /// checkpoint lands. With instant unstake the vault would already be empty.
    function test_frontRunOfFreezingCheckpoint_cannotDrain() public {
        vm.prank(agent);
        vault.requestUnstake(STAKE);

        vm.prank(registry);
        vault.onCheckpoint(agent, 100); // below threshold: freeze latches

        vm.warp(block.timestamp + 30 days);
        vm.prank(agent);
        vm.expectRevert(StakeVault.StakeFrozen.selector);
        vault.withdraw();

        assertEq(itk.balanceOf(address(vault)), STAKE, "collateral still in the vault");
    }

    function test_dispute_clawsBackQueuedFunds_andSlashBurnsThem() public {
        vm.prank(agent);
        vault.requestUnstake(STAKE);
        assertEq(vault.availableOf(agent), 0);

        vm.prank(disputer);
        uint256 id = vault.raiseDispute(agent, 700 ether, "fraud");

        (uint256 pending,) = vault.unbondingOf(agent);
        assertEq(pending, 300 ether, "dispute hold comes out of the queue");
        assertEq(vault.disputeLockedOf(agent), 700 ether);

        vm.warp(block.timestamp + 7 days);
        vm.prank(agent);
        vault.withdraw(); // only the undisputed remainder leaves
        assertEq(vault.stakeOf(agent).amount, 700 ether);

        uint256 supplyBefore = itk.totalSupply();
        vm.prank(admin);
        vault.resolveDispute(id, true);
        assertEq(itk.totalSupply(), supplyBefore - 700 ether);
        assertEq(vault.stakeOf(agent).amount, 0);
    }

    function test_requestUnstake_revertsWhenFrozen() public {
        vm.prank(registry);
        vault.onCheckpoint(agent, 100);
        vm.prank(agent);
        vm.expectRevert(StakeVault.StakeFrozen.selector);
        vault.requestUnstake(1 ether);
    }

    function test_requestUnstake_revertsAboveAvailable() public {
        vm.prank(agent);
        vault.lockForAction(agent, 600 ether);
        vm.prank(agent);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        vault.requestUnstake(500 ether);
    }

    function test_requestUnstake_revertsOnZero() public {
        vm.prank(agent);
        vm.expectRevert(StakeVault.ZeroAmount.selector);
        vault.requestUnstake(0);
    }

    function test_queuedFundsCannotBackAnAction() public {
        vm.prank(agent);
        vault.requestUnstake(900 ether);
        vm.prank(agent);
        vm.expectRevert(StakeVault.InsufficientAvailableStake.selector);
        vault.lockForAction(agent, 200 ether);
    }

    function test_secondRequest_accumulatesAndRestartsClock() public {
        vm.prank(agent);
        vault.requestUnstake(100 ether);
        vm.warp(block.timestamp + 6 days);
        vm.prank(agent);
        vault.requestUnstake(50 ether);

        (uint256 pending, uint256 releaseAt) = vault.unbondingOf(agent);
        assertEq(pending, 150 ether);
        assertEq(releaseAt, block.timestamp + 7 days, "topping up restarts the whole queue");
    }

    function test_cancelUnstake_restoresAvailability() public {
        vm.prank(agent);
        vault.requestUnstake(400 ether);
        vm.prank(agent);
        vault.cancelUnstake();
        (uint256 pending, uint256 releaseAt) = vault.unbondingOf(agent);
        assertEq(pending, 0);
        assertEq(releaseAt, 0);
        assertEq(vault.availableOf(agent), STAKE);
    }

    function test_withdraw_revertsWithNothingQueued() public {
        vm.prank(agent);
        vm.expectRevert(StakeVault.NothingUnbonding.selector);
        vault.withdraw();
    }

    function test_setUnbondingDelay_boundsAndAdminOnly() public {
        vm.startPrank(admin);
        vm.expectRevert(StakeVault.UnbondingDelayOutOfBounds.selector);
        vault.setUnbondingDelay(1 days - 1);
        vm.expectRevert(StakeVault.UnbondingDelayOutOfBounds.selector);
        vault.setUnbondingDelay(30 days + 1);
        vault.setUnbondingDelay(1 days);
        vault.setUnbondingDelay(30 days);
        vm.stopPrank();
        assertEq(vault.unbondingDelay(), 30 days);

        bytes32 adminRole = vault.DEFAULT_ADMIN_ROLE(); // read before prank: a view call would consume it
        vm.prank(agent);
        vm.expectRevert(
            abi.encodeWithSelector(IAccessControl.AccessControlUnauthorizedAccount.selector, agent, adminRole)
        );
        vault.setUnbondingDelay(2 days);
    }

    /// Governance shortening the delay must not let an in-flight request out early.
    function test_shorteningDelay_doesNotAccelerateInFlightRequest() public {
        vm.prank(agent);
        vault.requestUnstake(400 ether);
        vm.prank(admin);
        vault.setUnbondingDelay(1 days);

        vm.warp(block.timestamp + 2 days);
        vm.prank(agent);
        vm.expectRevert(StakeVault.UnbondingNotElapsed.selector);
        vault.withdraw();
    }
}
