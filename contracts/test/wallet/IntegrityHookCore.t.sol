// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IntegrityHookBase } from "./IntegrityHookBase.sol";
import {
    IntegrityHook,
    IAgentRegistryView,
    IAISRegistryView,
    IStakeVaultView
} from "../../src/wallet/IntegrityHook.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";
import { MockGovernedAccount, Execution } from "./mocks/MockGovernedAccount.sol";

contract IntegrityHookCoreTest is IntegrityHookBase {
    address internal target;
    address internal protocolTarget;

    function setUp() public override {
        super.setUp();
        target = makeAddr("target");
        protocolTarget = makeAddr("protocolTarget");

        vm.prank(governance);
        hook.setProtocolTarget(protocolTarget, true);
    }

    function test_admin_always_allowed_for_owner_even_when_frozen_and_unscored() public {
        MockGovernedAccount freshAccount = new MockGovernedAccount();
        verifier.setAccount(address(freshAccount), true, owner);

        // Account is frozen and has no checkpoint
        vault.setFrozen(address(freshAccount), true);
        assertEq(ais.postedAt(address(freshAccount)), 0);

        // Role is owner
        ctx.setRole(address(freshAccount), IOperationContext.Role.Owner);

        // Owner installing a module succeeds
        freshAccount.installModule(4, address(hook), abi.encode(uint32(1 days), uint32(0)));
        assertTrue(hook.isInitialized(address(freshAccount)));
    }

    function test_admin_by_session_reverts_NotOwner() public {
        ctx.setRole(address(account), IOperationContext.Role.Session);

        // Session trying to install module reverts NotOwner
        vm.expectRevert(IntegrityHook.NotOwner.selector);
        account.installModule(1, makeAddr("validator"), "");

        // Session trying to execute call to account itself (admin target) reverts NotOwner
        bytes memory execCalldata = _singleCall(address(account), 0, "");
        vm.expectRevert(IntegrityHook.NotOwner.selector);
        account.execute(bytes32(0), execCalldata);
    }

    function test_owner_anchor_is_admin_even_when_frozen() public {
        // Frozen + unscored account
        vault.setFrozen(address(account), true);
        ais.setCheckpoint(address(account), 0, 0, bytes32(0), 0);

        ctx.setRole(address(account), IOperationContext.Role.Owner);

        // Calling protocol target with 0 value is Admin -> succeeds even when frozen and unscored
        bytes memory execCalldata = _singleCall(protocolTarget, 0, hex"1234");
        account.execute(bytes32(0), execCalldata);
    }

    function test_session_call_to_protocol_target_NotOwner() public {
        ctx.setRole(address(account), IOperationContext.Role.Session);

        bytes memory execCalldata = _singleCall(protocolTarget, 0, hex"1234");
        vm.expectRevert(IntegrityHook.NotOwner.selector);
        account.execute(bytes32(0), execCalldata);
    }

    function test_value_reverts_Frozen() public {
        ctx.setRole(address(account), IOperationContext.Role.Session);
        vault.setFrozen(address(account), true);

        bytes memory execCalldata = _singleCall(target, 0, hex"aabb");
        vm.expectRevert(IntegrityHook.Frozen.selector);
        account.execute(bytes32(0), execCalldata);
    }

    function test_value_reverts_NotRegistered_and_after_retire() public {
        ctx.setRole(address(account), IOperationContext.Role.Session);

        // Unregistered agent reverts NotRegistered
        registry.setRegistered(address(account), false);
        bytes memory execCalldata = _singleCall(target, 0, hex"aabb");
        vm.expectRevert(IntegrityHook.NotRegistered.selector);
        account.execute(bytes32(0), execCalldata);

        // Register agent -> passes check
        registry.setRegistered(address(account), true);
        account.execute(bytes32(0), execCalldata);

        // After retire -> reverts NotRegistered
        registry.setRegistered(address(account), false);
        vm.expectRevert(IntegrityHook.NotRegistered.selector);
        account.execute(bytes32(0), execCalldata);
    }

    function test_value_reverts_AwaitingFirstCheckpoint() public {
        MockGovernedAccount fresh = new MockGovernedAccount();
        verifier.setAccount(address(fresh), true, owner);
        registry.setRegistered(address(fresh), true);
        // postedAt is 0 (no checkpoint)
        assertEq(ais.postedAt(address(fresh)), 0);

        ctx.setRole(address(fresh), IOperationContext.Role.Owner);
        fresh.installModule(4, address(hook), abi.encode(uint32(1 days), uint32(0)));

        ctx.setRole(address(fresh), IOperationContext.Role.Session);
        bytes memory execCalldata = _singleCall(target, 0, hex"aabb");
        vm.expectRevert(IntegrityHook.AwaitingFirstCheckpoint.selector);
        fresh.execute(bytes32(0), execCalldata);
    }

    function test_value_reverts_AisStale_after_maxCheckpointAge() public {
        ctx.setRole(address(account), IOperationContext.Role.Session);
        uint64 posted = ais.postedAt(address(account));

        // Warp past maxCheckpointAge (1 days)
        vm.warp(block.timestamp + 1 days + 1);

        bytes memory execCalldata = _singleCall(target, 0, hex"aabb");
        vm.expectRevert(abi.encodeWithSelector(IntegrityHook.AisStale.selector, posted));
        account.execute(bytes32(0), execCalldata);
    }

    function test_value_reverts_AisBelowFloor_max_of_protocol_and_owner() public {
        // Setup: protocol floor 5000, owner floor 9000, score 8000 -> floor 9000
        vm.prank(governance);
        hook.setProtocolFloor(5000);

        MockGovernedAccount accWithHighFloor = new MockGovernedAccount();
        verifier.setAccount(address(accWithHighFloor), true, owner);
        registry.setRegistered(address(accWithHighFloor), true);
        ais.setCheckpoint(
            address(accWithHighFloor),
            8000,
            100,
            bytes32(0),
            uint64(block.timestamp)
        );

        ctx.setRole(address(accWithHighFloor), IOperationContext.Role.Owner);
        accWithHighFloor.installModule(
            4,
            address(hook),
            abi.encode(uint32(1 days), uint32(9000))
        );

        ctx.setRole(address(accWithHighFloor), IOperationContext.Role.Session);
        bytes memory execCalldata = _singleCall(target, 0, hex"aabb");
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityHook.AisBelowFloor.selector, uint32(8000), uint32(9000))
        );
        accWithHighFloor.execute(bytes32(0), execCalldata);
    }

    function test_owner_value_op_still_runs_checks_1_to_3() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vault.setFrozen(address(account), true);

        bytes memory execCalldata = _singleCall(target, 0, hex"aabb");
        vm.expectRevert(IntegrityHook.Frozen.selector);
        account.execute(bytes32(0), execCalldata);
    }

    function test_delegatecall_denied_for_session() public {
        ctx.setRole(address(account), IOperationContext.Role.Session);

        // mode with callType = 0xff (byte 0 is 0xff)
        bytes32 mode = bytes32(uint256(0xff) << 248);
        bytes memory execCalldata = abi.encodePacked(target, hex"1234");

        vm.expectRevert(IntegrityHook.DelegatecallDenied.selector);
        account.execute(mode, execCalldata);
    }

    function test_constructor_rejects_zero_maxCheckpointAge() public {
        vm.expectRevert(IntegrityHook.ZeroMaxCheckpointAge.selector);
        new IntegrityHook(
            governance,
            IAgentRegistryView(address(registry)),
            IAISRegistryView(address(ais)),
            IStakeVaultView(address(vault)),
            IOperationContext(address(ctx)),
            DEFAULT_PROTOCOL_FLOOR,
            0
        );
    }
}
