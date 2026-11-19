// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {DomainRegistry} from "../../src/framework/DomainRegistry.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";
import {IPolicyModule} from "../../src/trust/IPolicyModule.sol";
import {MockGovernedAccount} from "../wallet/mocks/MockGovernedAccount.sol";
import {MockAccountVerifier} from "../wallet/mocks/MockAccountVerifier.sol";
import {MockOperationContext} from "../wallet/mocks/MockOperationContext.sol";
import {MockAISRegistry, MockStakeVault} from "../wallet/mocks/MockTrustLayer.sol";
import {IntegrityHook, IAgentRegistryView, IAISRegistryView, IStakeVaultView} from "../../src/wallet/IntegrityHook.sol";
import {IOperationContext} from "../../src/wallet/IOperationContext.sol";
import {IAccountVerifier} from "../../src/wallet/IAccountVerifier.sol";

contract GateAllowModule is IPolicyModule {
    uint16 public immutable weight;

    constructor(uint16 weight_) {
        weight = weight_;
    }

    function checkCompliance(address, bytes32, address, bytes calldata) external view returns (bool, uint16) {
        return (true, weight);
    }
}

contract GateTarget {
    uint256 public pings;

    function ping() external payable {
        pings++;
    }

    function other() external payable {}
}

/// @dev Shared v3 wiring for the gate suites: a `DomainRegistry` + `AgentRegistry` pair with one
/// oracle attester, and a helper that binds a mock governed account as the actor of a fresh record.
abstract contract GateRegistryFixture is Test {
    DomainRegistry internal domainRegistry;
    AgentRegistry internal agentRegistry;
    MockAccountVerifier internal verifier;
    IntegrityHook internal hook;
    MockOperationContext internal ctx;
    MockAISRegistry internal aisMock;
    MockStakeVault internal vaultMock;

    uint256 internal constant ATTESTER_PK = 0xA77E57;
    uint256 private _nonce;

    function _deployRegistry(address gov) internal {
        domainRegistry = new DomainRegistry(gov);
        agentRegistry = new AgentRegistry(gov, address(domainRegistry));

        ctx = new MockOperationContext();
        verifier = new MockAccountVerifier();
        aisMock = new MockAISRegistry();
        vaultMock = new MockStakeVault();

        hook = new IntegrityHook(
            gov,
            IAgentRegistryView(address(agentRegistry)),
            IAISRegistryView(address(aisMock)),
            IStakeVaultView(address(vaultMock)),
            IOperationContext(address(ctx)),
            0,
            1 days
        );

        vm.startPrank(gov);
        domainRegistry.grantRole(domainRegistry.REGISTRAR_ROLE(), address(agentRegistry));
        agentRegistry.addAttester(vm.addr(ATTESTER_PK));
        agentRegistry.setIntegrityHook(address(hook));
        agentRegistry.setAccountVerifier(IAccountVerifier(address(verifier)));
        vm.stopPrank();
    }

    /// @dev Registers `name` (Open) if absent; returns `keccak256(name)`, the id the gate resolves.
    function _ensureDomain(string memory name) internal returns (bytes32 id) {
        id = domainRegistry.domainId(name);
        (,, bool exists,) = domainRegistry.domains(id);
        if (!exists) domainRegistry.registerDomain(name, DomainRegistry.JoinMode.Open);
    }

    /// @dev For suites that only need SOME bound actor (not the gate): wires a fresh TrustConfig +
    /// PolicyRegistry (owned by `gov`) giving `name` a placeholder graph root, so binding into it is
    /// allowed. Returns the domain id.
    function _wireBindableDomain(address gov, string memory name) internal returns (bytes32 id) {
        id = _ensureDomain(name);
        TrustConfig cfg = new TrustConfig(gov);
        PolicyRegistry policy = new PolicyRegistry(gov);
        vm.startPrank(gov);
        policy.setGraphRoot(id, keccak256("placeholder-pack-root"));
        cfg.setPolicyRegistry(address(policy));
        agentRegistry.setTrustConfig(address(cfg));
        vm.stopPrank();
    }

    /// @dev A fresh canonical agent bound into `domainId`; its controller key is derived from `label`.
    function _boundAgent(string memory label, bytes32 domainId) internal returns (address) {
        (address ctl, uint256 pk) = makeAddrAndKey(label);
        MockGovernedAccount sa = _newAgent(string.concat("did:integrity:", label), ctl);
        _bind(address(sa), pk, domainId, ctl);
        return address(sa);
    }

    /// @dev A governed account for this registry.
    function _newAgent(string memory /*did*/, address controller) internal returns (MockGovernedAccount) {
        MockGovernedAccount a = new MockGovernedAccount();
        verifier.setAccount(address(a), true, controller);
        a.installModule(4, address(hook), abi.encode(uint32(1 days), uint32(0)));
        a.setSigner1271(controller);
        return a;
    }

    /// @dev Creates a record with a fresh (test-only) pubkey and binds `agent` as its actor in
    /// `domainId`. `controllerPk` signs the actor's EIP-1271 consent.
    function _bind(address agent, uint256 controllerPk, bytes32 domainId, address guardian)
        internal
        returns (bytes32 fingerprint)
    {
        bytes32 pubkey = keccak256(abi.encode("gate-fixture-pubkey", agent, ++_nonce));
        uint256 deadline = block.timestamp + 1 hours;
        // Signatures precomputed: view calls would otherwise consume an armed prank/expectRevert.
        bytes memory proof;
        {
            bytes32 digest = agentRegistry.registerDigest(pubkey, guardian, agent, domainId, "", deadline);
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(ATTESTER_PK, digest);
            proof = abi.encodePacked(r, s, v);
        }
        bytes memory consent;
        {
            bytes32 fp = sha256(abi.encodePacked(pubkey));
            bytes32 digest = agentRegistry.bindActorDigest(fp, agent, deadline);
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(controllerPk, digest);
            consent = abi.encodePacked(r, s, v);
        }
        fingerprint =
            agentRegistry.register(pubkey, guardian, agent, domainId, "", deadline, 1, proof, consent);
    }

    function _bind(MockGovernedAccount agent, uint256 controllerPk, bytes32 domainId, address guardian)
        internal
        returns (bytes32 fingerprint)
    {
        return _bind(address(agent), controllerPk, domainId, guardian);
    }
}
