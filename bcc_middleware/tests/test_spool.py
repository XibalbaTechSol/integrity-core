"""
Tests for app/spool.py -- the durable local audit-report spool -- and its
wiring into app/audit.py's report_decision/report_anchor_events.

The oracle HTTP boundary is mocked with respx, same convention as
test_scoring_loop.py; the spool itself is real SQLite against a real
tmp_path file, not mocked, since durability across a process restart is the
entire point being tested.
"""

from __future__ import annotations

import time

import respx
from httpx import Response

from app.audit import report_anchor_events, report_decision
from app.config import Settings
from app.spool import enqueue, run_retry_cycle, status

_ORACLE_URL = "http://oracle.test"


def _settings(tmp_path, **overrides) -> Settings:
    kwargs = dict(
        oracle_url=_ORACLE_URL,
        spool_db_path=str(tmp_path / "spool.sqlite3"),
        spool_retry_interval_seconds=1,
        spool_max_backoff_seconds=60,
    )
    kwargs.update(overrides)
    return Settings(**kwargs)


def test_enqueue_then_status_reports_pending(tmp_path):
    settings = _settings(tmp_path)
    assert status(settings).pending == 0

    enqueue(settings, kind="decision", endpoint_path="/v1/audit/ingest", payload={"a": 1}, error="boom")

    result = status(settings)
    assert result.pending == 1
    assert result.oldest_pending_age_seconds is not None
    assert result.oldest_pending_age_seconds >= 0


def test_retry_cycle_delivers_and_removes_row(tmp_path):
    settings = _settings(tmp_path)
    enqueue(settings, kind="decision", endpoint_path="/v1/audit/ingest", payload={"agent_id": "agent-1"}, error="boom")

    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(200, json={"ok": True}))
        result = run_retry_cycle(settings)

    assert result.attempted == 1
    assert result.delivered == 1
    assert result.still_pending == 0
    assert status(settings).pending == 0


def test_retry_cycle_reschedules_with_backoff_on_repeated_failure(tmp_path):
    settings = _settings(tmp_path, spool_retry_interval_seconds=10)
    enqueue(settings, kind="decision", endpoint_path="/v1/audit/ingest", payload={"agent_id": "agent-1"}, error="boom")

    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(503))
        result = run_retry_cycle(settings)

    assert result.attempted == 1
    assert result.delivered == 0
    assert result.still_pending == 1

    # A retry attempted immediately again must NOT be picked up yet -- the row's
    # next_retry_at was pushed forward by the backoff, not left at "now".
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(200, json={"ok": True}))
        immediate_retry = run_retry_cycle(settings, now=time.time())

    assert immediate_retry.attempted == 0
    assert immediate_retry.still_pending == 1

    # But once enough time has passed (first backoff = interval * 2**1 = 20s), it
    # is picked up and delivered.
    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(200, json={"ok": True}))
        later_retry = run_retry_cycle(settings, now=time.time() + 25)

    assert later_retry.attempted == 1
    assert later_retry.delivered == 1
    assert status(settings).pending == 0


def test_report_decision_spools_on_failure_then_retry_delivers(tmp_path):
    settings = _settings(tmp_path)

    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(500))
        report_decision(settings, agent_id="agent-1", decision="allow")

    assert status(settings).pending == 1

    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(200, json={"ok": True}))
        result = run_retry_cycle(settings)

    assert result.delivered == 1
    assert status(settings).pending == 0


def test_report_anchor_events_spools_on_failure(tmp_path):
    settings = _settings(tmp_path)

    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/anchor").mock(return_value=Response(500))
        report_anchor_events(settings, agent_id="agent-1", leaves=["0xabc"], root="0xroot", tx_hash="0xtx")

    assert status(settings).pending == 1


def test_report_anchor_events_with_no_leaves_never_spools(tmp_path):
    settings = _settings(tmp_path)
    # No mock registered at all -- this must return before any HTTP call, matching
    # the existing early-return for an empty leaves list.
    report_anchor_events(settings, agent_id="agent-1", leaves=[], root="0xroot", tx_hash="0xtx")
    assert status(settings).pending == 0


def test_spool_disabled_never_enqueues(tmp_path):
    settings = _settings(tmp_path, spool_enabled=False)

    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(500))
        report_decision(settings, agent_id="agent-1", decision="allow")

    assert status(settings).pending == 0


def test_successful_report_never_touches_the_spool(tmp_path):
    settings = _settings(tmp_path)

    with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{_ORACLE_URL}/v1/audit/ingest").mock(return_value=Response(200, json={"ok": True}))
        report_decision(settings, agent_id="agent-1", decision="allow")

    assert status(settings).pending == 0
