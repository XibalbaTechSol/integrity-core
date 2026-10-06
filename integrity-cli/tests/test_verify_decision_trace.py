from __future__ import annotations

import json

from typer.testing import CliRunner

from integrity_cli.main import app
from integrity_sdk.core import DecisionEnvelope, DecisionTrace, GENESIS_PARENT, build_trace_evidence
from integrity_sdk.core.receipts import ReceiptLog
from integrity_sdk.did import Keypair

runner = CliRunner()


def _event(trace_id: str, event_id: str, parent: str, **metadata: object) -> DecisionEnvelope:
    return DecisionEnvelope(
        tenant_id="tenant-a", agent_id="agent-a", trace_id=trace_id, event_id=event_id,
        event_type="policy_decision", timestamp="2026-10-05T00:00:00Z", parent_event_hash=parent,
        policy_ref="hipaa/tool-call", policy_decision="deny", metadata=metadata,
    )


def _trace_and_evidence_files(tmp_path, *, with_receipt: bool, advisory_statuses: list[str] | None = None):
    first = _event("trace-a", "event-1", GENESIS_PARENT, risk_hint="high")
    trace = DecisionTrace("trace-a", "tenant-a", "agent-a").append(first)
    second = _event("trace-a", "event-2", first.event_hash, risk_hint="low")
    trace = trace.append(second)

    receipt = None
    if with_receipt:
        keypair = Keypair.generate()
        log = ReceiptLog(keypair, "shield-log")
        receipt = log.append(
            agent_did="did:integrity:test", device_id_hmac="hmac-sha256:" + "11" * 32,
            action_hmac="hmac-sha256:" + "22" * 32, event_class="agent_event", pack_hash="0x" + "33" * 32,
            decision="deny", reason_code="TEST", mode="enforce",
        )

    evidence = build_trace_evidence(trace, receipt)

    advisory_statuses = advisory_statuses or []
    events_json = []
    for index, event in enumerate(trace.events):
        item = event.body()
        if index < len(advisory_statuses):
            item["advisory"] = {"status": advisory_statuses[index]}
        events_json.append(item)

    events_path = tmp_path / "decision-trace.json"
    events_path.write_text(json.dumps(events_json))
    evidence_path = tmp_path / "trace-evidence.json"
    evidence_path.write_text(json.dumps({
        "trace_id": evidence.trace_id, "root": evidence.root, "event_count": evidence.event_count,
        "receipt_hash": evidence.receipt_hash, "checkpoint_root": evidence.checkpoint_root,
    }))
    return events_path, evidence_path, receipt, log.signer_key if with_receipt else None


def _receipt_bundle_path(tmp_path, receipt, signer_key):
    bundle_path = tmp_path / "bundle.json"
    bundle_path.write_text(json.dumps({"receipts": [receipt]}))
    return bundle_path


def test_verify_decision_trace_passes_with_linked_receipt(tmp_path):
    events_path, evidence_path, receipt, signer_key = _trace_and_evidence_files(
        tmp_path, with_receipt=True, advisory_statuses=["available", "available"],
    )
    bundle_path = _receipt_bundle_path(tmp_path, receipt, signer_key)

    result = runner.invoke(app, [
        "verify", "--receipts", str(bundle_path), "--trusted-signer", signer_key,
        "--decision-trace", str(events_path), "--trace-evidence", str(evidence_path),
        "--json-output",
    ])
    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["valid"] is True
    assert document["decision_trace"] == "pass"
    assert document["advisory_status"] == "available"


def test_verify_decision_trace_reports_unavailable_advisory_without_failing(tmp_path):
    events_path, evidence_path, receipt, signer_key = _trace_and_evidence_files(
        tmp_path, with_receipt=True, advisory_statuses=["available", "unavailable"],
    )
    bundle_path = _receipt_bundle_path(tmp_path, receipt, signer_key)

    result = runner.invoke(app, [
        "verify", "--receipts", str(bundle_path), "--trusted-signer", signer_key,
        "--decision-trace", str(events_path), "--trace-evidence", str(evidence_path),
        "--json-output",
    ])
    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["valid"] is True
    assert document["decision_trace"] == "pass"
    assert document["advisory_status"] == "unavailable"


def test_verify_decision_trace_without_advisory_reports_not_present(tmp_path):
    events_path, evidence_path, receipt, signer_key = _trace_and_evidence_files(tmp_path, with_receipt=True)
    bundle_path = _receipt_bundle_path(tmp_path, receipt, signer_key)

    result = runner.invoke(app, [
        "verify", "--receipts", str(bundle_path), "--trusted-signer", signer_key,
        "--decision-trace", str(events_path), "--trace-evidence", str(evidence_path),
        "--json-output",
    ])
    assert result.exit_code == 0, result.stdout
    document = json.loads(result.stdout)
    assert document["decision_trace"] == "pass"
    assert document["advisory_status"] == "not_present"


def test_verify_decision_trace_fails_on_tampered_event(tmp_path):
    events_path, evidence_path, receipt, signer_key = _trace_and_evidence_files(tmp_path, with_receipt=True)
    bundle_path = _receipt_bundle_path(tmp_path, receipt, signer_key)

    events = json.loads(events_path.read_text())
    events[1]["policy_decision"] = "permit"  # mutate after evidence was built over the original
    events_path.write_text(json.dumps(events))

    result = runner.invoke(app, [
        "verify", "--receipts", str(bundle_path), "--trusted-signer", signer_key,
        "--decision-trace", str(events_path), "--trace-evidence", str(evidence_path),
        "--json-output",
    ])
    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert document["valid"] is False
    assert document["error"]["code"] == "TRACE_INVALID"


def test_verify_decision_trace_requires_both_flags_together(tmp_path):
    events_path, _evidence_path, _receipt, _signer = _trace_and_evidence_files(tmp_path, with_receipt=False)
    # --decision-trace without --trace-evidence: Typer's `exists=True` needs a real file
    # for --receipts, so point it at the events file -- its contents are never reached,
    # the flag-pairing check raises first.
    result = runner.invoke(app, [
        "verify", "--receipts", str(events_path), "--trusted-signer", "ztest",
        "--decision-trace", str(events_path), "--json-output",
    ])
    assert result.exit_code == 1
    document = json.loads(result.stdout)
    assert document["error"]["code"] == "MALFORMED"
    assert "trace-evidence" in document["error"]["detail"]
