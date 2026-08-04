// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {SovereignAgent} from "../core/SovereignAgent.sol";
import {XibalbaAgentRegistry} from "./XibalbaAgentRegistry.sol";
import {DomainRegistry} from "./DomainRegistry.sol";
import {ReputationRegistry} from "../oracle/ReputationRegistry.sol";
import {Slasher} from "../oracle/Slasher.sol";
import {VerifierRegistry} from "../oracle/VerifierRegistry.sol";
import {ComplianceGate} from "../health/ComplianceGate.sol";
import {AgentProfile} from "./AgentProfile.sol";

/// @title AgentPrimitivesFactory
/// @notice The self-sovereign replacement for the old AgentFactory. An agent no longer
/// gets its identity contracts deployed on its behalf — it deploys its own
/// `SovereignAgent` and `StateAnchor` directly, from its own EVM wallet, so those two
/// deployment transactions are themselves the cryptographic proof of self-sovereign
/// control (see docs/INTERFACE_CONTRACT.md's "Agent Primitives" section). This
/// contract's job starts *after* that: given the two agent-deployed addresses, it clones
/// the other 5 primitives (cheap EIP-1167 proxies of shared implementation contracts),
/// initializes each with the agent's SovereignAgent contract as admin — never the raw
/// EOA, per the protocol's call-routing convention — and atomically registers the full
/// 7-address PrimitiveSet into XibalbaAgentRegistry and DomainRegistry so no consumer can
/// ever observe an agent that only half-exists.
/// @dev Bootstrap exception to "SovereignAgent routes everything": this call is EOA-signed
/// directly (SovereignAgent cannot route a call to register itself — that would be
/// circular), verified instead by checking the caller actually holds DEFAULT_ADMIN_ROLE
/// on the SovereignAgent it claims to own. Holds REGISTRAR_ROLE on both registries
/// (granted to this contract's address at deploy time, see script/Deploy.s.sol) — no
/// other contract should hold that role, same reasoning as the old AgentFactory.
contract AgentPrimitivesFactory {
    XibalbaAgentRegistry public immutable registry;
    DomainRegistry public immutable domainRegistry;

    /// @dev The 5 shared implementation contracts that every agent's clones
    /// delegatecall into. Deployed once by script/Deploy.s.sol with
    /// `_disableInitializers()` already called on each, so they can never be
    /// initialized/hijacked directly — only clones of them can.
    address public immutable reputationRegistryImpl;
    address public immutable slasherImpl;
    address public immutable verifierRegistryImpl;
    address public immutable complianceGateImpl;
    address public immutable agentProfileImpl;

    /// @dev Protocol-held signers/addresses passed into each clone's `initialize` — never
    /// the registering agent's own key. See ReputationRegistry/Slasher NatSpec for why
    /// these are kept distinct from the agent's own admin role.
    address public immutable oracleSigner;
    address public immutable disputer;
    address public immutable governance;
    address public immutable itk;
    address public immutable initialZkVerifier;

    event PrimitivesRegistered(
        bytes32 indexed didHash,
        address indexed sovereignAgent,
        address indexed controller,
        address stateAnchor,
        address reputationRegistry,
        address slasher,
        address verifierRegistry,
        address complianceGate,
        address agentProfile,
        bytes32 domainId
    );

    error NotAgentController();
    error DomainJoinNotApproved();

    constructor(
        address _registry,
        address _domainRegistry,
        address _reputationRegistryImpl,
        address _slasherImpl,
        address _verifierRegistryImpl,
        address _complianceGateImpl,
        address _agentProfileImpl,
        address _oracleSigner,
        address _disputer,
        address _governance,
        address _itk,
        address _initialZkVerifier
    ) {
        registry = XibalbaAgentRegistry(_registry);
        domainRegistry = DomainRegistry(_domainRegistry);
        reputationRegistryImpl = _reputationRegistryImpl;
        slasherImpl = _slasherImpl;
        verifierRegistryImpl = _verifierRegistryImpl;
        complianceGateImpl = _complianceGateImpl;
        agentProfileImpl = _agentProfileImpl;
        oracleSigner = _oracleSigner;
        disputer = _disputer;
        governance = _governance;
        itk = _itk;
        initialZkVerifier = _initialZkVerifier;
    }

    /// @notice Clones and registers the remaining 5 primitives for an agent that has
    /// already (a) deployed its own SovereignAgent, (b) deployed its own StateAnchor
    /// with that SovereignAgent as admin, and (c) routed a call through
    /// `SovereignAgent.execute` to grant the protocol's oracle signer ANCHOR_ROLE on
    /// that StateAnchor (see integrity-sdk's registration.py for the exact sequence).
    /// @param sovereignAgent The agent-deployed SovereignAgent address.
    /// @param stateAnchor The agent-deployed StateAnchor address.
    /// @param did The DID string this SovereignAgent was constructed with — re-hashed
    /// here and checked for uniqueness by the registry, same as the old AgentFactory.
    /// @param domainId The domain this agent is registering under.
    /// @param vertical The regulated-industry vertical this agent declares (None for
    /// most agents; Healthcare for Integrity Health-integrated ones).
    /// @param profileURI Off-chain metadata pointer for AgentProfile.
    function registerPrimitives(
        address sovereignAgent,
        address stateAnchor,
        string calldata did,
        bytes32 domainId,
        ComplianceGate.Vertical vertical,
        string calldata profileURI
    )
        external
        returns (
            address reputationRegistry,
            address slasher,
            address verifierRegistry,
            address complianceGate,
            address agentProfile
        )
    {
        SovereignAgent sa = SovereignAgent(payable(sovereignAgent));
        if (!sa.hasRole(sa.DEFAULT_ADMIN_ROLE(), msg.sender)) revert NotAgentController();
        if (!domainRegistry.canJoin(domainId, msg.sender)) revert DomainJoinNotApproved();

        // Every clone's admin is the SovereignAgent contract address, not msg.sender —
        // see the interface contract's call-routing convention. Protocol-held roles
        // (oracle/disputer/governance) are this factory's own immutables, never
        // anything the registering agent controls.
        reputationRegistry = Clones.clone(reputationRegistryImpl);
        ReputationRegistry(reputationRegistry).initialize(sovereignAgent, oracleSigner, initialZkVerifier, stateAnchor);

        slasher = Clones.clone(slasherImpl);
        Slasher(slasher).initialize(governance, disputer);

        verifierRegistry = Clones.clone(verifierRegistryImpl);
        VerifierRegistry(verifierRegistry).initialize(sovereignAgent, initialZkVerifier);

        complianceGate = Clones.clone(complianceGateImpl);
        ComplianceGate(complianceGate).initialize(sovereignAgent, sovereignAgent, vertical);

        agentProfile = Clones.clone(agentProfileImpl);
        AgentProfile(agentProfile).initialize(sovereignAgent, sovereignAgent, domainId, profileURI);

        bytes32 didHash_ = registry.didHash(did);
        registry.registerPrimitives(
            didHash_,
            XibalbaAgentRegistry.PrimitiveSet({
                sovereignAgent: sovereignAgent,
                stateAnchor: stateAnchor,
                reputationRegistry: reputationRegistry,
                slasher: slasher,
                verifierRegistry: verifierRegistry,
                complianceGate: complianceGate,
                agentProfile: agentProfile
            }),
            msg.sender,
            domainId
        );
        domainRegistry.recordJoin(domainId, msg.sender, sovereignAgent);

        emit PrimitivesRegistered(
            didHash_,
            sovereignAgent,
            msg.sender,
            stateAnchor,
            reputationRegistry,
            slasher,
            verifierRegistry,
            complianceGate,
            agentProfile,
            domainId
        );
    }
}
