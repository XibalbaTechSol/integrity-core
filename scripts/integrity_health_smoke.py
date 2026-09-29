#!/usr/bin/env python3
"""Run the local Integrity Health synthetic-data smoke path.

This is an orchestration check, not a production service. It proves the local
contract boundary:

    Shield deny -> signed Integrity receipt -> Cortex provenance export
    -> offline verification

The Cortex store is created under a temporary directory and no Oracle, BCC,
chain, hosted service, or user data is contacted.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from urllib.parse import urlparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIELD_ROOT = ROOT.parent / "xibalba-shield"
CORTEX_SRC = ROOT.parent / "xibalba-cortex" / "src"
SDK_ROOT = ROOT / "integrity-sdk"
for path in (SHIELD_ROOT, CORTEX_SRC, SDK_ROOT):
    sys.path.insert(0, str(path))

from shield.opa_local import supervised_opa
from shield.policy_engine.engine import EvaluationContext, PolicyEngine
from shield.schemas.events import AgentContext, AgentEvent, AgentInfo, AgentActivity
from integrity_sdk.core import decision as decision_codes
from integrity_sdk.core import receipts
from integrity_sdk.core.offline import verify_receipt_log_offline
from integrity_sdk.did import Keypair, public_key_multibase
from xibalba_cortex.store import GraphStore


def main() -> int:
    event = AgentEvent(
        device_id="synthetic-device-001",
        agent=AgentInfo(agent_id="synthetic-agent-001", name="Synthetic Health Agent"),
        context=AgentContext(
            model_endpoint="https://approved.example/v1/chat/completions",
            data_sources=["synthetic_patient_record"],
        ),
        activity=AgentActivity(type="inference", risk_level="low"),
    )
    context = EvaluationContext(
        tenant_id="synthetic-tenant-001",
        device_role="clinical_desktop",
        device_id=event.device_id,
        registered_agent_ids=frozenset({event.agent.agent_id}),
    )

    with supervised_opa("regulated") as (opa_url, pack):
        opa_host = urlparse(opa_url).hostname
        if opa_host not in {"127.0.0.1", "localhost", "::1"}:
            raise AssertionError(f"Shield OPA endpoint escaped the local boundary: {opa_url}")
        shield_decision = PolicyEngine(opa_url=opa_url, pack=pack).evaluate(event, context)

    if shield_decision.decision.action != "deny":
        raise AssertionError(f"expected regulated no-BAA deny, got {shield_decision.decision.action}")

    signer = Keypair.generate()
    log = receipts.ReceiptLog(signer, "shield:synthetic-device-001")
    receipt = log.append(
        agent_did="did:integrity:synthetic-health-agent-001",
        device_id_hmac=receipts.hmac_identifier(b"synthetic-org-key-32-bytes-long-000", "device", event.device_id),
        action_hmac=receipts.hmac_identifier(b"synthetic-org-key-32-bytes-long-000", "action", "synthetic-health-inference"),
        event_class="agent.tool_call",
        pack_hash=shield_decision.policy.hash,
        decision=decision_codes.DENY,
        reason_code=(
            "REGULATED_DENY_PHI_CONTEXT"
            if shield_decision.rule.rule_id != "_no_match"
            else "REGULATED_NO_MATCH_DENY"
        ),
        mode=decision_codes.ENFORCE,
        controls=["HIPAA-164.312(a)(1)"],
        timestamp="2026-09-29T00:00:00Z",
    )
    for sequence in (1, 2):
        log.append(
            agent_did="did:integrity:synthetic-health-agent-001",
            device_id_hmac=receipts.hmac_identifier(b"synthetic-org-key-32-bytes-long-000", "device", event.device_id),
            action_hmac=receipts.hmac_identifier(b"synthetic-org-key-32-bytes-long-000", "action", f"synthetic-health-inference-{sequence}"),
            event_class="agent.tool_call",
            pack_hash=shield_decision.policy.hash,
            decision=decision_codes.DENY,
            reason_code="REGULATED_NO_MATCH_DENY",
            mode=decision_codes.ENFORCE,
            controls=["HIPAA-164.312(a)(1)"],
            timestamp=f"2026-09-29T00:00:0{sequence}Z",
        )
    trusted = [public_key_multibase(signer.public_bytes())]
    synthetic_content = "Synthetic regulated inference was denied because no active BAA was present."
    if synthetic_content in json.dumps(receipt):
        raise AssertionError("raw synthetic content entered the signed Shield receipt")
    checkpoint = log.checkpoint(timestamp="2026-09-29T00:00:03Z")
    receipt_result = verify_receipt_log_offline(log.receipts, trusted_signers=trusted, checkpoint=checkpoint)
    if not receipt_result.valid:
        raise AssertionError(receipt_result.detail)

    tampered_receipt = dict(receipt)
    tampered_receipt["decision"] = decision_codes.PERMIT
    tampered_result = verify_receipt_log_offline([tampered_receipt] + log.receipts[1:], trusted_signers=trusted)
    if tampered_result.valid or tampered_result.code != "BAD_SIGNATURE":
        raise AssertionError(f"tampered receipt was not rejected: {tampered_result}")

    foreign_signer = Keypair.generate()
    wrong_signer_result = verify_receipt_log_offline(
        log.receipts, trusted_signers=[public_key_multibase(foreign_signer.public_bytes())], checkpoint=checkpoint
    )
    if wrong_signer_result.valid or wrong_signer_result.code != "UNTRUSTED_SIGNER":
        raise AssertionError(f"wrong signer was not rejected: {wrong_signer_result}")

    truncated_result = verify_receipt_log_offline(log.receipts[:2], trusted_signers=trusted, checkpoint=checkpoint)
    if truncated_result.valid or truncated_result.code != "TRUNCATED":
        raise AssertionError(f"truncated log was not rejected: {truncated_result}")

    with tempfile.TemporaryDirectory(prefix="integrity-health-smoke-") as temp_dir:
        store = GraphStore(Path(temp_dir) / "cortex")
        memory = store.store_memory(
            synthetic_content,
            source={
                "kind": "integrity_health_smoke",
                "tenant_id": context.tenant_id,
                "agent_id": event.agent.agent_id,
                "receipt_hash": receipts.receipt_hash(receipt),
            },
            status="confirmed",
        )
        bundle = store.export_memory_bundle(memory_ids=[memory["id"]])
        store.close()

        bundle_path = Path(temp_dir) / "provenance.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        verifier = ROOT / "../xibalba-cortex/scripts/verify_provenance_export.py"
        verified = subprocess.run(
            [sys.executable, str(verifier.resolve()), str(bundle_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if verified.returncode != 0:
            raise AssertionError(verified.stderr.strip() or "Cortex provenance verification failed")

        tampered_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        tampered_bundle["memories"][0]["content"] += " TAMPERED"
        tampered_path = Path(temp_dir) / "tampered-provenance.json"
        tampered_path.write_text(json.dumps(tampered_bundle), encoding="utf-8")
        tampered_verified = subprocess.run(
            [sys.executable, str(verifier.resolve()), str(tampered_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if tampered_verified.returncode != 1:
            raise AssertionError("tampered Cortex provenance was not rejected")

    print(json.dumps({
        "scenario": "integrity_health_local",
        "shield": {
            "decision": shield_decision.decision.action,
            "reason_code": receipt["reason_code"],
            "pack_hash": shield_decision.policy.hash,
        },
        "integrity": {
            "receipt_log": log.log_id,
            "offline_verification": receipt_result.code,
            "tamper_rejection": tampered_result.code,
            "wrong_signer_rejection": wrong_signer_result.code,
            "truncation_rejection": truncated_result.code,
        },
        "cortex": {
            "provenance": "verified",
            "tamper_rejection": "verified",
            "content_boundary": "synthetic_only",
        },
        "data_boundary": {
            "shield_opa_scope": "loopback_only",
            "cortex_storage": "temporary_local_filesystem",
            "external_content_transport": 0,
            "receipt_raw_content": "absent",
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
