"""SDK core: decision receipts (contract C4) -- create, sign, chain, checkpoint, verify offline."""

from __future__ import annotations

import copy

import pytest

from integrity_sdk.core import decision as d
from integrity_sdk.core import receipts as r
from integrity_sdk.core.merkle import verify_leaf
from integrity_sdk.did import Keypair, public_key_multibase

HMAC_KEY = bytes(range(32))  # the organization's identifier key, never inside a receipt
AGENT_DID = "did:integrity:" + "ab" * 32
PACK_HASH = "sha256:" + "cd" * 32


@pytest.fixture
def gate_key():
    return Keypair.generate()


@pytest.fixture
def trusted(gate_key):
    return [public_key_multibase(gate_key.public_bytes())]


def _append(log, n, *, decision=d.DENY, reason="NO_BAA"):
    for i in range(n):
        log.append(
            agent_did=AGENT_DID,
            device_id_hmac=r.hmac_identifier(HMAC_KEY, "device", "laptop-17"),
            action_hmac=r.hmac_identifier(HMAC_KEY, "action", f"Bash:cat /records/{i}.json"),
            event_class="agent.tool_call",
            pack_hash=PACK_HASH,
            decision=decision,
            reason_code=reason,
            mode=d.ENFORCE,
            controls=["HIPAA-164.502(b)"],
            timestamp="2026-09-28T01:00:00Z",
        )
    return log


@pytest.fixture
def log(gate_key):
    return _append(r.ReceiptLog(gate_key, "shield:device-17"), 5)


def _code(excinfo):
    return excinfo.value.code


# ------------------------------------------------------------------------------- happy path ---


def test_a_receipt_is_created_signed_and_verified_locally_without_any_anchor(log, trusted):
    receipt = log.receipts[0]
    r.verify_receipt(receipt, trusted_signers=trusted)
    assert receipt["seq"] == 0 and receipt["prev_hash"] == r.GENESIS_PREV_HASH
    assert receipt["checkpoint_reference"] is None  # nothing anchored, still verifiable
    assert "laptop-17" not in str(receipt) and "/records/" not in str(receipt)  # identifiers are HMAC'd


def test_log_chain_checkpoint_and_inclusion_all_verify(log, trusted):
    checkpoint = log.checkpoint(timestamp="2026-09-28T01:05:00Z")
    r.verify_log(log.receipts, trusted_signers=trusted, checkpoint=checkpoint)
    for seq, receipt in enumerate(log.receipts):
        r.verify_inclusion(receipt, log.inclusion_proof(seq, checkpoint), checkpoint, trusted_signers=trusted)


def test_checkpoint_root_is_verifiable_with_the_on_chain_convention(log):
    checkpoint = log.checkpoint()
    proof = [bytes.fromhex(n[2:]) for n in log.inclusion_proof(3, checkpoint)]
    # Same check StateAnchor.verifyLeaf performs once the root is anchored (B4).
    assert verify_leaf(bytes.fromhex(checkpoint["root"][2:]), r.receipt_leaf(log.receipts[3]), proof)


def test_later_receipts_reference_the_latest_checkpoint(log):
    checkpoint = log.checkpoint()
    _append(log, 1)
    assert log.receipts[-1]["checkpoint_reference"] == {"tree_size": 5, "root": checkpoint["root"]}


def test_a_persisted_log_resumes_and_keeps_chaining(log, gate_key, trusted):
    checkpoint = log.checkpoint()
    resumed = r.ReceiptLog.resume(gate_key, log.log_id, copy.deepcopy(log.receipts), [checkpoint])
    _append(resumed, 1)
    r.verify_log(resumed.receipts, trusted_signers=trusted, checkpoint=checkpoint)
    assert resumed.receipts[-1]["seq"] == 5


# ------------------------------------------------------------------------------ tamper cases ---


def test_an_edited_receipt_fails_its_signature(log, trusted):
    edited = dict(log.receipts[2], decision=d.PERMIT)
    with pytest.raises(r.ReceiptError) as excinfo:
        r.verify_receipt(edited, trusted_signers=trusted)
    assert _code(excinfo) == "BAD_SIGNATURE"


def test_a_receipt_from_another_key_is_untrusted(trusted):
    foreign = _append(r.ReceiptLog(Keypair.generate(), "shield:device-17"), 1)
    with pytest.raises(r.ReceiptError) as excinfo:
        r.verify_receipt(foreign.receipts[0], trusted_signers=trusted)
    assert _code(excinfo) == "UNTRUSTED_SIGNER"


def test_removing_or_reordering_receipts_breaks_the_log(log, trusted):
    with pytest.raises(r.ReceiptError) as removed:
        r.verify_log(log.receipts[:2] + log.receipts[3:], trusted_signers=trusted)
    assert _code(removed) == "SEQ_GAP"
    reordered = [log.receipts[1], log.receipts[0]] + log.receipts[2:]
    with pytest.raises(r.ReceiptError) as swapped:
        r.verify_log(reordered, trusted_signers=trusted)
    assert _code(swapped) == "SEQ_GAP"


def test_a_substituted_receipt_breaks_the_chain(log, gate_key, trusted):
    # Re-signed by the real key but not linked to its predecessor: the chain catches it.
    forged_log = _append(r.ReceiptLog(gate_key, log.log_id), 3, decision=d.PERMIT, reason="BAA_ACTIVE")
    tampered = log.receipts[:2] + [forged_log.receipts[2]] + log.receipts[3:]
    with pytest.raises(r.ReceiptError) as excinfo:
        r.verify_log(tampered, trusted_signers=trusted)
    assert _code(excinfo) == "CHAIN_BROKEN"


def test_tail_truncation_is_caught_by_the_checkpoint(log, trusted):
    checkpoint = log.checkpoint()
    # Without a checkpoint a truncated prefix is indistinguishable from a shorter log...
    r.verify_log(log.receipts[:3], trusted_signers=trusted)
    # ...with one, it is refused.
    with pytest.raises(r.ReceiptError) as excinfo:
        r.verify_log(log.receipts[:3], trusted_signers=trusted, checkpoint=checkpoint)
    assert _code(excinfo) == "TRUNCATED"


def test_a_wrong_proof_or_foreign_checkpoint_fails_inclusion(log, gate_key, trusted):
    checkpoint = log.checkpoint()
    with pytest.raises(r.ReceiptError) as wrong_proof:
        r.verify_inclusion(log.receipts[1], log.inclusion_proof(2, checkpoint), checkpoint, trusted_signers=trusted)
    assert _code(wrong_proof) == "NOT_INCLUDED"

    other = _append(r.ReceiptLog(gate_key, "bcc:middleware-1"), 2)
    foreign_checkpoint = other.checkpoint()
    with pytest.raises(r.ReceiptError) as foreign:
        r.verify_inclusion(log.receipts[0], [], foreign_checkpoint, trusted_signers=trusted)
    assert _code(foreign) == "LOG_MISMATCH"


def test_an_edited_checkpoint_fails_its_signature(log, trusted):
    checkpoint = dict(log.checkpoint(), tree_size=2)
    with pytest.raises(r.ReceiptError) as excinfo:
        r.verify_checkpoint(checkpoint, trusted_signers=trusted)
    assert _code(excinfo) == "BAD_SIGNATURE"


@pytest.mark.parametrize(
    "field, value",
    [("decision", "allow"), ("mode", "audit"), ("device_id_hmac", "laptop-17"), ("timestamp", "yesterday")],
)
def test_appending_a_malformed_receipt_is_refused(gate_key, field, value):
    log = r.ReceiptLog(gate_key, "shield:device-17")
    fields = dict(
        agent_did=AGENT_DID,
        device_id_hmac=r.hmac_identifier(HMAC_KEY, "device", "d"),
        action_hmac=r.hmac_identifier(HMAC_KEY, "action", "a"),
        event_class="agent.tool_call",
        pack_hash=PACK_HASH,
        decision=d.DENY,
        reason_code="NO_BAA",
        mode=d.ENFORCE,
        timestamp="2026-09-28T01:00:00Z",
    )
    fields[field] = value
    with pytest.raises(r.ReceiptError) as excinfo:
        log.append(**fields)
    assert _code(excinfo) == "MALFORMED"
    assert log.receipts == []


# --------------------------------------------------------------------------------- identifiers ---


def test_hmac_identifiers_are_keyed_deterministic_and_domain_separated():
    a = r.hmac_identifier(HMAC_KEY, "device", "laptop-17")
    assert a == r.hmac_identifier(HMAC_KEY, "device", "laptop-17")
    assert a != r.hmac_identifier(HMAC_KEY, "action", "laptop-17")
    assert a != r.hmac_identifier(bytes(32), "device", "laptop-17")
    with pytest.raises(ValueError):
        r.hmac_identifier(b"short", "device", "laptop-17")
