from __future__ import annotations

import pytest

from integrity_sdk.core import (
    DecisionEnvelope,
    DecisionTrace,
    DecisionTraceError,
    FixtureJevProvider,
    GENESIS_PARENT,
    ReceiptLog,
    build_trace_evidence,
    verify_decision_trace_offline,
    verify_trace_evidence,
)
from integrity_sdk.did import Keypair


def _event(event_id: str, parent: str = GENESIS_PARENT, **metadata: object) -> DecisionEnvelope:
    return DecisionEnvelope(
        tenant_id="tenant-a",
        agent_id="agent-a",
        trace_id="trace-a",
        event_id=event_id,
        event_type="policy_decision",
        timestamp="2026-09-29T12:00:00Z",
        invocation_id="inv-a",
        parent_event_hash=parent,
        policy_ref="hipaa/tool-call",
        policy_decision="deny",
        metadata=metadata,
    )


def test_trace_is_parent_linked_and_merkle_verifiable():
    first = _event("event-1", risk_hint="high")
    trace = DecisionTrace("trace-a", "tenant-a", "agent-a").append(first)
    second = _event("event-2", parent=first.event_hash, risk_hint="low")
    trace = trace.append(second)

    assert trace.verify()
    assert trace.root
    assert trace.verify_inclusion(1, trace.proof(1))

    analysis = FixtureJevProvider().analyze(first)
    assert analysis.recommended_escalation is True
    assert analysis.observed_event_hash == first.event_hash
    assert analysis.causal_claim is False


def test_trace_rejects_wrong_parent_and_namespace():
    trace = DecisionTrace("trace-a", "tenant-a", "agent-a")
    with pytest.raises(DecisionTraceError, match="parent"):
        trace.append(_event("event-1", parent="0x" + "11" * 32))
    with pytest.raises(DecisionTraceError, match="namespace"):
        trace.append(DecisionEnvelope(
            tenant_id="tenant-b", agent_id="agent-a", trace_id="trace-a", event_id="event-1",
            event_type="tool_call", timestamp="2026-09-29T12:00:00Z",
        ))


def test_trace_rejects_raw_content_and_causal_claims():
    with pytest.raises(DecisionTraceError, match="raw content"):
        _event("event-1", prompt="do the thing")
    with pytest.raises(DecisionTraceError, match="causal"):
        DecisionEnvelope(
            tenant_id="tenant-a", agent_id="agent-a", trace_id="trace-a", event_id="event-1",
            event_type="tool_call", timestamp="2026-09-29T12:00:00Z", causal_claim=True,
        )


def test_trace_evidence_reuses_existing_signed_receipt_hash():
    first = _event("event-1")
    trace = DecisionTrace("trace-a", "tenant-a", "agent-a").append(first)
    keypair = Keypair.generate()
    log = ReceiptLog(keypair, "shield-log")
    receipt = log.append(
        agent_did="did:integrity:test", device_id_hmac="hmac-sha256:" + "11" * 32,
        action_hmac="hmac-sha256:" + "22" * 32, event_class="agent_event", pack_hash="0x" + "33" * 32,
        decision="deny", reason_code="TEST", mode="enforce",
    )
    evidence = build_trace_evidence(trace, receipt)
    assert evidence.receipt_hash
    assert verify_trace_evidence(trace, evidence, receipt)
    result = verify_decision_trace_offline(trace, evidence, receipt=receipt, trusted_signers={log.signer_key})
    assert result.valid is True
    assert not verify_trace_evidence(trace, evidence, {**receipt, "decision": "permit"})
