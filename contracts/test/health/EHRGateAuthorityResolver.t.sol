// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {EHRGate} from "../../src/health/EHRGate.sol";
import {SmartBAAFactory} from "../../src/health/SmartBAAFactory.sol";
import {SmartBAA} from "../../src/health/SmartBAA.sol";
import {CoveredEntityRegistry} from "../../src/health/CoveredEntityRegistry.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";
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
    CoveredEntityRegistry entityRegistry;
    IntegrityToken itk;
    SmartBAAFactory baaFactory;
    EHRGate gate;

    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address controller = makeAddr("controller");
    address arbitrator = makeAddr("arbitrator");
    address patient = makeAddr("patient");
    address coveredEntity = makeAddr("coveredEntity");
    uint256 constant COLLATERAL = 1_000 ether;

    MockSovereignAgentAis enterpriseAgent;

    function setUp() public {
        vm.prank(admin);
        registry = new XibalbaAgentRegistry(admin);
        bytes32 registrarRole = registry.REGISTRAR_ROLE();
        vm.prank(admin);
        registry.grantRole(registrarRole, registrar);

        resolver = new AgentAuthorityResolver(address(registry));
        itk = new IntegrityToken(admin, 1_000_000 ether);
        entityRegistry = new CoveredEntityRegistry(admin);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, admin);

        gate = new EHRGate(address(registry), address(baaFactory), address(resolver), 50, admin);

        enterpriseAgent = new MockSovereignAgentAis();
        enterpriseAgent.setAis(80);

        vm.prank(registrar);
        registry.registerEnterpriseAgent(address(enterpriseAgent), makeAddr("stateAnchor"), controller, bytes32(0));

        vm.prank(admin);
        entityRegistry.registerEntity(coveredEntity, CoveredEntityRegistry.EntityType.CoveredEntity, "uri");
        _signBAA(address(enterpriseAgent));

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
        _signBAA(stranger);

        vm.prank(stranger);
        assertFalse(gate.checkAccess(patient, keccak256("record-2")));
    }

    function _signBAA(address businessAssociate) internal {
        vm.prank(coveredEntity);
        address baaAddr = baaFactory.createBAA(businessAssociate, keccak256("baa-doc"), COLLATERAL);

        vm.prank(admin);
        itk.transfer(businessAssociate, COLLATERAL);

        vm.startPrank(businessAssociate);
        itk.approve(baaAddr, COLLATERAL);
        SmartBAA(baaAddr).sign();
        vm.stopPrank();
    }
}
