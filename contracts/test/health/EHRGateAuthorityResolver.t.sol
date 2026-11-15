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

/// @notice EHRGate's AIS floor through the registration v3 resolver: a bound `AgentRegistry` actor
/// passes or fails on its latest `AISRegistry` checkpoint, and the floor is in BASIS POINTS. The v2
/// suite used threshold 50 / AIS 80 on the 0..1000 ReputationRegistry scale; the same policy is
/// 500 / 800 here (x10), converted explicitly rather than by rescaling inside the resolver.
contract EHRGateAuthorityResolverTest is GateRegistryFixture {
    AgentAuthorityResolver resolver;
    AISRegistry ais;
    CoveredEntityRegistry entityRegistry;
    IntegrityToken itk;
    SmartBAAFactory baaFactory;
    EHRGate gate;

    address admin = makeAddr("admin");
    address scorer = makeAddr("scorer");
    address arbitrator = makeAddr("arbitrator");
    address patient = makeAddr("patient");
    address coveredEntity = makeAddr("coveredEntity");
    uint256 constant COLLATERAL = 1_000 ether;
    uint256 constant THRESHOLD_BPS = 500; // v2: 50 on the 0..1000 scale

    address agent;

    function setUp() public {
        _deployRegistry(admin);
        bytes32 dom = _wireBindableDomain(admin, "health.integrity");
        agent = _boundAgent("ehr-agent", dom);

        itk = new IntegrityToken(admin, 1_000_000 ether);
        vm.startPrank(admin);
        ais = new AISRegistry(admin);
        StakeVault vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(ais));
        ais.grantRole(ais.SCORER_ROLE(), scorer);
        ais.setStakeVault(address(vault));
        ais.setAgentRegistry(address(agentRegistry));
        vm.stopPrank();

        resolver = new AgentAuthorityResolver(address(agentRegistry), address(ais));
        entityRegistry = new CoveredEntityRegistry(admin);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, admin);
        gate = new EHRGate(address(agentRegistry), address(baaFactory), address(resolver), THRESHOLD_BPS, admin);

        _score(agent, 800);

        vm.prank(admin);
        entityRegistry.registerEntity(coveredEntity, CoveredEntityRegistry.EntityType.CoveredEntity, "uri");
        _signBAA(agent);

        vm.prank(patient);
        gate.grantAccess(keccak256("record-1"), agent, coveredEntity);
    }

    function _score(address a, uint32 bps) internal {
        vm.prank(scorer);
        ais.postCheckpoint(a, bps, uint64(block.timestamp), keccak256("evidence"), 0);
    }

    function testBoundAgentPassesAisGate() public {
        vm.prank(agent);
        assertTrue(gate.checkAccess(patient, keccak256("record-1")));
    }

    /// MUTATION: have the resolver return `score / 10` (silent rescale) -> 800 reads as 80 < 500 and
    /// the passing case above FAILS; this case pins the boundary from the other side.
    function testBoundAgentBelowThresholdDenied() public {
        _score(agent, 499);
        vm.prank(agent);
        assertFalse(gate.checkAccess(patient, keccak256("record-1")));
        _score(agent, 500);
        vm.prank(agent);
        assertTrue(gate.checkAccess(patient, keccak256("record-1")));
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
