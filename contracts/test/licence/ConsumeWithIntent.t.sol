// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {LicenceToken} from "../../src/licence/LicenceToken.sol";
import {LicenceAccount} from "../../src/licence/LicenceAccount.sol";
import {ILicenceHook} from "../../src/licence/ILicenceHook.sol";
import {Nonces} from "@openzeppelin/contracts/utils/Nonces.sol";

/// @notice Phase II ATCP/IP signed-intent slice
/// (`docs/plans/2026-08-24-phase2-atcpip-intent-format-proposal.md`, `PRODUCTION_GAPS.md` §48):
/// proves `consumeWithIntent()`'s signature/session/domain/nonce checks, each at their exact
/// boundary, same discipline as the base slice's own volume-cap/royalty/expiry tests.
contract ConsumeWithIntentTest is Test {
    LicenceToken licenceToken;
    LicenceAccount account;

    uint256 licenseeKey;
    address licensee;
    uint256 sessionKeyPk;
    address sessionKey;
    address relayer = makeAddr("relayer");

    uint256 constant VOLUME_CAP = 100;
    uint256 constant ROYALTY_PER_UNIT = 0.01 ether;
    uint256 constant LICENCE_START = 1000;
    uint256 constant LICENCE_DURATION = 30 days;
    uint256 LICENCE_END;

    uint256 tokenId;

    bytes32 constant CONSUME_INTENT_TYPEHASH =
        keccak256("ConsumeIntent(address account,uint256 units,uint256 nonce,uint256 expiry)");

    function setUp() public {
        vm.warp(LICENCE_START);
        LICENCE_END = LICENCE_START + LICENCE_DURATION;

        (licensee, licenseeKey) = makeAddrAndKey("licensee");
        (sessionKey, sessionKeyPk) = makeAddrAndKey("sessionKey");

        licenceToken = new LicenceToken(address(this));
        tokenId = licenceToken.mint(licensee);

        account = new LicenceAccount(
            address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, LICENCE_START, LICENCE_END, address(0), 0, ILicenceHook(address(0))
        );

        vm.deal(relayer, 100 ether);
    }

    function _domainSeparator() internal view returns (bytes32) {
        (, string memory name, string memory version, uint256 chainId, address verifyingContract,,) =
            account.eip712Domain();
        return keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes(name)),
                keccak256(bytes(version)),
                chainId,
                verifyingContract
            )
        );
    }

    function _signIntent(uint256 pk, LicenceAccount.ConsumeIntent memory intent) internal view returns (bytes memory) {
        bytes32 structHash =
            keccak256(abi.encode(CONSUME_INTENT_TYPEHASH, intent.account, intent.units, intent.nonce, intent.expiry));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", _domainSeparator(), structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    function _intent(uint256 units, uint256 nonce, uint256 expiry) internal view returns (LicenceAccount.ConsumeIntent memory) {
        return LicenceAccount.ConsumeIntent({account: address(account), units: units, nonce: nonce, expiry: expiry});
    }

    // --- owner-signed intents, submitted by an unrelated relayer -------------------------------

    function test_ownerSignedIntentSucceedsWhenSubmittedByAnyRelayer() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(10, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.prank(relayer);
        account.consumeWithIntent{value: 10 * ROYALTY_PER_UNIT}(intent, sig);

        assertEq(account.consumedUnits(), 10);
        assertEq(account.nonces(licensee), 1, "the signer's nonce must advance, not the relayer's");
    }

    // --- session keys ----------------------------------------------------------------------------

    function test_authorizedUnexpiredSessionKeySucceeds() public {
        vm.prank(licensee);
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 days);

        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(sessionKeyPk, intent);

        vm.prank(relayer);
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
        assertEq(account.consumedUnits(), 5);
    }

    function test_onlyOwnerCanAuthorizeASessionKey() public {
        address stranger = makeAddr("stranger");
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.NotAuthorized.selector, stranger));
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 days);
    }

    function test_authorizeSessionKeyRevertsOnZeroAddress() public {
        vm.prank(licensee);
        vm.expectRevert(LicenceAccount.ZeroSessionKey.selector);
        account.authorizeSessionKey(address(0), block.timestamp + 1 days);
    }

    function test_authorizeSessionKeyRevertsOnPastExpiry() public {
        vm.prank(licensee);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.SessionKeyExpiryInPast.selector, block.timestamp - 1, block.timestamp)
        );
        account.authorizeSessionKey(sessionKey, block.timestamp - 1);
    }

    function test_expiredSessionKeyIntentReverts() public {
        vm.prank(licensee);
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 hours);

        vm.warp(block.timestamp + 2 hours);
        // Snapshot into a local, and -- confirmed by isolating this exact expression with
        // console2.log under this repo's via_ir=true -- add the literal FIRST, not last. With
        // this file's solc 0.8.28 + via_ir build, `nowAfterWarp + 1 hours` miscompiles (it
        // silently reused a DIFFERENT block.timestamp-derived value already live in this
        // function, from `authorizeSessionKey`'s own `block.timestamp + 1 hours` argument
        // above, evaluated before the warp -- an operand-order-sensitive optimizer bug, not a
        // logic error in this test). `1 hours + nowAfterWarp` compiles correctly. Verified: the
        // reordered form alone (no local) also worked, but the local read is kept too for a
        // provably fresh TIMESTAMP opcode read, not just to dodge one bad codegen shape.
        uint256 nowAfterWarp = block.timestamp;

        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, 1 hours + nowAfterWarp);
        bytes memory sig = _signIntent(sessionKeyPk, intent);

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.UnauthorizedSigner.selector, sessionKey));
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
    }

    function test_sessionKeyValidExactlyAtItsOwnExpiryBoundary() public {
        vm.prank(licensee);
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 hours);

        vm.warp(block.timestamp + 1 hours);
        // See test_expiredSessionKeyIntentReverts's comment -- same via_ir operand-order
        // miscompilation; literal-first is the confirmed-working form.
        uint256 nowAfterWarp = block.timestamp;

        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, 1 hours + nowAfterWarp);
        bytes memory sig = _signIntent(sessionKeyPk, intent);

        vm.prank(relayer);
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
        assertEq(account.consumedUnits(), 5, "the exact expiry timestamp itself must still be valid");
    }

    function test_revokedSessionKeyIntentReverts() public {
        vm.prank(licensee);
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 days);
        vm.prank(licensee);
        account.revokeSessionKey(sessionKey);

        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(sessionKeyPk, intent);

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.UnauthorizedSigner.selector, sessionKey));
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
    }

    function test_onlyOwnerCanRevokeASessionKey() public {
        vm.prank(licensee);
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 days);

        address stranger = makeAddr("stranger");
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.NotAuthorized.selector, stranger));
        account.revokeSessionKey(sessionKey);
    }

    function test_neverAuthorizedKeyIntentReverts() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(sessionKeyPk, intent);

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.UnauthorizedSigner.selector, sessionKey));
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
    }

    function test_sessionKeyCannotCallExecuteOrArmTransferDirectly() public {
        vm.prank(licensee);
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 days);

        vm.prank(sessionKey);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.NotAuthorized.selector, sessionKey));
        account.execute(payable(relayer), 0, "", 0);

        vm.prank(sessionKey);
        vm.expectRevert(abi.encodeWithSelector(LicenceAccount.NotAuthorized.selector, sessionKey));
        account.armTransfer(0);
    }

    // --- domain binding --------------------------------------------------------------------------

    function test_intentSignedForADifferentAccountReverts() public {
        LicenceAccount otherAccount = new LicenceAccount(
            address(licenceToken), tokenId, VOLUME_CAP, ROYALTY_PER_UNIT, LICENCE_START, LICENCE_END, address(0), 0, ILicenceHook(address(0))
        );

        // Intent's `account` field names `otherAccount`, but we submit it against `account`.
        LicenceAccount.ConsumeIntent memory intent = LicenceAccount.ConsumeIntent({
            account: address(otherAccount),
            units: 5,
            nonce: 0,
            expiry: block.timestamp + 1 hours
        });
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.IntentDomainMismatch.selector, address(account), address(otherAccount))
        );
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
    }

    // --- intent expiry -----------------------------------------------------------------------------

    function test_intentPastItsOwnExpiryReverts() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.warp(block.timestamp + 1 hours + 1);

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.IntentExpired.selector, block.timestamp - 1, block.timestamp)
        );
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
    }

    function test_intentValidExactlyAtItsOwnExpiryBoundary() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.warp(block.timestamp + 1 hours);

        vm.prank(relayer);
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
        assertEq(account.consumedUnits(), 5);
    }

    // --- nonce replay-protection -------------------------------------------------------------------

    function test_reusedNonceReverts() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.prank(relayer);
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);

        // Same nonce again -- must revert even though the signature itself is validly formed.
        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(Nonces.InvalidAccountNonce.selector, licensee, 1));
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
    }

    function test_outOfOrderNonceReverts() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(5, 1, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.prank(relayer);
        vm.expectRevert(abi.encodeWithSelector(Nonces.InvalidAccountNonce.selector, licensee, 0));
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(intent, sig);
    }

    function test_sequentialIntentsFromTheSameSignerSucceed() public {
        LicenceAccount.ConsumeIntent memory first = _intent(5, 0, block.timestamp + 1 hours);
        vm.prank(relayer);
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT}(first, _signIntent(licenseeKey, first));

        LicenceAccount.ConsumeIntent memory second = _intent(3, 1, block.timestamp + 1 hours);
        vm.prank(relayer);
        account.consumeWithIntent{value: 3 * ROYALTY_PER_UNIT}(second, _signIntent(licenseeKey, second));

        assertEq(account.consumedUnits(), 8);
    }

    // --- falls through to the same enforcement consume() itself uses -------------------------------

    function test_intentStillEnforcesVolumeCap() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(VOLUME_CAP + 1, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.VolumeCapExceeded.selector, VOLUME_CAP + 1, VOLUME_CAP)
        );
        account.consumeWithIntent{value: (VOLUME_CAP + 1) * ROYALTY_PER_UNIT}(intent, sig);
    }

    function test_intentStillEnforcesRoyalty() public {
        LicenceAccount.ConsumeIntent memory intent = _intent(5, 0, block.timestamp + 1 hours);
        bytes memory sig = _signIntent(licenseeKey, intent);

        vm.prank(relayer);
        vm.expectRevert(
            abi.encodeWithSelector(LicenceAccount.InsufficientRoyalty.selector, 5 * ROYALTY_PER_UNIT, 5 * ROYALTY_PER_UNIT - 1)
        );
        account.consumeWithIntent{value: 5 * ROYALTY_PER_UNIT - 1}(intent, sig);
    }

    function test_consumeDirectPathStillWorksUnchanged() public {
        vm.deal(licensee, 10 ether);
        vm.prank(licensee);
        account.consume{value: 10 * ROYALTY_PER_UNIT}(10);
        assertEq(account.consumedUnits(), 10);
    }
}
