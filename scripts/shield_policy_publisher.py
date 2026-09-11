#!/usr/bin/env python3
"""Durable CORE -> Shield policy publisher with retry, DLQ, metrics, and audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path


def _request(url: str, payload: dict, token: str = "") -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        value = json.loads(response.read().decode())
    if not isinstance(value, dict):
        raise RuntimeError("endpoint returned a non-object response")
    return value


def _get(url: str, token: str = "") -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as response:
        value = json.loads(response.read().decode())
    if not isinstance(value, dict):
        raise RuntimeError("endpoint returned a non-object response")
    return value


class DeliveryStore:
    def __init__(self, path: str | Path, max_attempts: int = 8) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max(1, max_attempts)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS policy_deliveries (
                  delivery_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, device_id TEXT NOT NULL,
                  agent_id TEXT NOT NULL, policy_version TEXT NOT NULL, policy_hash TEXT NOT NULL,
                  token TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                  status TEXT NOT NULL DEFAULT 'pending', next_attempt_at REAL NOT NULL DEFAULT 0,
                  last_error TEXT, created_at REAL NOT NULL, sent_at REAL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_policy_delivery_scope
                  ON policy_deliveries(tenant_id, device_id, agent_id, policy_hash);
                CREATE TABLE IF NOT EXISTS policy_publisher_metrics (name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS policy_publisher_audit (
                  id INTEGER PRIMARY KEY AUTOINCREMENT, delivery_id TEXT NOT NULL,
                  event TEXT NOT NULL, detail_json TEXT NOT NULL, created_at REAL NOT NULL
                );
            """)

    @staticmethod
    def _metric(db: sqlite3.Connection, name: str) -> None:
        db.execute("INSERT INTO policy_publisher_metrics(name,value) VALUES(?,1) ON CONFLICT(name) DO UPDATE SET value=value+1", (name,))

    def enqueue(self, *, tenant_id: str, device_id: str, agent_id: str, policy_version: str, policy_hash: str, token: str) -> str:
        delivery_id = hashlib.sha256(f"{tenant_id}:{device_id}:{agent_id}:{policy_hash}".encode()).hexdigest()
        now = time.time()
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR IGNORE INTO policy_deliveries(delivery_id,tenant_id,device_id,agent_id,policy_version,policy_hash,token,created_at) VALUES(?,?,?,?,?,?,?,?)", (delivery_id, tenant_id, device_id, agent_id, policy_version, policy_hash, token, now))
            db.execute("INSERT INTO policy_publisher_audit(delivery_id,event,detail_json,created_at) VALUES(?,?,?,?)", (delivery_id, "enqueued", json.dumps({"policy_version": policy_version, "policy_hash": policy_hash}, sort_keys=True), now))
        return delivery_id

    def deliver_due(self, shield_url: str) -> dict[str, int]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM policy_deliveries WHERE status='pending' AND next_attempt_at <= ? ORDER BY created_at LIMIT 100", (time.time(),)).fetchall()
        attempted = delivered = dead_letter = 0
        for row in rows:
            attempted += 1
            try:
                result = _request(f"{shield_url}/api/v1/policy/push", {"token": row["token"]})
                with sqlite3.connect(self.path) as db:
                    db.execute("UPDATE policy_deliveries SET status='sent',sent_at=?,last_error=NULL WHERE delivery_id=?", (time.time(), row["delivery_id"]))
                    db.execute("INSERT INTO policy_publisher_audit(delivery_id,event,detail_json,created_at) VALUES(?,?,?,?)", (row["delivery_id"], "sent", json.dumps(result, sort_keys=True), time.time()))
                    self._metric(db, "delivered_total")
                delivered += 1
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
                attempts = int(row["attempts"]) + 1
                status = "dead_letter" if attempts >= self.max_attempts else "pending"
                with sqlite3.connect(self.path) as db:
                    db.execute("UPDATE policy_deliveries SET attempts=?,next_attempt_at=?,status=?,last_error=? WHERE delivery_id=?", (attempts, time.time() + min(900, 2 ** min(attempts, 8)), status, str(exc)[:500], row["delivery_id"]))
                    db.execute("INSERT INTO policy_publisher_audit(delivery_id,event,detail_json,created_at) VALUES(?,?,?,?)", (row["delivery_id"], status, json.dumps({"attempt": attempts, "error": str(exc)[:500]}, sort_keys=True), time.time()))
                    self._metric(db, "dead_letter_total" if status == "dead_letter" else "retry_total")
                dead_letter += status == "dead_letter"
        return {"attempted": attempted, "delivered": delivered, "dead_letter": dead_letter}

    def metrics(self) -> dict[str, int]:
        with sqlite3.connect(self.path) as db:
            counts = {row[0]: int(row[1]) for row in db.execute("SELECT status,COUNT(*) FROM policy_deliveries GROUP BY status")}
            totals = {row[0]: int(row[1]) for row in db.execute("SELECT name,value FROM policy_publisher_metrics")}
        return {"pending": counts.get("pending", 0), "sent": counts.get("sent", 0), "dead_letter": counts.get("dead_letter", 0), **totals}


def publish_once(store: DeliveryStore) -> dict:
    core = os.environ.get("CORE_ORACLE_URL", "http://127.0.0.1:8080").rstrip("/")
    shield = os.environ.get("SHIELD_URL", "http://127.0.0.1:8765").rstrip("/")
    tenant = os.environ["SHIELD_TENANT_ID"]
    policy = json.loads(os.environ.get("SHIELD_POLICY_JSON", '{"rules":[]}'))
    policy_version = str(os.environ.get("SHIELD_POLICY_VERSION", f"scheduler-{int(time.time())}"))
    discovery_error = None
    try:
        groups = _get(f"{shield}/api/shield/agents?tenant_id={tenant}", os.environ.get("SHIELD_ADMIN_TOKEN", "")).get("agents", [])
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
        # A control-plane outage must not crash the scheduler. Existing queued
        # deliveries can still make progress, and discovery is retried next tick.
        discovery_error = str(exc)[:500]
        groups = []
    for group in groups:
        for device in group.get("devices", []):
            agent_id = str(device.get("integrity_agent_id") or device.get("agent_id") or "")
            device_id = str(device.get("device_id") or "")
            if not agent_id or not device_id:
                continue
            signed = _request(f"{core}/v1/shield/policy-token", {"tenant_id": tenant, "device_id": device_id, "agent_id": agent_id, "policy": policy, "policy_version": policy_version}, os.environ.get("CORE_API_KEY", ""))
            store.enqueue(tenant_id=tenant, device_id=device_id, agent_id=agent_id, policy_version=policy_version, policy_hash=str(signed["policy_hash"]), token=str(signed["token"]))
    result = store.deliver_due(shield)
    if discovery_error:
        result["discovery_error"] = discovery_error
    result["metrics"] = store.metrics()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=int(os.environ.get("CORE_POLICY_PUSH_INTERVAL_SECONDS", "60")))
    parser.add_argument("--state", default=os.environ.get("CORE_POLICY_PUSH_STATE", "/var/lib/xibalba-integrity/policy-publisher.sqlite3"))
    parser.add_argument("--max-attempts", type=int, default=int(os.environ.get("CORE_POLICY_PUSH_MAX_ATTEMPTS", "8")))
    args = parser.parse_args()
    store = DeliveryStore(args.state, args.max_attempts)
    while True:
        print(json.dumps({"published": publish_once(store)}, sort_keys=True), flush=True)
        if args.once:
            return 0
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
