// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AgentLineageRegistry} from "../src/framework/AgentLineageRegistry.sol";
import {GateRegistryFixture} from "./trust/GateRegistryFixture.sol";

contract AgentLineageRegistryTest is GateRegistryFixture {
    AgentLineageRegistry lineage;
    address predecessor;
    address successor;
    address admin = makeAddr("admin");
    // `_boundAgent(label)` derives the controller from `label`, so these match the bound agents.
    address predecessorController = makeAddr("predecessorController");
    address successorController = makeAddr("successorController");

    function setUp() public {
        _deployRegistry(admin);
        bytes32 dom = _wireBindableDomain(admin, "lineage.integrity");
        predecessor = _boundAgent("predecessorController", dom);
        successor = _boundAgent("successorController", dom);
        lineage = new AgentLineageRegistry(address(agentRegistry));
    }

    function test_controllerRecordsImmutableLineage() public {
        bytes32 relationType = lineage.FORKED_FROM();
        vm.prank(successorController);
        lineage.recordLineage(successor, predecessor, relationType);
        (address parent, bytes32 recordedRelation, address attestor, uint256 recordedAt) = lineage.lineageOf(successor);
        assertEq(parent, predecessor);
        assertEq(recordedRelation, relationType);
        assertEq(attestor, successorController);
        assertGt(recordedAt, 0);
    }

    function test_rejectsSecondLineage() public {
        bytes32 migrated = lineage.MIGRATED_FROM();
        bytes32 recovered = lineage.RECOVERED_FROM();
        vm.prank(successorController);
        lineage.recordLineage(successor, predecessor, migrated);
        vm.expectRevert(AgentLineageRegistry.AlreadyRecorded.selector);
        vm.prank(successorController);
        lineage.recordLineage(successor, predecessor, recovered);
    }

    function test_rejectsNonController() public {
        bytes32 relation = lineage.FORKED_FROM();
        vm.expectRevert(AgentLineageRegistry.NotCurrentController.selector);
        lineage.recordLineage(successor, predecessor, relation);
    }
}
