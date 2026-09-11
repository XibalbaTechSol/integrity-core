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
