// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";
import {StateAnchor} from "../src/oracle/StateAnchor.sol";

/// @title MediationOk
/// @notice M5 auditor: pass/fail whether production hooks are installed.
/// @dev forge script contracts/script/MediationOk.s.sol --sig "run(address,address)" <agent> <anchor> -vvvv
contract MediationOk is Script {
    function run(address agent, address stateAnchor) external view {
        bool execOk = address(SovereignAgent(payable(agent)).executionPolicy()) != address(0);
        bool anchorOk = true;
        if (stateAnchor != address(0)) {
            anchorOk = address(StateAnchor(stateAnchor).anchorPolicy()) != address(0);
        }
        console.log("SovereignAgent", agent);
        console.log("  executionPolicy set", execOk);
        console.log("StateAnchor", stateAnchor);
        console.log("  anchorPolicy set", anchorOk);
        console.log("mediation_ok", execOk && anchorOk);
    }
}
