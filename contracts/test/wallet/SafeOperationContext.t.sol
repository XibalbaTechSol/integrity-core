// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { SafeOperationContext } from "../../src/wallet/SafeOperationContext.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";

contract SafeOperationContextTest is Test {
    address internal admin = makeAddr("admin");
    address internal guard = makeAddr("guard");
    address internal stranger = makeAddr("stranger");
    address internal account = makeAddr("account");

    SafeOperationContext internal ctx;

    function setUp() public {
        ctx = new SafeOperationContext(admin);
        vm.prank(admin);
        ctx.setIntegrityGuard(guard);
    }

    function test_admin_cannot_set_guard_twice() public {
        vm.prank(admin);
        vm.expectRevert(SafeOperationContext.GuardAlreadySet.selector);
        ctx.setIntegrityGuard(makeAddr("guard2"));
    }

    function test_stranger_cannot_set_guard() public {
        SafeOperationContext fresh = new SafeOperationContext(admin);
        vm.prank(stranger);
        vm.expectRevert(SafeOperationContext.Unauthorized.selector);
        fresh.setIntegrityGuard(guard);
    }

    function test_roleOf_zero_address_is_none() public view {
        assertEq(uint8(ctx.roleOf(address(0))), uint8(IOperationContext.Role.None));
    }

    function test_roleOf_default_is_session() public view {
        assertEq(uint8(ctx.roleOf(account)), uint8(IOperationContext.Role.Session));
    }

    function test_guard_can_set_and_clear_direct_execution() public {
        vm.prank(guard);
        ctx.setDirectExecution(account, true);
        assertEq(uint8(ctx.roleOf(account)), uint8(IOperationContext.Role.Owner));

        vm.prank(guard);
        ctx.setDirectExecution(account, false);
        assertEq(uint8(ctx.roleOf(account)), uint8(IOperationContext.Role.Session));
    }

    function test_stranger_cannot_set_direct_execution() public {
        vm.prank(stranger);
        vm.expectRevert(SafeOperationContext.Unauthorized.selector);
        ctx.setDirectExecution(account, true);
    }

    function test_guard_can_set_and_clear_maintenance_execution() public {
        vm.prank(guard);
        ctx.setMaintenanceExecution(account, true);
        assertEq(uint8(ctx.roleOf(account)), uint8(IOperationContext.Role.Maintenance));

        vm.prank(guard);
        ctx.setMaintenanceExecution(account, false);
        assertEq(uint8(ctx.roleOf(account)), uint8(IOperationContext.Role.Session));
    }

    function test_coSignature_set_and_read_and_clear() public {
        bytes memory sig = hex"deadbeef1234";

        vm.prank(guard);
        ctx.setCoSignature(account, sig);
        assertEq(ctx.coSignatureOf(account), sig);

        vm.prank(guard);
        ctx.clearCoSignature(account);
        assertEq(ctx.coSignatureOf(account), "");
    }

    function test_stranger_cannot_set_coSignature() public {
        vm.prank(stranger);
        vm.expectRevert(SafeOperationContext.Unauthorized.selector);
        ctx.setCoSignature(account, hex"1234");
    }
}
