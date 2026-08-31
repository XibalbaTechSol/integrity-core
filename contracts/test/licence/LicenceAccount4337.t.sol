// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {PackedUserOperation} from "@openzeppelin/contracts/interfaces/draft-IERC4337.sol";
import {ERC4337Utils} from "@openzeppelin/contracts/account/utils/draft-ERC4337Utils.sol";
import {LicenceAccount} from "../../src/licence/LicenceAccount.sol";
import {LicenceToken} from "../../src/licence/LicenceToken.sol";
import {ILicenceHook} from "../../src/licence/ILicenceHook.sol";
import {AdapterRegistry} from "../../src/registry/AdapterRegistry.sol";

/// @notice Concrete tests for LicenceAccount's additive ERC-4337 validation path.
/// The tests call the canonical EntryPoint address directly with vm.prank; this proves the
/// account-side authorization and execution hand-off, not a live bundler or paymaster service.
contract LicenceAccount4337Test is Test {
    uint256 constant PRICE = 0.001 ether;
    LicenceToken token;
    LicenceAccount account;
    address owner;
    uint256 ownerPk;
    address sessionKey;
    uint256 sessionKeyPk;

    function setUp() public {
        (owner, ownerPk) = makeAddrAndKey("licence-owner");
        (sessionKey, sessionKeyPk) = makeAddrAndKey("licence-session-key");
        token = new LicenceToken(owner);
        vm.prank(owner);
        uint256 tokenId = token.mint(owner);
        account = new LicenceAccount(
            address(token),
            tokenId,
            100,
            PRICE,
            0,
            type(uint256).max,
            address(0),
            0,
            ILicenceHook(address(0)),
            AdapterRegistry(address(0)),
            address(0)
        );
        deal(address(account), 10 ether);
    }

    function test_ownerSignedUserOpValidatesAndExecutesConsumeThroughEntryPoint() public {
        uint256 units = 2;
        bytes memory callData = abi.encodeWithSelector(
            account.execute.selector,
            address(account),
            units * PRICE,
            abi.encodeWithSelector(account.consume.selector, units),
            uint8(0)
        );
        bytes32 userOpHash = keccak256("owner-user-op");
        PackedUserOperation memory userOp = _userOp(callData, _sign(ownerPk, userOpHash));

        vm.prank(address(account.entryPoint()));
        uint256 validationData = account.validateUserOp(userOp, userOpHash, 0);
        assertEq(validationData, ERC4337Utils.SIG_VALIDATION_SUCCESS);

        vm.prank(address(account.entryPoint()));
        account.execute(address(account), units * PRICE, abi.encodeWithSelector(account.consume.selector, units), 0);

        assertEq(account.consumedUnits(), units);
        assertEq(account.state(), 2, "outer execute and nested consume each commit state");
    }

    function test_sessionKeyUserOpCanOnlyConsume() public {
        vm.prank(owner);
        account.authorizeSessionKey(sessionKey, block.timestamp + 1 days);

        bytes memory allowedCallData = abi.encodeWithSelector(
            account.execute.selector,
            address(account),
            PRICE,
            abi.encodeWithSelector(account.consume.selector, uint256(1)),
            uint8(0)
        );
        bytes32 allowedHash = keccak256("session-consume");
        PackedUserOperation memory allowed = _userOp(allowedCallData, _sign(sessionKeyPk, allowedHash));

        vm.prank(address(account.entryPoint()));
        assertEq(account.validateUserOp(allowed, allowedHash, 0), ERC4337Utils.SIG_VALIDATION_SUCCESS);
        vm.prank(address(account.entryPoint()));
        account.execute(address(account), PRICE, abi.encodeWithSelector(account.consume.selector, uint256(1)), 0);
        assertEq(account.consumedUnits(), 1);

        bytes memory forbiddenCallData = abi.encodeWithSelector(account.execute.selector, address(0xBEEF), 0, "", uint8(0));
        bytes32 forbiddenHash = keccak256("session-arbitrary-call");
        PackedUserOperation memory forbidden = _userOp(forbiddenCallData, _sign(sessionKeyPk, forbiddenHash));
        vm.prank(address(account.entryPoint()));
        assertEq(account.validateUserOp(forbidden, forbiddenHash, 0), ERC4337Utils.SIG_VALIDATION_FAILED);
    }

    function test_invalidSignatureReturnsValidationFailureAndDoesNotArmExecution() public {
        bytes memory callData = abi.encodeWithSelector(
            account.execute.selector, address(account), PRICE, abi.encodeWithSelector(account.consume.selector, 1), uint8(0)
        );
        bytes32 userOpHash = keccak256("invalid-user-op");
        (, uint256 strangerPk) = makeAddrAndKey("stranger");
        PackedUserOperation memory userOp = _userOp(callData, _sign(strangerPk, userOpHash));

        vm.prank(address(account.entryPoint()));
        assertEq(account.validateUserOp(userOp, userOpHash, 0), ERC4337Utils.SIG_VALIDATION_FAILED);

        vm.prank(address(account.entryPoint()));
        vm.expectRevert(LicenceAccount.UserOperationCallDataMismatch.selector);
        account.execute(address(account), PRICE, abi.encodeWithSelector(account.consume.selector, 1), 0);
    }

    function test_entryPointExecutionRequiresByteIdenticalValidatedCallData() public {
        bytes memory callData = abi.encodeWithSelector(
            account.execute.selector, address(account), PRICE, abi.encodeWithSelector(account.consume.selector, 1), uint8(0)
        );
        bytes32 userOpHash = keccak256("bound-user-op");
        PackedUserOperation memory userOp = _userOp(callData, _sign(ownerPk, userOpHash));

        vm.prank(address(account.entryPoint()));
        account.validateUserOp(userOp, userOpHash, 0);
        vm.prank(address(account.entryPoint()));
        vm.expectRevert(LicenceAccount.UserOperationCallDataMismatch.selector);
        account.execute(address(account), PRICE, abi.encodeWithSelector(account.consume.selector, 2), 0);
    }

    function _userOp(bytes memory callData, bytes memory signature) internal view returns (PackedUserOperation memory) {
        return PackedUserOperation({
            sender: address(account),
            nonce: 0,
            initCode: "",
            callData: callData,
            accountGasLimits: bytes32(0),
            preVerificationGas: 0,
            gasFees: bytes32(0),
            paymasterAndData: "",
            signature: signature
        });
    }

    function _sign(uint256 pk, bytes32 digest) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }
}
