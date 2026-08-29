// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";

import {IntegrityAccount} from "../src/kernel/IntegrityAccount.sol";
import {IntegrityKernel} from "../src/kernel/IntegrityKernel.sol";
import {ReputationRegistry} from "../src/oracle/ReputationRegistry.sol";
import {AdapterRegistry} from "../src/registry/AdapterRegistry.sol";
import {SpendBudgetAdapter} from "../src/registry/SpendBudgetAdapter.sol";

/// @title DeployKernelBridgeTestbed
/// @notice LOCAL-DEVNET-ONLY testbed for the "kernel-first intent-vs-outcome bridge" plan
/// (~/.claude/plans/iridescent-stirring-kettle.md). Deploys a SECOND, independent
/// IntegrityKernel/IntegrityAccount pair -- distinct from `experimentalPhase1Reference` in
/// `deployments.local.json`, which is bound to `AdapterRegistry(address(0))` (no adapter wired)
/// and so cannot exercise the registry-adapter path at all. This script deploys a real
/// `AdapterRegistry` + `SpendBudgetAdapter` and binds a fresh kernel/account to them, so the
/// off-chain bridge (Phase B of the plan) has something real to submit UserOperations against.
///
/// Same experimental-reference disclosure as `DeployKernelReference.s.sol`: NOT audited, NOT
/// integrated with `XibalbaAgentRegistry` or any real registered agent. Writes its own separate
/// `deployments.local.kernel-bridge.json` rather than touching `deployments.local.json`, so
/// nothing that reads the canonical deployments file is affected by this testbed.
///
/// Adapter budgets are deliberately TIGHTER than the kernel's own native-value budget
/// (0.2/0.5 ether vs. the kernel's 1/3 ether) so a `value` between the two triggers a kernel
/// PASS + adapter DENY -- the case that actually proves the registry-adapter path is being
/// consulted, not just the kernel's pre-existing native-balance check.
///
/// @dev Run against local anvil with:
///   forge script script/DeployKernelBridgeTestbed.s.sol --rpc-url localhost --broadcast
contract DeployKernelBridgeTestbed is Script {
    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant ADAPTER_PER_OP_BUDGET = 0.2 ether;
    uint256 constant ADAPTER_CUMULATIVE_BUDGET = 0.5 ether;
    uint256 constant ADAPTER_GAS_BOUND = 100_000;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days;
    uint256 constant MODULE_ACTION_TIMELOCK = 3 days;
    uint256 constant RESCUE_TIMELOCK = 1 days;
    uint256 constant GUARDIAN_THRESHOLD = 2;
    uint256 constant REFERENCE_BASE_SCORE = 800;
    uint256 constant ACCOUNT_FUNDING = 2 ether;

    address deployer;
    address reputationImplementation;
    address[] guardians;

    ReputationRegistry reputation;
    AdapterRegistry registry;
    SpendBudgetAdapter adapter;
    IntegrityKernel kernel;
    IntegrityAccount account;

    string existingJson;
    string path;
    string outPath;

    function run() external {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        deployer = vm.addr(deployerKey);

        // Local-devnet-only guardians: anvil's well-known default accounts #1-#3. Never use
        // these on a real network -- their private keys are public.
        guardians = [
            0x70997970C51812dc3A010C7d01b50e0d17dc79C8,
            0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC,
            0x90F79bf6EB2c4f870365E785982E1f101E93b906
        ];

        path = "../deployments.local.json";
        existingJson = vm.readFile(path);
        reputationImplementation = vm.parseJsonAddress(existingJson, ".cloneTemplates.ReputationRegistry");

        vm.startBroadcast(deployerKey);

        reputation = ReputationRegistry(Clones.clone(reputationImplementation));
        reputation.initialize(deployer, deployer, address(0), address(0));

        registry = new AdapterRegistry();
        adapter = new SpendBudgetAdapter(ADAPTER_PER_OP_BUDGET, ADAPTER_CUMULATIVE_BUDGET);
        registry.register(address(adapter), ADAPTER_GAS_BOUND, keccak256("spend-budget-v1-kernel-bridge-testbed"));

        // Same CREATE-nonce prediction pattern as DeployKernelReference.s.sol: read the deployer's
        // nonce BEFORE any further broadcast tx, account for updateScore + kernel deploy before
        // the account's own.
        uint256 nonceBeforeUpdateScore = vm.getNonce(deployer);
        address predictedAccount = vm.computeCreateAddress(deployer, nonceBeforeUpdateScore + 2);
        reputation.updateScore(predictedAccount, REFERENCE_BASE_SCORE);

        kernel = new IntegrityKernel(
            predictedAccount,
            PER_OP_BUDGET,
            CUMULATIVE_BUDGET,
            address(reputation),
            MIN_EFFECTIVE_SCORE,
            REPUTATION_EPOCH_LENGTH,
            address(0),
            0,
            0,
            registry,
            address(adapter)
        );

        account = new IntegrityAccount(
            deployer, address(kernel), MODULE_ACTION_TIMELOCK, guardians, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        require(address(account) == predictedAccount, "CREATE address prediction must match actual deployment");

        // Fund the account with real test ETH so preCheck/postCheck's native-value budget checks
        // have something to measure -- vm.deal does not persist to a live anvil RPC, so this is a
        // genuine broadcast transaction instead.
        (bool sent,) = payable(address(account)).call{value: ACCOUNT_FUNDING}("");
        require(sent, "account funding transfer failed");

        vm.stopBroadcast();

        _logSummary();
        _writeDeploymentsFile();
    }

    function _logSummary() internal view {
        console2.log("=== Kernel-bridge testbed deployment (LOCAL DEVNET ONLY, EXPERIMENTAL) ===");
        console2.log("AdapterRegistry:      ", address(registry));
        console2.log("SpendBudgetAdapter:   ", address(adapter));
        console2.log("  perOpBudgetWei:     ", ADAPTER_PER_OP_BUDGET);
        console2.log("  cumulativeBudgetWei:", ADAPTER_CUMULATIVE_BUDGET);
        console2.log("ReputationRegistry:   ", address(reputation));
        console2.log("IntegrityKernel:      ", address(kernel));
        console2.log("  perOpBudgetWei:     ", PER_OP_BUDGET);
        console2.log("  cumulativeBudgetWei:", CUMULATIVE_BUDGET);
        console2.log("IntegrityAccount:     ", address(account));
        console2.log("  funded:             ", ACCOUNT_FUNDING);
        console2.log("NOT integrated with XibalbaAgentRegistry or any real agent's PrimitiveSet.");
        console2.log("NOT audited. Local devnet testbed only -- see the deploy script's own NatSpec.");
    }

    function _writeDeploymentsFile() internal {
        string memory root = "root";
        vm.serializeString(
            root,
            "disclosure",
            "LOCAL DEVNET TESTBED, EXPERIMENTAL, NOT AUDITED. Second kernel/account pair, distinct from experimentalPhase1Reference, deployed specifically to exercise the AdapterRegistry path (which the reference deployment leaves at address(0))."
        );
        vm.serializeAddress(root, "AdapterRegistry", address(registry));
        vm.serializeAddress(root, "SpendBudgetAdapter", address(adapter));
        vm.serializeUint(root, "adapterPerOpBudgetWei", ADAPTER_PER_OP_BUDGET);
        vm.serializeUint(root, "adapterCumulativeBudgetWei", ADAPTER_CUMULATIVE_BUDGET);
        vm.serializeAddress(root, "ReputationRegistry", address(reputation));
        vm.serializeAddress(root, "IntegrityKernel", address(kernel));
        vm.serializeUint(root, "kernelPerOpBudgetWei", PER_OP_BUDGET);
        vm.serializeUint(root, "kernelCumulativeBudgetWei", CUMULATIVE_BUDGET);
        vm.serializeAddress(root, "IntegrityAccount", address(account));
        vm.serializeAddress(root, "deployer", deployer);
        vm.serializeAddress(root, "entryPoint", 0x433709009B8330FDa32311DF1C2AFA402eD8D009);
        string memory finalJson = vm.serializeUint(root, "chainId", block.chainid);

        outPath = "../deployments.local.kernel-bridge.json";
        vm.writeJson(finalJson, outPath);
        console2.log("Wrote", outPath);
    }
}
