// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {AgentAuthorityResolver} from "../src/framework/AgentAuthorityResolver.sol";

contract MockReputationRegistry {
    mapping(address => uint256) public scoreOf;

    function setScore(address agent, uint256 score) external {
        scoreOf[agent] = score;
    }

    function effectiveScore(address agent) external view returns (uint256) {
        return scoreOf[agent];
    }
}

contract MockSovereignAgent {
    uint256 public ais;

    function setAis(uint256 v) external {
        ais = v;
    }
}

contract AgentAuthorityResolverTest is Test {
    XibalbaAgentRegistry registry;
    AgentAuthorityResolver resolver;

    address admin = makeAddr("admin");
    address registrar = makeAddr("registrar");
    address controller = makeAddr("controller");

    function setUp() public {
        vm.prank(admin);
        registry = new XibalbaAgentRegistry(admin);
        bytes32 registrarRole = registry.REGISTRAR_ROLE();
        vm.prank(admin);
        registry.grantRole(registrarRole, registrar);
        resolver = new AgentAuthorityResolver(address(registry));
    }

    function testSovereignProfileResolvesThroughCloneSet() public {
        address sovereignAgent = makeAddr("sovereignAgent");
        address stateAnchor = makeAddr("stateAnchor");
        MockReputationRegistry reputationRegistry = new MockReputationRegistry();
        reputationRegistry.setScore(sovereignAgent, 77);

        XibalbaAgentRegistry.PrimitiveSet memory primitives = XibalbaAgentRegistry.PrimitiveSet({
            sovereignAgent: sovereignAgent,
            stateAnchor: stateAnchor,
            reputationRegistry: address(reputationRegistry),
            slasher: address(0),
            verifierRegistry: address(0),
            complianceGate: address(0),
            agentProfile: address(0)
        });

        vm.prank(registrar);
        registry.registerPrimitives(keccak256("did:integrity:sovereign"), primitives, controller, bytes32(0));

        assertTrue(resolver.isAuthorityRegistered(sovereignAgent));
        assertEq(resolver.getAis(sovereignAgent), 77);
        assertEq(resolver.getStateAnchor(sovereignAgent), stateAnchor);
    }

    function testEnterpriseProfileResolvesWithoutCloneSet() public {
        MockSovereignAgent enterpriseAgent = new MockSovereignAgent();
        enterpriseAgent.setAis(42);
        address stateAnchor = makeAddr("enterpriseStateAnchor");

        vm.prank(registrar);
        registry.registerEnterpriseAgent(address(enterpriseAgent), stateAnchor, controller, bytes32(0));

        assertTrue(resolver.isAuthorityRegistered(address(enterpriseAgent)));
        assertEq(resolver.getAis(address(enterpriseAgent)), 42);
        assertEq(resolver.getStateAnchor(address(enterpriseAgent)), stateAnchor);
    }

    function testUnregisteredAgentReverts() public {
        address stranger = makeAddr("stranger");
        assertFalse(resolver.isAuthorityRegistered(stranger));
        vm.expectRevert(abi.encodeWithSelector(AgentAuthorityResolver.NotRegistered.selector, stranger));
        resolver.getAis(stranger);
    }

    function testEnterpriseRegistrationRequiresRegistrarRole() public {
        MockSovereignAgent enterpriseAgent = new MockSovereignAgent();
        vm.expectRevert();
        registry.registerEnterpriseAgent(address(enterpriseAgent), makeAddr("anchor"), controller, bytes32(0));
    }
}
