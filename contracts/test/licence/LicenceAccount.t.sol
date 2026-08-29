// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LicenceToken} from "../../src/licence/LicenceToken.sol";
import {LicenceAccount} from "../../src/licence/LicenceAccount.sol";
import {ILicenceHook} from "../../src/licence/ILicenceHook.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";
import {IERC6551Account} from "../../src/licence/IERC6551.sol";

/// @notice Phase II tracer-bullet slice
/// (`docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`): proves the three
/// enforced licence terms (volume cap, royalty, expiry) and the transfer-drain guard (eq 17),
/// each at their exact boundary, not just interior cases -- same discipline as every Phase I
/// kernel test.
contract LicenceAccountTest is Test {
    LicenceToken licenceToken;
    LicenceAccount account;

    address licensee = makeAddr("licensee");
    address operator = address(this);

    uint256 constant VOLUME_CAP = 100;
    uint256 constant ROYALTY_PER_UNIT = 0.01 ether;
    uint256 constant LICENCE_START = 1000;
    uint256 constant LICENCE_DURATION = 30 days;
    uint256 LICENCE_END;

    uint256 tokenId;

    function setUp() public {
        vm.warp(LICENCE_START);
        LICENCE_END = LICENCE_START + LICENCE_DURATION;

        licenceToken = new LicenceToken(operator);
        tokenId = licenceToken.mint(licensee);

        account = new LicenceAccount(
            address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, LICENCE_START, LICENCE_END, address(0), 0, ILicenceHook(address(0)), AdapterRegistry(address(0)), address(0)
        );
        vm.deal(licensee, 100 ether);
    }

    // --- ERC-6551 identity/ownership plumbing -------------------------------------------------

    function test_ownerResolvesToCurrentNftHolder() public view {
        assertEq(account.owner(), licensee);
    }

    function test_ownerFollowsAnNftTransfer() public {
        address newOwner = makeAddr("newOwner");
        vm.prank(licensee);
        licenceToken.transferFrom(licensee, newOwner, tokenId);
        assertEq(account.owner(), newOwner, "authority must follow the NFT, not stay with the old holder");
    }

    function test_tokenReturnsTheBoundNft() public view {
        (uint256 chainId, address tokenContract, uint256 returnedTokenId) = account.token();
        assertEq(chainId, block.chainid);
        assertEq(tokenContract, address(licenceToken));
        assertEq(returnedTokenId, tokenId);
    }

    function test_isValidSignerAcceptsTheOwnerAndRejectsEveryoneElse() public {
        assertEq(account.isValidSigner(licensee, ""), IERC6551Account.isValidSigner.selector);
        assertEq(account.isValidSigner(makeAddr("stranger"), ""), bytes4(0));
    }

    // --- volume cap (monotone depletion, eq 13) -----------------------------------------------

    function test_consumeWithinCapSucceeds() public {
        vm.prank(licensee);
        account.consume{value: 10 * ROYALTY_PER_UNIT}(10);
        assertEq(account.consumedUnits(), 10);
    }

    function test_consumeExactlyAtCapSucceeds() public {
        vm.prank(licensee);
        account.consume{value: VOLUME_CAP * ROYALTY_PER_UNIT}(VOLUME_CAP);
        assertEq(account.consumedUnits(), VOLUME_CAP);
    }

    function test_consumeOneUnitOverCapReverts() public {
        vm.prank(licensee);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.VolumeCapExceeded.selector, VOLUME_CAP + 1, VOLUME_CAP));
        account.consume{value: (VOLUME_CAP + 1) * ROYALTY_PER_UNIT}(VOLUME_CAP + 1);
        assertEq(account.consumedUnits(), 0, "no partial consumption on revert");
    }

    function test_cumulativeConsumptionAcrossMultipleCallsCannotExceedCap() public {
        vm.prank(licensee);
        account.consume{value: 60 * ROYALTY_PER_UNIT}(60);
        vm.prank(licensee);
        account.consume{value: 30 * ROYALTY_PER_UNIT}(30);
        assertEq(account.consumedUnits(), 90);

        // 90 + 11 = 101 > 100 -- must revert even though 11 alone would be within a fresh cap.
        vm.prank(licensee);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.VolumeCapExceeded.selector, 11, 10));
        account.consume{value: 11 * ROYALTY_PER_UNIT}(11);
        assertEq(account.consumedUnits(), 90, "the reverted call must not have moved the meter");
    }

    // --- royalty (value conservation, eq 12) ----------------------------------------------------

    function test_consumeRevertsOnInsufficientRoyalty() public {
        vm.prank(licensee);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.InsufficientRoyalty.selector, 10 * ROYALTY_PER_UNIT, 10 * ROYALTY_PER_UNIT - 1)
        );
        account.consume{value: 10 * ROYALTY_PER_UNIT - 1}(10);
        assertEq(account.consumedUnits(), 0);
    }

    function test_royaltyPaymentDirectlyIncreasesTheAccountsOwnBalance() public {
        // Per eq (16), b_I (accrued royalties) IS the account's own balance -- no separate
        // accounting variable. Proven directly, not assumed from the implementation's own
        // comment.
        uint256 balanceBefore = address(account).balance;
        vm.prank(licensee);
        account.consume{value: 10 * ROYALTY_PER_UNIT}(10);
        assertEq(address(account).balance, balanceBefore + 10 * ROYALTY_PER_UNIT);
    }

    function test_consumeAcceptsOverpaymentAndStillCreditsTheFullAmountToBalance() public {
        // No refund logic exists (deliberately -- this slice doesn't implement one); the
        // account's balance grows by the FULL msg.value, not just the required royalty.
        vm.prank(licensee);
        account.consume{value: 20 * ROYALTY_PER_UNIT}(10);
        assertEq(address(account).balance, 20 * ROYALTY_PER_UNIT);
    }

    function test_onlyOwnerCanConsume() public {
        // A real bug caught by running this test, not assumed: a freshly `makeAddr`'d address
        // has zero ETH by default, so an unfunded stranger's call would fail on insufficient
        // balance for `msg.value` BEFORE ever reaching this contract's own `NotAuthorized`
        // check -- `vm.expectRevert` would then match "a revert happened" without confirming
        // it's the RIGHT one. Funding the stranger first ensures the authorization check is what
        // actually gates this call.
        address stranger = makeAddr("stranger");
        vm.deal(stranger, 1 ether);
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.NotAuthorized.selector, stranger));
        account.consume{value: ROYALTY_PER_UNIT}(1);
    }

    // --- expiry (block-timestamp bound, Table 2) ------------------------------------------------

    function test_consumeRevertsBeforeLicenceStarts() public {
        LicenceAccount futureAccount = new LicenceAccount(
            address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, block.timestamp + 1 days, block.timestamp + 31 days, address(0), 0, ILicenceHook(address(0)), AdapterRegistry(address(0)), address(0)
        );
        vm.prank(licensee);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.LicenceNotYetActive.selector, block.timestamp + 1 days, block.timestamp)
        );
        futureAccount.consume{value: ROYALTY_PER_UNIT}(1);
    }

    function test_consumeSucceedsExactlyAtLicenceStart() public {
        // setUp already warps to exactly LICENCE_START -- this test pins that boundary.
        assertEq(block.timestamp, LICENCE_START);
        vm.prank(licensee);
        account.consume{value: ROYALTY_PER_UNIT}(1);
        assertEq(account.consumedUnits(), 1);
    }

    function test_consumeSucceedsExactlyAtLicenceEnd() public {
        vm.warp(LICENCE_END);
        vm.prank(licensee);
        account.consume{value: ROYALTY_PER_UNIT}(1);
        assertEq(account.consumedUnits(), 1);
    }

    function test_consumeRevertsOneSecondAfterLicenceEnd() public {
        vm.warp(LICENCE_END + 1);
        vm.prank(licensee);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.LicenceExpired.selector, LICENCE_END, LICENCE_END + 1));
        account.consume{value: ROYALTY_PER_UNIT}(1);
    }

    function test_constructorRevertsIfStartIsNotBeforeEnd() public {
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.StartNotBeforeEnd.selector, LICENCE_START, LICENCE_START));
        new LicenceAccount(address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, LICENCE_START, LICENCE_START, address(0), 0, ILicenceHook(address(0)), AdapterRegistry(address(0)), address(0));
    }

    // --- transfer-drain guard (eq 17) -----------------------------------------------------------

    function _fundAccountRoyaltyBalance(uint256 amount) internal {
        uint256 units = amount / ROYALTY_PER_UNIT;
        vm.prank(licensee);
        account.consume{value: units * ROYALTY_PER_UNIT}(units);
    }

    function test_withdrawalSucceedsWhenNotArmed() public {
        _fundAccountRoyaltyBalance(10 * ROYALTY_PER_UNIT);
        address payable recipient = payable(makeAddr("recipient"));

        vm.prank(licensee);
        account.execute(recipient, 5 * ROYALTY_PER_UNIT, "", 0);

        assertEq(recipient.balance, 5 * ROYALTY_PER_UNIT);
    }

    function test_armedWithdrawalBelowCommittedBalanceReverts() public {
        _fundAccountRoyaltyBalance(10 * ROYALTY_PER_UNIT);
        vm.prank(licensee);
        account.armTransfer(8 * ROYALTY_PER_UNIT);

        // Withdrawing 3 units would leave 7 < the 8 committed -- must revert.
        address payable recipient = payable(makeAddr("recipient"));
        vm.prank(licensee);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.TransferArmedWithdrawalBlocked.selector, 7 * ROYALTY_PER_UNIT, 8 * ROYALTY_PER_UNIT)
        );
        account.execute(recipient, 3 * ROYALTY_PER_UNIT, "", 0);
        assertEq(address(account).balance, 10 * ROYALTY_PER_UNIT, "no funds may move on a reverted withdrawal");
    }

    function test_armedWithdrawalDownToExactlyCommittedBalanceSucceeds() public {
        _fundAccountRoyaltyBalance(10 * ROYALTY_PER_UNIT);
        vm.prank(licensee);
        account.armTransfer(8 * ROYALTY_PER_UNIT);

        address payable recipient = payable(makeAddr("recipient"));
        vm.prank(licensee);
        account.execute(recipient, 2 * ROYALTY_PER_UNIT, "", 0);
        assertEq(address(account).balance, 8 * ROYALTY_PER_UNIT, "the exact committed boundary must be reachable");
    }

    function test_disarmTransferRestoresUnrestrictedWithdrawal() public {
        _fundAccountRoyaltyBalance(10 * ROYALTY_PER_UNIT);
        vm.prank(licensee);
        account.armTransfer(8 * ROYALTY_PER_UNIT);
        vm.prank(licensee);
        account.disarmTransfer();

        address payable recipient = payable(makeAddr("recipient"));
        vm.prank(licensee);
        account.execute(recipient, 10 * ROYALTY_PER_UNIT, "", 0);
        assertEq(address(account).balance, 0, "disarming must fully lift the withdrawal restriction");
    }

    /// @notice The disclosed simplification, proven directly: arming does NOT auto-clear when
    /// the underlying NFT transfers -- the NEW owner inherits the armed state.
    function test_armedStateSurvivesAnNftTransfer() public {
        _fundAccountRoyaltyBalance(10 * ROYALTY_PER_UNIT);
        vm.prank(licensee);
        account.armTransfer(8 * ROYALTY_PER_UNIT);

        address newOwner = makeAddr("newOwner");
        vm.prank(licensee);
        licenceToken.transferFrom(licensee, newOwner, tokenId);

        assertTrue(account.armed(), "armed state must survive the transfer, not silently clear");

        address payable recipient = payable(makeAddr("recipient"));
        vm.prank(newOwner);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.TransferArmedWithdrawalBlocked.selector, 7 * ROYALTY_PER_UNIT, 8 * ROYALTY_PER_UNIT)
        );
        account.execute(recipient, 3 * ROYALTY_PER_UNIT, "", 0);

        // The new owner CAN disarm it themselves.
        vm.prank(newOwner);
        account.disarmTransfer();
        vm.prank(newOwner);
        account.execute(recipient, 3 * ROYALTY_PER_UNIT, "", 0);
        assertEq(recipient.balance, 3 * ROYALTY_PER_UNIT);
    }

    function test_onlyOwnerCanArmOrDisarmTransfer() public {
        address stranger = makeAddr("stranger");
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.NotAuthorized.selector, stranger));
        account.armTransfer(1);

        vm.prank(licensee);
        account.armTransfer(1);
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.NotAuthorized.selector, stranger));
        account.disarmTransfer();
    }

    // --- execute() mode restriction --------------------------------------------------------------

    function test_executeRejectsNonCallOperations() public {
        vm.prank(licensee);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.UnsupportedOperation.selector, uint8(1)));
        account.execute(makeAddr("target"), 0, "", 1);
    }

    // --- state() counter, ERC-6551's own replay-relevant signal ---------------------------------

    function test_stateIncrementsOnConsumeAndExecute() public {
        uint256 s0 = account.state();
        vm.prank(licensee);
        account.consume{value: ROYALTY_PER_UNIT}(1);
        uint256 s1 = account.state();
        assertGt(s1, s0);

        vm.prank(licensee);
        account.execute(payable(makeAddr("recipient")), 0, "", 0);
        uint256 s2 = account.state();
        assertGt(s2, s1);
    }
}
