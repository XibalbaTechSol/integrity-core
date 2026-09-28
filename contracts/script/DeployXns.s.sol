// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {XibalbaNameService} from "../src/framework/XibalbaNameService.sol";

/// @title DeployXns
/// @notice Incremental deploy: adds `XibalbaNameService` (XNS) to an ALREADY-LIVE deployment.
/// @dev The XNS half of the former `DeployXnsGovernance.s.sol`, split out when `IntegrityGovernance`
/// was cut (docs/EXECUTION_PLAN.md A1). A fresh genesis already deploys XNS in `Deploy.s.sol`; this
/// script exists for a deployment that predates it or needs XNS redeployed, without re-running
/// genesis (which would orphan every registered agent).
///
/// "Funder signs, agent owns": the FUNDER key signs and pays gas, but XNS's DEFAULT_ADMIN_ROLE and
/// REGISTRAR_ROLE go to the Xibalba agent (`XIBALBA_AGENT_ADDRESS`, default the FAUCET_INFO.md
/// "Agent Derived Address").
///
/// Unlike the script it replaces, this one updates ONLY `.singletons.XibalbaNameService` in the
/// deployments file, in place. It never re-serializes the file from a fixed key list, which is how
/// the old merge step dropped keys it did not know about. If the key is absent, the file is left
/// untouched and the address is printed for a reviewed manual edit.
///
/// Run against Base Sepolia (owner-approved broadcasts only) with:
///   forge script script/DeployXns.s.sol --rpc-url base_sepolia --broadcast --verify
contract DeployXns is Script {
    // Default Xibalba agent (FAUCET_INFO.md "Agent Derived Address"). Overridable via env.
    address constant DEFAULT_AGENT = 0xabfeEaCbA00F38810E697b2970399fE03080FBeB;
    string constant XNS_KEY = ".singletons.XibalbaNameService";

    function run() external returns (XibalbaNameService xns) {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);
        address agent = vm.envOr("XIBALBA_AGENT_ADDRESS", DEFAULT_AGENT);

        string memory network = block.chainid == 84532 ? "baseSepolia" : "local";
        string memory path = string.concat("../deployments.", network, ".json");
        string memory existingJson = vm.readFile(path);
        address registry = vm.parseJsonAddress(existingJson, ".singletons.XibalbaAgentRegistry");

        vm.startBroadcast(deployerKey);
        // Admin = agent (DEFAULT_ADMIN_ROLE + REGISTRAR_ROLE); resolves against the existing registry.
        xns = new XibalbaNameService(agent, registry);
        vm.stopBroadcast();

        console2.log("=== XNS incremental deploy ===");
        console2.log("network:               ", network);
        console2.log("signer/payer (funder): ", deployer);
        console2.log("admin (agent):         ", agent);
        console2.log("existing AgentRegistry:", registry);
        console2.log("XibalbaNameService:    ", address(xns));

        if (vm.keyExistsJson(existingJson, XNS_KEY)) {
            vm.writeJson(vm.toString(address(xns)), path, XNS_KEY);
            console2.log("Updated", XNS_KEY, "in", path);
        } else {
            console2.log("No", XNS_KEY, "key in", path);
            console2.log("File left unchanged; add the address above in a reviewed edit.");
        }
    }
}
