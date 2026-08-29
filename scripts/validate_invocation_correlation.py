#!/usr/bin/env python3
"""Exercise the deployed local Shield/BCC/Oracle invocation correlation boundary."""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import uuid

import requests


def main() -> int:
    shield_root = os.environ.get("SHIELD_ROOT", "/home/xibalba/Projects/xibalba-shield")
    sys.path.insert(0, shield_root)
    from shield.integrity_exporter import IntegrityExporter
    from shield.schemas.events import Decision, EventRef, PolicyDecision, RuleRef

    bcc_url = os.environ.get("BCC_URL", "http://localhost:8000")
    oracle_url = os.environ.get("ORACLE_URL", "http://localhost:8080")
    invocation_id = str(uuid.uuid4())
    exporter = IntegrityExporter(
        bcc_middleware_url=bcc_url,
        oracle_url=oracle_url,
        agent_label=os.environ.get("AGENT_LABEL", "xibalba"),
    )
    decision = PolicyDecision(
        device_id="correlation-http-harness",
        event_ref=EventRef(klass="agent_event", event_id=f"corr-{invocation_id[:8]}"),
        rule=RuleRef(rule_id="correlation.harness", name="HTTP correlation harness", version="1"),
        decision=Decision(action="deny", reason="service-level correlation validation"),
        invocation_id=invocation_id,
    )
    bcc = exporter.export_decision(decision)
    assert bcc.get("authorized") is True, bcc
    assert bcc.get("invocation_id_signed") is True, bcc

    effect = {
        "agent_id": exporter.agent_id,
        "invocation_id": invocation_id,
        "intended_state_hash": bcc["intended_state_hash"],
        "effect_hash": f"effect-{invocation_id}",
        "matches": True,
    }

    def submit(payload: dict) -> tuple[int, dict]:
        response = requests.post(f"{oracle_url}/v1/audit/effect", json=payload, timeout=15)
        return response.status_code, response.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _: submit(effect), range(16)))
    assert all(status == 200 for status, _ in results), results
    ids = {body["id"] for _, body in results}
    assert len(ids) == 1, ids

    conflict = dict(effect, effect_hash=f"conflict-{invocation_id}", matches=False)
    conflict_status, conflict_body = submit(conflict)
    assert conflict_status == 400, (conflict_status, conflict_body)

    malformed = requests.post(f"{bcc_url}/v1/bcc/intercept", json={"invocation_id": "not-a-uuid"}, timeout=15)
    assert malformed.status_code in (400, 422), malformed.status_code

    lookup = requests.get(f"{oracle_url}/v1/audit/invocation/{invocation_id}", timeout=15)
    assert lookup.status_code == 200, lookup.text
    events = lookup.json().get("rows", lookup.json().get("events", []))
    print(json.dumps({
        "invocation_id": invocation_id,
        "agent_id": exporter.agent_id,
        "bcc_authorized": bcc["authorized"],
        "invocation_id_signed": bcc["invocation_id_signed"],
        "concurrent_requests": len(results),
        "unique_effect_ids": sorted(ids),
        "conflict_status": conflict_status,
        "malformed_bcc_status": malformed.status_code,
        "lookup_status": lookup.status_code,
        "event_types": sorted({row.get("event_type") for row in events}),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
