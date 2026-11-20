// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import { Test } from "forge-std/Test.sol";
import { Deploy } from "../../script/Deploy.s.sol";
import { AgentRegistry } from "../../src/framework/AgentRegistry.sol";
import { IntegrityHook } from "../../src/wallet/IntegrityHook.sol";

contract DeployLocalTest is Test {
    Deploy internal deployScript;
    address internal funder = vm.addr(0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80);

    function setUp() public {
        vm.deal(funder, 1_000 ether);
        vm.setEnv("FUNDER_PRIVATE_KEY", "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80");
        deployScript = new Deploy();
        deployScript.run();
    }

    function test_deploy_local_wires_integrity_hook_and_fail_closed_adapters() public {
        IntegrityHook hook = deployScript.integrityHook();
        AgentRegistry registry = deployScript.agentRegistry();

        assertEq(hook.protocolFloor(), 0);
        assertEq(address(registry.integrityHook()), address(hook));
        assertEq(address(registry.accountVerifier()), address(deployScript.safeAccountVerifier()));
        assertEq(address(deployScript.integrityGuard()), address(deployScript.safeAccountVerifier().integrityGuard()));

        address anyEOA = makeAddr("anyEOA");
        assertFalse(registry.isGoverned(anyEOA));

        bytes32 pubkey = bytes32(uint256(1));
        address guardian = makeAddr("guardian");
        uint256 deadline = block.timestamp + 1 hours;

        bytes32 digest = registry.registerDigest(pubkey, guardian, anyEOA, bytes32(0), "", deadline);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80, digest);
        bytes memory proof = abi.encodePacked(r, s, v);

        vm.prank(anyEOA);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.NotGoverned.selector, anyEOA));
        registry.register(pubkey, guardian, anyEOA, bytes32(0), "", deadline, 1, proof, "");
    }
}
