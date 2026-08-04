// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {HIPAAGuardrailRegistry} from "../../src/health/HIPAAGuardrailRegistry.sol";

contract HIPAAGuardrailRegistryTest is Test {
    HIPAAGuardrailRegistry registry;
    address admin = makeAddr("admin");
    address oracle = makeAddr("oracle");
    address agent = makeAddr("agent");

    bytes32 constant POLICY_V1 = keccak256("hipaa-policy-bundle-v1");
    bytes32 constant POLICY_V2 = keccak256("hipaa-policy-bundle-v2");

    function setUp() public {
        registry = new HIPAAGuardrailRegistry(admin, oracle);
    }

    function test_activatePolicy() public {
        vm.prank(admin);
        registry.setActivePolicy(POLICY_V1, "v1.0.0");

        assertEq(registry.activePolicyHash(), POLICY_V1);
        assertEq(registry.activePolicyVersion(), "v1.0.0");
    }

    function test_anchorAuditRequiresMatchingPolicyHash() public {
        vm.prank(admin);
        registry.setActivePolicy(POLICY_V1, "v1.0.0");

        vm.prank(oracle);
        vm.expectRevert(HIPAAGuardrailRegistry.StalePolicyHash.selector);
        registry.anchorAccessAudit(agent, keccak256("record"), POLICY_V2, true);
    }

    function test_anchorAuditSucceedsWithCurrentPolicyHash() public {
        vm.prank(admin);
        registry.setActivePolicy(POLICY_V1, "v1.0.0");

        vm.prank(oracle);
        uint256 idx = registry.anchorAccessAudit(agent, keccak256("record"), POLICY_V1, true);

        assertEq(idx, 0);
        assertEq(registry.auditLogLength(), 1);

        (address a, bytes32 rec, bytes32 policyHash, bool allowed, uint256 ts) = registry.auditLog(0);
        assertEq(a, agent);
        assertEq(rec, keccak256("record"));
        assertEq(policyHash, POLICY_V1);
        assertTrue(allowed);
        assertEq(ts, block.timestamp);
    }

    /// @notice A policy rotation must invalidate audits claiming the OLD hash — this is
    /// the mechanism that stops backdating an access decision to a policy that is no
    /// longer (or was never) actually in effect.
    function test_policyRotationInvalidatesOldHashClaims() public {
        vm.startPrank(admin);
        registry.setActivePolicy(POLICY_V1, "v1.0.0");
        registry.setActivePolicy(POLICY_V2, "v2.0.0");
        vm.stopPrank();

        vm.prank(oracle);
        vm.expectRevert(HIPAAGuardrailRegistry.StalePolicyHash.selector);
        registry.anchorAccessAudit(agent, keccak256("record"), POLICY_V1, true);
    }

    function test_noActivePolicyReverts() public {
        vm.prank(oracle);
        vm.expectRevert(HIPAAGuardrailRegistry.NoActivePolicy.selector);
        registry.anchorAccessAudit(agent, keccak256("record"), POLICY_V1, true);
    }

    function test_onlyOracleRoleCanAnchor() public {
        vm.prank(admin);
        registry.setActivePolicy(POLICY_V1, "v1.0.0");

        vm.expectRevert();
        registry.anchorAccessAudit(agent, keccak256("record"), POLICY_V1, true);
    }
}
