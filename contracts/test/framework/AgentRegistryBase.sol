// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {IEd25519Verifier} from "../../src/framework/IEd25519Verifier.sol";
import {DomainRegistry} from "../../src/framework/DomainRegistry.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {TrustConfig} from "../../src/trust/TrustConfig.sol";
import {PolicyRegistry} from "../../src/trust/PolicyRegistry.sol";

/// @dev Accepts exactly one (pubkey, digest, signature) triple, so tests can prove the kind-2 door
/// works without an Ed25519 implementation on chain.
contract MockEd25519Verifier is IEd25519Verifier {
    mapping(bytes32 => bool) public ok;

    function allow(bytes32 pubkey, bytes32 digest, bytes calldata sig) external {
        ok[keccak256(abi.encode(pubkey, digest, sig))] = true;
    }

    function verify(bytes32 pubkey, bytes32 digest, bytes calldata sig) external view returns (bool) {
        return ok[keccak256(abi.encode(pubkey, digest, sig))];
    }
}

abstract contract AgentRegistryBase is Test {
    /// Phase 1 golden vector (integrity-sdk test_registration_offchain.py, seed 7). Never a real key.
    bytes32 internal constant PUBKEY = 0xea4a6c63e29c520abef5507b132ec5f9954776aebebe7b92421eea691446d22c;
    bytes32 internal constant FINGERPRINT = 0xfe812c12f3ab4ce6ac5db69ac352f906cb1b11ef43fb33e252ef7ff552263889;
    string internal constant DID = "did:integrity:fe812c12f3ab4ce6ac5db69ac352f906cb1b11ef43fb33e252ef7ff552263889";

    address internal admin = makeAddr("governance");
    uint256 internal attesterPk = 0xA77E57;
    address internal attester;
    uint256 internal controllerPk = 0xC0417;
    address internal controller;
    address internal guardian = makeAddr("guardian");

    AgentRegistry internal registry;
    DomainRegistry internal domains;
    TrustConfig internal cfg;
    PolicyRegistry internal policy;
    bytes32 internal domainId;
    bytes32 internal bareDomainId; // exists, no policy

    function setUp() public virtual {
        attester = vm.addr(attesterPk);
        controller = vm.addr(controllerPk);
        vm.warp(1_800_000_000);

        domains = new DomainRegistry(admin);
        registry = new AgentRegistry(admin, address(domains));
        cfg = new TrustConfig(admin);
        policy = new PolicyRegistry(admin);

        vm.startPrank(admin);
        domains.grantRole(domains.REGISTRAR_ROLE(), address(registry));
        cfg.setPolicyRegistry(address(policy));
        registry.setTrustConfig(address(cfg));
        registry.addAttester(attester);
        domainId = domains.registerDomain("health", DomainRegistry.JoinMode.Open);
        bareDomainId = domains.registerDomain("bare", DomainRegistry.JoinMode.Open);
        policy.setGraphRoot(domainId, keccak256("pack-root"));
        vm.stopPrank();
    }

    function _newActor() internal returns (SovereignAgent) {
        return new SovereignAgent(DID, controller, address(0), address(registry));
    }

    function _attest(bytes32 pubkey, address g, address actor, bytes32 dom, string memory uri, uint256 deadline)
        internal
        view
        returns (bytes memory)
    {
        bytes32 digest = registry.registerDigest(pubkey, g, actor, dom, uri, deadline);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(attesterPk, digest);
        return abi.encodePacked(r, s, v);
    }

    function _consent(bytes32 fp, address actor, uint256 deadline) internal view returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(controllerPk, registry.bindActorDigest(fp, actor, deadline));
        return abi.encodePacked(r, s, v);
    }

    function _registerExistence() internal returns (bytes32) {
        uint256 dl = block.timestamp + 1 hours;
        return registry.register(
            PUBKEY, guardian, address(0), bytes32(0), "", dl, 1, _attest(PUBKEY, guardian, address(0), bytes32(0), "", dl), ""
        );
    }

    function _registerConfined(address actor) internal returns (bytes32) {
        uint256 dl = block.timestamp + 1 hours;
        return registry.register(
            PUBKEY,
            guardian,
            actor,
            domainId,
            "ipfs://doc",
            dl,
            1,
            _attest(PUBKEY, guardian, actor, domainId, "ipfs://doc", dl),
            _consent(FINGERPRINT, actor, dl)
        );
    }
}
