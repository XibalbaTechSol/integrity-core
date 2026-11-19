// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {AgentRegistry} from "../../src/framework/AgentRegistry.sol";
import {DomainRegistry} from "../../src/framework/DomainRegistry.sol";
import {MockGovernedAccount} from "../wallet/mocks/MockGovernedAccount.sol";
import {IOperationContext} from "../../src/wallet/IOperationContext.sol";
import {AgentRegistryBase, MockEd25519Verifier} from "./AgentRegistryBase.sol";

/// Spec acceptance (docs/superpowers/specs/2026-11-14-agent-registration-v3-design.md, Phase 2),
/// one test per clause, plus the reads and guardian surface.
contract AgentRegistryTest is AgentRegistryBase {
    // ── existence + fingerprint ──────────────────────────────────────────────

    function test_existence_record_keyed_by_offchain_did_fingerprint() public {
        bytes32 fp = _registerExistence();
        assertEq(fp, FINGERPRINT, "on-chain sha256(pubkey) == off-chain DID suffix");
        assertEq(registry.fingerprintOfDID(DID), FINGERPRINT);
        AgentRegistry.AgentRecord memory r = registry.resolveDID(DID);
        assertEq(r.pubkey, PUBKEY);
        assertEq(r.guardian, guardian);
        assertEq(r.actor, address(0));
        assertEq(r.proofKind, 1);
        assertEq(r.registeredAt, block.timestamp);
    }

    function test_resolveDID_rejects_malformed() public {
        vm.expectRevert(AgentRegistry.InvalidDid.selector);
        registry.fingerprintOfDID("did:integrity:FE812C12f3ab4ce6ac5db69ac352f906cb1b11ef43fb33e252ef7ff552263889");
        vm.expectRevert(AgentRegistry.InvalidDid.selector);
        registry.fingerprintOfDID("did:other:fe812c12f3ab4ce6ac5db69ac352f906cb1b11ef43fb33e252ef7ff552263889");
    }

    // ── acceptance: squatting, second write, attester power ──────────────────

    function test_squatting_copied_pubkey_without_valid_proof_reverts() public {
        uint256 dl = block.timestamp + 1 hours;
        address squatter = makeAddr("squatter");
        (uint8 v, bytes32 r, bytes32 s) =
            vm.sign(0xBAD, registry.registerDigest(PUBKEY, squatter, address(0), bytes32(0), "", dl));
        vm.expectRevert(AgentRegistry.InvalidProof.selector);
        registry.register(PUBKEY, squatter, address(0), bytes32(0), "", dl, 1, abi.encodePacked(r, s, v), "");

        // A genuine attestation for a different guardian cannot be replayed for the squatter.
        bytes memory forGuardian = _attest(PUBKEY, guardian, address(0), bytes32(0), "", dl);
        vm.expectRevert(AgentRegistry.InvalidProof.selector);
        registry.register(PUBKEY, squatter, address(0), bytes32(0), "", dl, 1, forGuardian, "");

        vm.expectRevert(AgentRegistry.InvalidProof.selector);
        registry.register(PUBKEY, squatter, address(0), bytes32(0), "", dl, 1, hex"", "");
    }

    function test_second_write_of_a_fingerprint_reverts() public {
        _registerExistence();
        uint256 dl = block.timestamp + 1 hours;
        address other = makeAddr("other");
        bytes memory proof = _attest(PUBKEY, other, address(0), bytes32(0), "", dl);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.AlreadyRegistered.selector, FINGERPRINT));
        registry.register(PUBKEY, other, address(0), bytes32(0), "", dl, 1, proof, "");
    }

    function test_attester_cannot_modify_an_existing_record() public {
        _registerExistence();
        vm.startPrank(attester);
        vm.expectRevert(AgentRegistry.NotGuardian.selector);
        registry.setUri(FINGERPRINT, "evil");
        vm.expectRevert(AgentRegistry.NotGuardian.selector);
        registry.proposeGuardian(FINGERPRINT, attester);
        vm.expectRevert(AgentRegistry.NotGuardian.selector);
        registry.retire(FINGERPRINT);
        vm.expectRevert(AgentRegistry.NotGuardian.selector);
        registry.setDomain(FINGERPRINT, domainId);
        vm.expectRevert(AgentRegistry.NotGuardian.selector);
        registry.clearActor(FINGERPRINT);
        vm.stopPrank();
        // Nor by re-attesting: first write wins.
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, attester, address(0), bytes32(0), "", dl);
        vm.prank(attester);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.AlreadyRegistered.selector, FINGERPRINT));
        registry.register(PUBKEY, attester, address(0), bytes32(0), "", dl, 1, proof, "");
        assertEq(registry.resolve(FINGERPRINT).guardian, guardian);
    }

    function test_removed_attester_proof_reverts() public {
        vm.prank(admin);
        registry.removeAttester(attester);
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(0), bytes32(0), "", dl);
        vm.expectRevert(AgentRegistry.InvalidProof.selector);
        registry.register(PUBKEY, guardian, address(0), bytes32(0), "", dl, 1, proof, "");
    }

    function test_expired_deadline_reverts() public {
        uint256 dl = block.timestamp - 1;
        bytes memory proof = _attest(PUBKEY, guardian, address(0), bytes32(0), "", dl);
        vm.expectRevert(AgentRegistry.DeadlineExpired.selector);
        registry.register(PUBKEY, guardian, address(0), bytes32(0), "", dl, 1, proof, "");
    }

    // ── acceptance: kind 2 door ──────────────────────────────────────────────

    function test_kind2_reverts_while_no_verifier_is_set() public {
        uint256 dl = block.timestamp + 1 hours;
        vm.expectRevert(AgentRegistry.ProofKindDisabled.selector);
        registry.register(PUBKEY, guardian, address(0), bytes32(0), "", dl, 2, new bytes(64), "");
    }

    function test_kind2_succeeds_with_a_mock_verifier() public {
        MockEd25519Verifier v = new MockEd25519Verifier();
        vm.prank(admin);
        registry.setEd25519Verifier(address(v));
        uint256 dl = block.timestamp + 1 hours;
        bytes memory sig = abi.encodePacked(keccak256("r"), keccak256("s"));
        bytes32 digest = registry.registerDigest(PUBKEY, guardian, address(0), bytes32(0), "", dl);

        vm.expectRevert(AgentRegistry.InvalidProof.selector);
        registry.register(PUBKEY, guardian, address(0), bytes32(0), "", dl, 2, sig, "");

        v.allow(PUBKEY, digest, sig);
        registry.register(PUBKEY, guardian, address(0), bytes32(0), "", dl, 2, sig, "");
        assertEq(registry.resolve(FINGERPRINT).proofKind, 2);
    }

    function test_unknown_proof_kind_reverts() public {
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.UnknownProofKind.selector, uint8(3)));
        registry.register(PUBKEY, guardian, address(0), bytes32(0), "", block.timestamp + 1, 3, "", "");
    }

    // ── acceptance: actor binding ────────────────────────────────────────────

    function test_confined_record_binds_actor_and_joins_domain() public {
        MockGovernedAccount a = _newActor();
        _registerConfined(address(a));
        assertTrue(registry.isRegisteredAgent(address(a)));
        assertEq(registry.agentOf(address(a)), FINGERPRINT);
        assertEq(registry.resolveAgent(address(a)).domainId, domainId);
        assertTrue(domains.isMember(domainId, address(a)));
    }

    function test_actor_consent_by_msg_sender_through_execute() public {
        MockGovernedAccount a = _newActor();
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(a), domainId, "", dl);
        bytes memory call = abi.encodeCall(
            AgentRegistry.register, (PUBKEY, guardian, address(a), domainId, "", dl, uint8(1), proof, bytes(""))
        );
        ctx.setRole(address(a), IOperationContext.Role.Owner);
        bytes memory singleCall = abi.encodePacked(address(registry), uint256(0), call);
        a.execute(bytes32(0), singleCall);
        assertTrue(registry.isRegisteredAgent(address(a)));
    }

    function test_binding_actor_without_consent_reverts() public {
        MockGovernedAccount a = _newActor();
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(a), domainId, "", dl);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.ActorConsentMissing.selector, address(a)));
        registry.register(PUBKEY, guardian, address(a), domainId, "", dl, 1, proof, "");

        // A signature from someone other than the actor's controller is not consent.
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(0xBAD, registry.bindActorDigest(FINGERPRINT, address(a), dl));
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.ActorConsentMissing.selector, address(a)));
        registry.register(PUBKEY, guardian, address(a), domainId, "", dl, 1, proof, abi.encodePacked(r, s, v));
    }

    function test_binding_an_eoa_as_actor_reverts() public {
        address eoa = makeAddr("wallet");
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, eoa, domainId, "", dl);
        vm.prank(eoa); // even with msg.sender consent
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.NotGoverned.selector, eoa));
        registry.register(PUBKEY, guardian, eoa, domainId, "", dl, 1, proof, "");
    }

    function test_binding_a_non_canonical_contract_as_actor_reverts() public {
        // An arbitrary contract without hook or verification.
        address junk = address(new MockEd25519Verifier());
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, junk, domainId, "", dl);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.NotGoverned.selector, junk));
        registry.register(PUBKEY, guardian, junk, domainId, "", dl, 1, proof, "");
    }

    function test_binding_actor_with_no_domain_succeeds() public {
        MockGovernedAccount a = _newActor();
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(a), bytes32(0), "", dl);
        bytes memory c = _consent(FINGERPRINT, address(a), dl);
        registry.register(PUBKEY, guardian, address(a), bytes32(0), "", dl, 1, proof, c);
        assertTrue(registry.isRegisteredAgent(address(a)));
        assertEq(registry.resolveAgent(address(a)).domainId, bytes32(0));
    }

    function test_binding_actor_in_a_domain_with_no_policy_succeeds() public {
        MockGovernedAccount a = _newActor();
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(a), bareDomainId, "", dl);
        bytes memory consent = _consent(FINGERPRINT, address(a), dl);
        registry.register(PUBKEY, guardian, address(a), bareDomainId, "", dl, 1, proof, consent);
        assertTrue(registry.isRegisteredAgent(address(a)));
        assertEq(registry.resolveAgent(address(a)).domainId, bareDomainId);
    }

    function test_actor_cannot_be_bound_to_two_agents() public {
        MockGovernedAccount a = _newActor();
        _registerConfined(address(a));

        bytes32 pk2 = keccak256("second agent key");
        bytes32 fp2 = sha256(abi.encodePacked(pk2));
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(pk2, guardian, address(a), domainId, "", dl);
        bytes memory consent2 = _consent(fp2, address(a), dl);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.ActorAlreadyBound.selector, address(a)));
        registry.register(pk2, guardian, address(a), domainId, "", dl, 1, proof, consent2);

        // Still not after the first agent clears it: an actor serves one identity for life.
        vm.prank(guardian);
        registry.clearActor(FINGERPRINT);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.ActorAlreadyBound.selector, address(a)));
        registry.register(pk2, guardian, address(a), domainId, "", dl, 1, proof, consent2);
    }

    function test_domain_join_not_allowed_reverts() public {
        vm.prank(admin);
        bytes32 closed = domains.registerDomain("closed", DomainRegistry.JoinMode.Permissioned);
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(0), closed, "", dl);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.DomainJoinNotAllowed.selector, closed));
        registry.register(PUBKEY, guardian, address(0), closed, "", dl, 1, proof, "");
    }

    // ── guardian surface ─────────────────────────────────────────────────────

    function test_guardian_transfer_is_two_step() public {
        _registerExistence();
        address next = makeAddr("next");
        vm.prank(guardian);
        registry.proposeGuardian(FINGERPRINT, next);
        assertEq(registry.resolve(FINGERPRINT).guardian, guardian, "proposal alone changes nothing");

        vm.prank(makeAddr("stranger"));
        vm.expectRevert(AgentRegistry.NotPendingGuardian.selector);
        registry.acceptGuardian(FINGERPRINT);

        vm.prank(next);
        registry.acceptGuardian(FINGERPRINT);
        assertEq(registry.resolve(FINGERPRINT).guardian, next);
        assertEq(registry.pendingGuardian(FINGERPRINT), address(0));

        vm.prank(guardian);
        vm.expectRevert(AgentRegistry.NotGuardian.selector);
        registry.setUri(FINGERPRINT, "old guardian");
    }

    function test_retire_is_irreversible() public {
        MockGovernedAccount a = _newActor();
        _registerConfined(address(a));
        vm.prank(guardian);
        registry.retire(FINGERPRINT);
        assertFalse(registry.isRegisteredAgent(address(a)));
        AgentRegistry.AgentRecord memory r = registry.resolve(FINGERPRINT);
        assertGt(r.retiredAt, 0);
        assertEq(r.actor, address(a), "binding kept, marked inactive");

        vm.startPrank(guardian);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.Retired.selector, FINGERPRINT));
        registry.retire(FINGERPRINT);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.Retired.selector, FINGERPRINT));
        registry.clearActor(FINGERPRINT);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.Retired.selector, FINGERPRINT));
        registry.setDomain(FINGERPRINT, domainId);
        vm.stopPrank();

        // And the fingerprint can never be registered again.
        uint256 dl = block.timestamp + 1 hours;
        bytes memory proof = _attest(PUBKEY, guardian, address(0), bytes32(0), "", dl);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.AlreadyRegistered.selector, FINGERPRINT));
        registry.register(PUBKEY, guardian, address(0), bytes32(0), "", dl, 1, proof, "");
    }

    function test_retire_cancels_pending_guardian() public {
        _registerExistence();
        address next = makeAddr("next");
        vm.startPrank(guardian);
        registry.proposeGuardian(FINGERPRINT, next);
        registry.retire(FINGERPRINT);
        vm.stopPrank();
        vm.prank(next);
        vm.expectRevert(abi.encodeWithSelector(AgentRegistry.Retired.selector, FINGERPRINT));
        registry.acceptGuardian(FINGERPRINT);
    }

    function test_guardian_binds_actor_later_with_eip1271_consent() public {
        _registerExistence();
        MockGovernedAccount a = _newActor();
        uint256 dl = block.timestamp + 1 hours;
        bytes memory c = _consent(FINGERPRINT, address(a), dl);
        vm.startPrank(guardian);
        registry.setActor(FINGERPRINT, address(a), dl, c);
        vm.stopPrank();
        assertTrue(registry.isRegisteredAgent(address(a)));
    }

    function test_setDomain_with_actor_allows_bare_domain_and_zero() public {
        MockGovernedAccount a = _newActor();
        _registerConfined(address(a));
        vm.startPrank(guardian);
        registry.setDomain(FINGERPRINT, bareDomainId);
        assertEq(registry.resolve(FINGERPRINT).domainId, bareDomainId);
        registry.setDomain(FINGERPRINT, bytes32(0));
        assertEq(registry.resolve(FINGERPRINT).domainId, bytes32(0));
        vm.stopPrank();
    }

    function test_clear_then_rebind_same_actor_is_allowed() public {
        MockGovernedAccount a = _newActor();
        _registerConfined(address(a));
        uint256 dl = block.timestamp + 1 hours;
        bytes memory c = _consent(FINGERPRINT, address(a), dl);
        vm.startPrank(guardian);
        registry.clearActor(FINGERPRINT);
        assertFalse(registry.isRegisteredAgent(address(a)));
        registry.setActor(FINGERPRINT, address(a), dl, c);
        vm.stopPrank();
        assertTrue(registry.isRegisteredAgent(address(a)));
    }

    function test_setUri_by_guardian() public {
        _registerExistence();
        vm.prank(guardian);
        registry.setUri(FINGERPRINT, "ipfs://new");
        assertEq(registry.resolve(FINGERPRINT).uri, "ipfs://new");
    }

    function test_governance_setters_are_admin_only() public {
        vm.startPrank(attester);
        vm.expectRevert();
        registry.setEd25519Verifier(address(1));
        vm.expectRevert();
        registry.addAttester(attester);
        vm.expectRevert();
        registry.setTrustConfig(address(1));
        vm.stopPrank();
    }

    function test_mock_governed_account_eip1271() public {
        MockGovernedAccount a = _newActor();
        bytes32 h = keccak256("msg");
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(controllerPk, h);
        assertEq(a.isValidSignature(h, abi.encodePacked(r, s, v)), bytes4(0x1626ba7e));
        (v, r, s) = vm.sign(0xBAD, h);
        assertEq(a.isValidSignature(h, abi.encodePacked(r, s, v)), bytes4(0xffffffff));
        assertEq(a.isValidSignature(h, hex"00"), bytes4(0xffffffff));
    }
}
