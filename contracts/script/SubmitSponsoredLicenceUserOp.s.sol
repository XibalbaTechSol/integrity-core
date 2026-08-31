// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {IEntryPoint, PackedUserOperation} from "@openzeppelin/contracts/interfaces/draft-IERC4337.sol";
import {IEntryPointExtra} from "@openzeppelin/contracts/account/utils/draft-ERC4337Utils.sol";
import {LicenceAccount} from "../src/licence/LicenceAccount.sol";
import {LicencePaymaster} from "../src/licence/LicencePaymaster.sol";

/// @title SubmitSponsoredLicenceUserOp
/// @notice Broadcasts one real, paymaster-sponsored licence consumption through EntryPoint v0.9.
/// @dev This uses EntryPoint.handleOps directly because no external bundler credential is required
/// for the evidence transaction. It still exercises the canonical EntryPoint validation, paymaster,
/// prefund, account execution, royalty settlement, and consumed-unit state transition on Base Sepolia.
contract SubmitSponsoredLicenceUserOp is Script {
    IEntryPoint constant ENTRY_POINT = IEntryPoint(0x433709009B8330FDa32311DF1C2AFA402eD8D009);
    address constant ACCOUNT = 0x62526e8B67F04A5ea3F09Bd48C171A7e1dBA7373;
    address constant PAYMASTER = 0xf50f52B64fD0ED724c5cE8E706bD9784eDadeD68;
    uint256 constant UNITS = 1;
    uint256 constant ROYALTY = 0.0001 ether;
    uint256 constant PAYMASTER_DEPOSIT = 0.01 ether;

    function run() external {
        uint256 signerKey = vm.envUint("ORACLE_SIGNER_PRIVATE_KEY");
        address signer = vm.addr(signerKey);
        LicenceAccount account = LicenceAccount(payable(ACCOUNT));
        LicencePaymaster paymaster = LicencePaymaster(PAYMASTER);
        uint256 beforeConsumed = account.consumedUnits();
        uint256 beforeDeposit = paymaster.getDeposit();
        uint256 beforeAccountBalance = ACCOUNT.balance;

        vm.startBroadcast(signerKey);
        if (beforeDeposit < PAYMASTER_DEPOSIT) paymaster.deposit{value: PAYMASTER_DEPOSIT - beforeDeposit}();
        if (beforeAccountBalance < ROYALTY) payable(ACCOUNT).transfer(ROYALTY - beforeAccountBalance);

        bytes memory innerCall = abi.encodeCall(LicenceAccount.consume, (UNITS));
        bytes memory callData = abi.encodeCall(LicenceAccount.execute, (ACCOUNT, ROYALTY, innerCall, 0));
        bytes memory paymasterAndData = abi.encodePacked(PAYMASTER, uint128(500_000), uint128(500_000));
        PackedUserOperation memory userOp = PackedUserOperation({
            sender: ACCOUNT,
            nonce: ENTRY_POINT.getNonce(ACCOUNT, 0),
            initCode: "",
            callData: callData,
            accountGasLimits: bytes32((uint256(500_000) << 128) | uint256(500_000)),
            preVerificationGas: 50_000,
            gasFees: bytes32((uint256(1 gwei) << 128) | uint256(1 gwei)),
            paymasterAndData: paymasterAndData,
            signature: ""
        });
        bytes32 userOpHash = IEntryPointExtra(address(ENTRY_POINT)).getUserOpHash(userOp);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerKey, userOpHash);
        userOp.signature = abi.encodePacked(r, s, v);
        PackedUserOperation[] memory ops = new PackedUserOperation[](1);
        ops[0] = userOp;
        console2.log("fresh handleOps calldata:");
        console2.logBytes(abi.encodeCall(IEntryPoint.handleOps, (ops, payable(signer))));
        ENTRY_POINT.handleOps(ops, payable(signer));
        vm.stopBroadcast();

        require(account.consumedUnits() == beforeConsumed + UNITS, "sponsored consume did not advance meter");
        require(paymaster.getDeposit() < beforeDeposit, "paymaster deposit was not charged");
        console2.log("sponsored userOp hash:");
        console2.logBytes32(userOpHash);
        console2.log("consumed units before:", beforeConsumed);
        console2.log("consumed units after:", account.consumedUnits());
        console2.log("paymaster deposit before:", beforeDeposit);
        console2.log("paymaster deposit after:", paymaster.getDeposit());
    }
}
