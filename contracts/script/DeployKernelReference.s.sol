// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";

import {IntegrityAccount} from "../src/kernel/IntegrityAccount.sol";
import {IntegrityKernel} from "../src/kernel/IntegrityKernel.sol";
import {ReputationRegistry} from "../src/oracle/ReputationRegistry.sol";

/// @title DeployKernelReference
/// @notice Workstream 4 of Phase I (`docs/plans/2026-08-24-phase1-testnet-deployment-proposal.md`,
/// authorized 2026-08-24). Deploys ONE experimental, non-production reference instance of
/// `IntegrityAccount`/`IntegrityKernel` -- explicitly NOT integrated with any real registered
/// agent, `XibalbaAgentRegistry`, or `PrimitiveSet`. Deliberately separate from `Deploy.s.sol`
/// (the real production stack), same incremental-deploy convention as `DeployMarkets.s.sol`/
/// `DeployEHRGate.s.sol`: reads the existing `../deployments.<network>.json`, adds only this run's
/// addresses under a clearly separate `experimentalPhase1Reference` key (NOT `singletons`, which
/// reads as canonical/production), and re-serializes every other field unchanged.
///
/// **Design decisions, made explicitly, not defaulted (docs/plans/2026-08-24-phase1-testnet-
/// deployment-proposal.md's own four open questions):**
/// 1. A FRESH `ReputationRegistry` clone (cloned from the ALREADY-DEPLOYED, real
///    `cloneTemplates.ReputationRegistry` implementation this network already uses -- not a new
///    implementation contract, avoiding a redundant, separately-unverified copy) -- never bound to
///    a real agent's actual reputation state.
/// 2. Reuses `IntegrityAccountTest`'s own budget constants exactly (`PER_OP_BUDGET = 1 ether`,
///    `CUMULATIVE_BUDGET = 3 ether`, `MIN_EFFECTIVE_SCORE = 500`, `REPUTATION_EPOCH_LENGTH =
///    3 days`) -- not new, unvalidated "production-shaped" numbers; this deployment is then
///    provably the same configuration already exercised by 321 concrete tests and all six Halmos
///    properties (`PRODUCTION_GAPS.md` §43), not a fresh, unverified one.
/// 3. `trackedToken` DISABLED (`address(0)`) -- avoids conflating this deployment's own findings
///    with the already-disclosed Table 4 gas crossing (`PRODUCTION_GAPS.md` §41), which only
///    applies once `trackedToken` is enabled.
/// 4. Guardian addresses are REQUIRED env vars with no default -- the constructor rejects
///    duplicate guardians, and this repo's existing protocol role addresses mostly collapse to
///    the same deployer address (verified against the live `deployments.baseSepolia.json` before
///    writing this: only 2 of 6 `protocolAddresses` entries are actually distinct), so reusing
///    them is not viable and inventing placeholder addresses nobody controls would defeat the
///    entire point of a multi-party mechanism, even for a reference deployment.
///
/// @dev Run against Base Sepolia with:
///   forge script script/DeployKernelReference.s.sol --rpc-url base_sepolia --broadcast --verify
/// Requires `../deployments.<network>.json` to already exist with a `cloneTemplates.
/// ReputationRegistry` entry, and PHASE1_GUARDIAN_1/2/3_ADDRESS env vars set to three distinct,
/// real, controlled addresses. Deliberately NOT run automatically as part of this change --
/// broadcasting to a live network is a real, gas-costing, operator-triggered action requiring its
/// own separate authorization, same discipline as every other deploy script in this repo.
contract DeployKernelReference is Script {
    uint256 constant PER_OP_BUDGET = 1 ether;
    uint256 constant CUMULATIVE_BUDGET = 3 ether;
    uint256 constant MIN_EFFECTIVE_SCORE = 500;
    uint256 constant REPUTATION_EPOCH_LENGTH = 3 days;
    uint256 constant MODULE_ACTION_TIMELOCK = 3 days;
    uint256 constant RESCUE_TIMELOCK = 1 days;
    uint256 constant GUARDIAN_THRESHOLD = 2;
    // A modest, disclosed initial score -- enough to clear MIN_EFFECTIVE_SCORE (500) with the
    // registry's own ZK_BOOST_BPS applied, matching the test suite's own ABOVE_FLOOR_SCORE. This
    // is a reference instance's own registry, not a real agent's earned score.
    uint256 constant REFERENCE_BASE_SCORE = 800;
    uint256 constant REFERENCE_ZK_BOOST_DURATION = 7 days;

    address deployer;
    address reputationImplementation;
    address[] guardians;

    ReputationRegistry reputation;
    IntegrityKernel kernel;
    IntegrityAccount account;

    string existingJson;
    string network;
    string path;

    function run() external {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        deployer = vm.addr(deployerKey);

        // Required, no default -- see the contract-level NatSpec's design decision 4.
        address guardian1 = vm.envAddress("PHASE1_GUARDIAN_1_ADDRESS");
        address guardian2 = vm.envAddress("PHASE1_GUARDIAN_2_ADDRESS");
        address guardian3 = vm.envAddress("PHASE1_GUARDIAN_3_ADDRESS");
        require(guardian1 != guardian2 && guardian1 != guardian3 && guardian2 != guardian3, "guardians must be distinct");
        guardians = [guardian1, guardian2, guardian3];

        network = block.chainid == 84532 ? "baseSepolia" : "local";
        path = string.concat("../deployments.", network, ".json");
        existingJson = vm.readFile(path);

        reputationImplementation = vm.parseJsonAddress(existingJson, ".cloneTemplates.ReputationRegistry");

        vm.startBroadcast(deployerKey);

        // Fresh clone of the ALREADY-DEPLOYED, real ReputationRegistry implementation -- see
        // design decision 1. `admin`/`oracleSigner` both the deployer, matching this repo's own
        // single-operator-testnet convention for every other protocol role (Deploy.s.sol).
        // zkVerifier/stateAnchor are address(0): this reference instance has no real
        // StateAnchor to bind to (it isn't a registered agent), matching exactly how
        // `contracts/test/halmos/HalmosKernelFixture.sol`'s own `_deployRealKernel` constructs
        // a `ReputationRegistry` for the same reason.
        reputation = ReputationRegistry(Clones.clone(reputationImplementation));
        reputation.initialize(deployer, deployer, address(0), address(0));

        // Genesis-placeholder-then-governance-swap is NOT needed here (unlike the Halmos
        // harness) -- CREATE-nonce address prediction, unavailable under Halmos's own address
        // model, works correctly for a real forge script exactly as it already does throughout
        // this repo's concrete Foundry tests. Read the deployer's nonce ONCE, before ANY further
        // broadcast transaction in this run, and account for BOTH intervening transactions
        // (`updateScore`, then the kernel deployment) before the account's own -- a real
        // off-by-one caught by this script's own local dry run (an earlier draft read the nonce
        // AFTER `updateScore` had already consumed one, so the KERNEL landed at the address
        // predicted for the ACCOUNT, and `updateScore` itself targeted the wrong address as a
        // result too). `updateScore` must target the ACCOUNT's future address, not the kernel's
        // -- `preCheck` checks `effectiveScore(boundAccount)`, where `boundAccount` is the
        // account, never the kernel.
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
            address(0), // trackedToken disabled -- design decision 3
            0,
            0
        );

        account = new IntegrityAccount(
            deployer, address(kernel), MODULE_ACTION_TIMELOCK, guardians, GUARDIAN_THRESHOLD, RESCUE_TIMELOCK
        );
        require(address(account) == predictedAccount, "CREATE address prediction must match actual deployment");

        vm.stopBroadcast();

        _logSummary();
        _mergeDeploymentsFile();
    }

    function _logSummary() internal view {
        console2.log("=== Phase I kernel reference deployment (EXPERIMENTAL, non-production) ===");
        console2.log("network:                      ", network);
        console2.log("ReputationRegistry (fresh clone):", address(reputation));
        console2.log("IntegrityKernel:              ", address(kernel));
        console2.log("IntegrityAccount:             ", address(account));
        console2.log("trackedToken:                  DISABLED (native-ETH-only budget)");
        console2.log("NOT integrated with XibalbaAgentRegistry or any real agent's PrimitiveSet.");
        console2.log("NOT audited. See PRODUCTION_GAPS.md and README.md 'Whitepaper v3.2");
        console2.log("implementation status' section before treating this as production-ready.");
    }

    /// @dev Re-serializes every existing top-level field unchanged, adding only
    /// `experimentalPhase1Reference` -- same defensive discipline as `DeployEHRGate.s.sol`'s own
    /// merge (that script's own history recorded a real bug: an earlier version silently dropped
    /// `network`/`domains` by only re-serializing three of five top-level sections). Every field
    /// this repo's `Deploy.s.sol` is known to write is parsed unconditionally;
    /// `XibalbaNameService` and `IntegrityIdentityReadV1` are guarded with `keyExistsJson` for
    /// the same reason `DeployEHRGate.s.sol` guards them.
    function _mergeDeploymentsFile() internal {
        string memory singletons = "singletons";
        vm.serializeAddress(singletons, "A2ACapitalPool", vm.parseJsonAddress(existingJson, ".singletons.A2ACapitalPool"));
        vm.serializeAddress(
            singletons, "AgentPrimitivesFactory", vm.parseJsonAddress(existingJson, ".singletons.AgentPrimitivesFactory")
        );
        vm.serializeAddress(
            singletons, "CoveredEntityRegistry", vm.parseJsonAddress(existingJson, ".singletons.CoveredEntityRegistry")
        );
        vm.serializeAddress(singletons, "DomainRegistry", vm.parseJsonAddress(existingJson, ".singletons.DomainRegistry"));
        vm.serializeAddress(singletons, "EHRGate", vm.parseJsonAddress(existingJson, ".singletons.EHRGate"));
        vm.serializeAddress(
            singletons, "HIPAAGuardrailRegistry", vm.parseJsonAddress(existingJson, ".singletons.HIPAAGuardrailRegistry")
        );
        vm.serializeAddress(
            singletons, "IntegrityGovernance", vm.parseJsonAddress(existingJson, ".singletons.IntegrityGovernance")
        );
        vm.serializeAddress(singletons, "IntegrityToken", vm.parseJsonAddress(existingJson, ".singletons.IntegrityToken"));
        vm.serializeAddress(singletons, "MarketFactory", vm.parseJsonAddress(existingJson, ".singletons.MarketFactory"));
        vm.serializeAddress(singletons, "SmartBAAFactory", vm.parseJsonAddress(existingJson, ".singletons.SmartBAAFactory"));
        vm.serializeAddress(
            singletons, "UltraPlonkVerifier", vm.parseJsonAddress(existingJson, ".singletons.UltraPlonkVerifier")
        );
        if (vm.keyExistsJson(existingJson, ".singletons.IntegrityIdentityReadV1")) {
            vm.serializeAddress(
                singletons,
                "IntegrityIdentityReadV1",
                vm.parseJsonAddress(existingJson, ".singletons.IntegrityIdentityReadV1")
            );
        }
        if (vm.keyExistsJson(existingJson, ".singletons.XibalbaNameService")) {
            vm.serializeAddress(
                singletons, "XibalbaNameService", vm.parseJsonAddress(existingJson, ".singletons.XibalbaNameService")
            );
        } else {
            console2.log("NOTE: .singletons.XibalbaNameService absent from the existing file -- not written here either.");
        }
        // Always-present field last, so its return value captures the FULL accumulated object
        // regardless of which conditional branches above ran -- avoids the spurious placeholder
        // key an earlier draft of this script used to force a capture point.
        string memory singletonsJson = vm.serializeAddress(
            singletons, "XibalbaAgentRegistry", vm.parseJsonAddress(existingJson, ".singletons.XibalbaAgentRegistry")
        );

        string memory cloneTemplates = "cloneTemplates";
        vm.serializeAddress(cloneTemplates, "AgentProfile", vm.parseJsonAddress(existingJson, ".cloneTemplates.AgentProfile"));
        vm.serializeAddress(
            cloneTemplates, "ComplianceGate", vm.parseJsonAddress(existingJson, ".cloneTemplates.ComplianceGate")
        );
        vm.serializeAddress(
            cloneTemplates, "IntegrityMarket", vm.parseJsonAddress(existingJson, ".cloneTemplates.IntegrityMarket")
        );
        vm.serializeAddress(cloneTemplates, "ReputationRegistry", reputationImplementation);
        vm.serializeAddress(cloneTemplates, "Slasher", vm.parseJsonAddress(existingJson, ".cloneTemplates.Slasher"));
        string memory cloneTemplatesJson = vm.serializeAddress(
            cloneTemplates, "VerifierRegistry", vm.parseJsonAddress(existingJson, ".cloneTemplates.VerifierRegistry")
        );

        string memory protocolAddresses = "protocolAddresses";
        vm.serializeAddress(
            protocolAddresses, "arbitrator", vm.parseJsonAddress(existingJson, ".protocolAddresses.arbitrator")
        );
        vm.serializeAddress(
            protocolAddresses, "disputer", vm.parseJsonAddress(existingJson, ".protocolAddresses.disputer")
        );
        vm.serializeAddress(
            protocolAddresses, "funderWallet", vm.parseJsonAddress(existingJson, ".protocolAddresses.funderWallet")
        );
        vm.serializeAddress(
            protocolAddresses, "governance", vm.parseJsonAddress(existingJson, ".protocolAddresses.governance")
        );
        vm.serializeAddress(
            protocolAddresses, "oracleSigner", vm.parseJsonAddress(existingJson, ".protocolAddresses.oracleSigner")
        );
        string memory protocolAddressesJson = vm.serializeAddress(
            protocolAddresses, "resolverSigner", vm.parseJsonAddress(existingJson, ".protocolAddresses.resolverSigner")
        );

        // experimentalPhase1Reference -- a deliberately SEPARATE top-level key, not nested under
        // singletons, so it can never be mistaken for a canonical/production address by anything
        // that reads .singletons.* generically. Carries an inline disclosure string, not just
        // addresses, so a bare grep of this file surfaces the caveat immediately -- see
        // docs/plans/2026-08-24-phase1-testnet-deployment-proposal.md's design decision 4.
        string memory phase1 = "phase1Reference";
        vm.serializeString(
            phase1,
            "disclosure",
            "EXPERIMENTAL, NOT AUDITED, NOT integrated with XibalbaAgentRegistry or any real agent. See PRODUCTION_GAPS.md and README.md before treating as production."
        );
        vm.serializeAddress(phase1, "IntegrityAccount", address(account));
        vm.serializeAddress(phase1, "IntegrityKernel", address(kernel));
        vm.serializeAddress(phase1, "ReputationRegistry", address(reputation));
        string memory phase1Json = vm.serializeString(phase1, "deployedFromCommit", vm.envOr("GIT_COMMIT_SHA", string("unknown")));

        string memory root = "root";
        vm.serializeString(root, "singletons", singletonsJson);
        vm.serializeString(root, "cloneTemplates", cloneTemplatesJson);
        vm.serializeString(root, "protocolAddresses", protocolAddressesJson);
        vm.serializeString(root, "network", vm.parseJsonString(existingJson, ".network"));
        vm.serializeString(root, "domains", _rawDomains(existingJson));
        vm.serializeString(root, "experimentalPhase1Reference", phase1Json);
        string memory finalJson = vm.serializeUint(root, "chainId", block.chainid);

        vm.writeJson(finalJson, path);
        console2.log("Merged experimentalPhase1Reference into", path);
    }

    /// @dev domains has dynamic keys -- and, a real bug caught by this script's own local dry
    /// run, those keys are themselves dotted domain names (e.g. "general.integrity"). Naive
    /// dot-path concatenation (`.domains.` + key, `DeployEHRGate.s.sol`'s own pattern, copied
    /// here uncritically at first) makes `vm.parseJsonBytes32` treat each dot in the KEY as a
    /// further path-traversal segment, reverting "must return exactly one JSON value" -- this
    /// repo's real Base Sepolia `domains` section was empty (`{}`) when `DeployEHRGate.s.sol` was
    /// written and run, so that script's own version of this bug was never actually exercised.
    /// Bracket notation (`.domains["general.integrity"]`) addresses the key literally, not as a
    /// further path segment, and is the fix.
    function _rawDomains(string memory json) internal returns (string memory) {
        string[] memory keys = vm.parseJsonKeys(json, ".domains");
        if (keys.length == 0) {
            return "{}";
        }
        string memory d = "domainsTmp";
        string memory result;
        for (uint256 i = 0; i < keys.length; i++) {
            result = vm.serializeBytes32(
                d, keys[i], vm.parseJsonBytes32(json, string.concat(".domains[\"", keys[i], "\"]"))
            );
        }
        return result;
    }
}
