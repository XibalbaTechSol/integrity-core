// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {DomainRegistry} from "../../src/framework/DomainRegistry.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";

/// @dev Shared v3 wiring for the gate suites: a `DomainRegistry` + `AgentRegistry` pair with one
/// oracle attester, and a helper that binds a `SovereignAgent` as the actor of a fresh record the
/// way production does (attester proof kind 1 + the actor's EIP-1271 consent via its controller).
abstract contract GateRegistryFixture is Test {
    DomainRegistry internal domainRegistry;
    AgentRegistry internal agentRegistry;

    uint256 internal constant ATTESTER_PK = 0xA77E57;
    uint256 private _nonce;

    function _deployRegistry(address gov) internal {
        domainRegistry = new DomainRegistry(gov);
        agentRegistry = new AgentRegistry(gov, address(domainRegistry));
        vm.startPrank(gov);
        domainRegistry.grantRole(domainRegistry.REGISTRAR_ROLE(), address(agentRegistry));
        agentRegistry.addAttester(vm.addr(ATTESTER_PK));
        vm.stopPrank();
    }

    /// @dev Registers `name` (Open) if absent; returns `keccak256(name)`, the id the gate resolves.
    function _ensureDomain(string memory name) internal returns (bytes32 id) {
        id = domainRegistry.domainId(name);
        (,, bool exists,) = domainRegistry.domains(id);
        if (!exists) domainRegistry.registerDomain(name, DomainRegistry.JoinMode.Open);
    }

    /// @dev A canonical agent for this registry: `factory` == the registry, so the codehash pin holds.
    function _newAgent(string memory did, address controller) internal returns (SovereignAgent) {
        return new SovereignAgent(did, controller, address(0), address(agentRegistry));
    }

    /// @dev Creates a record with a fresh (test-only) pubkey and binds `agent` as its actor in
    /// `domainId`. `controllerPk` signs the actor's EIP-1271 consent.
    function _bind(SovereignAgent agent, uint256 controllerPk, bytes32 domainId, address guardian)
        internal
        returns (bytes32 fingerprint)
    {
        bytes32 pubkey = keccak256(abi.encode("gate-fixture-pubkey", address(agent), ++_nonce));
        uint256 deadline = block.timestamp + 1 hours;
        // Signatures precomputed: view calls would otherwise consume an armed prank/expectRevert.
        bytes memory proof;
        {
            bytes32 digest = agentRegistry.registerDigest(pubkey, guardian, address(agent), domainId, "", deadline);
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(ATTESTER_PK, digest);
            proof = abi.encodePacked(r, s, v);
        }
        bytes memory consent;
        {
            bytes32 fp = sha256(abi.encodePacked(pubkey));
            bytes32 digest = agentRegistry.bindActorDigest(fp, address(agent), deadline);
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(controllerPk, digest);
            consent = abi.encodePacked(r, s, v);
        }
        fingerprint =
            agentRegistry.register(pubkey, guardian, address(agent), domainId, "", deadline, 1, proof, consent);
    }
}
