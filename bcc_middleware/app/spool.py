"""
Durable local spool for audit-report deliveries the oracle failed to accept.

`app/audit.py`'s `report_decision`/`report_anchor_events` are best-effort HTTP
POSTs to the oracle -- by design, a failure there must never block or slow
down the caller's response (see audit.py's own module docstring). Before this
module, a failed POST was silently and permanently lost: logged once, then
gone. `docs/PRODUCTION_READINESS_PLAN.md`'s Workstream D names this gap
directly -- "a durable local export/spool queue in bcc_middleware so an
oracle outage cannot silently drop an audit report."

Closed with the simplest thing that is actually durable across a process
restart: one local SQLite file. This is a deliberate exception to this
service's usual "state is in-memory, single-process" posture
(`nonce_store.py`/`circuit_breaker.py`/`scoring_loop.py`'s dispute cooldown
all accept losing state on restart as fine) -- losing state on restart is
exactly the problem an audit trail cannot accept. A row is enqueued only
when the oracle POST itself fails; a successful POST never touches this file
-- the spool exists for the exception path, not the steady state.

Retry is a periodic background loop (`app/main.py`, mirroring
`scoring_loop.py`'s own periodic-cycle pattern: a pure, synchronous
`run_retry_cycle` here, wrapped in an asyncio loop there), with capped
exponential backoff per row so a prolonged outage doesn't turn into a retry
storm the moment the oracle comes back.

**Disclosed scope limitation, same axis as `nonce_store.py`/
`circuit_breaker.py`:** a single SQLite file is single-process/single-replica.
A multi-replica deployment needs a shared durable queue (e.g. the Redis
already present in the broader docker-compose topology), not N independent
local spools each retrying the same undelivered rows.

**Disclosed scope limitation, different axis:** rows are retried
indefinitely with a capped backoff interval, never dropped or dead-lettered
-- an oracle outage lasting long enough grows this file unboundedly. No
operator alert/dead-letter view exists yet; `status()` at least exposes the
pending count and oldest-pending age so an operator polling it can notice.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import Settings

logger = logging.getLogger("bcc_middleware.spool")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    endpoint_path TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    next_retry_at REAL NOT NULL,
    last_error TEXT
)
"""


def _connect(settings: Settings) -> sqlite3.Connection:
    path = Path(settings.spool_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn


def enqueue(settings: Settings, *, kind: str, endpoint_path: str, payload: dict, error: str) -> None:
    """Called from `audit.py` only after the live oracle POST already failed.

    Best-effort itself: if even writing to the local spool file fails (disk
    full, permissions), the original audit record is lost with a logged
    error -- there is no second fallback beyond local disk."""
    try:
        conn = _connect(settings)
        try:
            now = time.time()
            conn.execute(
                "INSERT INTO spool (kind, endpoint_path, payload_json, attempts, created_at, next_retry_at, last_error) "
                "VALUES (?, ?, ?, 0, ?, ?, ?)",
                (kind, endpoint_path, json.dumps(payload), now, now, error),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("failed to spool undelivered audit report (kind=%s) -- record is lost", kind)


@dataclass
class RetryCycleResult:
    attempted: int
    delivered: int
    still_pending: int


def _backoff_seconds(settings: Settings, attempts: int) -> float:
    return min(settings.spool_max_backoff_seconds, settings.spool_retry_interval_seconds * (2**attempts))


def run_retry_cycle(settings: Settings, *, now: float | None = None) -> RetryCycleResult:
    """One pass over every row due for retry: POST it again, delete the row
    on success, bump `attempts` and reschedule with backoff on failure.

    Pure w.r.t. any event loop -- no asyncio here, matching
    `scoring_loop.run_sync_cycle`'s own separation. `app/main.py` wraps this
    in a periodic asyncio task the same way it wraps that function."""
    if now is None:
        now = time.time()
    conn = _connect(settings)
    try:
        rows = conn.execute(
            "SELECT id, endpoint_path, payload_json, attempts FROM spool WHERE next_retry_at <= ? ORDER BY id",
            (now,),
        ).fetchall()
        delivered = 0
        for row_id, endpoint_path, payload_json, attempts in rows:
            try:
                resp = httpx.post(
                    f"{settings.oracle_url.rstrip('/')}{endpoint_path}",
                    json=json.loads(payload_json),
                    timeout=3.0,
                )
                resp.raise_for_status()
            except Exception as exc:
                next_attempts = attempts + 1
                conn.execute(
                    "UPDATE spool SET attempts = ?, next_retry_at = ?, last_error = ? WHERE id = ?",
                    (next_attempts, now + _backoff_seconds(settings, next_attempts), str(exc), row_id),
                )
                logger.warning(
                    "spool retry failed for row %d (kind via %s), attempt %d, next retry in %.0fs: %s",
                    row_id,
                    endpoint_path,
                    next_attempts,
                    _backoff_seconds(settings, next_attempts),
                    exc,
                )
            else:
                conn.execute("DELETE FROM spool WHERE id = ?", (row_id,))
                delivered += 1
        conn.commit()
        still_pending = conn.execute("SELECT COUNT(*) FROM spool").fetchone()[0]
    finally:
        conn.close()
    return RetryCycleResult(attempted=len(rows), delivered=delivered, still_pending=still_pending)


@dataclass
class SpoolStatus:
    pending: int
    oldest_pending_age_seconds: float | None


def status(settings: Settings) -> SpoolStatus:
    """Read-only snapshot for an ops/health endpoint -- see `main.py`'s
    `GET /v1/audit/spool/status`."""
    conn = _connect(settings)
    try:
        pending = conn.execute("SELECT COUNT(*) FROM spool").fetchone()[0]
        oldest = conn.execute("SELECT MIN(created_at) FROM spool").fetchone()[0]
    finally:
        conn.close()
    age = (time.time() - oldest) if oldest is not None else None
    return SpoolStatus(pending=pending, oldest_pending_age_seconds=age)
