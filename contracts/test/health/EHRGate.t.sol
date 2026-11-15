// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {EHRGate} from "../../src/health/EHRGate.sol";
import {SmartBAAFactory} from "../../src/health/SmartBAAFactory.sol";
import {SmartBAA} from "../../src/health/SmartBAA.sol";
import {CoveredEntityRegistry} from "../../src/health/CoveredEntityRegistry.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";
import {AgentAuthorityResolver} from "../../src/framework/AgentAuthorityResolver.sol";
import {AISRegistry} from "../../src/trust/AISRegistry.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {GateRegistryFixture} from "../trust/GateRegistryFixture.sol";

/// @notice EHRGate must require ALL THREE of: patient consent, an active SmartBAA, and
/// a sufficient reputation score. This is the test that proves the old prototype's gap
/// (patient consent was the *only* thing ever checked) is actually closed.
contract EHRGateTest is GateRegistryFixture {
    EHRGate gate;
    AISRegistry ais;
    SmartBAAFactory baaFactory;
    CoveredEntityRegistry entityRegistry;
    IntegrityToken itk;
    AgentAuthorityResolver resolver;

    address admin = makeAddr("admin");
    address arbitrator = makeAddr("arbitrator");
    address hospital = makeAddr("hospital");
    address scorer = makeAddr("scorer");
    address agent;
    address patient = makeAddr("patient");

    /// Basis points (AISRegistry scale). v2 used 800 on the 0..1000 ReputationRegistry scale.
    uint256 constant THRESHOLD = 8000;
    uint256 constant COLLATERAL = 1_000 ether;
    bytes32 constant RECORD_HASH = keccak256("patient-ehr-doc-1");

    function setUp() public {
        itk = new IntegrityToken(admin, 1_000_000 ether);
        entityRegistry = new CoveredEntityRegistry(admin);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, admin);

        // Registration v3: `agent` is a canonical SovereignAgent bound as an actor in AgentRegistry;
        // its AIS is the latest AISRegistry checkpoint (basis points).
        _deployRegistry(admin);
        agent = _boundAgent("ehrgate-test-agent", _wireBindableDomain(admin, "health.integrity"));
        vm.startPrank(admin);
        ais = new AISRegistry(admin);
        StakeVault vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(ais));
        ais.grantRole(ais.SCORER_ROLE(), scorer);
        ais.setStakeVault(address(vault));
        ais.setAgentRegistry(address(agentRegistry));
        vm.stopPrank();

        resolver = new AgentAuthorityResolver(address(agentRegistry), address(ais));
        gate = new EHRGate(address(agentRegistry), address(baaFactory), address(resolver), THRESHOLD, admin);

        vm.prank(admin);
        entityRegistry.registerEntity(hospital, CoveredEntityRegistry.EntityType.CoveredEntity, "uri");
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

    /// @dev `score` in basis points; posted through the real AISRegistry checkpoint path.
    function _setScore(uint256 score) internal {
        vm.prank(scorer);
        ais.postCheckpoint(agent, uint32(score), uint64(block.timestamp), keccak256("evidence"), 0);
    }

    function test_allThreeConditionsMet_accessGranted() public {
        _signBAA();
        _setScore(9000);

        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        assertTrue(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_noPatientConsent_accessDenied() public {
        _signBAA();
        _setScore(9000);
        // patient never called grantAccess

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_noBAA_accessDenied() public {
        _setScore(9000);
        // BAA never signed
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_lowReputation_accessDenied() public {
        _signBAA();
        _setScore(5000); // below THRESHOLD

        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_revokedBAA_revokesAccess() public {
        _signBAA();
        _setScore(9000);
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
        _setScore(9000);
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(patient);
        gate.revokeAccess(RECORD_HASH, agent);

        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, RECORD_HASH));
    }

    function test_onlyAdminCanSetThreshold() public {
        vm.expectRevert(EHRGate.NotAdmin.selector);
        gate.setThreshold(1);
    }

    // --- verifyAndLogAccess: regression coverage. This function was silently dropped when
    // EHRGate.sol was rewritten to resolve AIS through IAgentAuthorityResolver -- the ABI
    // (integrity-sdk/integrity_sdk/abis/EHRGate.json) still declared it, so integrity_sdk's
    // health.verify_and_log_access() built calldata for a function that no longer existed on
    // the deployed contract and every call reverted (CI: test_full_health_flow_grants_and_
    // verifies_ehr_access). No Solidity test called this function before, which is exactly how
    // the regression went unnoticed at this layer -- these tests close that gap.

    function test_verifyAndLogAccess_grantedCase_returnsTrueAndEmitsLog() public {
        _signBAA();
        _setScore(9000);
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.expectEmit(true, true, true, true);
        emit EHRGate.AccessLogged(patient, RECORD_HASH, agent, true);

        vm.prank(agent);
        bool result = gate.verifyAndLogAccess(patient, RECORD_HASH);
        assertTrue(result);
    }

    function test_verifyAndLogAccess_deniedCase_returnsFalseAndEmitsLog() public {
        // No BAA, no consent, no score -- must return false and still emit an auditable
        // "denied" log entry, not revert.
        vm.expectEmit(true, true, true, true);
        emit EHRGate.AccessLogged(patient, RECORD_HASH, agent, false);

        vm.prank(agent);
        bool result = gate.verifyAndLogAccess(patient, RECORD_HASH);
        assertFalse(result);
    }

    function test_verifyAndLogAccess_matchesCheckAccess() public {
        // Proves the two functions agree, not merely that each individually looks right.
        _signBAA();
        _setScore(9000);
        vm.prank(patient);
        gate.grantAccess(RECORD_HASH, agent, hospital);

        vm.prank(agent);
        bool checked = gate.checkAccess(patient, RECORD_HASH);

        vm.prank(agent);
        bool logged = gate.verifyAndLogAccess(patient, RECORD_HASH);

        assertEq(checked, logged);
    }
}
