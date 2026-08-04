// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {CoveredEntityRegistry} from "../../src/health/CoveredEntityRegistry.sol";
import {SmartBAAFactory} from "../../src/health/SmartBAAFactory.sol";
import {SmartBAA} from "../../src/health/SmartBAA.sol";
import {IntegrityToken} from "../../src/oracle/IntegrityToken.sol";

/// @notice Full lifecycle test across SmartBAAFactory + SmartBAA + CoveredEntityRegistry
/// + IntegrityToken collateral — the escrow/dispute machinery that's the whole point of
/// the Integrity Health HIPAA vertical.
contract SmartBAATest is Test {
    CoveredEntityRegistry entityRegistry;
    SmartBAAFactory factory;
    IntegrityToken itk;

    address admin = makeAddr("admin");
    address arbitrator = makeAddr("arbitrator");
    address hospital = makeAddr("hospital");
    address aiAgent = makeAddr("aiAgent");
    uint256 constant COLLATERAL = 5_000 ether;

    function setUp() public {
        itk = new IntegrityToken(admin, 1_000_000 ether);
        entityRegistry = new CoveredEntityRegistry(admin);
        factory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, admin);

        vm.prank(admin);
        entityRegistry.registerEntity(hospital, CoveredEntityRegistry.EntityType.CoveredEntity, "uri");

        vm.prank(admin);
        itk.transfer(aiAgent, COLLATERAL * 2);
    }

    function _createAndSignBAA() internal returns (SmartBAA baa) {
        vm.prank(hospital);
        address baaAddr = factory.createBAA(aiAgent, keccak256("legal-doc-v1"), COLLATERAL);
        baa = SmartBAA(baaAddr);

        vm.startPrank(aiAgent);
        itk.approve(baaAddr, COLLATERAL);
        baa.sign();
        vm.stopPrank();
    }

    function test_nonCoveredEntityCannotCreateBAA() public {
        vm.prank(aiAgent);
        vm.expectRevert(SmartBAAFactory.NotActiveCoveredEntity.selector);
        factory.createBAA(aiAgent, keccak256("doc"), COLLATERAL);
    }

    function test_signActivatesAndLocksCollateral() public {
        SmartBAA baa = _createAndSignBAA();

        assertEq(uint8(baa.status()), uint8(SmartBAA.Status.Active));
        assertEq(itk.balanceOf(address(baa)), COLLATERAL);
        assertTrue(factory.isBAAActive(hospital, aiAgent));
    }

    function test_disputeAndSlash_paysCoveredEntity() public {
        SmartBAA baa = _createAndSignBAA();

        vm.prank(hospital);
        baa.raiseDispute();
        assertEq(uint8(baa.status()), uint8(SmartBAA.Status.Disputed));
        assertFalse(factory.isBAAActive(hospital, aiAgent)); // disputed != active

        uint256 hospitalBalBefore = itk.balanceOf(hospital);
        vm.prank(arbitrator);
        baa.arbitrate(true);

        assertEq(uint8(baa.status()), uint8(SmartBAA.Status.Terminated));
        assertEq(itk.balanceOf(hospital), hospitalBalBefore + COLLATERAL);
        assertEq(itk.balanceOf(address(baa)), 0);
    }

    function test_disputeDismissed_returnsToActive() public {
        SmartBAA baa = _createAndSignBAA();

        vm.prank(hospital);
        baa.raiseDispute();

        vm.prank(arbitrator);
        baa.arbitrate(false);

        assertEq(uint8(baa.status()), uint8(SmartBAA.Status.Active));
        assertEq(itk.balanceOf(address(baa)), COLLATERAL); // untouched
        assertTrue(factory.isBAAActive(hospital, aiAgent));
    }

    function test_revokeReturnsCollateralToAgent() public {
        SmartBAA baa = _createAndSignBAA();

        uint256 agentBalBefore = itk.balanceOf(aiAgent);
        vm.prank(hospital);
        baa.revoke();

        assertEq(uint8(baa.status()), uint8(SmartBAA.Status.Terminated));
        assertEq(itk.balanceOf(aiAgent), agentBalBefore + COLLATERAL);
    }

    function test_cannotRevokeWhileDisputed() public {
        SmartBAA baa = _createAndSignBAA();
        vm.prank(hospital);
        baa.raiseDispute();

        vm.prank(hospital);
        vm.expectRevert(abi.encodeWithSelector(SmartBAA.WrongStatus.selector, SmartBAA.Status.Disputed));
        baa.revoke();
    }

    function test_onlyArbitratorCanArbitrate() public {
        SmartBAA baa = _createAndSignBAA();
        vm.prank(hospital);
        baa.raiseDispute();

        vm.prank(hospital);
        vm.expectRevert(SmartBAA.NotArbitrator.selector);
        baa.arbitrate(true);
    }

    function test_duplicateBAABetweenSamePairReverts() public {
        _createAndSignBAA();
        vm.prank(hospital);
        vm.expectRevert(SmartBAAFactory.BAAAlreadyExists.selector);
        factory.createBAA(aiAgent, keccak256("another-doc"), COLLATERAL);
    }

    function test_unsignedBAAIsNotActive() public {
        vm.prank(hospital);
        factory.createBAA(aiAgent, keccak256("doc"), COLLATERAL);
        assertFalse(factory.isBAAActive(hospital, aiAgent));
    }

    /// @notice Regression test: `createBAA` used to permanently block re-forming a BAA
    /// for the same (hospital, agent) pair after ANY termination — `baaOf` was set once
    /// and never cleared, so `BAAAlreadyExists` reverted forever even once the prior
    /// agreement had legitimately ended via `revoke()`. BAAs are routinely renewed in
    /// practice, so this must succeed.
    function test_canReformBAAAfterRevoke() public {
        SmartBAA first = _createAndSignBAA();
        vm.prank(hospital);
        first.revoke();
        assertEq(uint8(first.status()), uint8(SmartBAA.Status.Terminated));

        vm.prank(hospital);
        address secondAddr = factory.createBAA(aiAgent, keccak256("renewed-doc"), COLLATERAL);
        assertTrue(secondAddr != address(first), "re-formation must deploy a fresh escrow, not reuse the terminated one");
        assertEq(factory.baaOf(hospital, aiAgent), secondAddr, "the pair must now point at the new BAA");

        vm.startPrank(aiAgent);
        itk.approve(secondAddr, COLLATERAL);
        SmartBAA(secondAddr).sign();
        vm.stopPrank();
        assertTrue(factory.isBAAActive(hospital, aiAgent), "the renewed BAA must be usable exactly like a fresh one");
    }

    /// @notice Same re-formation path, but reaching Terminated via a slashing arbitration
    /// rather than a mutual revoke — both termination routes must equally unblock reformation.
    function test_canReformBAAAfterSlash() public {
        SmartBAA first = _createAndSignBAA();
        vm.prank(hospital);
        first.raiseDispute();
        vm.prank(arbitrator);
        first.arbitrate(true);
        assertEq(uint8(first.status()), uint8(SmartBAA.Status.Terminated));

        vm.prank(hospital);
        address secondAddr = factory.createBAA(aiAgent, keccak256("post-slash-doc"), COLLATERAL);
        assertTrue(secondAddr != address(first));
        assertEq(factory.baaOf(hospital, aiAgent), secondAddr);
    }

    /// @notice The other side of the fix: re-formation must stay blocked while the
    /// existing agreement is genuinely still in force (Disputed, not yet resolved) —
    /// only `Terminated` unblocks it.
    function test_cannotReformBAAWhileDisputed() public {
        SmartBAA baa = _createAndSignBAA();
        vm.prank(hospital);
        baa.raiseDispute();

        vm.prank(hospital);
        vm.expectRevert(SmartBAAFactory.BAAAlreadyExists.selector);
        factory.createBAA(aiAgent, keccak256("another-doc"), COLLATERAL);
    }
}
