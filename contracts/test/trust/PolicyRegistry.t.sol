// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {IPolicyModule} from "../../src/trust/IPolicyModule.sol";

/// @dev Test-only fixture; deliberately not in src/.
contract AllowAllPolicyModule is IPolicyModule {
    uint16 public immutable weight;

    constructor(uint16 weight_) {
        weight = weight_;
    }

    function checkCompliance(address, bytes32, address, bytes calldata) external view returns (bool, uint16) {
        return (true, weight);
    }
}

contract PolicyRegistryTest is Test {
    PolicyRegistry registry;
    AllowAllPolicyModule domainModule;
    AllowAllPolicyModule overrideModule;

    address admin = makeAddr("admin");
    address curator = makeAddr("curator");
    address agent = makeAddr("agent");
    address target = makeAddr("target");

    bytes32 constant DOMAIN = keccak256("domain-A");
    bytes32 constant FROM = bytes32(uint256(1));
    bytes32 constant REL = bytes32(uint256(2));
    bytes32 constant TO = bytes32(uint256(3));
    bytes32 constant OTHER_TO = bytes32(uint256(4));
    bytes4 constant SEL = 0xa9059cbb;
    bytes4 constant OTHER_SEL = 0x095ea7b3;
    uint16 constant RISK = 500;

    bytes32 leafA;
    bytes32 leafB;

    function setUp() public {
        registry = new PolicyRegistry(admin);
        domainModule = new AllowAllPolicyModule(100);
        overrideModule = new AllowAllPolicyModule(900);

        vm.startPrank(admin);
        registry.grantRole(registry.GRAPH_CURATOR_ROLE(), curator);
        registry.setModule(DOMAIN, address(domainModule));
        vm.stopPrank();

        leafA = registry.leafOf(FROM, REL, TO, SEL, RISK);
        leafB = registry.leafOf(FROM, REL, OTHER_TO, SEL, RISK);
        bytes32 root = leafA < leafB
            ? keccak256(abi.encodePacked(leafA, leafB))
            : keccak256(abi.encodePacked(leafB, leafA));
        vm.prank(curator);
        registry.setGraphRoot(DOMAIN, root);
    }

    function _proofA() internal view returns (bytes32[] memory p) {
        p = new bytes32[](1);
        p[0] = leafB;
    }

    function test_checkCompliance_usesAgentOverrideWhenSet() public {
        vm.prank(admin);
        registry.setAgentOverride(agent, address(overrideModule));
        (bool ok, uint16 w) = registry.checkCompliance(agent, DOMAIN, target, "");
        assertTrue(ok);
        assertEq(w, 900);
    }

    function test_checkCompliance_fallsBackToDomainModule() public view {
        (bool ok, uint16 w) = registry.checkCompliance(agent, DOMAIN, target, "");
        assertTrue(ok);
        assertEq(w, 100);
    }

    function test_checkCompliance_revertsWhenNoModuleConfigured() public {
        vm.expectRevert(PolicyRegistry.NoModuleConfigured.selector);
        registry.checkCompliance(agent, keccak256("unconfigured"), target, "");
    }

    function test_checkGraphEdge_trueForCommittedEdge() public view {
        assertTrue(registry.checkGraphEdge(DOMAIN, FROM, REL, TO, SEL, RISK, _proofA()));
    }

    function test_checkGraphEdge_falseWhenEdgeAbsent() public view {
        // edge (FROM, REL, bytes32(5)) was never committed
        assertFalse(registry.checkGraphEdge(DOMAIN, FROM, REL, bytes32(uint256(5)), SEL, RISK, _proofA()));
    }

    function test_checkGraphEdge_falseWhenRiskWeightMismatched() public view {
        assertFalse(registry.checkGraphEdge(DOMAIN, FROM, REL, TO, SEL, RISK + 1, _proofA()));
    }

    function test_checkGraphEdge_falseWhenSelectorMismatched() public view {
        assertFalse(registry.checkGraphEdge(DOMAIN, FROM, REL, TO, OTHER_SEL, RISK, _proofA()));
    }

    function test_setters_accessControl() public {
        vm.expectRevert();
        registry.setModule(DOMAIN, address(0));
        vm.expectRevert();
        registry.setGraphRoot(DOMAIN, bytes32(0));
        vm.expectRevert();
        registry.setDomainFloor(DOMAIN, 1);
        vm.prank(admin);
        registry.setDomainFloor(DOMAIN, 7);
        assertEq(registry.domainFloor(DOMAIN), 7);
    }
}
