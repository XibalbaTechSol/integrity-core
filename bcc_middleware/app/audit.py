"""
Reports every `run_intercept` decision (allow AND deny) to the oracle's real,
durable `audit_log` table via `POST /v1/audit/ingest`.

Before this module existed, `bcc_middleware` had ZERO durable storage anywhere
(confirmed by grep across app/ for sqlite/psycopg/sqlalchemy/CREATE TABLE) --
the single most audit-worthy event type in the whole protocol (real per-request
OPA ALLOW/DENY policy decisions) only ever existed in the HTTP response body,
gone the instant the response was sent. This is what made the dashboard's old
"Audit Logs" panel 100% fake: there was nothing real to query.

*** Reporting is best-effort, NOT a security gate ***
Same asymmetry as anchor.py's on-chain anchoring: by the time this is called,
run_intercept has already decided allow/deny. Reporting failure (oracle down,
network blip) must never change that decision or block the caller's response
-- it only means this one decision is missing from the audit trail until the
next successful report.

**No longer a silent, permanent loss on failure** (as of app/spool.py): a POST
that fails here is durably spooled to local SQLite and retried by a periodic
background loop (app/main.py), rather than only logged and forgotten. See
app/spool.py's own module docstring for the full design and its disclosed
scope limitations.
"""

from __future__ import annotations

import logging

import httpx

from app import spool
from app.config import Settings

logger = logging.getLogger("bcc_middleware.audit")


def report_decision(
    settings: Settings,
    *,
    agent_id: str | None,
    decision: str,
    reason_code: str | None = None,
    detail: str | None = None,
    intent_type: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Fire-and-forget POST to the oracle's audit ingest endpoint. Never raises --
    catches and logs any failure so a slow/unreachable oracle can't add latency
    or failure modes to the actual intercept decision path.

    `metadata` (evidence-export linkage, docs/design/evidence-export.md) carries
    the ALLOW row's Merkle `leaf` (plus batch_index / verification_token) so the
    anchor event later reported by `report_anchor_events` can be JOINed to this
    decision at export time. Omitted for deny/shadow_deny rows, which have no leaf."""
    payload = {
        "agent_id": agent_id,
        "source": "bcc_middleware",
        "event_type": "bcc_intercept",
        "decision": decision,
        "reason_code": reason_code,
        "detail": detail,
        "intent_type": intent_type,
    }
    if metadata is not None:
        payload["metadata"] = metadata
    endpoint_path = "/v1/audit/ingest"
    try:
        resp = httpx.post(
            f"{settings.oracle_url.rstrip('/')}{endpoint_path}",
            json=payload,
            timeout=3.0,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(
            "failed to report audit decision for agent %s: %s -- spooling for retry", agent_id, exc
        )
        if settings.spool_enabled:
            spool.enqueue(settings, kind="decision", endpoint_path=endpoint_path, payload=payload, error=str(exc))


def report_anchor_events(
    settings: Settings,
    *,
    agent_id: str,
    leaves: list[str],
    root: str,
    tx_hash: str,
) -> None:
    """Fire-and-forget POST to the oracle's anchor-event endpoint after an agent's
    Merkle sub-tree is anchored on-chain, so each anchored ALLOW decision can be
    JOINed to its StateAnchor transaction at export time (evidence export, Lever
    4). Written to `anchor_events` independently of the decision row -- see
    migration 0007 for the write-ordering race that motivates the JOIN over a
    back-fill. Best-effort/never-raises, same posture as report_decision and
    on-chain anchoring itself: a missed anchor report only means that decision is
    un-linked in the audit trail until re-reported, never a gate on anything."""
    if not leaves:
        return
    payload = {"agent_id": agent_id, "leaves": leaves, "root": root, "tx_hash": tx_hash}
    endpoint_path = "/v1/audit/anchor"
    try:
        resp = httpx.post(
            f"{settings.oracle_url.rstrip('/')}{endpoint_path}",
            json=payload,
            timeout=3.0,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(
            "failed to report anchor events for agent %s: %s -- spooling for retry", agent_id, exc
        )
        if settings.spool_enabled:
            spool.enqueue(settings, kind="anchor_event", endpoint_path=endpoint_path, payload=payload, error=str(exc))
