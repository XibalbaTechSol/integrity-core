// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";

contract XibalbaAgentRegistryTest is Test {
    XibalbaAgentRegistry registry;
    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address controller = makeAddr("controller");
    address sovereignAgent = makeAddr("sovereignAgent");

    string constant DID = "did:integrity:abc123";
    bytes32 domainId = keccak256("healthcare.integrity");

    XibalbaAgentRegistry.PrimitiveSet primitives;

    function setUp() public {
        registry = new XibalbaAgentRegistry(admin);
        // `registry.REGISTRAR_ROLE()` is itself an external call — evaluating it as an
        // argument expression would consume a single-shot vm.prank before grantRole
        // ever runs, so the role constant is cached first.
        bytes32 registrarRole = registry.REGISTRAR_ROLE();
        vm.prank(admin);
        registry.grantRole(registrarRole, registrar);

        primitives = XibalbaAgentRegistry.PrimitiveSet({
            sovereignAgent: sovereignAgent,
            stateAnchor: makeAddr("stateAnchor"),
            reputationRegistry: makeAddr("reputationRegistry"),
            slasher: makeAddr("slasher"),
            verifierRegistry: makeAddr("verifierRegistry"),
            complianceGate: makeAddr("complianceGate"),
            agentProfile: makeAddr("agentProfile")
        });
    }

    function test_registerPrimitivesStoresFullSet() public {
        bytes32 h = registry.didHash(DID);
        vm.prank(registrar);
        registry.registerPrimitives(h, primitives, controller, domainId);

        XibalbaAgentRegistry.AgentRecord memory record = registry.resolveDID(DID);
        assertEq(record.primitives.sovereignAgent, sovereignAgent);
        assertEq(record.primitives.stateAnchor, primitives.stateAnchor);
        assertEq(record.primitives.reputationRegistry, primitives.reputationRegistry);
        assertEq(record.primitives.slasher, primitives.slasher);
        assertEq(record.primitives.verifierRegistry, primitives.verifierRegistry);
        assertEq(record.primitives.complianceGate, primitives.complianceGate);
        assertEq(record.primitives.agentProfile, primitives.agentProfile);
        assertEq(record.controller, controller);
        assertEq(record.domainId, domainId);
        assertTrue(record.exists);
    }

    function test_resolveAgentByPSovereignAgentAddress() public {
        bytes32 h = registry.didHash(DID);
        vm.prank(registrar);
        registry.registerPrimitives(h, primitives, controller, domainId);

        XibalbaAgentRegistry.AgentRecord memory record = registry.resolveAgent(sovereignAgent);
        assertEq(record.primitives.reputationRegistry, primitives.reputationRegistry);
    }

    function test_resolveDIDHashMatchesResolveDID() public {
        bytes32 h = registry.didHash(DID);
        vm.prank(registrar);
        registry.registerPrimitives(h, primitives, controller, domainId);

        XibalbaAgentRegistry.AgentRecord memory byHash = registry.resolveDIDHash(h);
        XibalbaAgentRegistry.AgentRecord memory byDID = registry.resolveDID(DID);
        assertEq(byHash.primitives.sovereignAgent, byDID.primitives.sovereignAgent);
    }

    function test_isRegisteredAgentTrueAfterRegistration() public {
        assertFalse(registry.isRegisteredAgent(sovereignAgent));

        bytes32 h = registry.didHash(DID);
        vm.prank(registrar);
        registry.registerPrimitives(h, primitives, controller, domainId);

        assertTrue(registry.isRegisteredAgent(sovereignAgent));
    }

    function test_totalAgentsIncrementsOnEachRegistration() public {
        assertEq(registry.totalAgents(), 0);

        bytes32 h = registry.didHash(DID);
        vm.prank(registrar);
        registry.registerPrimitives(h, primitives, controller, domainId);

        assertEq(registry.totalAgents(), 1);
    }

    function test_cannotRegisterSameDIDTwice() public {
        bytes32 h = registry.didHash(DID);
        vm.prank(registrar);
        registry.registerPrimitives(h, primitives, controller, domainId);

        vm.prank(registrar);
        vm.expectRevert(XibalbaAgentRegistry.AlreadyRegistered.selector);
        registry.registerPrimitives(h, primitives, controller, domainId);
    }

    function test_onlyRegistrarRoleCanRegister() public {
        bytes32 h = registry.didHash(DID);
        vm.expectRevert();
        registry.registerPrimitives(h, primitives, controller, domainId);
    }

    function test_registerPrimitivesRejectsZeroController() public {
        vm.prank(registrar);
        vm.expectRevert(XibalbaAgentRegistry.ZeroController.selector);
        registry.registerPrimitives(registry.didHash("did:integrity:zero-controller"), primitives, address(0), domainId);
    }

    function test_registerEnterpriseAgentRejectsZeroController() public {
        vm.prank(registrar);
        vm.expectRevert(XibalbaAgentRegistry.ZeroController.selector);
        registry.registerEnterpriseAgent(makeAddr("enterpriseAgent"), makeAddr("enterpriseAnchor"), address(0), domainId);
    }

    function test_resolveUnknownDIDReverts() public {
        vm.expectRevert(XibalbaAgentRegistry.UnknownDID.selector);
        registry.resolveDID("did:integrity:never-registered");
    }

    function test_resolveUnknownAgentReverts() public {
        vm.expectRevert(XibalbaAgentRegistry.UnknownAgent.selector);
        registry.resolveAgent(makeAddr("stranger"));
    }
}
