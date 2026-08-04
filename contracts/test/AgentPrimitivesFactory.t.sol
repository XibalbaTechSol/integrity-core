// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {SovereignAgent} from "../src/core/SovereignAgent.sol";
import {StateAnchor} from "../src/oracle/StateAnchor.sol";
import {ReputationRegistry} from "../src/oracle/ReputationRegistry.sol";
import {Slasher} from "../src/oracle/Slasher.sol";
import {VerifierRegistry} from "../src/oracle/VerifierRegistry.sol";
import {ComplianceGate} from "../src/health/ComplianceGate.sol";
import {AgentProfile} from "../src/framework/AgentProfile.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {DomainRegistry} from "../src/framework/DomainRegistry.sol";
import {AgentPrimitivesFactory} from "../src/framework/AgentPrimitivesFactory.sol";
import {CoveredEntityRegistry} from "../src/health/CoveredEntityRegistry.sol";
import {SmartBAAFactory} from "../src/health/SmartBAAFactory.sol";
import {IntegrityToken} from "../src/oracle/IntegrityToken.sol";

/// @notice Mirrors the real self-sovereign registration sequence end-to-end:
/// (1) the agent's own wallet directly deploys SovereignAgent, (2) directly deploys
/// StateAnchor with that SovereignAgent as admin, (3) routes a call through
/// SovereignAgent.execute to grant the protocol oracle signer ANCHOR_ROLE on that
/// StateAnchor, (4) calls AgentPrimitivesFactory.registerPrimitives to clone+register
/// the remaining 5 primitives — exactly the sequence integrity-sdk's registration.py
/// performs against real Base Sepolia. No shortcuts: every step here is the real
/// contract call a real agent wallet would sign.
contract AgentPrimitivesFactoryTest is Test {
    // Protocol-held singletons.
    XibalbaAgentRegistry registry;
    DomainRegistry domainRegistry;
    IntegrityToken itk;
    CoveredEntityRegistry entityRegistry;
    SmartBAAFactory baaFactory;

    // Clone implementations.
    ReputationRegistry reputationRegistryImpl;
    Slasher slasherImpl;
    VerifierRegistry verifierRegistryImpl;
    ComplianceGate complianceGateImpl;
    AgentProfile agentProfileImpl;

    AgentPrimitivesFactory factory;

    address protocolAdmin = makeAddr("protocolAdmin");
    address oracleSigner = makeAddr("oracleSigner");
    address disputer = makeAddr("disputer");
    address governance = makeAddr("governance");
    address arbitrator = makeAddr("arbitrator");
    address initialZkVerifier = makeAddr("initialZkVerifier");

    // The registering agent's own wallet — signs every step below, exactly like a real
    // agent's EVM key funded by the protocol's faucet wallet would.
    uint256 agentPk = 0xA11CE;
    address agentWallet;

    bytes32 domainId;

    function setUp() public {
        agentWallet = vm.addr(agentPk);

        itk = new IntegrityToken(protocolAdmin, 1_000_000 ether);
        registry = new XibalbaAgentRegistry(protocolAdmin);
        domainRegistry = new DomainRegistry(protocolAdmin);
        entityRegistry = new CoveredEntityRegistry(protocolAdmin);
        baaFactory = new SmartBAAFactory(address(entityRegistry), address(itk), arbitrator, protocolAdmin);

        reputationRegistryImpl = new ReputationRegistry();
        slasherImpl = new Slasher(address(itk));
        verifierRegistryImpl = new VerifierRegistry();
        complianceGateImpl = new ComplianceGate(address(entityRegistry), address(baaFactory));
        agentProfileImpl = new AgentProfile(address(domainRegistry));

        factory = new AgentPrimitivesFactory(
            address(registry),
            address(domainRegistry),
            address(reputationRegistryImpl),
            address(slasherImpl),
            address(verifierRegistryImpl),
            address(complianceGateImpl),
            address(agentProfileImpl),
            oracleSigner,
            disputer,
            governance,
            address(itk),
            initialZkVerifier
        );

        vm.startPrank(protocolAdmin);
        registry.grantRole(registry.REGISTRAR_ROLE(), address(factory));
        domainRegistry.grantRole(domainRegistry.REGISTRAR_ROLE(), address(factory));
        vm.stopPrank();

        vm.prank(protocolAdmin);
        domainId = domainRegistry.registerDomain("general.integrity", DomainRegistry.JoinMode.Open);
    }

    /// @dev Runs steps 1-4 of the real registration sequence as `agentWallet`, returning
    /// the two directly-deployed addresses for assertions.
    function _registerAgent(string memory did, ComplianceGate.Vertical vertical)
        internal
        returns (address sovereignAgent, address stateAnchor)
    {
        vm.startPrank(agentWallet);

        SovereignAgent sa = new SovereignAgent(did, agentWallet, oracleSigner, address(0));
        sovereignAgent = address(sa);

        StateAnchor anchor = new StateAnchor(sovereignAgent);
        stateAnchor = address(anchor);

        // Step 3: route the ANCHOR_ROLE grant through the agent's own SovereignAgent,
        // since StateAnchor's admin is that contract, not the raw EOA.
        sa.execute(
            stateAnchor, 0, abi.encodeCall(AccessControl.grantRole, (anchor.ANCHOR_ROLE(), oracleSigner))
        );

        factory.registerPrimitives(sovereignAgent, stateAnchor, did, domainId, vertical, "ipfs://profile");
        vm.stopPrank();
    }

    function test_fullRegistrationWiresAllSevenPrimitives() public {
        (address sovereignAgent, address stateAnchor) =
            _registerAgent("did:integrity:full-flow", ComplianceGate.Vertical.None);

        XibalbaAgentRegistry.AgentRecord memory record = registry.resolveAgent(sovereignAgent);
        assertEq(record.primitives.sovereignAgent, sovereignAgent);
        assertEq(record.primitives.stateAnchor, stateAnchor);
        assertTrue(record.primitives.reputationRegistry != address(0));
        assertTrue(record.primitives.slasher != address(0));
        assertTrue(record.primitives.verifierRegistry != address(0));
        assertTrue(record.primitives.complianceGate != address(0));
        assertTrue(record.primitives.agentProfile != address(0));
        assertEq(record.controller, agentWallet);
        assertEq(record.domainId, domainId);
    }

    function test_clonesAreAdminedBySovereignAgentNotTheEOA() public {
        (address sovereignAgent,) = _registerAgent("did:integrity:admin-check", ComplianceGate.Vertical.None);
        XibalbaAgentRegistry.AgentRecord memory record = registry.resolveAgent(sovereignAgent);

        ReputationRegistry rep = ReputationRegistry(record.primitives.reputationRegistry);
        assertTrue(rep.hasRole(rep.DEFAULT_ADMIN_ROLE(), sovereignAgent));
        assertFalse(rep.hasRole(rep.DEFAULT_ADMIN_ROLE(), agentWallet));

        // ReputationRegistry's ORACLE_ROLE is the protocol's oracle signer, never the
        // agent — see ReputationRegistry.initialize's NatSpec.
        assertTrue(rep.hasRole(rep.ORACLE_ROLE(), oracleSigner));
    }

    /// @notice Slasher's arbiter must be protocol governance, never the agent — an
    /// agent cannot be trusted to arbitrate its own slashing dispute.
    function test_slasherAdminIsGovernanceNotAgent() public {
        (address sovereignAgent,) = _registerAgent("did:integrity:governance-check", ComplianceGate.Vertical.None);
        XibalbaAgentRegistry.AgentRecord memory record = registry.resolveAgent(sovereignAgent);

        Slasher slasher = Slasher(record.primitives.slasher);
        assertTrue(slasher.hasRole(slasher.DEFAULT_ADMIN_ROLE(), governance));
        assertFalse(slasher.hasRole(slasher.DEFAULT_ADMIN_ROLE(), sovereignAgent));
        assertTrue(slasher.hasRole(slasher.DISPUTER_ROLE(), disputer));
    }

    function test_healthcareVerticalWiresComplianceGate() public {
        (address sovereignAgent,) = _registerAgent("did:integrity:healthcare-agent", ComplianceGate.Vertical.Healthcare);
        XibalbaAgentRegistry.AgentRecord memory record = registry.resolveAgent(sovereignAgent);

        ComplianceGate gate = ComplianceGate(record.primitives.complianceGate);
        assertEq(uint8(gate.vertical()), uint8(ComplianceGate.Vertical.Healthcare));
        assertEq(gate.agent(), sovereignAgent);
    }

    function test_stateAnchorGrantedAnchorRoleToOracleSigner() public {
        (, address stateAnchor) = _registerAgent("did:integrity:anchor-check", ComplianceGate.Vertical.None);
        StateAnchor anchor = StateAnchor(stateAnchor);
        assertTrue(anchor.hasRole(anchor.ANCHOR_ROLE(), oracleSigner));
    }

    function test_domainMembershipRecorded() public {
        (address sovereignAgent,) = _registerAgent("did:integrity:domain-check", ComplianceGate.Vertical.None);
        assertTrue(domainRegistry.isMember(domainId, sovereignAgent));
    }

    function test_revertsIfCallerDoesNotControlClaimedSovereignAgent() public {
        vm.prank(agentWallet);
        SovereignAgent sa = new SovereignAgent("did:integrity:mismatch", agentWallet, oracleSigner, address(0));
        vm.prank(agentWallet);
        StateAnchor anchor = new StateAnchor(address(sa));

        address impersonator = makeAddr("impersonator");
        vm.prank(impersonator);
        vm.expectRevert(AgentPrimitivesFactory.NotAgentController.selector);
        factory.registerPrimitives(
            address(sa), address(anchor), "did:integrity:mismatch", domainId, ComplianceGate.Vertical.None, ""
        );
    }

    function test_revertsIfDomainJoinNotApproved() public {
        vm.prank(protocolAdmin);
        bytes32 gatedDomain = domainRegistry.registerDomain("gated.integrity", DomainRegistry.JoinMode.Permissioned);

        vm.startPrank(agentWallet);
        SovereignAgent sa = new SovereignAgent("did:integrity:gated", agentWallet, oracleSigner, address(0));
        StateAnchor anchor = new StateAnchor(address(sa));

        vm.expectRevert(AgentPrimitivesFactory.DomainJoinNotApproved.selector);
        factory.registerPrimitives(
            address(sa), address(anchor), "did:integrity:gated", gatedDomain, ComplianceGate.Vertical.None, ""
        );
        vm.stopPrank();
    }

    function test_cannotRegisterSameDIDTwice() public {
        _registerAgent("did:integrity:dupe", ComplianceGate.Vertical.None);

        vm.startPrank(agentWallet);
        SovereignAgent sa2 = new SovereignAgent("did:integrity:dupe", agentWallet, oracleSigner, address(0));
        StateAnchor anchor2 = new StateAnchor(address(sa2));

        vm.expectRevert(XibalbaAgentRegistry.AlreadyRegistered.selector);
        factory.registerPrimitives(
            address(sa2), address(anchor2), "did:integrity:dupe", domainId, ComplianceGate.Vertical.None, ""
        );
        vm.stopPrank();
    }

    /// @notice Two different agents registering must never collide on clone addresses
    /// or share any admin-role state — each EIP-1167 clone is genuinely independent.
    function test_twoAgentsGetIndependentClones() public {
        (address agentOneSA,) = _registerAgent("did:integrity:agent-one", ComplianceGate.Vertical.None);

        uint256 agentTwoPk = 0xB0B;
        address agentTwoWallet = vm.addr(agentTwoPk);
        vm.deal(agentTwoWallet, 1 ether);
        vm.startPrank(agentTwoWallet);
        SovereignAgent sa2 = new SovereignAgent("did:integrity:agent-two", agentTwoWallet, oracleSigner, address(0));
        StateAnchor anchor2 = new StateAnchor(address(sa2));
        sa2.execute(address(anchor2), 0, abi.encodeCall(AccessControl.grantRole, (anchor2.ANCHOR_ROLE(), oracleSigner)));
        factory.registerPrimitives(
            address(sa2), address(anchor2), "did:integrity:agent-two", domainId, ComplianceGate.Vertical.None, ""
        );
        vm.stopPrank();

        XibalbaAgentRegistry.AgentRecord memory r1 = registry.resolveAgent(agentOneSA);
        XibalbaAgentRegistry.AgentRecord memory r2 = registry.resolveAgent(address(sa2));

        assertTrue(r1.primitives.reputationRegistry != r2.primitives.reputationRegistry);
        assertTrue(r1.primitives.slasher != r2.primitives.slasher);

        ReputationRegistry rep2 = ReputationRegistry(r2.primitives.reputationRegistry);
        assertFalse(rep2.hasRole(rep2.DEFAULT_ADMIN_ROLE(), agentOneSA));
    }
}
