// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {AgentRegistryBase} from "./AgentRegistryBase.sol";
import {MockGovernedAccount} from "../wallet/mocks/MockGovernedAccount.sol";

/// Drives every write path with a small pool of keys, actors and guardians, recording ghost state
/// the invariants compare against.
contract AgentRegistryHandler is Test {
    AgentRegistry internal registry;
    bytes32 internal domainId;
    uint256 internal attesterPk;
    uint256 internal controllerPk;

    bytes32[] public pubkeys;
    address[] public actors;
    address[] public guardians;

    mapping(bytes32 => bytes32) public ghostPubkey; // fp -> pubkey at first write
    mapping(bytes32 => uint64) public ghostRegisteredAt;
    mapping(bytes32 => bool) public ghostRetired;
    mapping(address => bytes32) public ghostClaimedBy;

    constructor(AgentRegistry r, bytes32 dom, uint256 attPk, uint256 ctlPk, address[] memory acts) {
        registry = r;
        domainId = dom;
        attesterPk = attPk;
        controllerPk = ctlPk;
        actors = acts;
        for (uint256 i = 0; i < 4; i++) {
            pubkeys.push(keccak256(abi.encode("key", i)));
            guardians.push(makeAddr(string(abi.encode("g", i))));
        }
    }

    function fpCount() external view returns (uint256) {
        return pubkeys.length;
    }

    function actorCount() external view returns (uint256) {
        return actors.length;
    }

    function fpAt(uint256 i) public view returns (bytes32) {
        return sha256(abi.encodePacked(pubkeys[i]));
    }

    function _sign(uint256 pk, bytes32 digest) internal pure returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    function register(uint256 k, uint256 g, uint256 a, bool withActor) external {
        bytes32 pk = pubkeys[k % pubkeys.length];
        address guardian = guardians[g % guardians.length];
        address actor = withActor ? actors[a % actors.length] : address(0);
        bytes32 dom = withActor ? domainId : bytes32(0);
        uint256 dl = block.timestamp + 1;
        bytes memory proof = _sign(attesterPk, registry.registerDigest(pk, guardian, actor, dom, "", dl));
        bytes32 fp = sha256(abi.encodePacked(pk));
        bytes memory consent = actor == address(0) ? bytes("") : _sign(controllerPk, registry.bindActorDigest(fp, actor, dl));
        try registry.register(pk, guardian, actor, dom, "", dl, 1, proof, consent) {
            ghostPubkey[fp] = pk;
            ghostRegisteredAt[fp] = uint64(block.timestamp);
            if (actor != address(0)) ghostClaimedBy[actor] = fp;
        } catch {}
    }

    function setActor(uint256 k, uint256 a) external {
        bytes32 fp = fpAt(k % pubkeys.length);
        address actor = actors[a % actors.length];
        uint256 dl = block.timestamp + 1;
        bytes memory consent = _sign(controllerPk, registry.bindActorDigest(fp, actor, dl));
        vm.prank(registry.resolve(fp).guardian);
        try registry.setActor(fp, actor, dl, consent) {
            if (ghostClaimedBy[actor] == bytes32(0)) ghostClaimedBy[actor] = fp;
        } catch {}
    }

    function setDomain(uint256 k, bool zero) external {
        bytes32 fp = fpAt(k % pubkeys.length);
        vm.prank(registry.resolve(fp).guardian);
        try registry.setDomain(fp, zero ? bytes32(0) : domainId) {} catch {}
    }

    function clearActor(uint256 k) external {
        bytes32 fp = fpAt(k % pubkeys.length);
        vm.prank(registry.resolve(fp).guardian);
        try registry.clearActor(fp) {} catch {}
    }

    function retire(uint256 k) external {
        bytes32 fp = fpAt(k % pubkeys.length);
        vm.prank(registry.resolve(fp).guardian);
        try registry.retire(fp) {
            ghostRetired[fp] = true;
        } catch {}
    }

    function transferGuardian(uint256 k, uint256 g) external {
        bytes32 fp = fpAt(k % pubkeys.length);
        address next = guardians[g % guardians.length];
        vm.prank(registry.resolve(fp).guardian);
        try registry.proposeGuardian(fp, next) {} catch {}
        vm.prank(next);
        try registry.acceptGuardian(fp) {} catch {}
    }

    function warp(uint32 dt) external {
        vm.warp(block.timestamp + (dt % 1 days));
    }
}

contract AgentRegistryInvariants is AgentRegistryBase {
    AgentRegistryHandler internal handler;
    address[] internal actorPool;

    function setUp() public override {
        super.setUp();
        for (uint256 i = 0; i < 4; i++) {
            address g = makeAddr(string(abi.encode("g", i)));
            MockGovernedAccount a = _newActor();
            verifier.setAccount(address(a), true, g);
            actorPool.push(address(a));
        }
        handler = new AgentRegistryHandler(registry, domainId, attesterPk, controllerPk, actorPool);
        targetContract(address(handler));
    }

    /// One actor <-> one agent: agentOf and records[fp].actor agree in both directions.
    function invariant_actor_binding_is_a_bijection() public view {
        for (uint256 i = 0; i < handler.actorCount(); i++) {
            address a = actorPool[i];
            bytes32 fp = registry.agentOf(a);
            if (fp != bytes32(0)) assertEq(registry.resolve(fp).actor, a);
        }
        for (uint256 i = 0; i < handler.fpCount(); i++) {
            bytes32 fp = handler.fpAt(i);
            address a = registry.resolve(fp).actor;
            if (a != address(0)) assertEq(registry.agentOf(a), fp);
        }
    }

    /// First write wins: pubkey and registeredAt never change after the first write.
    function invariant_records_are_never_overwritten() public view {
        for (uint256 i = 0; i < handler.fpCount(); i++) {
            bytes32 fp = handler.fpAt(i);
            AgentRegistry.AgentRecord memory r = registry.resolve(fp);
            assertEq(r.pubkey, handler.ghostPubkey(fp));
            assertEq(r.registeredAt, handler.ghostRegisteredAt(fp));
            if (r.registeredAt != 0) assertEq(sha256(abi.encodePacked(r.pubkey)), fp);
        }
    }

    /// Retirement is irreversible, and a retired record never reports an active agent.
    function invariant_retire_is_irreversible() public view {
        for (uint256 i = 0; i < handler.fpCount(); i++) {
            bytes32 fp = handler.fpAt(i);
            AgentRegistry.AgentRecord memory r = registry.resolve(fp);
            if (handler.ghostRetired(fp)) {
                assertGt(r.retiredAt, 0);
                if (r.actor != address(0)) assertFalse(registry.isRegisteredAgent(r.actor));
            }
        }
    }

    /// An actor only ever serves the fingerprint that first bound it.
    function invariant_actor_serves_one_identity_for_life() public view {
        for (uint256 i = 0; i < handler.actorCount(); i++) {
            address a = actorPool[i];
            assertEq(registry.actorClaimedBy(a), handler.ghostClaimedBy(a));
            bytes32 fp = registry.agentOf(a);
            if (fp != bytes32(0)) assertEq(fp, registry.actorClaimedBy(a));
        }
    }

    /// A bound actor sits in domainId or 0 (domain is optional in v3).
    function invariant_bound_actor_has_valid_domain() public view {
        for (uint256 i = 0; i < handler.fpCount(); i++) {
            AgentRegistry.AgentRecord memory r = registry.resolve(handler.fpAt(i));
            if (r.actor != address(0)) {
                assertTrue(r.domainId == domainId || r.domainId == bytes32(0));
            }
        }
    }
}
