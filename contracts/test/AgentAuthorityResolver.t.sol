// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AgentAuthorityResolver} from "../src/framework/AgentAuthorityResolver.sol";
import {AISRegistry} from "../src/trust/AISRegistry.sol";
import {StakeVault} from "../src/trust/StakeVault.sol";
import {ITK} from "../src/trust/ITK.sol";
import {GateRegistryFixture} from "./trust/GateRegistryFixture.sol";

/// @notice Registration v3: registered = bound actor in `AgentRegistry`; AIS = latest `AISRegistry`
/// checkpoint, returned in basis points with no rescaling.
contract AgentAuthorityResolverTest is GateRegistryFixture {
    AgentAuthorityResolver resolver;
    AISRegistry ais;

    address admin = makeAddr("admin");
    address scorer = makeAddr("scorer");
    bytes32 domainId;

    function setUp() public {
        _deployRegistry(admin);
        domainId = _wireBindableDomain(admin, "resolver.integrity");
        // Real checkpoint path: AISRegistry -> StakeVault, with the AgentRegistry wired.
        vm.startPrank(admin);
        ais = new AISRegistry(admin);
        ITK itk = new ITK(admin, 0);
        StakeVault vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(ais));
        ais.grantRole(ais.SCORER_ROLE(), scorer);
        ais.setStakeVault(address(vault));
        ais.setAgentRegistry(address(agentRegistry));
        vm.stopPrank();
        resolver = new AgentAuthorityResolver(address(agentRegistry), address(ais));
    }

    /// AIS comes from the AISRegistry checkpoint, in basis points, unchanged.
    /// MUTATION: return `score / 10` (the old 0..1000 scale) -> 7700 != 770, test FAILS.
    function testBoundAgentResolvesAisFromCheckpoint() public {
        address agent = _boundAgent("bound", domainId);
        assertTrue(resolver.isAuthorityRegistered(agent));
        assertEq(resolver.getAis(agent), 0, "registered, no checkpoint yet");

        vm.prank(scorer);
        ais.postCheckpoint(agent, 7700, 1, keccak256("evidence"), 0);
        assertEq(resolver.getAis(agent), 7700);
    }

    function testUnboundCanonicalAgentIsNotRegistered() public {
        (address ctl,) = makeAddrAndKey("unbound");
        address agent = address(_newAgent("did:integrity:unbound", ctl));
        assertFalse(resolver.isAuthorityRegistered(agent));
        vm.expectRevert(abi.encodeWithSelector(AgentAuthorityResolver.NotRegistered.selector, agent));
        resolver.getAis(agent);
    }

    function testUnregisteredAgentReverts() public {
        address stranger = makeAddr("stranger");
        assertFalse(resolver.isAuthorityRegistered(stranger));
        vm.expectRevert(abi.encodeWithSelector(AgentAuthorityResolver.NotRegistered.selector, stranger));
        resolver.getAis(stranger);
    }

    function testZeroAddressesRejected() public {
        vm.expectRevert(bytes("AgentAuthorityResolver: zero registry"));
        new AgentAuthorityResolver(address(0), address(ais));
        vm.expectRevert(bytes("AgentAuthorityResolver: zero AIS registry"));
        new AgentAuthorityResolver(address(agentRegistry), address(0));
    }
}
