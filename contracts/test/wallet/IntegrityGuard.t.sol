// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { IntegrityGuard } from "../../src/wallet/IntegrityGuard.sol";
import { SafeOperationContext } from "../../src/wallet/SafeOperationContext.sol";
import {
    IntegrityHook,
    IAgentRegistryView,
    IAISRegistryView,
    IStakeVaultView
} from "../../src/wallet/IntegrityHook.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";
import {
    MockAgentRegistry,
    MockAISRegistry,
    MockStakeVault
} from "./mocks/MockTrustLayer.sol";

contract IntegrityGuardTest is Test {
    address internal admin = makeAddr("admin");
    address internal safe7579 = makeAddr("safe7579");
    address internal target = makeAddr("target");
    address internal protocolTarget = makeAddr("protocolTarget");
    address internal safeAccount = makeAddr("safeAccount");

    SafeOperationContext internal ctx;
    MockAgentRegistry internal registry;
    MockAISRegistry internal ais;
    MockStakeVault internal vault;
    IntegrityHook internal hook;
    IntegrityGuard internal guard;

    function setUp() public {
        ctx = new SafeOperationContext(admin);
        registry = new MockAgentRegistry();
        ais = new MockAISRegistry();
        vault = new MockStakeVault();

        hook = new IntegrityHook(
            admin,
            IAgentRegistryView(address(registry)),
            IAISRegistryView(address(ais)),
            IStakeVaultView(address(vault)),
            IOperationContext(address(ctx)),
            1000,
            1 days
        );

        guard = new IntegrityGuard(ctx, hook, safe7579);

        vm.prank(admin);
        ctx.setIntegrityGuard(address(guard));

        vm.prank(admin);
        hook.setProtocolTarget(protocolTarget, true);

        // Baseline valid account in trust layer
        registry.setRegistered(safeAccount, true);
        ais.setCheckpoint(safeAccount, 5000, 100, bytes32(0), uint64(block.timestamp));

        // Install hook on safeAccount (ownerFloor = 2000)
        vm.prank(safeAccount);
        hook.onInstall(abi.encode(uint32(1 days), uint32(2000)));
    }

    function _checkTx(address to, uint256 val, bytes memory data) internal {
        vm.prank(safeAccount);
        guard.checkTransaction(
            to, val, data, 0, 0, 0, 0, address(0), payable(address(0)), "", safeAccount
        );
    }

    function _checkAfter() internal {
        vm.prank(safeAccount);
        guard.checkAfterExecution(bytes32(0), true);
    }

    function test_checkTransaction_sets_and_clears_direct_execution() public {
        assertEq(uint8(ctx.roleOf(safeAccount)), uint8(IOperationContext.Role.Session));

        _checkTx(target, 0, "");
        assertEq(uint8(ctx.roleOf(safeAccount)), uint8(IOperationContext.Role.Owner));

        _checkAfter();
        assertEq(uint8(ctx.roleOf(safeAccount)), uint8(IOperationContext.Role.Session));
    }

    function test_checkTransaction_admin_self_call_allows_normal_actions() public {
        // e.g. adding owner
        bytes memory data = abi.encodeWithSignature("addOwnerWithThreshold(address,uint256)", makeAddr("newOwner"), 1);
        _checkTx(safeAccount, 0, data);
        _checkAfter();
    }

    function test_checkTransaction_admin_reverts_on_setGuard() public {
        bytes memory data = abi.encodeWithSignature("setGuard(address)", makeAddr("newGuard"));
        vm.expectRevert(IntegrityGuard.GuardProtected.selector);
        _checkTx(safeAccount, 0, data);
    }

    function test_checkTransaction_admin_reverts_on_disableModule_safe7579() public {
        bytes memory data = abi.encodeWithSignature("disableModule(address,address)", address(1), safe7579);
        vm.expectRevert(IntegrityGuard.ModuleProtected.selector);
        _checkTx(safeAccount, 0, data);
    }

    function test_checkTransaction_admin_allows_disableModule_other() public {
        bytes memory data = abi.encodeWithSignature("disableModule(address,address)", address(1), makeAddr("otherModule"));
        _checkTx(safeAccount, 0, data);
        _checkAfter();
    }

    function test_checkTransaction_protocol_target_zero_value_allowed_even_if_frozen() public {
        vault.setFrozen(safeAccount, true);
        _checkTx(protocolTarget, 0, "");
        _checkAfter();
    }

    function test_checkTransaction_protocol_target_with_value_enforces_gates() public {
        vault.setFrozen(safeAccount, true);
        vm.expectRevert(IntegrityGuard.Frozen.selector);
        _checkTx(protocolTarget, 1 ether, "");
    }

    function test_checkTransaction_value_moving_reverts_if_frozen() public {
        vault.setFrozen(safeAccount, true);
        vm.expectRevert(IntegrityGuard.Frozen.selector);
        _checkTx(target, 1 ether, "");
    }

    function test_checkTransaction_value_moving_reverts_if_not_registered() public {
        registry.setRegistered(safeAccount, false);
        vm.expectRevert(IntegrityGuard.NotRegistered.selector);
        _checkTx(target, 1 ether, "");
    }

    function test_checkTransaction_value_moving_reverts_if_awaiting_first_checkpoint() public {
        ais.setCheckpoint(safeAccount, 0, 0, bytes32(0), 0);
        vm.expectRevert(IntegrityGuard.AwaitingFirstCheckpoint.selector);
        _checkTx(target, 1 ether, "");
    }

    function test_checkTransaction_value_moving_reverts_if_stale_checkpoint() public {
        vm.warp(block.timestamp + 2 days);
        vm.expectRevert(abi.encodeWithSelector(IntegrityGuard.AisStale.selector, uint64(block.timestamp - 2 days)));
        _checkTx(target, 1 ether, "");
    }

    function test_checkTransaction_value_moving_reverts_if_below_ais_floor() public {
        // Floor is 2000 (ownerFloor); score is 1500
        ais.setCheckpoint(safeAccount, 1500, 100, bytes32(0), uint64(block.timestamp));
        vm.expectRevert(abi.encodeWithSelector(IntegrityGuard.AisBelowFloor.selector, 1500, 2000));
        _checkTx(target, 1 ether, "");
    }
}
