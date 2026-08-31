// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {LicenceAccount} from "../src/licence/LicenceAccount.sol";

/// @title DemoLicenceConsumption
/// @notice Executes one real, owner-authorized Phase II consumption against the
/// recorded experimental Base Sepolia licence and prints post-transaction state.
/// @dev This is evidence tooling, not a commercial licensing workflow. It must
/// be run only after the operator has confirmed the target deployment and accepts
/// spending one unit of testnet ETH:
///
///   forge script script/DemoLicenceConsumption.s.sol \
///     --rpc-url base_sepolia --broadcast
///
/// The script is read-only with respect to deployments.baseSepolia.json. It does
/// not overwrite deployment records and refuses to run against an expired or
/// missing reference account.
contract DemoLicenceConsumption is Script {
    string constant DEPLOYMENTS_PATH = "../deployments.baseSepolia.json";
    string constant DEPLOYMENT_KEY = ".experimentalPhase2LicenceReference";

    function run() external {
        uint256 signerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        address signer = vm.addr(signerKey);
        string memory deployments = vm.readFile(DEPLOYMENTS_PATH);
        address accountAddress = vm.parseJsonAddress(
            deployments, string.concat(DEPLOYMENT_KEY, ".tokenBoundAccount")
        );
        require(accountAddress != address(0), "missing phase2 token-bound account");

        LicenceAccount account = LicenceAccount(payable(accountAddress));
        require(account.owner() == signer, "FUNDER_PRIVATE_KEY is not current NFT owner");
        require(block.timestamp >= account.licenceStartTime(), "licence is not active yet");
        require(block.timestamp <= account.licenceEndTime(), "licence is already expired");
        require(account.consumedUnits() < account.volumeCapTotal(), "licence volume cap exhausted");

        uint256 units = 1;
        uint256 royaltyDue = units * account.royaltyPricePerUnitWei();
        uint256 beforeConsumed = account.consumedUnits();
        uint256 beforeAccountBalance = address(account).balance;
        uint256 beforeRecipientBalance;
        address feeRecipient = account.protocolFeeRecipient();
        address adapterAddress = account.registryAdapter();
        require(address(account.registryHook()) != address(0), "reference account has no adapter registry");
        require(adapterAddress != address(0), "reference account has no registry adapter");
        uint256 beforeAdapterSpend = _adapterSpend(adapterAddress, signer);
        if (feeRecipient != address(0)) {
            beforeRecipientBalance = feeRecipient.balance;
        }

        console2.log("=== Phase II live consumption evidence ===");
        console2.log("chainId:", block.chainid);
        console2.log("account:", accountAddress);
        console2.log("owner / signer:", signer);
        console2.log("units:", units);
        console2.log("royaltyDue:", royaltyDue);
        console2.log("protocolFeeRecipient:", feeRecipient);
        console2.log("protocolFeeBps:", account.protocolFeeBps());

        vm.startBroadcast(signerKey);
        account.consume{value: royaltyDue}(units);
        vm.stopBroadcast();

        uint256 afterConsumed = account.consumedUnits();
        uint256 afterAccountBalance = address(account).balance;
        uint256 afterRecipientBalance;
        if (feeRecipient != address(0)) {
            afterRecipientBalance = feeRecipient.balance;
        }
        uint256 afterAdapterSpend = _adapterSpend(adapterAddress, signer);

        require(afterConsumed == beforeConsumed + units, "consumedUnits did not increment by one");
        require(afterAccountBalance >= beforeAccountBalance, "account balance unexpectedly decreased");
        require(afterAdapterSpend == beforeAdapterSpend + royaltyDue, "registry adapter did not record amount");
        if (account.protocolFeeBps() > 0 && feeRecipient != signer) {
            uint256 expectedFee = (royaltyDue * account.protocolFeeBps()) / 10_000;
            require(afterRecipientBalance == beforeRecipientBalance + expectedFee, "protocol fee mismatch");
        }

        console2.log("consumedUnits before:", beforeConsumed);
        console2.log("consumedUnits after:", afterConsumed);
        console2.log("account balance before:", beforeAccountBalance);
        console2.log("account balance after:", afterAccountBalance);
        console2.log("recipient balance before:", beforeRecipientBalance);
        console2.log("recipient balance after:", afterRecipientBalance);
        console2.log("adapter spend before:", beforeAdapterSpend);
        console2.log("adapter spend after:", afterAdapterSpend);
        console2.log("LIVE CONSUMPTION VERIFIED: receipt and post-state checks passed");
    }

    function _adapterSpend(address adapterAddress, address subject) internal view returns (uint256) {
        (bool ok, bytes memory data) = adapterAddress.staticcall(
            abi.encodeWithSignature("cumulativeSpentWei(address)", subject)
        );
        require(ok && data.length == 32, "registry adapter does not expose spend accounting");
        return abi.decode(data, (uint256));
    }
}
