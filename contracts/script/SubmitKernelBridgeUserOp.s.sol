// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {IEntryPoint, PackedUserOperation} from "@openzeppelin/contracts/interfaces/draft-IERC4337.sol";
import {IERC7579Execution} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";
import {IEntryPointExtra} from "@openzeppelin/contracts/account/utils/draft-ERC4337Utils.sol";

/// @title SubmitKernelBridgeUserOp
/// @notice Phase B of the kernel-first intent-vs-outcome bridge plan
/// (~/.claude/plans/iridescent-stirring-kettle.md). Constructs, signs, and submits TWO real
/// ERC-4337 UserOperations directly against the canonical EntryPoint (no bundler -- `handleOps`
/// called directly from this script, exactly as the plan's "good news" finding described), each
/// a plain native-value transfer routed through `IntegrityAccount.execute()` so `IntegrityKernel
/// .preCheck`/`postCheck` and the registered `SpendBudgetAdapter` genuinely fire.
///
/// Case 1: value = 0.1 ether -- within both the kernel's native budget (1/3 ether) and the
/// adapter's tighter budget (0.2/0.5 ether). Result (confirmed live, 2026-08-28): succeeds.
///
/// Case 2: value = 0.3 ether -- within the kernel's own 1 ether per-op budget, but OVER the
/// adapter's 0.2 ether per-op budget. This was DESIGNED to prove the registry-adapter path is
/// genuinely consulted (kernel allows, adapter should deny). **Real result (confirmed live,
/// 2026-08-28): it also succeeds -- the adapter does NOT deny it.** Root cause, traced via
/// `-vvvv`: `AccountERC7579Hooked`'s `withHook` modifier calls
/// `hook.preCheck(msg.sender, msg.value, msg.data)` -- the OUTER `execute()` call's `msg.value`,
/// not the amount encoded inside `executionCalldata`. For the standard "account spends its own
/// balance" pattern (no ETH attached to the `execute()` call itself, which is how essentially
/// every real UserOp of this shape works), that `msg.value` is always 0, and `preCheck` forwards
/// it unchanged into `IAdapter(registryAdapter).check(boundAccount, value)`. So
/// `SpendBudgetAdapter` always receives `amount=0` here and trivially approves regardless of the
/// real spend -- not a mock, a genuine call, just checking the wrong number. This appears to be
/// an undisclosed integration gap (not found in `PRODUCTION_GAPS.md` as of this writing) between
/// `IntegrityKernel`'s registry-adapter hook and the standard ERC-7579 single-call self-spend
/// pattern -- distinct from the kernel's OWN native per-op/cumulative budget check, which is
/// unaffected (it measures the real `boundAccount.balance` delta in `postCheck`, independent of
/// this `value` parameter) -- see Case 3.
///
/// Case 3: value = 1.5 ether -- OVER the kernel's own 1 ether per-op budget (irrespective of the
/// adapter). Result (confirmed live, 2026-08-28): correctly denied -- proves the kernel's own
/// native budget enforcement genuinely works via real balance-delta measurement, isolating that
/// the gap above is specific to the registry-adapter forwarding path, not the kernel mechanism
/// as a whole.
///
/// @dev Run against local anvil with:
///   forge script script/SubmitKernelBridgeUserOp.s.sol --rpc-url localhost --broadcast -vvvv
contract SubmitKernelBridgeUserOp is Script {
    uint256 constant MATCHED_VALUE = 0.1 ether;
    uint256 constant DIVERGENT_VALUE = 0.3 ether;
    uint256 constant KERNEL_EXCEEDING_VALUE = 1.5 ether;

    IEntryPoint entryPoint;
    address account;
    address recipient;
    uint256 signerKey;

    function run() external {
        string memory json = vm.readFile("../deployments.local.kernel-bridge.json");
        entryPoint = IEntryPoint(vm.parseJsonAddress(json, ".entryPoint"));
        account = vm.parseJsonAddress(json, ".IntegrityAccount");
        signerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        recipient = vm.addr(uint256(keccak256("kernel-bridge-testbed-recipient")));

        console2.log("=== Case 1: matched intent (0.1 ether, within both budgets) ===");
        _submit(MATCHED_VALUE);

        console2.log("=== Case 2: divergent intent (0.3 ether, kernel allows, adapter denies) ===");
        _submit(DIVERGENT_VALUE);

        console2.log("=== Case 3: kernel-native-budget-exceeding intent (1.5 ether, over the kernel's own 1 ether per-op cap) ===");
        _submit(KERNEL_EXCEEDING_VALUE);
    }

    function _submit(uint256 value) internal {
        bytes memory executionCalldata = abi.encodePacked(recipient, value);
        bytes memory callData = abi.encodeCall(IERC7579Execution.execute, (bytes32(0), executionCalldata));

        PackedUserOperation memory userOp = PackedUserOperation({
            sender: account,
            nonce: entryPoint.getNonce(account, 0),
            initCode: "",
            callData: callData,
            accountGasLimits: bytes32((uint256(1_000_000) << 128) | uint256(1_000_000)),
            preVerificationGas: 100_000,
            gasFees: bytes32((uint256(1 gwei) << 128) | uint256(10 gwei)),
            paymasterAndData: "",
            signature: ""
        });

        bytes32 userOpHash = IEntryPointExtra(address(entryPoint)).getUserOpHash(userOp);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerKey, userOpHash);
        userOp.signature = abi.encodePacked(r, s, v);

        PackedUserOperation[] memory ops = new PackedUserOperation[](1);
        ops[0] = userOp;

        uint256 recipientBefore = recipient.balance;
        uint256 accountBefore = account.balance;

        vm.startBroadcast(signerKey);
        entryPoint.handleOps(ops, payable(vm.addr(signerKey)));
        vm.stopBroadcast();

        console2.log("recipient balance delta:", recipient.balance - recipientBefore);
        console2.log("account balance delta (incl. prefund/gas):", accountBefore - account.balance);
        console2.log("declared value:", value);
        if (recipient.balance - recipientBefore == value) {
            console2.log("RESULT: execution succeeded -- recipient received the declared value");
        } else {
            console2.log("RESULT: execution did NOT transfer the declared value (denied or reverted)");
        }
    }
}
