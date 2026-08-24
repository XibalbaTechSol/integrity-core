// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {EHRGate} from "../../src/health/EHRGate.sol";
import {SmartBAAFactory} from "../../src/health/SmartBAAFactory.sol";
import {XibalbaAgentRegistry} from "../../src/framework/XibalbaAgentRegistry.sol";
import {AgentAuthorityResolver} from "../../src/framework/AgentAuthorityResolver.sol";

contract MockSovereignAgentAis {
    uint256 public ais;

    function setAis(uint256 v) external {
        ais = v;
    }
}

/// @notice Covers the Stream 2 cutover: an enterprise (StateAnchor-only, no
/// ReputationRegistry clone) agent must be able to pass EHRGate.checkAccess once
/// registered via XibalbaAgentRegistry.registerEnterpriseAgent, using only its own
/// cached ais(). This is the case that reverted before this PR (EHRGate previously
/// called registry.resolveAgent(...).primitives.reputationRegistry directly, which
/// reverts with UnknownAgent for any agent with no clone-set registration).
contract EHRGateAuthorityResolverTest is Test {
    XibalbaAgentRegistry registry;
    AgentAuthorityResolver resolver;
    SmartBAAFactory baaFactory;
    EHRGate gate;

    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address controller = makeAddr("controller");
    address patient = makeAddr("patient");
    address coveredEntity = makeAddr("coveredEntity");

    MockSovereignAgentAis enterpriseAgent;

    function setUp() public {
        vm.prank(admin);
        registry = new XibalbaAgentRegistry(admin);
        vm.prank(admin);
        registry.grantRole(registry.REGISTRAR_ROLE(), registrar);

        resolver = new AgentAuthorityResolver(address(registry));
        baaFactory = new SmartBAAFactory();

        gate = new EHRGate(address(registry), address(baaFactory), address(resolver), 50, admin);

        enterpriseAgent = new MockSovereignAgentAis();
        enterpriseAgent.setAis(80);

        vm.prank(registrar);
        registry.registerEnterpriseAgent(address(enterpriseAgent), makeAddr("stateAnchor"), controller, bytes32(0));

        baaFactory.activateBAA(coveredEntity, address(enterpriseAgent));

        vm.prank(patient);
        gate.grantAccess(keccak256("record-1"), address(enterpriseAgent), coveredEntity);
    }

    function testEnterpriseAgentPassesAisGate() public {
        vm.prank(address(enterpriseAgent));
        assertTrue(gate.checkAccess(patient, keccak256("record-1")));
    }

    function testEnterpriseAgentBelowThresholdDenied() public {
        enterpriseAgent.setAis(10);
        vm.prank(address(enterpriseAgent));
        assertFalse(gate.checkAccess(patient, keccak256("record-1")));
    }

    function testUnregisteredAgentDeniedNotReverted() public {
        address stranger = makeAddr("stranger");
        vm.prank(patient);
        gate.grantAccess(keccak256("record-2"), stranger, coveredEntity);
        baaFactory.activateBAA(coveredEntity, stranger);

        vm.prank(stranger);
        assertFalse(gate.checkAccess(patient, keccak256("record-2")));
    }
}
