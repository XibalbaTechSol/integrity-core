// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {ComplianceGate} from "../../src/health/ComplianceGate.sol";
import {CoveredEntityRegistry} from "../../src/health/CoveredEntityRegistry.sol";
import {SmartBAAFactory} from "../../src/health/SmartBAAFactory.sol";
import {SmartBAA} from "../../src/health/SmartBAA.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";

/// @notice Proves ComplianceGate never fakes compliance: `isHealthcareCompliant` must
/// track a real, live CoveredEntityRegistry + SmartBAAFactory read, not just the
/// self-declared vertical flag.
contract ComplianceGateTest is Test {
    ComplianceGate gate;
    CoveredEntityRegistry entityRegistry;
    SmartBAAFactory baaFactory;
    IntegrityToken itk;

    address admin = makeAddr("admin");
    address arbitrator = makeAddr("arbitrator");
    address hospital = makeAddr("hospital");
    address agent = makeAddr("agent");
    uint256 constant COLLATERAL = 1_000 ether;

    function setUp() public {
        itk = new IntegrityToken(admin, 1_000_000 ether);
        entityRegistry = new CoveredEntityRegistry(admin);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, admin);

        ComplianceGate impl = new ComplianceGate(address(entityRegistry), address(baaFactory));
        gate = ComplianceGate(Clones.clone(address(impl)));
        gate.initialize(agent, agent, ComplianceGate.Vertical.Healthcare);

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

    function test_notHealthcareCompliantWithoutBAA() public view {
        assertFalse(gate.isHealthcareCompliant(hospital));
    }

    function test_healthcareCompliantWithActiveBAA() public {
        _signBAA();
        assertTrue(gate.isHealthcareCompliant(hospital));
    }

    function test_nonHealthcareVerticalNeverCompliantEvenWithBAA() public {
        ComplianceGate impl = new ComplianceGate(address(entityRegistry), address(baaFactory));
        ComplianceGate noneGate = ComplianceGate(Clones.clone(address(impl)));
        noneGate.initialize(agent, agent, ComplianceGate.Vertical.None);

        _signBAA();
        assertFalse(noneGate.isHealthcareCompliant(hospital));
    }

    /// @notice Self-declared flags must never influence the live-verified boolean — a
    /// dishonest agent cannot self-declare its way into compliance.
    function test_selfDeclaredFlagsDoNotAffectLiveCheck() public {
        vm.prank(agent);
        gate.setSelfDeclaredCompliance(true, true, false, "us-east");
        assertFalse(gate.isHealthcareCompliant(hospital));
    }

    function test_onlyAdminCanSetSelfDeclaredCompliance() public {
        vm.expectRevert();
        gate.setSelfDeclaredCompliance(true, true, false, "us-east");
    }

    function test_revokedBAALosesCompliance() public {
        _signBAA();
        assertTrue(gate.isHealthcareCompliant(hospital));

        address baaAddr = baaFactory.baaOf(hospital, agent);
        vm.prank(hospital);
        SmartBAA(baaAddr).revoke();

        assertFalse(gate.isHealthcareCompliant(hospital));
    }
}
