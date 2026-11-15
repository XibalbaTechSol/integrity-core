// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {XibalbaNameService} from "../src/framework/XibalbaNameService.sol";
import {GateRegistryFixture} from "./trust/GateRegistryFixture.sol";

contract XibalbaNameServiceTest is GateRegistryFixture {
    XibalbaNameService xns;

    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address sovereignAgent;
    address otherSovereignAgent;
    address stranger = makeAddr("stranger");

    bytes32 domainId;

    function setUp() public {
        _deployRegistry(admin);
        domainId = _wireBindableDomain(admin, "healthcare.integrity");
        xns = new XibalbaNameService(admin, address(agentRegistry));
        // XNS's register() checks isRegisteredAgent(msg.sender): a genuinely bound actor.
        sovereignAgent = _boundAgent("sovereignAgent", domainId);
    }

    // --- registration -----------------------------------------------------------

    function test_registeredAgentCanClaimAHandle() public {
        vm.prank(sovereignAgent);
        bytes32 id = xns.register("hermes.integrity");

        assertEq(id, xns.handleId("hermes.integrity"));
        assertEq(xns.resolve("hermes.integrity"), sovereignAgent);
        assertTrue(xns.handleExists("hermes.integrity"));
    }

    function test_firstHandleBecomesPrimaryAutomatically() public {
        vm.prank(sovereignAgent);
        xns.register("hermes.integrity");

        assertEq(xns.primaryHandle(sovereignAgent), "hermes.integrity");
    }

    function test_unregisteredCallerCannotClaimAHandle() public {
        vm.prank(stranger);
        vm.expectRevert(XibalbaNameService.NotRegisteredAgent.selector);
        xns.register("squatter.integrity");
    }

    function test_cannotRegisterDuplicateHandle() public {
        vm.prank(sovereignAgent);
        xns.register("hermes.integrity");

        vm.prank(sovereignAgent);
        vm.expectRevert(XibalbaNameService.HandleAlreadyRegistered.selector);
        xns.register("hermes.integrity");
    }

    function test_cannotRegisterEmptyHandle() public {
        vm.prank(sovereignAgent);
        vm.expectRevert(XibalbaNameService.EmptyHandle.selector);
        xns.register("");
    }

    function test_resolvingUnregisteredHandleReverts() public {
        vm.expectRevert(XibalbaNameService.HandleNotFound.selector);
        xns.resolve("nobody.integrity");
    }

    function test_handleExistsIsFalseForUnclaimedHandle() public view {
        assertFalse(xns.handleExists("nobody.integrity"));
    }

    // --- primary handle -----------------------------------------------------------

    function test_agentCanChoosePrimaryAmongMultipleHandles() public {
        vm.startPrank(sovereignAgent);
        xns.register("hermes.integrity");
        xns.register("hermes-alt.integrity");
        assertEq(xns.primaryHandle(sovereignAgent), "hermes.integrity");

        xns.setPrimaryHandle("hermes-alt.integrity");
        vm.stopPrank();

        assertEq(xns.primaryHandle(sovereignAgent), "hermes-alt.integrity");
    }

    function test_cannotSetPrimaryToAHandleYouDontOwn() public {
        vm.prank(sovereignAgent);
        xns.register("hermes.integrity");

        vm.prank(stranger);
        vm.expectRevert(XibalbaNameService.NotHandleOwner.selector);
        xns.setPrimaryHandle("hermes.integrity");
    }

    // --- self-release -----------------------------------------------------------

    function test_ownerCanReleaseTheirOwnHandle() public {
        vm.startPrank(sovereignAgent);
        xns.register("hermes.integrity");
        xns.release("hermes.integrity");
        vm.stopPrank();

        assertFalse(xns.handleExists("hermes.integrity"));
        assertEq(xns.primaryHandle(sovereignAgent), "");
    }

    function test_releasedHandleCanBeReclaimedByAnotherAgent() public {
        vm.startPrank(sovereignAgent);
        xns.register("hermes.integrity");
        xns.release("hermes.integrity");
        vm.stopPrank();

        // Make otherSovereignAgent a real bound agent too, distinct record.
        otherSovereignAgent = _boundAgent("otherSovereignAgent", domainId);

        vm.prank(otherSovereignAgent);
        xns.register("hermes.integrity");
        assertEq(xns.resolve("hermes.integrity"), otherSovereignAgent);
    }

    function test_strangerCannotReleaseSomeoneElsesHandle() public {
        vm.prank(sovereignAgent);
        xns.register("hermes.integrity");

        vm.prank(stranger);
        vm.expectRevert(XibalbaNameService.NotHandleOwner.selector);
        xns.release("hermes.integrity");
    }

    // --- dispute-intervention path -----------------------------------------------------------

    function test_registrarCanRevokeAHandleForDisputeResolution() public {
        vm.prank(sovereignAgent);
        xns.register("hermes.integrity");

        bytes32 xnsRegistrarRole = xns.REGISTRAR_ROLE();
        vm.prank(admin);
        xns.grantRole(xnsRegistrarRole, registrar);

        vm.prank(registrar);
        xns.revokeByRegistrar("hermes.integrity");

        assertFalse(xns.handleExists("hermes.integrity"));
    }

    function test_nonRegistrarCannotForceRevoke() public {
        vm.prank(sovereignAgent);
        xns.register("hermes.integrity");

        vm.prank(stranger);
        vm.expectRevert();
        xns.revokeByRegistrar("hermes.integrity");
    }
}
