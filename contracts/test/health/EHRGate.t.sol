// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {EHRGate} from "../../src/health/EHRGate.sol";
import {SmartBAAFactory} from "../../src/health/SmartBAAFactory.sol";
import {SmartBAA} from "../../src/health/SmartBAA.sol";
import {CoveredEntityRegistry} from "../../src/health/CoveredEntityRegistry.sol";
import {ReputationRegistry} from "../../src/oracle/ReputationRegistry.sol";
import {StateAnchor} from "../../src/oracle/StateAnchor.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";
import {XibalbaAgentRegistry} from "../../src/framework/XibalbaAgentRegistry.sol";

/// @notice EHRGate must require ALL THREE of: patient consent, an active SmartBAA, and
/// a sufficient reputation score. This is the test that proves the old prototype's gap
/// (patient consent was the *only* thing ever checked) is actually closed.
contract EHRGateTest is Test {
    EHRGate gate;
    ReputationRegistry reputation;
    StateAnchor anchor;
    SmartBAAFactory baaFactory;
    CoveredEntityRegistry entityRegistry;
    IntegrityToken itk;
    XibalbaAgentRegistry registry;

    address admin = makeAddr("admin");
    address arbitrator = makeAddr("arbitrator");
    address hospital = makeAddr("hospital");
    address agent = makeAddr("agent");
    address patient = makeAddr("patient");

    uint256 constant THRESHOLD = 800;
    uint256 constant COLLATERAL = 1_000 ether;
    bytes32 constant RECORD_HASH = keccak256("patient-ehr-doc-1");

    function setUp() public {
        itk = new IntegrityToken(admin, 1_000_000 ether);
        anchor = new StateAnchor(admin);
        ReputationRegistry repImpl = new ReputationRegistry();
        reputation = ReputationRegistry(Clones.clone(address(repImpl)));
        reputation.initialize(admin, admin, address(0xBEEF), address(anchor));
        entityRegistry = new CoveredEntityRegistry(admin);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, admin);

        // EHRGate now resolves an agent's ReputationRegistry clone through the shared
        // XibalbaAgentRegistry rather than holding one immutable global registry (see
        // EHRGate.sol's NatSpec). Register `agent` as a stand-in Sovereign Agent whose
        // reputationRegistry primitive is the `reputation` clone above — this mirrors
        // what AgentPrimitivesFactory does in production without pulling the full
        // factory/SovereignAgent deploy sequence into what is otherwise a focused
        // EHRGate test (that sequence gets its own coverage in
        // AgentPrimitivesFactory.t.sol).
        registry = new XibalbaAgentRegistry(admin);
        gate = new EHRGate(address(registry), address(baaFactory), THRESHOLD, admin);

        vm.startPrank(admin);
        registry.grantRole(registry.REGISTRAR_ROLE(), admin);
        registry.registerPrimitives(
            registry.didHash("did:integrity:ehrgate-test-agent"),
            XibalbaAgentRegistry.PrimitiveSet({
                sovereignAgent: agent,
                stateAnchor: address(anchor),
                reputationRegistry: address(reputation),
                slasher: address(0),
                verifierRegistry: address(0),
                complianceGate: address(0),
                agentProfile: address(0)
            }),
            admin,
            bytes32(0)
        );
        entityRegistry.registerEntity(hospital, CoveredEntityRegistry.EntityType.CoveredEntity, "uri");
        vm.stopPrank();

        vm.prank(admin);
        itk.transfer(agent, COLLATERAL);
    }

    function _signBAA() internal {
        vm.prank(hospital);
        address baaAddr = baaFactory.createBAA(agent, keccak256("baa-doc"), COLLATERAL);
        vm.startPrank(agent);
        itk.approve(baaAddr, COLLATERAL);
        SmartBAA(baaAddr).sign();
        vm.stopPrank();
    }

    function _setScore(uint256 score) internal {
        vm.prank(admin);
        reputation.updateScore(agent, score);
    }

    function test_allThreeConditionsMet_accessGranted() public {
        _signBAA();
        _setScore(900);

        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        assertTrue(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_noPatientConsent_accessDenied() public {
        _signBAA();
        _setScore(900);
        // patient never called grantAccess

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_noBAA_accessDenied() public {
        _setScore(900);
        // BAA never signed
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_lowReputation_accessDenied() public {
        _signBAA();
        _setScore(500); // below THRESHOLD

        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_revokedBAA_revokesAccess() public {
        _signBAA();
        _setScore(900);
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        assertTrue(gate.checkAccess(patient, RECORD_HASH));

        address baaAddr = baaFactory.baaOf(hospital, agent);
        vm.prank(hospital);
        SmartBAA(baaAddr).revoke();

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_patientCanRevokeConsent() public {
        _signBAA();
        _setScore(900);
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(patient);
        gate.revokeAccess(RECORD_HASH, agent);

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_verifyAndLogAccessEmitsAuditEvent() public {
        _signBAA();
        _setScore(900);
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        vm.expectEmit(true, true, true, true);
        emit EHRGate.AccessLogged(patient, RECORD_HASH, agent, true);
        gate.verifyAndLogAccess(patient, RECORD_HASH);
    }

    function test_onlyAdminCanSetThreshold() public {
        vm.expectRevert(EHRGate.NotAdmin.selector);
        gate.setThreshold(1);
    }
}
