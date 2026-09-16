"""Small durable local boundary for redacted SDK events."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class LocalEventStore:
    def __init__(self, path: str | Path, *, jsonl: bool = True) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl = jsonl
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None
        if not jsonl:
            self._db = sqlite3.connect(self.path, check_same_thread=False)
            self._db.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)")
            self._db.execute("CREATE TABLE IF NOT EXISTS delivery_attempts (event_id TEXT NOT NULL, destination TEXT NOT NULL, attempt INTEGER NOT NULL, attempted_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT, retry_state TEXT NOT NULL, dead_lettered INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(event_id, destination, attempt))")
            self._db.commit()

    def append(self, event: dict[str, Any]) -> str:
        event_id = str(event["event_id"])
        with self._lock:
            if self.jsonl:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            else:
                assert self._db is not None
                self._db.execute("INSERT OR IGNORE INTO events(event_id, agent_id, payload, created_at) VALUES (?, ?, ?, ?)", (event_id, event["agent_id"], json.dumps(event, sort_keys=True), event["timestamp"]))
                self._db.commit()
        return event_id

    def record_delivery(self, receipt: dict[str, Any]) -> None:
        """Persist a delivery attempt after the event itself is durable."""
        required = ("event_id", "destination", "attempt", "timestamp", "status", "retry_state")
        missing = [key for key in required if key not in receipt]
        if missing:
            raise ValueError(f"delivery receipt missing fields: {', '.join(missing)}")
        with self._lock:
            if self.jsonl:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"record_type": "delivery_attempt", **receipt}, sort_keys=True, ensure_ascii=False) + "\n")
            else:
                assert self._db is not None
                self._db.execute(
                    "INSERT OR IGNORE INTO delivery_attempts(event_id,destination,attempt,attempted_at,status,error,retry_state,dead_lettered) VALUES (?,?,?,?,?,?,?,?)",
                    (receipt["event_id"], receipt["destination"], receipt["attempt"], receipt["timestamp"], receipt["status"], receipt.get("error"), receipt["retry_state"], int(bool(receipt.get("dead_lettered", False))))
                )
                self._db.commit()

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
