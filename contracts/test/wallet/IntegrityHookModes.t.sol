// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Vm } from "forge-std/Vm.sol";
import { IntegrityHookBase } from "./IntegrityHookBase.sol";
import { IntegrityHook } from "../../src/wallet/IntegrityHook.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";
import { ITK } from "../../src/trust/ITK.sol";

contract IntegrityHookModesTest is IntegrityHookBase {
    ITK internal itk;
    address internal recipient;
    Vm.Wallet internal cosignerWallet;

    uint128 internal constant TOKEN_PER_CALL = 100e18;
    uint128 internal constant TOKEN_PER_WINDOW = 250e18;

    function setUp() public override {
        super.setUp();

        recipient = makeAddr("recipient");
        cosignerWallet = vm.createWallet("cosigner");

        itk = new ITK(address(this), 0);
        itk.grantRole(itk.MINTER_ROLE(), address(this));

        vm.prank(governance);
        hook.setKnownToken(address(itk), true);

        ctx.setRole(address(account), IOperationContext.Role.Owner);

        vm.startPrank(address(account));
        hook.setTokenLimit(address(itk), TOKEN_PER_CALL, TOKEN_PER_WINDOW);
        hook.setWindow(uint32(1 days));
        hook.setAllowlisted(address(itk), true);
        hook.setAllowlisted(recipient, true);
        vm.stopPrank();

        itk.mint(address(account), 2000e18);

        ctx.setRole(address(account), IOperationContext.Role.Session);
    }

    function _signCoSign(
        address acc,
        address tgt,
        uint256 val,
        bytes memory data,
        uint256 nonce,
        uint256 deadline
    ) internal view returns (bytes memory) {
        bytes32 digest = hook.coSignDigest(acc, tgt, val, keccak256(data), nonce, deadline);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(cosignerWallet.privateKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);
        return abi.encode(sig, deadline);
    }

    function test_cosign_required_when_cosigner_set() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.setCoSigner(cosignerWallet.addr);

        ctx.setRole(address(account), IOperationContext.Role.Session);
        bytes memory transferCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 10e18)
        );

        // No signature provided
        vm.expectRevert(IntegrityHook.CoSignerRequired.selector);
        account.execute(bytes32(0), transferCall);
    }

    function test_cosign_valid_passes_and_nonce_increments() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.setCoSigner(cosignerWallet.addr);

        ctx.setRole(address(account), IOperationContext.Role.Session);
        bytes memory data = abi.encodeWithSelector(itk.transfer.selector, recipient, 10e18);
        bytes memory transferCall = _singleCall(address(itk), 0, data);

        uint256 nonceBefore = hook.coSignNonce(address(account));
        assertEq(nonceBefore, 0);

        bytes memory coSig = _signCoSign(
            address(account),
            address(itk),
            0,
            data,
            nonceBefore,
            block.timestamp + 1 hours
        );
        ctx.setCoSignature(address(account), coSig);

        account.execute(bytes32(0), transferCall);

        assertEq(hook.coSignNonce(address(account)), 1);
        assertEq(itk.balanceOf(recipient), 10e18);
    }

    function test_cosign_replay_and_expired_deadline_rejected() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.setCoSigner(cosignerWallet.addr);

        ctx.setRole(address(account), IOperationContext.Role.Session);
        bytes memory data = abi.encodeWithSelector(itk.transfer.selector, recipient, 10e18);
        bytes memory transferCall = _singleCall(address(itk), 0, data);

        // 1. Expired deadline
        bytes memory expiredSig = _signCoSign(
            address(account),
            address(itk),
            0,
            data,
            0,
            block.timestamp - 1
        );
        ctx.setCoSignature(address(account), expiredSig);
        vm.expectRevert(IntegrityHook.CoSignerRequired.selector);
        account.execute(bytes32(0), transferCall);

        // 2. Valid signature succeeds
        bytes memory validSig = _signCoSign(
            address(account),
            address(itk),
            0,
            data,
            0,
            block.timestamp + 1 hours
        );
        ctx.setCoSignature(address(account), validSig);
        account.execute(bytes32(0), transferCall);

        // 3. Replay with same signature (nonce already incremented to 1)
        vm.expectRevert(IntegrityHook.CoSignerRequired.selector);
        account.execute(bytes32(0), transferCall);
    }

    function test_owner_approve_threshold() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.setOwnerApproveAbove(address(itk), 50e18);

        // Session transfer of 60e18 (above 50e18 threshold) reverts OwnerApprovalRequired
        ctx.setRole(address(account), IOperationContext.Role.Session);
        bytes memory transfer60 = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 60e18)
        );
        vm.expectRevert(IntegrityHook.OwnerApprovalRequired.selector);
        account.execute(bytes32(0), transfer60);

        // Owner sending 60e18 passes
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        account.execute(bytes32(0), transfer60);
        assertEq(itk.balanceOf(recipient), 60e18);
    }

    function test_owner_override_skips_limits_not_freeze_or_floor() public {
        // Owner transferring 1000e18 (far above 100e18 per-call and 250e18 window caps) succeeds
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        bytes memory transfer1000 = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 1000e18)
        );
        account.execute(bytes32(0), transfer1000);
        assertEq(itk.balanceOf(recipient), 1000e18);

        // When frozen, owner is still blocked by Check 1
        vault.setFrozen(address(account), true);
        vm.expectRevert(IntegrityHook.Frozen.selector);
        account.execute(bytes32(0), transfer1000);
        vault.setFrozen(address(account), false);

        // When score < floor, owner is still blocked by Check 3
        vm.prank(governance);
        hook.setProtocolFloor(9000); // score is 8000
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityHook.AisBelowFloor.selector, uint32(8000), uint32(9000))
        );
        account.execute(bytes32(0), transfer1000);
    }

    function test_owner_spend_counts_toward_window() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);

        // Owner sends 200e18
        bytes memory transfer200 = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 200e18)
        );
        account.execute(bytes32(0), transfer200);

        // Window spent is updated to 200e18
        assertEq(hook.windowSpent(address(account), address(itk)), 200e18);

        // Switch to session: only 50e18 remaining in 250e18 window
        ctx.setRole(address(account), IOperationContext.Role.Session);
        bytes memory transfer100 = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18)
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.LimitExceeded.selector,
                address(itk),
                uint256(100e18),
                uint256(50e18)
            )
        );
        account.execute(bytes32(0), transfer100);
    }

    function test_paused_blocks_session_not_owner() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.pause();

        // Session is blocked by pause
        ctx.setRole(address(account), IOperationContext.Role.Session);
        bytes memory transfer10 = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 10e18)
        );
        vm.expectRevert(IntegrityHook.Paused.selector);
        account.execute(bytes32(0), transfer10);

        // Owner is NOT blocked by pause
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        account.execute(bytes32(0), transfer10);
        assertEq(itk.balanceOf(recipient), 10e18);
    }
}
