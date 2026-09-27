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

**Bounded:** the spool holds at most `settings.spool_max_rows` undelivered
rows. Rows already queued are retried indefinitely with a capped backoff and
are never deleted by the cap. At the cap, a *new* report is refused instead
(drop-newest) and counted in `spool_metrics.dropped_total`, with a throttled
warning log -- explicit, counted backpressure rather than silent loss or an
unbounded file. No dead-letter view exists yet; `status()` exposes pending
count, oldest-pending age, the cap and the drop counter.
"""

from __future__ import annotations

import json
import logging
import hashlib
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
;
CREATE TABLE IF NOT EXISTS delivery_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spool_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    oracle_ack TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    delivered_at REAL NOT NULL
)
;
CREATE TABLE IF NOT EXISTS spool_metrics (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL
)
"""

# Throttle for the at-capacity warning: during a sustained outage every report
# is refused, so log at most once a minute (the counter still records each drop).
_DROP_WARN_INTERVAL_SECONDS = 60.0
_last_drop_warning = 0.0

# COUNT(*) on a large spool costs ~70 ms (measured on 300k rows), too much for
# every enqueue during an outage. Re-count at most every few seconds per DB file
# and track our own inserts in between; the cap may overshoot by at most one
# refresh window of inserts, negligible against spool_max_rows.
_COUNT_REFRESH_SECONDS = 10.0
_pending_cache: dict[str, tuple[int, float]] = {}


def _pending_estimate(conn: sqlite3.Connection, db_path: str, now: float) -> int:
    cached = _pending_cache.get(db_path)
    if cached is None or now - cached[1] >= _COUNT_REFRESH_SECONDS:
        count = conn.execute("SELECT COUNT(*) FROM spool").fetchone()[0]
        _pending_cache[db_path] = (count, now)
        return count
    return cached[0]


def _connect(settings: Settings) -> sqlite3.Connection:
    path = Path(settings.spool_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def enqueue(settings: Settings, *, kind: str, endpoint_path: str, payload: dict, error: str) -> None:
    """Called from `audit.py` only after the live oracle POST already failed.

    Best-effort itself: if even writing to the local spool file fails (disk
    full, permissions), the original audit record is lost with a logged
    error -- there is no second fallback beyond local disk."""
    global _last_drop_warning
    try:
        conn = _connect(settings)
        try:
            now = time.time()
            pending = _pending_estimate(conn, settings.spool_db_path, now)
            if pending >= settings.spool_max_rows:
                conn.execute(
                    "INSERT INTO spool_metrics (name, value) VALUES ('dropped_total', 1) "
                    "ON CONFLICT(name) DO UPDATE SET value = value + 1"
                )
                conn.commit()
                if now - _last_drop_warning >= _DROP_WARN_INTERVAL_SECONDS:
                    _last_drop_warning = now
                    dropped = conn.execute("SELECT value FROM spool_metrics WHERE name = 'dropped_total'").fetchone()[0]
                    logger.warning(
                        "audit spool at capacity (%d rows, max %d) -- refusing new %s report; dropped_total=%d",
                        pending, settings.spool_max_rows, kind, dropped,
                    )
                return
            conn.execute(
                "INSERT INTO spool (kind, endpoint_path, payload_json, attempts, created_at, next_retry_at, last_error) "
                "VALUES (?, ?, ?, 0, ?, ?, ?)",
                (kind, endpoint_path, json.dumps(payload), now, now, error),
            )
            conn.commit()
            count, checked_at = _pending_cache.get(settings.spool_db_path, (pending, now))
            _pending_cache[settings.spool_db_path] = (count + 1, checked_at)
        finally:
            conn.close()
    except Exception:
        logger.exception("failed to spool undelivered audit report (kind=%s) -- record is lost", kind)


@dataclass
class RetryCycleResult:
    attempted: int
    delivered: int
    still_pending: int


def _payload_sha256(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _oracle_ack(resp: httpx.Response, endpoint_path: str) -> str:
    """Return a durable, non-secret acknowledgment value from Oracle."""
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if endpoint_path == "/v1/audit/ingest":
        value = body.get("id") if isinstance(body, dict) else None
        if not value:
            raise RuntimeError("Oracle audit acknowledgment did not include an id")
        return str(value)
    if endpoint_path == "/v1/audit/anchor":
        value = body.get("recorded") if isinstance(body, dict) else None
        if value is None:
            raise RuntimeError("Oracle anchor acknowledgment did not include recorded")
        return f"recorded:{value}"
    return "http:200"


def _backoff_seconds(settings: Settings, attempts: int) -> float:
    return min(settings.spool_max_backoff_seconds, settings.spool_retry_interval_seconds * (2**attempts))


def run_retry_cycle(settings: Settings, *, now: float | None = None) -> RetryCycleResult:
    """Retry one bounded batch of due rows: POST each again, delete it on
    success, and bump `attempts`/reschedule it on failure.

    Pure w.r.t. any event loop -- no asyncio here, matching
    `scoring_loop.run_sync_cycle`'s own separation. `app/main.py` wraps this
    in a periodic asyncio task the same way it wraps that function."""
    if now is None:
        now = time.time()
    conn = _connect(settings)
    try:
        rows = conn.execute(
            "SELECT id, endpoint_path, payload_json, attempts FROM spool "
            "WHERE next_retry_at <= ? ORDER BY id LIMIT ?",
            (now, settings.spool_retry_batch_size),
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
                oracle_ack = _oracle_ack(resp, endpoint_path)
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
                conn.execute(
                    "INSERT INTO delivery_receipts "
                    "(spool_id, kind, oracle_ack, payload_sha256, delivered_at) "
                    "SELECT id, kind, ?, ?, ? FROM spool WHERE id = ?",
                    (oracle_ack, _payload_sha256(payload_json), now, row_id),
                )
                conn.execute("DELETE FROM spool WHERE id = ?", (row_id,))
                delivered += 1
        conn.commit()
        still_pending = conn.execute("SELECT COUNT(*) FROM spool").fetchone()[0]
    finally:
        conn.close()
    if delivered:
        # Deliveries delete rows; force the next enqueue to re-count rather than
        # refuse reports against a stale, too-high cached count.
        _pending_cache.pop(settings.spool_db_path, None)
    return RetryCycleResult(attempted=len(rows), delivered=delivered, still_pending=still_pending)


@dataclass
class SpoolStatus:
    pending: int
    oldest_pending_age_seconds: float | None
    max_rows: int = 0
    dropped_total: int = 0


def status(settings: Settings) -> SpoolStatus:
    """Read-only snapshot for an ops/health endpoint -- see `main.py`'s
    `GET /v1/audit/spool/status`."""
    conn = _connect(settings)
    try:
        pending = conn.execute("SELECT COUNT(*) FROM spool").fetchone()[0]
        oldest = conn.execute("SELECT MIN(created_at) FROM spool").fetchone()[0]
        row = conn.execute("SELECT value FROM spool_metrics WHERE name = 'dropped_total'").fetchone()
    finally:
        conn.close()
    age = (time.time() - oldest) if oldest is not None else None
    return SpoolStatus(
        pending=pending,
        oldest_pending_age_seconds=age,
        max_rows=settings.spool_max_rows,
        dropped_total=row[0] if row else 0,
    )


def recent_receipts(settings: Settings, *, limit: int = 20) -> list[dict]:
    """Return non-sensitive delivery receipts for operator attribution."""
    conn = _connect(settings)
    try:
        rows = conn.execute(
            "SELECT spool_id, kind, oracle_ack, payload_sha256, delivered_at "
            "FROM delivery_receipts ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "spool_id": row[0],
            "kind": row[1],
            "oracle_ack": row[2],
            "payload_sha256": row[3],
            "delivered_at": row[4],
        }
        for row in rows
    ]
