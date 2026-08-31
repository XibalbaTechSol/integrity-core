// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LicenceEconomy} from "../../src/licence/LicenceEconomy.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";

contract MockBuybackExecutor {
    IntegrityToken immutable token;

    constructor(IntegrityToken token_) {
        token = token_;
    }

    fallback() external payable {
        token.transfer(msg.sender, 5 ether);
    }
}

contract LicenceEconomyTest is Test {
    IntegrityToken token;
    LicenceEconomy economy;
    MockBuybackExecutor executor;
    address owner = makeAddr("economy-owner");
    address source = makeAddr("licence-account");
    address adapter = makeAddr("adapter");
    address author = makeAddr("adapter-author");
    address staker = makeAddr("staker");

    function setUp() public {
        token = new IntegrityToken(address(this), 0);
        economy = new LicenceEconomy(owner, address(token), 2_000, 3_000, 2_000, 3_000);
        executor = new MockBuybackExecutor(token);
        token.mint(staker, 100 ether);
        token.mint(address(executor), 100 ether);
        vm.deal(source, 10 ether);
    }

    function test_feeIsRoutedToAuthorStakersBuybackAndTreasury() public {
        vm.startPrank(owner);
        economy.setAdapterAuthor(adapter, author);
        economy.bindLicenceAdapter(source, adapter);
        vm.stopPrank();

        vm.startPrank(staker);
        token.approve(address(economy), 10 ether);
        economy.stake(10 ether);
        vm.stopPrank();

        vm.prank(source);
        (bool sent,) = address(economy).call{value: 1 ether}("");
        assertTrue(sent);
        assertEq(economy.authorRewards(author), 0.2 ether);
        assertEq(economy.accNativeRewardPerShare(), 0.03 ether);
        assertEq(economy.buybackReserve(), 0.2 ether);
        assertEq(economy.treasuryReserve(), 0.3 ether);
    }

    function test_authorAndStakerCanClaimTheirShares() public {
        vm.startPrank(owner);
        economy.setAdapterAuthor(adapter, author);
        economy.bindLicenceAdapter(source, adapter);
        vm.stopPrank();
        vm.startPrank(staker);
        token.approve(address(economy), 10 ether);
        economy.stake(10 ether);
        vm.stopPrank();
        vm.prank(source);
        (bool sent,) = address(economy).call{value: 1 ether}("");
        assertTrue(sent);

        uint256 authorBefore = author.balance;
        vm.prank(author);
        economy.claimAuthorReward();
        assertEq(author.balance - authorBefore, 0.2 ether);

        uint256 stakerBefore = staker.balance;
        vm.prank(staker);
        economy.claimStakerReward();
        assertEq(staker.balance - stakerBefore, 0.3 ether);
    }

    function test_missingAuthorShareFallsBackToTreasury() public {
        vm.prank(source);
        (bool sent,) = address(economy).call{value: 1 ether}("");
        assertTrue(sent);
        assertEq(economy.treasuryReserve(), 0.8 ether);
        assertEq(economy.buybackReserve(), 0.2 ether);
    }

    function test_buybackExecutorOutputIsBurnedAndReserveDecreases() public {
        vm.prank(source);
        (bool sent,) = address(economy).call{value: 1 ether}("");
        assertTrue(sent);
        uint256 supplyBefore = token.totalSupply();
        vm.prank(owner);
        economy.buybackAndBurn(
            payable(address(executor)), 0.2 ether, 5 ether,
            hex"deadbeef"
        );
        assertEq(economy.buybackReserve(), 0);
        assertEq(token.totalSupply(), supplyBefore - 5 ether);
    }

    function test_feeShareGovernanceIsDelayed() public {
        vm.prank(owner);
        economy.proposeFeeShares(1_000, 4_000, 1_000, 4_000);
        vm.expectRevert(abi.encodeWithSelector(LicenceEconomy.FeeSharesNotReady.selector, block.timestamp + 2 days));
        economy.activateFeeShares();
        vm.warp(block.timestamp + 2 days);
        economy.activateFeeShares();
        assertEq(economy.adapterAuthorBps(), 1_000);
        assertEq(economy.stakerBps(), 4_000);
        assertEq(economy.buybackBps(), 1_000);
        assertEq(economy.treasuryBps(), 4_000);
    }

    function test_feeSharesMustSumToOneHundredPercent() public {
        vm.prank(owner);
        vm.expectRevert(LicenceEconomy.InvalidFeeShares.selector);
        economy.proposeFeeShares(1, 2, 3, 4);
    }
}
