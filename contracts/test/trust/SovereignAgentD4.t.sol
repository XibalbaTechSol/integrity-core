// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {SovereignAgent} from "../../src/core/SovereignAgent.sol";
import {ConstraintExecutionPolicy} from "../../src/core/ConstraintExecutionPolicy.sol";
import {AISRegistry} from "../../src/trust/AISRegistry.sol";
import {StakeVault} from "../../src/trust/StakeVault.sol";
import {ITK} from "../../src/trust/ITK.sol";
import {GateRegistryFixture} from "./GateRegistryFixture.sol";

contract Sink {
    uint256 public hits;

    receive() external payable {
        hits += 1;
    }
}

/// @notice v2 deletion slice D4: `SovereignAgent` drops its oracle-pushed AIS cache, renames its
/// registry pin `factory` -> `registry`, and `ConstraintExecutionPolicy` reads the AIS floor from
/// `AISRegistry.latest(agent).score` (basis points).
contract SovereignAgentD4Test is GateRegistryFixture {
    address admin = makeAddr("admin");
    address scorer = makeAddr("scorer");
    AISRegistry ais;
    bytes32 domainId;

    function setUp() public {
        _deployRegistry(admin);
        domainId = _wireBindableDomain(admin, "d4.integrity");
        // Real checkpoint path, AgentRegistry unset so plain (unbound) agents can be scored.
        vm.startPrank(admin);
        ais = new AISRegistry(admin);
        ITK itk = new ITK(admin, 0);
        StakeVault vault = new StakeVault(address(itk), admin);
        vault.grantRole(vault.AIS_REGISTRY_ROLE(), address(ais));
        ais.grantRole(ais.SCORER_ROLE(), scorer);
        ais.setStakeVault(address(vault));
        vm.stopPrank();
    }

    function _score(address agent, uint32 bps) internal {
        vm.prank(scorer);
        ais.postCheckpoint(agent, bps, uint64(block.timestamp), keccak256("evidence"), 0);
    }

    function _policy(uint256 minAis) internal returns (ConstraintExecutionPolicy p) {
        p = new ConstraintExecutionPolicy(admin, minAis, 0, false);
        vm.prank(admin);
        p.setAisRegistry(address(ais));
    }

    // ── ConstraintExecutionPolicy AIS floor ─────────────────────────────────

    /// MUTATION: replace the checkpoint read with a constant `score = 10000` -> 4999 passes, FAILS.
    function test_floor_denies_4999_allows_5000() public {
        ConstraintExecutionPolicy p = _policy(5000);
        address low = makeAddr("low");
        address ok = makeAddr("ok");
        _score(low, 4999);
        _score(ok, 5000);
        assertFalse(p.check(low, address(1), 0, ""), "4999 bps is below the 5000 floor");
        assertTrue(p.check(ok, address(1), 0, ""), "5000 bps meets the floor");
        assertFalse(p.check(makeAddr("never-scored"), address(1), 0, ""), "no checkpoint = 0 bps");
    }

    /// The floor gates `SovereignAgent.execute` end to end, and a later checkpoint lifts it.
    function test_floor_gates_execute_through_agent() public {
        (address ctl,) = makeAddrAndKey("exec");
        SovereignAgent sa = new SovereignAgent("did:integrity:exec", ctl, address(0), address(0));
        Sink sink = new Sink();
        ConstraintExecutionPolicy p = _policy(5000);
        vm.prank(ctl);
        sa.setExecutionPolicy(address(p));

        _score(address(sa), 4999);
        vm.prank(ctl);
        vm.expectRevert(SovereignAgent.PolicyDenied.selector);
        sa.execute(address(sink), 0, "");

        _score(address(sa), 5000);
        vm.prank(ctl);
        sa.execute(address(sink), 0, "");
        assertEq(sink.hits(), 1);
    }

    /// `minAis == 0` never touches the registry (genesis deploys it unset-then-wired).
    function test_zero_floor_needs_no_registry() public {
        ConstraintExecutionPolicy p = new ConstraintExecutionPolicy(admin, 0, 0, false);
        assertTrue(p.check(makeAddr("any"), address(1), 0, ""));
    }

    /// MUTATION: drop the `aisRegistry == 0` guard -> the call to address(0) reverts, test FAILS.
    function test_positive_floor_without_registry_fails_closed() public {
        ConstraintExecutionPolicy p = new ConstraintExecutionPolicy(admin, 1, 0, false);
        assertFalse(p.check(makeAddr("any"), address(1), 0, ""));
    }

    function test_registry_pin_must_be_contract_and_admin_only() public {
        ConstraintExecutionPolicy p = new ConstraintExecutionPolicy(admin, 1, 0, false);
        address eoa = makeAddr("eoa");
        vm.prank(admin);
        vm.expectRevert(abi.encodeWithSelector(ConstraintExecutionPolicy.NotAContract.selector, eoa));
        p.setAisRegistry(eoa);
        vm.prank(makeAddr("stranger"));
        vm.expectRevert();
        p.setAisRegistry(address(ais));
    }

    // ── SovereignAgent surface + codehash pin ───────────────────────────────

    function test_canonical_agent_binds_and_exposes_registry() public {
        address agent = _boundAgent("canon", domainId);
        assertEq(SovereignAgent(payable(agent)).registry(), address(agentRegistry));
        assertEq(agent.codehash, agentRegistry.agentCodehash());
        assertTrue(agentRegistry.isRegisteredAgent(agent));
    }

    /// The removed selectors are gone from the runtime: `ais()` and `updateAIS(uint256)` revert.
    function test_score_cache_selectors_removed() public {
        SovereignAgent sa = _newAgent("did:integrity:sel", makeAddr("ctl"));
        (bool okAis,) = address(sa).staticcall(abi.encodeWithSignature("ais()"));
        (bool okUpd,) = address(sa).call(abi.encodeWithSignature("updateAIS(uint256)", 1));
        (bool okFac,) = address(sa).staticcall(abi.encodeWithSignature("factory()"));
        assertFalse(okAis);
        assertFalse(okUpd);
        assertFalse(okFac);
    }

    /// Why D4 precedes the Base Sepolia broadcast: a registry pins the SovereignAgent runtime
    /// codehash at construction, so an agent whose code differs by ONE byte (here: a byte in the
    /// metadata tail, which any comment edit also changes) can never be bound to it.
    /// MUTATION: make `isGatedAccount` ignore the codehash compare -> binding succeeds, FAILS.
    function test_registry_rejects_agent_with_one_byte_different_code() public {
        (address ctl, uint256 pk) = makeAddrAndKey("edited");
        SovereignAgent canon = _newAgent("did:integrity:edited", ctl);
        bytes memory code = address(canon).code;
        code[code.length - 10] = bytes1(uint8(code[code.length - 10]) ^ 0x01);
        address edited = makeAddr("edited-agent");
        vm.etch(edited, code);
        assertTrue(edited.codehash != agentRegistry.agentCodehash());

        // Sign first: the digest view calls would otherwise consume the armed expectRevert.
        bytes32 pubkey = keccak256("d4-edited-pubkey");
        uint256 deadline = block.timestamp + 1 hours;
        bytes memory proof;
        {
            bytes32 d = agentRegistry.registerDigest(pubkey, ctl, edited, domainId, "", deadline);
            (uint8 v, bytes32 r, bytes32 s_) = vm.sign(ATTESTER_PK, d);
            proof = abi.encodePacked(r, s_, v);
        }
        bytes memory consent;
        {
            bytes32 d = agentRegistry.bindActorDigest(sha256(abi.encodePacked(pubkey)), edited, deadline);
            (uint8 v, bytes32 r, bytes32 s_) = vm.sign(pk, d);
            consent = abi.encodePacked(r, s_, v);
        }
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.NotGatedAccount.selector, edited));
        agentRegistry.register(pubkey, ctl, edited, domainId, "", deadline, 1, proof, consent);

        // Control: the unedited agent binds under the same key and domain.
        _bind(canon, pk, domainId, ctl);
        assertTrue(agentRegistry.isRegisteredAgent(address(canon)));
    }
}
