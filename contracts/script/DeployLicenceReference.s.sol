// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {LicenceAccount} from "../src/licence/LicenceAccount.sol";
import {ILicenceHook} from "../src/licence/ILicenceHook.sol";
import {IERC6551Registry} from "../src/licence/IERC6551.sol";
import {LicenceToken} from "../src/licence/LicenceToken.sol";

/// @title DeployLicenceReference
/// @notice Phase II reference deployment script for one experimental, non-production licence
/// account instance. Deploys a fresh LicenceToken, one LicenceAccount implementation, mints one
/// reference NFT to the deployer, then creates the token-bound account through the canonical
/// ERC-6551 registry. Adds only `experimentalPhase2LicenceReference` to the existing deployments
/// JSON; never overwrites the production singleton keys.
/// @dev Broadcast to Base Sepolia only after explicit operator approval:
///   forge script script/DeployLicenceReference.s.sol --rpc-url base_sepolia --broadcast --verify
contract DeployLicenceReference is Script {
    IERC6551Registry constant ERC6551_REGISTRY =
        IERC6551Registry(0x000000006551c19487814612e58FE06813775758);

    uint256 constant VOLUME_CAP_TOTAL = 1_000;
    uint256 constant ROYALTY_PRICE_PER_UNIT_WEI = 0.0001 ether;
    uint256 constant LICENCE_DURATION = 30 days;
    uint256 constant PROTOCOL_FEE_BPS = 100;
    bytes32 constant SALT = bytes32(0);

    address deployer;
    address protocolFeeRecipient;
    LicenceToken licenceToken;
    LicenceAccount implementation;
    address tokenBoundAccount;
    uint256 tokenId;
    uint256 licenceStartTime;
    uint256 licenceEndTime;

    string existingJson;
    string network;
    string path;

    function run() external {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        deployer = vm.addr(deployerKey);

        network = block.chainid == 84532 ? "baseSepolia" : "local";
        path = string.concat("../deployments.", network, ".json");
        existingJson = vm.readFile(path);
        protocolFeeRecipient = vm.envOr(
            "PHASE2_LICENCE_PROTOCOL_FEE_RECIPIENT", vm.parseJsonAddress(existingJson, ".protocolAddresses.governance")
        );

        licenceStartTime = block.timestamp;
        licenceEndTime = licenceStartTime + LICENCE_DURATION;

        vm.startBroadcast(deployerKey);

        licenceToken = new LicenceToken(deployer);
        tokenId = licenceToken.mint(deployer);
        implementation = new LicenceAccount(
            address(licenceToken),
            tokenId,
            VOLUME_CAP_TOTAL,
            ROYALTY_PRICE_PER_UNIT_WEI,
            licenceStartTime,
            licenceEndTime,
            protocolFeeRecipient,
            PROTOCOL_FEE_BPS,
            ILicenceHook(address(0))
        );

        address predicted = ERC6551_REGISTRY.account(
            address(implementation), SALT, block.chainid, address(licenceToken), tokenId
        );
        tokenBoundAccount = ERC6551_REGISTRY.createAccount(
            address(implementation), SALT, block.chainid, address(licenceToken), tokenId
        );
        require(tokenBoundAccount == predicted, "ERC-6551 prediction mismatch");

        vm.stopBroadcast();

        _assertReferenceAccount();
        _logSummary();
        _mergeDeploymentsFile();
    }

    function _assertReferenceAccount() internal view {
        (uint256 chainId, address boundToken, uint256 boundTokenId) = LicenceAccount(payable(tokenBoundAccount)).token();
        require(chainId == block.chainid, "TBA chain mismatch");
        require(boundToken == address(licenceToken), "TBA token mismatch");
        require(boundTokenId == tokenId, "TBA tokenId mismatch");
        require(LicenceAccount(payable(tokenBoundAccount)).owner() == deployer, "TBA owner mismatch");
        require(LicenceAccount(payable(tokenBoundAccount)).protocolFeeRecipient() == protocolFeeRecipient, "fee recipient mismatch");
        require(LicenceAccount(payable(tokenBoundAccount)).protocolFeeBps() == PROTOCOL_FEE_BPS, "fee bps mismatch");
    }

    function _logSummary() internal view {
        console2.log("=== Phase II licence reference deployment (EXPERIMENTAL, non-production) ===");
        console2.log("network:                    ", network);
        console2.log("deployer / NFT owner:        ", deployer);
        console2.log("LicenceToken:                ", address(licenceToken));
        console2.log("LicenceAccount implementation:", address(implementation));
        console2.log("ERC-6551 token-bound account:", tokenBoundAccount);
        console2.log("tokenId:                    ", tokenId);
        console2.log("volumeCapTotal:             ", VOLUME_CAP_TOTAL);
        console2.log("royaltyPricePerUnitWei:     ", ROYALTY_PRICE_PER_UNIT_WEI);
        console2.log("protocolFeeRecipient:       ", protocolFeeRecipient);
        console2.log("protocolFeeBps:             ", PROTOCOL_FEE_BPS);
        console2.log("licenceStartTime:           ", licenceStartTime);
        console2.log("licenceEndTime:             ", licenceEndTime);
        console2.log("NOT audited. Illustrative terms only; not a commercial licence offer.");
    }

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
        }
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
        vm.serializeAddress(
            cloneTemplates, "ReputationRegistry", vm.parseJsonAddress(existingJson, ".cloneTemplates.ReputationRegistry")
        );
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

        string memory phase2 = "phase2LicenceReference";
        vm.serializeString(
            phase2,
            "disclosure",
            "EXPERIMENTAL, NOT AUDITED, illustrative terms only, not a commercial licence offer. See PRODUCTION_GAPS.md before treating as production."
        );
        vm.serializeAddress(phase2, "LicenceToken", address(licenceToken));
        vm.serializeAddress(phase2, "LicenceAccountImplementation", address(implementation));
        vm.serializeAddress(phase2, "tokenBoundAccount", tokenBoundAccount);
        vm.serializeAddress(phase2, "owner", deployer);
        vm.serializeAddress(phase2, "protocolFeeRecipient", protocolFeeRecipient);
        vm.serializeUint(phase2, "protocolFeeBps", PROTOCOL_FEE_BPS);
        vm.serializeUint(phase2, "royaltyPricePerUnitWei", ROYALTY_PRICE_PER_UNIT_WEI);
        vm.serializeUint(phase2, "volumeCapTotal", VOLUME_CAP_TOTAL);
        vm.serializeUint(phase2, "licenceStartTime", licenceStartTime);
        vm.serializeUint(phase2, "licenceEndTime", licenceEndTime);
        vm.serializeBytes32(phase2, "salt", SALT);
        vm.serializeUint(phase2, "tokenId", tokenId);
        string memory phase2Json = vm.serializeString(phase2, "deployedFromCommit", vm.envOr("GIT_COMMIT_SHA", string("unknown")));

        string memory root = "root";
        vm.serializeString(root, "singletons", singletonsJson);
        vm.serializeString(root, "cloneTemplates", cloneTemplatesJson);
        vm.serializeString(root, "protocolAddresses", protocolAddressesJson);
        vm.serializeString(root, "network", vm.parseJsonString(existingJson, ".network"));
        vm.serializeString(root, "domains", _rawDomains(existingJson));
        if (vm.keyExistsJson(existingJson, ".experimentalPhase1Reference")) {
            vm.serializeString(root, "experimentalPhase1Reference", _phase1ReferenceJson(existingJson));
        }
        vm.serializeString(root, "experimentalPhase2LicenceReference", phase2Json);
        string memory finalJson = vm.serializeUint(root, "chainId", block.chainid);

        vm.writeJson(finalJson, path);
        console2.log("Merged experimentalPhase2LicenceReference into", path);
    }

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

    function _phase1ReferenceJson(string memory json) internal returns (string memory) {
        string memory phase1 = "phase1ReferenceExisting";
        vm.serializeAddress(
            phase1, "IntegrityAccount", vm.parseJsonAddress(json, ".experimentalPhase1Reference.IntegrityAccount")
        );
        vm.serializeAddress(
            phase1, "IntegrityKernel", vm.parseJsonAddress(json, ".experimentalPhase1Reference.IntegrityKernel")
        );
        vm.serializeAddress(
            phase1, "ReputationRegistry", vm.parseJsonAddress(json, ".experimentalPhase1Reference.ReputationRegistry")
        );
        vm.serializeString(
            phase1, "deployedFromCommit", vm.parseJsonString(json, ".experimentalPhase1Reference.deployedFromCommit")
        );
        return vm.serializeString(
            phase1, "disclosure", vm.parseJsonString(json, ".experimentalPhase1Reference.disclosure")
        );
    }
}
