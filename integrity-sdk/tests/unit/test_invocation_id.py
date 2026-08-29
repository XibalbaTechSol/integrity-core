from __future__ import annotations

import uuid

import pytest

from integrity_sdk import bcc, posttool_report
from integrity_sdk.did import Keypair
from integrity_sdk.telemetry.intent import invoke_intent


AGENT_ID = "did:integrity:test-agent"
VERIFYING_CONTRACT = "0x111111111111111111111111111111111111111a"
INVOCATION_ID = "018f47a2-4e31-7c90-b187-8d4f82d6c921"


def _commitment(keypair: Keypair, *, invocation_id: str | None = INVOCATION_ID):
    return bcc.build_bcc_commitment(
        agent_id=AGENT_ID,
        intent_type="TOOL_CALL",
        intent_payload={"tool": "read_file", "path": "/tmp/example"},
        nonce=1,
        keypair=keypair,
        chain_id=31337,
        verifying_contract=VERIFYING_CONTRACT,
        timestamp_ms=1_800_000_000_000,
        invocation_id=invocation_id,
    )


def test_new_invocation_id_returns_canonical_uuid():
    value = bcc.new_invocation_id()
    assert value == str(uuid.UUID(value))


def test_commitment_signature_binds_invocation_id():
    keypair = Keypair.generate()
    commitment = _commitment(keypair)
    assert bcc.verify_bcc_commitment(commitment, keypair.public_bytes())

    commitment["invocation_id"] = "018f47a2-4e31-7c90-b187-8d4f82d6c922"
    assert not bcc.verify_bcc_commitment(commitment, keypair.public_bytes())


def test_legacy_commitment_without_invocation_id_still_verifies():
    keypair = Keypair.generate()
    commitment = _commitment(keypair, invocation_id=None)
    assert "invocation_id" not in commitment
    assert bcc.verify_bcc_commitment(commitment, keypair.public_bytes())


def test_build_commitment_rejects_malformed_invocation_id():
    with pytest.raises(ValueError):
        _commitment(Keypair.generate(), invocation_id="not-a-uuid")


def test_invoke_intent_propagates_one_id_to_commitment_and_trace_run():
    with invoke_intent(
        intent_type="TOOL_CALL",
        intent_payload={"tool": "read_file"},
        keypair=Keypair.generate(),
        nonce=1,
        agent_id=AGENT_ID,
        chain_id=31337,
        verifying_contract=VERIFYING_CONTRACT,
        invocation_id=INVOCATION_ID,
    ) as intent:
        pass

    assert intent.commitment["invocation_id"] == INVOCATION_ID
    assert intent.run.inputs["invocation_id"] == INVOCATION_ID


def test_submit_effect_report_includes_invocation_id(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"accepted": True}

    def fake_post(url, *, json, timeout):
        captured.update(url=url, json=json, timeout=timeout)
        return Response()

    monkeypatch.setattr("requests.post", fake_post)
    result = posttool_report.submit_effect_report(
        agent_id=AGENT_ID,
        intended_state_hash="0x" + "11" * 32,
        effect_hash="0x" + "22" * 32,
        matches=False,
        invocation_id=INVOCATION_ID,
        oracle_url="http://oracle.test",
        timeout=3,
    )

    assert result == {"accepted": True}
    assert captured["url"] == "http://oracle.test/v1/audit/effect"
    assert captured["timeout"] == 3
    assert captured["json"]["invocation_id"] == INVOCATION_ID
