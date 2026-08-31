// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {IEntryPoint, IPaymaster, PackedUserOperation} from "@openzeppelin/contracts/interfaces/draft-IERC4337.sol";
import {LicencePaymaster} from "../../src/licence/LicencePaymaster.sol";

contract LicencePaymasterTest is Test {
    LicencePaymaster paymaster;
    IEntryPoint entryPoint;
    address admin;
    address account;

    function setUp() public {
        entryPoint = IEntryPoint(makeAddr("entry-point"));
        admin = makeAddr("paymaster-admin");
        account = makeAddr("licence-account");
        paymaster = new LicencePaymaster(entryPoint, admin, 0.01 ether);
    }

    function test_ownerCanAllowlistAndSponsorWithinCap() public {
        vm.prank(admin);
        paymaster.setSponsoredAccount(account, true);

        PackedUserOperation memory userOp = _userOp(account);
        vm.prank(address(entryPoint));
        (bytes memory context, uint256 validationData) = paymaster.validatePaymasterUserOp(userOp, bytes32(0), 0.01 ether);

        assertEq(context.length, 0);
        assertEq(validationData, 0);
    }

    function test_unapprovedAccountIsRejected() public {
        vm.prank(address(entryPoint));
        vm.expectRevert(abi.encodeWithSelector(LicencePaymaster.SenderNotSponsored.selector, account));
        paymaster.validatePaymasterUserOp(_userOp(account), bytes32(0), 1);
    }

    function test_costAboveConfiguredCapIsRejected() public {
        vm.prank(admin);
        paymaster.setSponsoredAccount(account, true);
        vm.prank(address(entryPoint));
        vm.expectRevert(abi.encodeWithSelector(LicencePaymaster.MaxCostExceeded.selector, 0.01 ether + 1, 0.01 ether));
        paymaster.validatePaymasterUserOp(_userOp(account), bytes32(0), 0.01 ether + 1);
    }

    function test_nonEntryPointCannotValidateOrPostOp() public {
        vm.expectRevert(abi.encodeWithSelector(LicencePaymaster.NotEntryPoint.selector, address(this)));
        paymaster.validatePaymasterUserOp(_userOp(account), bytes32(0), 0);

        vm.expectRevert(abi.encodeWithSelector(LicencePaymaster.NotEntryPoint.selector, address(this)));
        paymaster.postOp(IPaymaster.PostOpMode.opSucceeded, bytes(""), 0, 0);
    }

    function _userOp(address sender) internal pure returns (PackedUserOperation memory) {
        return PackedUserOperation({
            sender: sender,
            nonce: 0,
            initCode: "",
            callData: "",
            accountGasLimits: bytes32(0),
            preVerificationGas: 0,
            gasFees: bytes32(0),
            paymasterAndData: "",
            signature: ""
        });
    }
}
