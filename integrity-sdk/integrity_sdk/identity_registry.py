"""Append-only, non-secret runtime identity registry.

The DID directory remains authoritative for key continuity and DID identity.
This journal records the surrounding runtime bindings and their provenance so
operators can audit how a harness was attributed without creating another key
store or treating a display-label file as authority.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from .did import did_home

_LOCK = threading.Lock()
_REQUIRED = {"identity_version", "agent_id", "harness", "did", "key_fingerprint"}


def registry_path(root: str | Path | None = None) -> Path:
    return (Path(root).expanduser() if root is not None else did_home()) / "identity_registry.jsonl"


def record_identity(snapshot: dict[str, Any], *, event: str = "identity_observed", path: str | Path | None = None) -> dict[str, Any]:
    """Append one non-secret identity observation and return the stored record."""
    missing = sorted(_REQUIRED - snapshot.keys())
    if missing:
        raise ValueError(f"identity snapshot missing fields: {', '.join(missing)}")
    record = dict(snapshot)
    record["event"] = event
    record["observed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # The registry must never become a covert secret sink.
    forbidden = {"private_key", "private_key_pem", "seed", "password", "bearer_token", "keystore"}
    if forbidden.intersection(str(key).lower() for key in record):
        raise ValueError("identity registry cannot contain secret-bearing fields")
    target = registry_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
    with _LOCK:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    return record


def _records(path: str | Path | None = None) -> Iterable[dict[str, Any]]:
    target = registry_path(path)
    if not target.exists():
        return []
    records = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def history(agent_id: str, *, path: str | Path | None = None) -> list[dict[str, Any]]:
    return [record for record in _records(path) if record.get("agent_id") == agent_id]


def latest(agent_id: str, *, path: str | Path | None = None) -> dict[str, Any] | None:
    rows = history(agent_id, path=path)
    return rows[-1] if rows else None
