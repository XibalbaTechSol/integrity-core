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
import datetime as dt
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
from shield.integrations.siem import export_decision_log_to_jsonl
from integrity_sdk.core import decision as decision_codes
from integrity_sdk.core import receipts
from integrity_sdk.core.offline import verify_receipt_log_offline
from integrity_sdk.core import packs
from integrity_sdk.core import ReceiptQueue, receipt_hash
from integrity_sdk.core import CapabilityDenied, EntitlementSet, require_capability
from integrity_sdk.core import BreakGlassError, create_approval, verify_approval
from integrity_sdk.core import run_adapter_conformance
from integrity_sdk.core import (
    AgentRegistration,
    DeviceRegistration,
    LocalRegistry,
    RegistryError,
    TenantIdentity,
)
from integrity_sdk.did import Keypair, public_key_multibase
from xibalba_cortex.store import GraphStore
from xibalba_cortex.ingest_tokens import verify_token_record
from xibalba_cortex.tenant_onboarding import provision_tenant
from integrity_sdk.integrations.sample_adapter import adapt_event


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
    shadow_result = decision_codes.resolve(
        "agent.tool_call",
        {"decision": decision_codes.DENY, "reason_code": "REGULATED_NO_MATCH_DENY"},
        event_defaults=pack.event_defaults,
        mode=decision_codes.SHADOW,
        pack_hash=pack.pack_hash,
    )
    if shadow_result.decision != decision_codes.DENY or shadow_result.blocks:
        raise AssertionError("shadow mode did not record the deny without blocking")
    break_glass_signer = Keypair.generate()
    break_glass = create_approval(
        break_glass_signer,
        tenant_id=context.tenant_id,
        agent_did="did:integrity:synthetic-health-agent-001",
        reason="synthetic incident response",
        issued_at="2026-09-29T00:00:00Z",
        expires_at="2026-09-29T01:00:00Z",
        nonce="integrity-health-smoke",
    )
    verify_approval(
        break_glass,
        trusted_signers=[break_glass["signer_key"]],
        now=dt.datetime(2026, 9, 29, 0, 30, tzinfo=dt.timezone.utc),
    )
    try:
        verify_approval(
            break_glass,
            trusted_signers=[break_glass["signer_key"]],
            now=dt.datetime(2026, 9, 29, 1, 0, tzinfo=dt.timezone.utc),
        )
    except BreakGlassError as expired:
        if expired.code != "EXPIRED":
            raise AssertionError(f"break-glass expiry failed with {expired.code}")
    else:
        raise AssertionError("expired break-glass approval was accepted")

    # Simulate the local policy sidecar disappearing after a verified pack is
    # installed. The configured pack must still fail closed rather than turn a
    # transport error into a permit.
    unavailable_engine = PolicyEngine(opa_url="http://127.0.0.1:1")
    unavailable_engine._pack = pack  # test-only injection; no network is used
    unavailable_engine._opa_client._installed_pack_hash = pack.pack_hash  # preserve the verified-pack branch
    unavailable_decision = unavailable_engine.evaluate(event, context)
    if unavailable_decision.decision.action != "deny":
        raise AssertionError(
            "policy-sidecar outage did not fail closed: "
            f"{unavailable_decision.decision.action}"
        )

    # Sign and reload a synthetic pack, then prove that a policy relaxation is
    # rejected before it can become an enforcement input.
    with tempfile.TemporaryDirectory(prefix="integrity-health-pack-") as pack_dir_name:
        pack_dir = Path(pack_dir_name)
        (pack_dir / "pack.yaml").write_text(
            """pack_format: integrity.pack/1
name: synthetic-health
version: 1.0.0
kernel_range: ">=1.0.0 <2.0.0"
decision_contract: integrity.decision/1
entrypoint: data.integrity.pack.decision
event_classes:
  agent.tool_call: {no_match: deny}
""",
            encoding="utf-8",
        )
        (pack_dir / "policy.rego").write_text(
            'package integrity.pack\n\ndecision := {"decision": "deny", "reason_code": "NO_BAA"} if { not input.baa_active }\n',
            encoding="utf-8",
        )
        (pack_dir / "controls.yaml").write_text("NO_BAA: [HIPAA-164.502(b)]\n", encoding="utf-8")
        pack_signer = Keypair.generate()
        compiled_pack = packs.sign_pack(pack_dir, pack_signer)
        loaded_pack = packs.load_pack(
            pack_dir,
            trusted_signers=[public_key_multibase(pack_signer.public_bytes())],
            expected_pack_hash=compiled_pack.pack_hash,
        )
        if loaded_pack.pack_hash != compiled_pack.pack_hash:
            raise AssertionError("verified pack hash did not match the signed pack")
        (pack_dir / "pack.yaml").write_text(
            (pack_dir / "pack.yaml").read_text(encoding="utf-8").replace("no_match: deny", "no_match: permit"),
            encoding="utf-8",
        )
        try:
            packs.load_pack(
                pack_dir,
                trusted_signers=[public_key_multibase(pack_signer.public_bytes())],
            )
        except packs.PackError as refused:
            if refused.code != "TAMPERED":
                raise AssertionError(f"relaxed pack failed with {refused.code}, not TAMPERED")
        else:
            raise AssertionError("relaxed signed pack was accepted")

    # Exercise the local tenancy boundary before creating any receipt. A device
    # must be active, belong to the requested tenant, and belong to the agent
    # named by the request. This is synthetic registry metadata only; no hosted
    # control plane or private credential is involved.
    with tempfile.TemporaryDirectory(prefix="integrity-health-registry-") as registry_dir:
        registry = LocalRegistry(Path(registry_dir) / "registry.json")
        tenant_a = TenantIdentity("org-a", "tenant-a", "Tenant A")
        tenant_b = TenantIdentity("org-b", "tenant-b", "Tenant B")
        agent_a = AgentRegistration(tenant_a.tenant_id, "did:integrity:agent-a", "Agent A")
        agent_b = AgentRegistration(tenant_b.tenant_id, "did:integrity:agent-b", "Agent B")
        device_a = DeviceRegistration(
            tenant_a.tenant_id, "device-a", agent_a.agent_did, "zsynthetic-a", shield_decision.policy.hash
        )
        revoked_device = DeviceRegistration(
            tenant_b.tenant_id,
            "device-b",
            agent_b.agent_did,
            "zsynthetic-b",
            shield_decision.policy.hash,
            status="revoked",
        )
        for tenant in (tenant_a, tenant_b):
            registry.register_tenant(tenant)
        for agent in (agent_a, agent_b):
            registry.register_agent(agent)
        registry.register_device(device_a)
        registry.register_device(revoked_device)

        if registry.get_device(device_a.device_id, tenant_id=tenant_b.tenant_id) is not None:
            raise AssertionError("cross-tenant device lookup was not isolated")
        if registry.get_agent(agent_a.agent_did, tenant_id=tenant_b.tenant_id) is not None:
            raise AssertionError("cross-tenant agent lookup was not isolated")
        if registry.authorize_device(
            tenant_id=tenant_a.tenant_id, agent_did=agent_a.agent_did, device_id=device_a.device_id
        ) != device_a:
            raise AssertionError("active device was not authorized for its own tenant")
        try:
            registry.authorize_device(
                tenant_id=tenant_b.tenant_id, agent_did=agent_a.agent_did, device_id=device_a.device_id
            )
        except RegistryError:
            pass
        else:
            raise AssertionError("cross-tenant device authorization was not rejected")
        try:
            registry.authorize_device(
                tenant_id=tenant_b.tenant_id, agent_did=agent_b.agent_did, device_id=revoked_device.device_id
            )
        except RegistryError:
            pass
        else:
            raise AssertionError("revoked device was authorized to receive a pack or append a receipt")

    entitlements = EntitlementSet("tenant-a", frozenset({"shield.enforce", "cortex.write"}))
    require_capability(entitlements, "shield.enforce", tenant_id="tenant-a")
    try:
        require_capability(entitlements, "billing.admin", tenant_id="tenant-a")
    except CapabilityDenied:
        pass
    else:
        raise AssertionError("ungranted entitlement was accepted")
    try:
        require_capability(entitlements, "shield.enforce", tenant_id="tenant-b")
    except CapabilityDenied:
        pass
    else:
        raise AssertionError("cross-tenant entitlement was accepted")

    adapter_result = run_adapter_conformance(adapt_event)
    if adapter_result["tenant_id"] != "tenant-a":
        raise AssertionError("sample adapter changed the tenant identity scope")

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
    vanta_fixture = {
        "schema_version": "integrity.vanta-fixture/1",
        "control_id": "HIPAA-164.312(b)",
        "status": "pass",
        "pack_hash": shield_decision.policy.hash,
        "receipt_hash": receipts.receipt_hash(receipt),
        "verification": receipt_result.code,
    }
    if vanta_fixture["verification"] != "OK" or not all(
        isinstance(vanta_fixture[field], str) and vanta_fixture[field]
        for field in ("control_id", "pack_hash", "receipt_hash")
    ):
        raise AssertionError("Vanta fixture is missing the control-to-receipt evidence link")
    with tempfile.TemporaryDirectory(prefix="integrity-health-ocsf-") as export_dir_name:
        export_dir = Path(export_dir_name)
        source = export_dir / "decisions.jsonl"
        destination = export_dir / "ocsf.jsonl"
        source.write_text(
            json.dumps(
                {
                    "class": "policy_decision",
                    "device_id": event.device_id,
                    "decision": {"action": shield_decision.decision.action},
                    "policy": {"hash": shield_decision.policy.hash},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        export_result = export_decision_log_to_jsonl(source, destination)
        exported_row = json.loads(destination.read_text(encoding="utf-8").strip())
        if export_result.exported != 1 or exported_row.get("event.module") != "xibalba-shield":
            raise AssertionError("OCSF-style JSONL export did not produce the expected module record")
        if "content" in exported_row or "prompt" in exported_row:
            raise AssertionError("OCSF-style JSONL export included raw content")

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

    # Verify that an offline transport failure preserves receipts and that a
    # later retry acknowledges exactly the submitted item.
    with tempfile.TemporaryDirectory(prefix="integrity-health-queue-") as queue_dir:
        queue_path = Path(queue_dir) / "receipts.json"
        queue = ReceiptQueue(signer, "shield:synthetic-device-queue", queue_path)
        queued = queue.append(
            agent_did="did:integrity:synthetic-health-agent-001",
            device_id_hmac=receipts.hmac_identifier(b"synthetic-org-key-32-bytes-long-000", "device", event.device_id),
            action_hmac=receipts.hmac_identifier(b"synthetic-org-key-32-bytes-long-000", "action", "queue-test"),
            event_class="agent.tool_call",
            pack_hash=shield_decision.policy.hash,
            decision=decision_codes.DENY,
            reason_code="REGULATED_NO_MATCH_DENY",
            mode=decision_codes.ENFORCE,
            controls=["HIPAA-164.312(b)"],
            timestamp="2026-09-29T00:00:04Z",
        )
        try:
            queue.submit(lambda _pending: (_ for _ in ()).throw(RuntimeError("offline")))
        except RuntimeError:
            pass
        else:
            raise AssertionError("offline queue submission unexpectedly succeeded")
        resumed_queue = ReceiptQueue(signer, "shield:synthetic-device-queue", queue_path)
        if resumed_queue.pending() != [queued]:
            raise AssertionError("offline submission did not preserve the pending receipt")
        accepted = resumed_queue.submit(lambda pending: [receipt_hash(pending[0])])
        if accepted != [receipt_hash(queued)] or resumed_queue.pending():
            raise AssertionError("queue retry did not acknowledge exactly the submitted receipt")

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

        retention_session = "integrity-health-retention"
        store.start_session(retention_session, retention_tier="digest")
        retained = store.store_memory(
            "Synthetic retention candidate",
            source={"kind": "integrity_health_smoke", "session_id": retention_session},
            status="confirmed",
        )
        store.end_session(retention_session)
        retention = store.retention_sweep(max_age_days={"digest": 0}, apply=True)
        if retention["candidate_count"] != 1 or not retention["deletion_receipts"]:
            raise AssertionError("retention sweep did not produce a deletion receipt")
        if store.get_memory(retained["id"])["status"] != "forgotten":
            raise AssertionError("retention sweep did not forget the expired synthetic memory")
        store_health = store.status(fast=True)
        if (
            store_health.get("profile_id") != "default"
            or store_health.get("journal_mode") != "wal"
            or not store_health.get("backup_ready")
        ):
            raise AssertionError(f"Cortex local store health is not ready: {store_health}")
        audit = store.audit_report(limit=25)
        if (
            audit.get("schema_version") != "xibalba.audit_report.v1"
            or audit.get("profile_id") != "default"
            or int(audit.get("forgotten_memory_count", 0)) < 1
            or int(audit.get("memory_event_counts", {}).get("create", 0)) < 1
        ):
            raise AssertionError(f"Cortex audit summary is incomplete: {audit}")
        store.close()

        tenant_a_store = GraphStore(Path(temp_dir) / "tenant-a", profile_id="tenant-a")
        tenant_b_store = GraphStore(Path(temp_dir) / "tenant-b", profile_id="tenant-b")
        try:
            tenant_a_memory = tenant_a_store.store_memory(
                "tenant-a synthetic evidence", source={"kind": "integrity_health_smoke"}, status="confirmed"
            )
            try:
                tenant_b_store.get_memory(tenant_a_memory["id"])
            except KeyError:
                pass
            else:
                raise AssertionError("tenant B read tenant A memory")
            if tenant_b_store.search("tenant-a synthetic", limit=10):
                raise AssertionError("tenant B search returned tenant A memory")
        finally:
            tenant_a_store.close()
            tenant_b_store.close()

        provisioned = provision_tenant(Path(temp_dir) / "tenants", "tenant-c", ttl_hours=24, max_memories=10)
        principal = verify_token_record(Path(provisioned["home"]), str(provisioned["token"]))
        if (
            provisioned.get("schema_version") != "xibalba.tenant_onboarding.v1"
            or provisioned.get("profile_id") != "tenant-c"
            or principal.get("profile_id") != "tenant-c"
            or "memory:read" not in principal.get("scopes", [])
        ):
            raise AssertionError("temporary tenant onboarding did not bind the operator token to its profile")

    print(json.dumps({
        "scenario": "integrity_health_local",
        "shield": {
            "decision": shield_decision.decision.action,
            "reason_code": receipt["reason_code"],
            "pack_hash": shield_decision.policy.hash,
            "policy_sidecar_outage": "fail_closed",
            "shadow_mode": "recorded_without_blocking",
            "break_glass": "signed_and_expiring",
        },
        "integrity": {
            "receipt_log": log.log_id,
            "offline_verification": receipt_result.code,
            "tamper_rejection": tampered_result.code,
            "wrong_signer_rejection": wrong_signer_result.code,
            "truncation_rejection": truncated_result.code,
            "queue_recovery": "verified",
        },
        "cortex": {
            "provenance": "verified",
            "tamper_rejection": "verified",
            "content_boundary": "synthetic_only",
            "retention_purge": "verified",
            "store_health": "operational",
            "audit_summary": "verified",
        },
        "data_boundary": {
            "shield_opa_scope": "loopback_only",
            "cortex_storage": "temporary_local_filesystem",
            "external_content_transport": 0,
            "receipt_raw_content": "absent",
        },
        "tenancy": {
            "cross_tenant_lookup": "denied",
            "cross_tenant_authorization": "denied",
            "cortex_store_isolation": "verified",
            "tenant_onboarding_auth": "verified",
            "revoked_device_authorization": "denied",
            "receipt_or_pack_gate": "fail_closed",
        },
        "packs": {
            "signed_load": "verified",
            "hash_pin": "verified",
            "policy_relaxation": "rejected",
        },
        "entitlements": {
            "granted_capability": "verified",
            "missing_capability": "denied",
            "tenant_mismatch": "denied",
            "billing_dependency": "none",
        },
        "adapter": {
            "conformance": "verified",
            "payload_export": "hash_only",
        },
        "exports": {
            "vanta_fixture": "verified",
            "ocsf_jsonl": "verified",
            "raw_content": "absent",
        },
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
