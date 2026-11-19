// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IntegrityHookBase } from "./IntegrityHookBase.sol";
import { IntegrityHook } from "../../src/wallet/IntegrityHook.sol";
import { IOperationContext } from "../../src/wallet/IOperationContext.sol";
import { ITK } from "../../src/trust/ITK.sol";
import { Execution } from "./mocks/MockGovernedAccount.sol";

contract SpenderContract {
    function pullTokens(address token, address from, address to, uint256 amount) external {
        (bool ok, ) = token.call(
            abi.encodeWithSignature("transferFrom(address,address,uint256)", from, to, amount)
        );
        require(ok, "pull failed");
    }
}

contract IntegrityHookLimitsTest is IntegrityHookBase {
    ITK internal itk;
    address internal recipient;
    address internal spender;
    SpenderContract internal spenderContract;

    uint128 internal constant TOKEN_PER_CALL = 100e18;
    uint128 internal constant TOKEN_PER_WINDOW = 250e18;
    uint128 internal constant NATIVE_PER_CALL = 1 ether;
    uint128 internal constant NATIVE_PER_WINDOW = 2 ether;

    function setUp() public override {
        super.setUp();

        recipient = makeAddr("recipient");
        spender = makeAddr("spender");
        spenderContract = new SpenderContract();

        itk = new ITK(address(this), 0);
        itk.grantRole(itk.MINTER_ROLE(), address(this));

        // Governance registers ITK as a known token
        vm.prank(governance);
        hook.setKnownToken(address(itk), true);

        // Account config: owner sets limits and allowlists
        ctx.setRole(address(account), IOperationContext.Role.Owner);

        vm.startPrank(address(account));
        hook.setTokenLimit(address(itk), TOKEN_PER_CALL, TOKEN_PER_WINDOW);
        hook.setNativeLimit(NATIVE_PER_CALL, NATIVE_PER_WINDOW);
        hook.setWindow(uint32(1 days));
        hook.setAllowlisted(address(itk), true);
        hook.setAllowlisted(recipient, true);
        hook.setAllowlisted(spender, true);
        hook.setAllowlisted(address(spenderContract), true);
        vm.stopPrank();

        // Mint ITK to account and fund native ETH
        itk.mint(address(account), 1000e18);
        vm.deal(address(account), 10 ether);

        // Default role for execution tests is Session
        ctx.setRole(address(account), IOperationContext.Role.Session);
    }

    function test_transfer_within_caps_passes_and_counts() public {
        bytes memory execCalldata = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18)
        );

        account.execute(bytes32(0), execCalldata);

        assertEq(hook.windowSpent(address(account), address(itk)), 100e18);
        assertEq(itk.balanceOf(recipient), 100e18);
    }

    function test_per_call_cap_LimitExceeded() public {
        bytes memory execCalldata = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18 + 1)
        );

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.LimitExceeded.selector,
                address(itk),
                uint256(100e18 + 1),
                uint256(TOKEN_PER_CALL)
            )
        );
        account.execute(bytes32(0), execCalldata);
    }

    function test_window_boundary_and_reset() public {
        // 100e18 + 100e18 + 50e18 = 250e18 ok
        bytes memory call100 = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18)
        );
        bytes memory call50 = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 50e18)
        );

        account.execute(bytes32(0), call100);
        account.execute(bytes32(0), call100);
        account.execute(bytes32(0), call50);
        assertEq(hook.windowSpent(address(account), address(itk)), 250e18);

        // +1 wei fails
        bytes memory call1wei = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 1)
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.LimitExceeded.selector,
                address(itk),
                uint256(1),
                uint256(0)
            )
        );
        account.execute(bytes32(0), call1wei);

        // warp 1 days -> resets window, 100e18 ok
        vm.warp(block.timestamp + 1 days);
        account.execute(bytes32(0), call100);
        assertEq(hook.windowSpent(address(account), address(itk)), 100e18);
    }

    function test_batch_split_caught_by_window() public {
        // Batch of 3x 100e18. Each is <= 100e18 per-call cap, but together 300e18 > 250e18 window cap.
        Execution[] memory execs = new Execution[](3);
        execs[0] = Execution({
            target: address(itk),
            value: 0,
            callData: abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18)
        });
        execs[1] = Execution({
            target: address(itk),
            value: 0,
            callData: abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18)
        });
        execs[2] = Execution({
            target: address(itk),
            value: 0,
            callData: abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18)
        });

        // Mode for batch: byte 0 is 0x01
        bytes32 batchMode = bytes32(uint256(0x01) << 248);
        bytes memory batchCalldata = abi.encode(execs);

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.LimitExceeded.selector,
                address(itk),
                uint256(300e18),
                uint256(TOKEN_PER_WINDOW)
            )
        );
        account.execute(batchMode, batchCalldata);
    }

    function test_approve_counts_against_window() public {
        // approve 200e18 counts against window at preCheck time
        bytes memory approveCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.approve.selector, spender, 200e18)
        );
        account.execute(bytes32(0), approveCall);
        assertEq(hook.windowSpent(address(account), address(itk)), 200e18);

        // subsequent transfer of 100e18 exceeds 250e18 window cap (remaining was 50e18)
        bytes memory transferCall = _singleCall(
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
        account.execute(bytes32(0), transferCall);
    }

    function test_approve_to_unlisted_spender_NotAllowlisted() public {
        address unlistedSpender = makeAddr("unlistedSpender");
        bytes memory approveCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.approve.selector, unlistedSpender, 50e18)
        );

        vm.expectRevert(
            abi.encodeWithSelector(IntegrityHook.NotAllowlisted.selector, unlistedSpender)
        );
        account.execute(bytes32(0), approveCall);
    }

    function test_unknown_selector_on_known_token_denied() public {
        // e.g. increaseAllowance(spender, 10) selector
        bytes memory unknownCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSignature("increaseAllowance(address,uint256)", spender, 10)
        );

        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.UnknownSelector.selector,
                address(itk),
                bytes4(keccak256("increaseAllowance(address,uint256)"))
            )
        );
        account.execute(bytes32(0), unknownCall);
    }

    function test_burn_and_burnFrom_capped() public {
        // burn(50e18) passes
        bytes memory burnCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.burn.selector, 50e18)
        );
        account.execute(bytes32(0), burnCall);
        assertEq(hook.windowSpent(address(account), address(itk)), 50e18);

        // burn(100e18 + 1) exceeds per-call cap
        bytes memory overBurnCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.burn.selector, 100e18 + 1)
        );
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.LimitExceeded.selector,
                address(itk),
                uint256(100e18 + 1),
                uint256(TOKEN_PER_CALL)
            )
        );
        account.execute(bytes32(0), overBurnCall);
    }

    function test_unlisted_target_NotAllowlisted() public {
        address unlistedTarget = makeAddr("unlistedTarget");
        bytes memory call = _singleCall(unlistedTarget, 0, hex"1122");

        vm.expectRevert(
            abi.encodeWithSelector(IntegrityHook.NotAllowlisted.selector, unlistedTarget)
        );
        account.execute(bytes32(0), call);
    }

    function test_native_and_token_conjunction() public {
        // batch: 1 ether native + 100e18 ITK ok
        Execution[] memory execs = new Execution[](2);
        execs[0] = Execution({
            target: recipient,
            value: 1 ether,
            callData: ""
        });
        execs[1] = Execution({
            target: address(itk),
            value: 0,
            callData: abi.encodeWithSelector(itk.transfer.selector, recipient, 100e18)
        });

        bytes32 batchMode = bytes32(uint256(0x01) << 248);
        account.execute(batchMode, abi.encode(execs));

        assertEq(hook.windowSpent(address(account), address(0)), 1 ether);
        assertEq(hook.windowSpent(address(account), address(itk)), 100e18);

        // 1 ether + 1 wei native in same window -> exceeds native window cap (2 ether)
        bytes memory overNativeCall = _singleCall(recipient, 1 ether + 1, "");
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.LimitExceeded.selector,
                address(0),
                uint256(1 ether + 1),
                uint256(NATIVE_PER_CALL) // per-call exceeded
            )
        );
        account.execute(bytes32(0), overNativeCall);
    }

    function test_undecoded_movement_counted_by_measured_delta() public {
        // Allow spenderContract to pull 50e18
        bytes memory approveCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.approve.selector, address(spenderContract), 50e18)
        );
        account.execute(bytes32(0), approveCall);
        assertEq(hook.windowSpent(address(account), address(itk)), 50e18);

        // Now account calls spenderContract.pullTokens(...) which is an allowlisted contract calling transferFrom
        bytes memory pullCall = _singleCall(
            address(spenderContract),
            0,
            abi.encodeWithSelector(
                spenderContract.pullTokens.selector,
                address(itk),
                address(account),
                recipient,
                50e18
            )
        );
        account.execute(bytes32(0), pullCall);

        // Window spent rises from 50e18 to 100e18 because postCheck measured the balance drop
        assertEq(hook.windowSpent(address(account), address(itk)), 100e18);
    }

    function test_leaked_session_key_stops_at_limits() public {
        bytes memory transferCall = _singleCall(
            address(itk),
            0,
            abi.encodeWithSelector(itk.transfer.selector, recipient, 50e18)
        );

        // 5 transfers of 50e18 = 250e18 (hits exactly the window cap)
        for (uint256 i = 0; i < 5; i++) {
            account.execute(bytes32(0), transferCall);
        }
        assertEq(hook.windowSpent(address(account), address(itk)), 250e18);

        // 6th transfer halts with LimitExceeded
        vm.expectRevert(
            abi.encodeWithSelector(
                IntegrityHook.LimitExceeded.selector,
                address(itk),
                uint256(50e18),
                uint256(0)
            )
        );
        account.execute(bytes32(0), transferCall);
    }
}
