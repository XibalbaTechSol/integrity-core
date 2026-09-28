from __future__ import annotations

from integrity_sdk.core import (
    ReceiptLog,
    hmac_identifier,
    verify_receipt_log_offline,
)
from integrity_sdk.did import Keypair, public_key_multibase


def test_receipt_log_facade_reports_stable_offline_result():
    signer = Keypair.generate()
    log = ReceiptLog(signer, "shield:offline")
    log.append(
        agent_did="did:integrity:" + "a" * 64,
        device_id_hmac=hmac_identifier(b"k" * 32, "device", "laptop"),
        action_hmac=hmac_identifier(b"k" * 32, "action", "tool.call"),
        event_class="agent.tool_call",
        pack_hash="sha256:" + "a" * 64,
        decision="deny",
        reason_code="TEST",
        mode="enforce",
        timestamp="2026-09-28T12:00:00Z",
    )
    trusted = [public_key_multibase(signer.public_bytes())]
    result = verify_receipt_log_offline(log.receipts, trusted_signers=trusted)
    assert result.valid is True
    assert (result.code, result.identifier) == ("OK", "shield:offline")

    tampered = {**log.receipts[0], "reason_code": "FORGED"}
    invalid = verify_receipt_log_offline([tampered], trusted_signers=trusted)
    assert (invalid.valid, invalid.code) == (False, "BAD_SIGNATURE")
