// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IntegrityHookBase } from "./IntegrityHookBase.sol";
import { IntegrityHook } from "../../src/wallet/IntegrityHook.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";
import { ITK } from "../../src/trust/ITK.sol";
import { IAccessControl } from "@openzeppelin/contracts/access/IAccessControl.sol";

contract IntegrityHookConfigTest is IntegrityHookBase {
    ITK internal itk;
    address internal recipient;
    address internal cosigner;

    function setUp() public override {
        super.setUp();

        recipient = makeAddr("recipient");
        cosigner = makeAddr("cosigner");

        itk = new ITK(address(this), 0);
        itk.grantRole(itk.MINTER_ROLE(), address(this));

        vm.prank(governance);
        hook.setKnownToken(address(itk), true);

        itk.mint(address(account), 2000e18);
    }

    function test_owner_can_loosen_and_tighten() public {
        ctx.setRole(address(account), IOperationContext.Role.Owner);

        vm.startPrank(address(account));

        // 1. Token limit: tighten and loosen
        hook.setTokenLimit(address(itk), 100e18, 500e18);
        (uint128 pc1, uint128 pw1) = hook.tokenLimits(address(account), address(itk));
        assertEq(pc1, 100e18);
        assertEq(pw1, 500e18);

        hook.setTokenLimit(address(itk), 50e18, 200e18); // tighten
        (uint128 pc2, uint128 pw2) = hook.tokenLimits(address(account), address(itk));
        assertEq(pc2, 50e18);
        assertEq(pw2, 200e18);

        hook.setTokenLimit(address(itk), 200e18, 1000e18); // loosen
        (uint128 pc3, uint128 pw3) = hook.tokenLimits(address(account), address(itk));
        assertEq(pc3, 200e18);
        assertEq(pw3, 1000e18);

        // 2. Native limit: tighten and loosen
        hook.setNativeLimit(10 ether, 50 ether);
        hook.setNativeLimit(5 ether, 20 ether); // tighten
        hook.setNativeLimit(20 ether, 100 ether); // loosen
        (uint128 npc, uint128 npw) = hook.tokenLimits(address(account), address(0));
        assertEq(npc, 20 ether);
        assertEq(npw, 100 ether);

        // 3. Window: tighten (shorter) and loosen (longer)
        hook.setWindow(uint32(12 hours)); // tighten
        (uint32 w1,,,) = hook.config(address(account));
        assertEq(w1, uint32(12 hours));
        hook.setWindow(uint32(2 days)); // loosen
        (uint32 w2,,,) = hook.config(address(account));
        assertEq(w2, uint32(2 days));

        // 4. Allowlisted: remove and add
        hook.setAllowlisted(recipient, true);
        assertTrue(hook.isAllowlisted(address(account), recipient));
        hook.setAllowlisted(recipient, false);
        assertFalse(hook.isAllowlisted(address(account), recipient));
        hook.setAllowlisted(recipient, true);
        assertTrue(hook.isAllowlisted(address(account), recipient));

        // 5. Allowlist enabled: toggle
        hook.setAllowlistEnabled(false);
        assertTrue(hook.allowlistDisabled(address(account)));
        hook.setAllowlistEnabled(true);
        assertFalse(hook.allowlistDisabled(address(account)));

        // 6. Co-signer: set, change, clear
        hook.setCoSigner(cosigner);
        assertEq(hook.coSigners(address(account)), cosigner);
        address cosigner2 = makeAddr("cosigner2");
        hook.setCoSigner(cosigner2);
        assertEq(hook.coSigners(address(account)), cosigner2);
        hook.setCoSigner(address(0));
        assertEq(hook.coSigners(address(account)), address(0));

        // 7. Owner approve above: set, lower, raise, clear
        hook.setOwnerApproveAbove(address(itk), 100e18);
        assertEq(hook.ownerApproveAbove(address(account), address(itk)), 100e18);
        hook.setOwnerApproveAbove(address(itk), 50e18);
        assertEq(hook.ownerApproveAbove(address(account), address(itk)), 50e18);
        hook.setOwnerApproveAbove(address(itk), 200e18);
        assertEq(hook.ownerApproveAbove(address(account), address(itk)), 200e18);
        hook.setOwnerApproveAbove(address(itk), 0);
        assertEq(hook.ownerApproveAbove(address(account), address(itk)), 0);

        // 8. Owner floor: set, raise, lower (>= protocolFloor)
        hook.setOwnerFloor(5000);
        (, uint32 of1,,) = hook.config(address(account));
        assertEq(of1, 5000);
        hook.setOwnerFloor(7000); // raise
        (, uint32 of2,,) = hook.config(address(account));
        assertEq(of2, 7000);
        hook.setOwnerFloor(2000); // lower
        (, uint32 of3,,) = hook.config(address(account));
        assertEq(of3, 2000);

        // 9. Pause and unpause
        hook.pause();
        assertTrue(hook.isPaused(address(account)));
        hook.unpause();
        assertFalse(hook.isPaused(address(account)));

        vm.stopPrank();
    }

    function test_session_cannot_write_config() public {
        ctx.setRole(address(account), IOperationContext.Role.Session);

        vm.startPrank(address(account));

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setTokenLimit(address(itk), 10e18, 50e18);

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setNativeLimit(1 ether, 5 ether);

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setWindow(uint32(1 hours));

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setAllowlisted(recipient, true);

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setAllowlistEnabled(false);

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setCoSigner(cosigner);

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setOwnerApproveAbove(address(itk), 10e18);

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.setOwnerFloor(5000);

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.pause();

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.unpause();

        vm.stopPrank();
    }

    function test_maintenance_tighten_only_each_setter() public {
        // Step 1: Owner sets up baseline config
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.startPrank(address(account));
        hook.setTokenLimit(address(itk), 100e18, 200e18);
        hook.setNativeLimit(10 ether, 20 ether);
        hook.setWindow(uint32(1 days));
        hook.setAllowlisted(recipient, true);
        hook.setAllowlistEnabled(false); // currently disabled
        hook.setCoSigner(address(0)); // no cosigner
        hook.setOwnerApproveAbove(address(itk), 0); // off
        hook.setOwnerFloor(3000);
        vm.stopPrank();

        // Step 2: Switch to Maintenance role
        ctx.setRole(address(account), IOperationContext.Role.Maintenance);
        vm.startPrank(address(account));

        // --- 1. setTokenLimit: lower caps allowed, higher caps revert LoosenNotAllowed ---
        // Tighten perCall & perWindow
        hook.setTokenLimit(address(itk), 50e18, 100e18);
        (uint128 tpc, uint128 tpw) = hook.tokenLimits(address(account), address(itk));
        assertEq(tpc, 50e18);
        assertEq(tpw, 100e18);

        // Loosen perCall
        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setTokenLimit(address(itk), 60e18, 100e18);

        // Loosen perWindow
        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setTokenLimit(address(itk), 50e18, 120e18);

        // --- 2. setNativeLimit: lower caps allowed, higher caps revert LoosenNotAllowed ---
        hook.setNativeLimit(5 ether, 10 ether);
        (uint128 npc, uint128 npw) = hook.tokenLimits(address(account), address(0));
        assertEq(npc, 5 ether);
        assertEq(npw, 10 ether);

        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setNativeLimit(6 ether, 10 ether);

        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setNativeLimit(5 ether, 15 ether);

        // --- 3. setWindow: shorter window allowed, longer window reverts LoosenNotAllowed ---
        hook.setWindow(uint32(12 hours));
        (uint32 mw1,,,) = hook.config(address(account));
        assertEq(mw1, uint32(12 hours));

        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setWindow(uint32(1 days));

        // --- 4. setAllowlisted: removing allowed, adding reverts LoosenNotAllowed ---
        address unlisted = makeAddr("unlisted");
        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setAllowlisted(unlisted, true);

        hook.setAllowlisted(recipient, false);
        assertFalse(hook.isAllowlisted(address(account), recipient));

        // --- 5. setAllowlistEnabled: enabling allowed, disabling reverts LoosenNotAllowed ---
        hook.setAllowlistEnabled(true);
        assertFalse(hook.allowlistDisabled(address(account)));

        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setAllowlistEnabled(false);

        // --- 6. setCoSigner: setting when none set allowed, changing or clearing reverts LoosenNotAllowed ---
        hook.setCoSigner(cosigner);
        assertEq(hook.coSigners(address(account)), cosigner);

        address otherCosigner = makeAddr("otherCosigner");
        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setCoSigner(otherCosigner);

        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setCoSigner(address(0));

        // --- 7. setOwnerApproveAbove: turn on or lower threshold allowed, raising or disabling reverts ---
        // Turn on from 0
        hook.setOwnerApproveAbove(address(itk), 50e18);
        assertEq(hook.ownerApproveAbove(address(account), address(itk)), 50e18);

        // Lower threshold
        hook.setOwnerApproveAbove(address(itk), 25e18);
        assertEq(hook.ownerApproveAbove(address(account), address(itk)), 25e18);

        // Raise threshold
        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setOwnerApproveAbove(address(itk), 30e18);

        // Disable threshold (0)
        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setOwnerApproveAbove(address(itk), 0);

        // --- 8. setOwnerFloor: raising allowed, lowering reverts LoosenNotAllowed ---
        hook.setOwnerFloor(5000);
        (, uint32 mof1,,) = hook.config(address(account));
        assertEq(mof1, 5000);

        vm.expectRevert(IntegrityHook.LoosenNotAllowed.selector);
        hook.setOwnerFloor(4000);

        vm.stopPrank();
    }

    function test_maintenance_can_pause_not_unpause() public {
        ctx.setRole(address(account), IOperationContext.Role.Maintenance);

        vm.startPrank(address(account));

        // Maintenance can pause
        hook.pause();
        assertTrue(hook.isPaused(address(account)));

        // Maintenance CANNOT unpause
        vm.expectRevert(IntegrityHook.NotOwner.selector);
        hook.unpause();

        vm.stopPrank();

        // Owner can unpause
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.prank(address(account));
        hook.unpause();
        assertFalse(hook.isPaused(address(account)));
    }

    function test_maintenance_cannot_spend() public {
        // Setup allowlist & limits as owner
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.startPrank(address(account));
        hook.setTokenLimit(address(itk), 100e18, 500e18);
        hook.setAllowlisted(address(itk), true);
        hook.setAllowlisted(recipient, true);
        vm.stopPrank();

        // Switch to Maintenance role and attempt to move value
        ctx.setRole(address(account), IOperationContext.Role.Maintenance);
        bytes memory transferCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 10e18)
        );

        vm.expectRevert(IntegrityHook.NotOwner.selector);
        account.execute(bytes32(0), transferCall);
    }

    function test_owner_floor_cannot_go_below_protocol() public {
        vm.prank(governance);
        hook.setProtocolFloor(4000);

        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.startPrank(address(account));

        // Reverts when floor < protocolFloor
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityHook.FloorBelowProtocol.selector, uint32(3999), uint32(4000))
        );
        hook.setOwnerFloor(3999);

        // Succeeds when floor == protocolFloor
        hook.setOwnerFloor(4000);
        (, uint32 pof1,,) = hook.config(address(account));
        assertEq(pof1, 4000);

        // Succeeds when floor > protocolFloor
        hook.setOwnerFloor(6000);
        (, uint32 pof2,,) = hook.config(address(account));
        assertEq(pof2, 6000);

        vm.stopPrank();
    }

    function test_governance_setters_role_gated() public {
        address nonGov = makeAddr("nonGov");

        // Non-governance calls revert
        vm.startPrank(nonGov);

        vm.expectRevert();
        hook.setProtocolFloor(5000);

        vm.expectRevert();
        hook.setMaxCheckpointAge(uint64(2 days));

        vm.expectRevert();
        hook.setKnownToken(address(itk), false);

        vm.expectRevert();
        hook.setProtocolTarget(address(itk), true);

        vm.expectRevert();
        hook.setOperationContext(IOperationContext(address(ctx)));

        vm.stopPrank();

        // Governance calls succeed
        vm.startPrank(governance);

        hook.setProtocolFloor(5000);
        assertEq(hook.protocolFloor(), 5000);

        hook.setMaxCheckpointAge(uint64(2 days));
        assertEq(hook.maxCheckpointAge(), uint64(2 days));

        // Zero maxCheckpointAge reverts
        vm.expectRevert(IntegrityHook.ZeroMaxCheckpointAge.selector);
        hook.setMaxCheckpointAge(0);

        hook.setKnownToken(address(itk), true);
        assertTrue(hook.isKnownToken(address(itk)));

        hook.setProtocolTarget(address(itk), true);
        assertTrue(hook.isProtocolTarget(address(itk)));

        hook.setOperationContext(IOperationContext(address(ctx)));
        assertEq(address(hook.ctx()), address(ctx));

        vm.stopPrank();
    }

    function test_raising_protocol_floor_applies_to_existing_accounts() public {
        // Setup account: ownerFloor = 4000
        ctx.setRole(address(account), IOperationContext.Role.Owner);
        vm.startPrank(address(account));
        hook.setOwnerFloor(4000);
        hook.setTokenLimit(address(itk), 100e18, 500e18);
        hook.setAllowlisted(address(itk), true);
        hook.setAllowlisted(recipient, true);
        vm.stopPrank();

        // AIS score is 4500 (above both 0 protocol floor and 4000 owner floor)
        ais.setCheckpoint(
            address(account),
            4500,
            100,
            bytes32(0),
            uint64(block.timestamp)
        );

        // Session transfer succeeds
        ctx.setRole(address(account), IOperationContext.Role.Session);
        bytes memory transferCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 10e18)
        );
        account.execute(bytes32(0), transferCall);
        assertEq(itk.balanceOf(recipient), 10e18);

        // Governance raises protocol floor to 5000 (above account's 4500 score)
        vm.prank(governance);
        hook.setProtocolFloor(5000);

        // Transfer now reverts AisBelowFloor(4500, 5000)
        vm.expectRevert(
            abi.encodeWithSelector(IntegrityHook.AisBelowFloor.selector, uint32(4500), uint32(5000))
        );
        account.execute(bytes32(0), transferCall);
    }
}
