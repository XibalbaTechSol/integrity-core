// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";

import {StateAnchor} from "../src/oracle/StateAnchor.sol";

/// @title DeployProtocolEvidenceAnchor
/// @notice Incremental deploy: adds a single, protocol-wide `StateAnchor` instance,
/// dedicated to BCC/receipt evidence, to an ALREADY-LIVE deployment (docs/EXECUTION_PLAN.md B4).
/// @dev Same contract code as every per-agent memory StateAnchor, but this one is NOT a
/// per-agent clone and is NOT resolved via the oracle: it is a single `singletons` entry
/// every gate (bcc_middleware's Merkle batches, a Shield/other gate's ReceiptQueue checkpoints)
/// anchors evidence roots into. This exists because `anchor_batch_per_agent` previously wrote
/// BCC receipt roots into each agent's OWN memory StateAnchor -- the same contract C2
/// registration reads `latestRoot()` from as the memory root -- so a flushed BCC batch and a
/// memory-root anchor silently raced for the same on-chain slot. Splitting the target fixes
/// that: an agent's memory StateAnchor's `latestRoot` is memory-only again, and evidence has
/// its own home where `latestRoot` meaning nothing cross-agent is expected and harmless
/// (verification is always against a specific historically-anchored root via `verifyLeaf`,
/// never `latestRoot` -- see StateAnchor.sol's own `isAnchoredRoot` mapping).
///
/// Admin = the broadcasting FUNDER key directly (unlike a per-agent StateAnchor, whose admin
/// is that agent's SovereignAgent contract) -- this is a protocol-operated singleton, not an
/// agent-owned primitive, so a raw EOA calling `anchorRoot` is the correct, simpler path, same
/// as bcc_middleware's existing `app/anchor.py::anchor_root` already assumes for whatever
/// address this script deploys. `ANCHOR_SIGNER_ADDRESS` (bcc_middleware's configured anchor
/// signer, if different from the deployer) is granted `ANCHOR_ROLE` explicitly when supplied.
///
/// Run against Base Sepolia (owner-approved broadcasts only) with:
///   forge script script/DeployProtocolEvidenceAnchor.s.sol --rpc-url base_sepolia --broadcast --verify
contract DeployProtocolEvidenceAnchor is Script {
    string constant KEY = ".singletons.ProtocolEvidenceAnchor";

    function run() external returns (StateAnchor anchor) {
        uint256 deployerKey = vm.envUint("FUNDER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);
        address anchorSigner = vm.envOr("ANCHOR_SIGNER_ADDRESS", deployer);

        string memory network = block.chainid == 84532 ? "baseSepolia" : "local";
        string memory path = string.concat("../deployments.", network, ".json");

        vm.startBroadcast(deployerKey);
        anchor = new StateAnchor(deployer);
        if (anchorSigner != deployer) {
            anchor.grantRole(anchor.ANCHOR_ROLE(), anchorSigner);
        }
        vm.stopBroadcast();

        console2.log("=== Protocol evidence anchor incremental deploy ===");
        console2.log("network:                ", network);
        console2.log("signer/payer (funder):  ", deployer);
        console2.log("admin:                  ", deployer);
        console2.log("anchor signer:          ", anchorSigner);
        console2.log("ProtocolEvidenceAnchor: ", address(anchor));

        string memory existingJson = vm.readFile(path);
        if (vm.keyExistsJson(existingJson, KEY)) {
            vm.writeJson(vm.toString(address(anchor)), path, KEY);
            console2.log("Updated", KEY, "in", path);
        } else {
            console2.log("No", KEY, "key in", path);
            console2.log("File left unchanged; add the address above in a reviewed edit.");
        }
    }
}
