// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {LicenceAccount} from "../src/licence/LicenceAccount.sol";
import {LicenceEconomy} from "../src/licence/LicenceEconomy.sol";
import {LicencePaymaster} from "../src/licence/LicencePaymaster.sol";
import {AdapterRegistry} from "../src/registry/AdapterRegistry.sol";

/// @title VerifyLicenceReference
/// @notice Read-only deployment and binding verifier for the Phase II/III reference stack.
/// @dev Run against the target RPC without `--broadcast`. It deliberately requires the newer
/// deployment record fields and therefore fails on the superseded pre-hook/pre-registry record.
/// The output is intended to be archived with the transaction receipts and live consumption log.
contract VerifyLicenceReference is Script {
    string constant DEPLOYMENTS_PATH = "../deployments.baseSepolia.json";
    string constant DEPLOYMENT_KEY = ".experimentalPhase2LicenceReference";
    address constant CANONICAL_ENTRY_POINT = 0x433709009B8330FDa32311DF1C2AFA402eD8D009;

    function run() external {
        string memory deployments = vm.readFile(DEPLOYMENTS_PATH);
        require(vm.keyExistsJson(deployments, string.concat(DEPLOYMENT_KEY, ".LicenceEconomy")), "stale deployment record: economy missing");
        require(vm.keyExistsJson(deployments, string.concat(DEPLOYMENT_KEY, ".AdapterRegistry")), "stale deployment record: registry missing");
        require(vm.keyExistsJson(deployments, string.concat(DEPLOYMENT_KEY, ".LicencePaymaster")), "stale deployment record: paymaster missing");

        address accountAddress = vm.parseJsonAddress(deployments, string.concat(DEPLOYMENT_KEY, ".tokenBoundAccount"));
        address implementation = vm.parseJsonAddress(deployments, string.concat(DEPLOYMENT_KEY, ".LicenceAccountImplementation"));
        address registry = vm.parseJsonAddress(deployments, string.concat(DEPLOYMENT_KEY, ".AdapterRegistry"));
        address adapter = vm.parseJsonAddress(deployments, string.concat(DEPLOYMENT_KEY, ".SpendBudgetAdapter"));
        address paymasterAddress = vm.parseJsonAddress(deployments, string.concat(DEPLOYMENT_KEY, ".LicencePaymaster"));
        address economyAddress = vm.parseJsonAddress(deployments, string.concat(DEPLOYMENT_KEY, ".LicenceEconomy"));
        address recordedOwner = vm.parseJsonAddress(deployments, string.concat(DEPLOYMENT_KEY, ".owner"));

        _requireCode("LicenceAccountImplementation", implementation);
        _requireCode("tokenBoundAccount", accountAddress);
        _requireCode("AdapterRegistry", registry);
        _requireCode("SpendBudgetAdapter", adapter);
        _requireCode("LicencePaymaster", paymasterAddress);
        _requireCode("LicenceEconomy", economyAddress);

        LicenceAccount account = LicenceAccount(payable(accountAddress));
        LicencePaymaster paymaster = LicencePaymaster(paymasterAddress);
        LicenceEconomy economy = LicenceEconomy(payable(economyAddress));
        require(account.owner() == recordedOwner, "account owner mismatch");
        require(address(account.registryHook()) == registry, "account registry mismatch");
        require(account.registryAdapter() == adapter, "account adapter mismatch");
        require(address(account.entryPoint()) == CANONICAL_ENTRY_POINT, "account EntryPoint mismatch");
        require(account.protocolFeeRecipient() == economyAddress, "account fee router mismatch");
        require(account.protocolFeeBps() > 0, "account protocol fee is disabled");
        require(address(paymaster.entryPoint()) == CANONICAL_ENTRY_POINT, "paymaster EntryPoint mismatch");
        require(paymaster.sponsoredAccount(accountAddress), "account is not allowlisted by paymaster");
        require(economy.licenceAdapter(accountAddress) == adapter, "economy account binding mismatch");
        require(economy.adapterAuthor(adapter) != address(0), "adapter author is unset");

        (uint256 chainId, address token, uint256 tokenId) = account.token();
        require(chainId == block.chainid, "account chain mismatch");
        require(token != address(0), "account token is zero");
        console2.log("=== Phase II/III reference verification (read-only) ===");
        console2.log("chainId:", block.chainid);
        console2.log("account:", accountAddress);
        console2.log("implementation:", implementation);
        console2.log("token:", token);
        console2.log("tokenId:", tokenId);
        console2.log("registry:", registry);
        console2.log("adapter:", adapter);
        console2.log("paymaster:", paymasterAddress);
        console2.log("economy:", economyAddress);
        console2.log("owner:", account.owner());
        console2.log("consumedUnits:", account.consumedUnits());
        console2.log("volumeCapTotal:", account.volumeCapTotal());
        console2.log("paymasterDeposit:", paymaster.getDeposit());
        console2.log("economyTreasuryReserve:", economy.treasuryReserve());
        console2.log("economyBuybackReserve:", economy.buybackReserve());
        console2.log("DEPLOYMENT BINDINGS VERIFIED");
    }

    function _requireCode(string memory label, address target) internal view {
        require(target != address(0), string.concat(label, " is zero"));
        require(target.code.length > 0, string.concat(label, " has no deployed bytecode"));
    }
}
