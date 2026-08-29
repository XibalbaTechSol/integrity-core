// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LicenceToken} from "../../src/licence/LicenceToken.sol";
import {LicenceAccount} from "../../src/licence/LicenceAccount.sol";
import {ILicenceHook} from "../../src/licence/ILicenceHook.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";

/// @notice A recipient with no `receive()`/`fallback()` -- any native-value `call` to it fails,
/// used to prove the protocol-fee leg's failure genuinely reverts the whole settlement.
contract RejectingRecipient {}

/// @notice Phase II settlement-integration slice
/// (`docs/plans/2026-08-24-phase2-settlement-integration-proposal.md`, `PRODUCTION_GAPS.md` #49):
/// proves the protocol fee split (eq 12's phi term) is computed off `royaltyDue`, settled
/// atomically with consumption, and that `protocolFeeBps == 0` is a fully valid no-fee
/// configuration -- same boundary-testing discipline as every other guard in this slice.
contract ProtocolFeeSettlementTest is Test {
    LicenceToken licenceToken;
    address licensee = makeAddr("licensee");
    address protocolFeeRecipient = makeAddr("protocolFeeRecipient");

    uint256 constant VOLUME_CAP = 100;
    uint256 constant ROYALTY_PER_UNIT = 0.01 ether;
    uint256 constant LICENCE_START = 1000;
    uint256 constant LICENCE_DURATION = 30 days;
    uint256 LICENCE_END;

    uint256 constant FEE_BPS = 100; // 1%

    uint256 tokenId;

    function setUp() public {
        vm.warp(LICENCE_START);
        LICENCE_END = LICENCE_START + LICENCE_DURATION;

        licenceToken = new LicenceToken(address(this));
        tokenId = licenceToken.mint(licensee);
        vm.deal(licensee, 100 ether);
    }

    function _accountWithFee(address recipient, uint256 feeBps) internal returns (LicenceAccount) {
        return new LicenceAccount(
            address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, LICENCE_START, LICENCE_END, recipient, feeBps, ILicenceHook(address(0)), AdapterRegistry(address(0)), address(0)
        );
    }

    // --- constructor validation ------------------------------------------------------------------

    function test_constructorRevertsOnNonzeroFeeWithZeroRecipient() public {
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.ZeroFeeRecipient.selector, FEE_BPS));
        _accountWithFee(address(0), FEE_BPS);
    }

    function test_constructorAllowsZeroFeeWithZeroRecipient() public {
        LicenceAccount account = _accountWithFee(address(0), 0);
        assertEq(account.protocolFeeBps(), 0);
        assertEq(account.protocolFeeRecipient(), address(0));
    }

    function test_constructorAllowsZeroFeeWithNonzeroRecipient() public {
        LicenceAccount account = _accountWithFee(protocolFeeRecipient, 0);
        assertEq(account.protocolFeeBps(), 0);
        assertEq(account.protocolFeeRecipient(), protocolFeeRecipient);
    }

    // --- fee computed off royaltyDue, not msg.value ------------------------------------------------

    function test_feeSplitsAtomicallyOnConsume() public {
        LicenceAccount account = _accountWithFee(protocolFeeRecipient, FEE_BPS);
        uint256 units = 10;
        uint256 royaltyDue = units * ROYALTY_PER_UNIT;
        uint256 expectedFee = (royaltyDue * FEE_BPS) / 10_000;

        uint256 recipientBalanceBefore = protocolFeeRecipient.balance;

        vm.prank(licensee);
        account.consume{value: royaltyDue}(units);

        assertEq(protocolFeeRecipient.balance, recipientBalanceBefore + expectedFee, "fee recipient must receive exactly the fee");
        assertEq(address(account).balance, royaltyDue - expectedFee, "account balance must retain exactly the remainder");
    }

    function test_feeSplitsAtomicallyOnConsumeWithIntent() public {
        LicenceAccount account = _accountWithFee(protocolFeeRecipient, FEE_BPS);
        (address licenseeAddr, uint256 licenseeKey) = makeAddrAndKey("feeLicensee");
        vm.prank(licensee);
        licenceToken.transferFrom(licensee, licenseeAddr, tokenId);

        uint256 units = 10;
        uint256 royaltyDue = units * ROYALTY_PER_UNIT;
        uint256 expectedFee = (royaltyDue * FEE_BPS) / 10_000;

        LicenceAccount.ConsumeIntent memory intent =
            LicenceAccount.ConsumeIntent({account: address(account), units: units, nonce: 0, expiry: block.timestamp + 1 hours});
        bytes32 typehash = keccak256("ConsumeIntent(address account,uint256 units,uint256 nonce,uint256 expiry)");
        bytes32 structHash = keccak256(abi.encode(typehash, intent.account, intent.units, intent.nonce, intent.expiry));
        (, string memory name, string memory version, uint256 chainId, address verifyingContract,,) = account.eip712Domain();
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes(version)),
                chainId,
                verifyingContract
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(licenseeKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);

        address relayer = makeAddr("feeRelayer");
        vm.deal(relayer, 10 ether);
        uint256 recipientBalanceBefore = protocolFeeRecipient.balance;

        vm.prank(relayer);
        account.consumeWithIntent{value: royaltyDue}(intent, sig);

        assertEq(protocolFeeRecipient.balance, recipientBalanceBefore + expectedFee);
        assertEq(address(account).balance, royaltyDue - expectedFee);
    }

    function test_feeIsUnaffectedByOverpayment() public {
        // The fee must be computed off royaltyDue (what was actually owed for the units
        // consumed), NOT off msg.value -- an overpaying caller's excess must land entirely in
        // the account's own balance, exactly as it did before any fee existed.
        LicenceAccount account = _accountWithFee(protocolFeeRecipient, FEE_BPS);
        uint256 units = 10;
        uint256 royaltyDue = units * ROYALTY_PER_UNIT;
        uint256 overpayment = 5 * ROYALTY_PER_UNIT;
        uint256 expectedFee = (royaltyDue * FEE_BPS) / 10_000;

        vm.prank(licensee);
        account.consume{value: royaltyDue + overpayment}(units);

        assertEq(protocolFeeRecipient.balance, expectedFee, "overpayment must not inflate the fee");
        assertEq(address(account).balance, royaltyDue + overpayment - expectedFee);
    }

    function test_zeroFeeBpsReproducesPreFeeBehaviorExactly() public {
        LicenceAccount account = _accountWithFee(address(0), 0);
        uint256 units = 10;
        uint256 royaltyDue = units * ROYALTY_PER_UNIT;

        vm.prank(licensee);
        account.consume{value: royaltyDue}(units);

        assertEq(address(account).balance, royaltyDue, "with zero fee, the account must retain the full payment");
    }

    // --- atomic failure -----------------------------------------------------------------------------

    function test_feeTransferFailureRevertsTheWholeConsumption() public {
        RejectingRecipient rejecting = new RejectingRecipient();
        LicenceAccount account = _accountWithFee(address(rejecting), FEE_BPS);
        uint256 units = 10;
        uint256 royaltyDue = units * ROYALTY_PER_UNIT;

        vm.prank(licensee);
        vm.expectRevert();
        account.consume{value: royaltyDue}(units);

        assertEq(account.consumedUnits(), 0, "no partial consumption when the fee leg fails");
        assertEq(address(account).balance, 0, "no funds may move when the fee leg fails");
    }

    function test_feeTransferFailureRevertsConsumeWithIntentToo() public {
        RejectingRecipient rejecting = new RejectingRecipient();
        LicenceAccount account = _accountWithFee(address(rejecting), FEE_BPS);

        (address licenseeAddr, uint256 licenseeKey) = makeAddrAndKey("feeLicensee2");
        vm.prank(licensee);
        licenceToken.transferFrom(licensee, licenseeAddr, tokenId);

        uint256 units = 10;
        uint256 royaltyDue = units * ROYALTY_PER_UNIT;
        LicenceAccount.ConsumeIntent memory intent =
            LicenceAccount.ConsumeIntent({account: address(account), units: units, nonce: 0, expiry: block.timestamp + 1 hours});
        bytes32 typehash = keccak256("ConsumeIntent(address account,uint256 units,uint256 nonce,uint256 expiry)");
        bytes32 structHash = keccak256(abi.encode(typehash, intent.account, intent.units, intent.nonce, intent.expiry));
        (, string memory name, string memory version, uint256 chainId, address verifyingContract,,) = account.eip712Domain();
        bytes32 domainSeparator = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes(version)),
                chainId,
                verifyingContract
            )
        );
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator, structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(licenseeKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);

        address relayer = makeAddr("feeRelayer2");
        vm.deal(relayer, 10 ether);

        vm.prank(relayer);
        vm.expectRevert();
        account.consumeWithIntent{value: royaltyDue}(intent, sig);

        assertEq(account.consumedUnits(), 0);
    }
}
