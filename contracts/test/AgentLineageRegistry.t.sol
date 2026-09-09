// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentLineageRegistry} from "../src/framework/AgentLineageRegistry.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";

contract LineageMockAgent {
    bytes32 public constant DEFAULT_ADMIN_ROLE = 0x00;
    mapping(address => bool) public admins;

    constructor(address controller) {
        admins[controller] = true;
    }

    function hasRole(bytes32 role, address account) external view returns (bool) {
        return role == DEFAULT_ADMIN_ROLE && admins[account];
    }
}

contract AgentLineageRegistryTest is Test {
    XibalbaAgentRegistry registry;
    AgentLineageRegistry lineage;
    LineageMockAgent predecessor;
    LineageMockAgent successor;
    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address predecessorController = makeAddr("predecessorController");
    address successorController = makeAddr("successorController");

    function setUp() public {
        registry = new XibalbaAgentRegistry(admin);
        bytes32 registrarRole = registry.REGISTRAR_ROLE();
        vm.startPrank(admin);
        registry.grantRole(registrarRole, registrar);
        vm.stopPrank();
        predecessor = new LineageMockAgent(predecessorController);
        successor = new LineageMockAgent(successorController);
        _register(address(predecessor), "predecessor");
        _register(address(successor), "successor");
        lineage = new AgentLineageRegistry(address(registry));
    }

    function _register(address agent, string memory label) internal {
        XibalbaAgentRegistry.PrimitiveSet memory p = XibalbaAgentRegistry.PrimitiveSet(
            agent, makeAddr(string.concat(label, "-state")), makeAddr(string.concat(label, "-rep")),
            makeAddr(string.concat(label, "-slasher")), makeAddr(string.concat(label, "-verifier")),
            makeAddr(string.concat(label, "-gate")), makeAddr(string.concat(label, "-profile"))
        );
        bytes32 didHash = registry.didHash(label);
        vm.prank(registrar);
        registry.registerPrimitives(didHash, p, address(0xBEEF), bytes32(0));
    }

    function test_controllerRecordsImmutableLineage() public {
        bytes32 relationType = lineage.FORKED_FROM();
        vm.prank(successorController);
        lineage.recordLineage(address(successor), address(predecessor), relationType);
        (address parent, bytes32 recordedRelation, address attestor, uint256 recordedAt) = lineage.lineageOf(address(successor));
        assertEq(parent, address(predecessor));
        assertEq(recordedRelation, relationType);
        assertEq(attestor, successorController);
        assertGt(recordedAt, 0);
    }

    function test_rejectsSecondLineage() public {
        bytes32 migrated = lineage.MIGRATED_FROM();
        bytes32 recovered = lineage.RECOVERED_FROM();
        vm.prank(successorController);
        lineage.recordLineage(address(successor), address(predecessor), migrated);
        vm.expectRevert(AgentLineageRegistry.AlreadyRecorded.selector);
        vm.prank(successorController);
        lineage.recordLineage(address(successor), address(predecessor), recovered);
    }

    function test_rejectsNonController() public {
        bytes32 relation = lineage.FORKED_FROM();
        vm.expectRevert(AgentLineageRegistry.NotCurrentController.selector);
        lineage.recordLineage(address(successor), address(predecessor), relation);
    }
}
