from __future__ import annotations

import sqlite3
import urllib.error

from scripts import shield_policy_publisher as publisher


def _enqueue(store: publisher.DeliveryStore) -> str:
    return store.enqueue(
        tenant_id="tenant",
        device_id="device",
        agent_id="did:integrity:agent",
        policy_version="v1",
        policy_hash="sha256:" + "a" * 64,
        token="signed-token",
    )


def test_delivery_records_sent_audit_and_metrics(tmp_path, monkeypatch):
    store = publisher.DeliveryStore(tmp_path / "publisher.sqlite3")
    delivery_id = _enqueue(store)
    monkeypatch.setattr(publisher, "_request", lambda *args, **kwargs: {"accepted": True})

    assert store.deliver_due("http://shield") == {"attempted": 1, "delivered": 1, "dead_letter": 0}
    assert store.metrics()["sent"] == 1
    with sqlite3.connect(store.path) as db:
        events = [row[0] for row in db.execute("SELECT event FROM policy_publisher_audit WHERE delivery_id=? ORDER BY id", (delivery_id,))]
    assert events == ["enqueued", "sent"]


def test_failed_delivery_retries_then_dead_letters(tmp_path, monkeypatch):
    store = publisher.DeliveryStore(tmp_path / "publisher.sqlite3", max_attempts=2)
    delivery_id = _enqueue(store)
    monkeypatch.setattr(publisher, "_request", lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")))

    first = store.deliver_due("http://shield")
    assert first == {"attempted": 1, "delivered": 0, "dead_letter": 0}
    with sqlite3.connect(store.path) as db:
        db.execute("UPDATE policy_deliveries SET next_attempt_at=0 WHERE delivery_id=?", (delivery_id,))
        db.commit()

    second = store.deliver_due("http://shield")
    assert second == {"attempted": 1, "delivered": 0, "dead_letter": 1}
    metrics = store.metrics()
    assert metrics["dead_letter"] == 1
    assert metrics["retry_total"] == 1
    with sqlite3.connect(store.path) as db:
        row = db.execute("SELECT status, attempts FROM policy_deliveries WHERE delivery_id=?", (delivery_id,)).fetchone()
        events = [row[0] for row in db.execute("SELECT event FROM policy_publisher_audit WHERE delivery_id=? ORDER BY id", (delivery_id,))]
    assert row == ("dead_letter", 2)
    assert events == ["enqueued", "pending", "dead_letter"]


def test_publish_once_issues_and_delivers_pair_bound_policy(tmp_path, monkeypatch):
    store = publisher.DeliveryStore(tmp_path / "publisher.sqlite3")
    calls: list[tuple[str, dict]] = []

    monkeypatch.setenv("CORE_ORACLE_URL", "http://core")
    monkeypatch.setenv("SHIELD_URL", "http://shield")
    monkeypatch.setenv("SHIELD_TENANT_ID", "tenant")
    monkeypatch.setenv("SHIELD_POLICY_VERSION", "v2")
    monkeypatch.setenv("SHIELD_POLICY_JSON", '{"rules":[{"action":"observe"}]}')

    monkeypatch.setattr(
        publisher,
        "_get",
        lambda url, token="": {
            "agents": [{"devices": [{"device_id": "device-1", "integrity_agent_id": "did:integrity:agent-1"}]}]
        },
    )

    def request(url: str, payload: dict, token: str = "") -> dict:
        calls.append((url, payload))
        if url == "http://core/v1/shield/policy-token":
            return {"policy_hash": "sha256:" + "b" * 64, "token": "signed-token"}
        return {"accepted": True}

    monkeypatch.setattr(publisher, "_request", request)

    result = publisher.publish_once(store)

    assert result["attempted"] == 1
    assert result["delivered"] == 1
    assert calls[0] == (
        "http://core/v1/shield/policy-token",
        {
            "tenant_id": "tenant",
            "device_id": "device-1",
            "agent_id": "did:integrity:agent-1",
            "policy": {"rules": [{"action": "observe"}]},
            "policy_version": "v2",
        },
    )
    assert calls[1] == ("http://shield/api/v1/policy/push", {"token": "signed-token"})
    assert store.metrics()["sent"] == 1


def test_publish_once_keeps_scheduler_alive_when_discovery_is_unavailable(tmp_path, monkeypatch):
    store = publisher.DeliveryStore(tmp_path / "publisher.sqlite3")
    _enqueue(store)
    monkeypatch.setenv("SHIELD_TENANT_ID", "tenant")
    monkeypatch.setattr(publisher, "_get", lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    monkeypatch.setattr(publisher, "_request", lambda *args, **kwargs: {"accepted": True})

    result = publisher.publish_once(store)

    assert result["discovery_error"] == "<urlopen error offline>"
    assert result["attempted"] == 1
    assert result["delivered"] == 1
    assert store.metrics()["sent"] == 1
