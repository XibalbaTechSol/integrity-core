"""
Proves the lifespan shutdown drain actually waits for in-flight audit reports
(audit E16, docs/design/e2e-audit-2026-07-31.md).

`_report_decision_background` dispatches via `asyncio.ensure_future(asyncio.to_thread(...))`
and nothing in the request path awaits it -- the HTTP response returns immediately. Before
the fix, `lifespan`'s shutdown phase cancelled the score-sync task and returned, so a report
still in flight when the process exits was silently dropped. The fix makes shutdown await
`_audit_report_tasks` (bounded, so a genuinely stuck report can't hang shutdown forever).

The test proves this WITHOUT calling `_await_reported` (which would mask the bug by giving
the background thread time to finish on its own regardless of whether shutdown waits for
it) -- it exits the TestClient context immediately after the request returns, so the ONLY
thing that can make the report land is the shutdown drain itself.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.merkle import MerkleBatcher
from tests.helpers import new_agent, sign_commitment


def test_shutdown_waits_for_in_flight_audit_report(real_opa_server, monkeypatch):
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "batcher", MerkleBatcher(batch_size=999))
    main_module.circuit_breaker.reset()
    main_module.nonce_store.reset()

    reported: list[dict] = []

    def _slow_report_decision(settings, **kw):
        # Long enough that the request handler returns well before this finishes,
        # short enough to keep the test fast. Simulates a real network call in flight.
        time.sleep(0.3)
        reported.append(kw)

    monkeypatch.setattr(main_module.audit_module, "report_decision", _slow_report_decision)

    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)

    with TestClient(main_module.app) as client:
        resp = client.post("/v1/bcc/intercept", json=payload)
        assert resp.json()["authorized"] is True
        # Deliberately NOT waiting here. If the background task hasn't even been
        # scheduled onto a thread yet, that's fine -- `__exit__` triggers shutdown,
        # and the drain must still catch it.
        assert reported == [], "test setup invariant: the report must not have landed yet"

    # Context manager has exited -> lifespan shutdown ran -> the drain must have
    # awaited the pending task before returning control here.
    assert reported, (
        "audit report was dropped on shutdown -- the drain in lifespan() either "
        "isn't running or isn't actually waiting for _audit_report_tasks"
    )
    assert reported[0]["decision"] == "allow"


@pytest.mark.asyncio
async def test_shutdown_drain_gives_up_after_10s_and_logs_it(monkeypatch, caplog):
    """
    The DRAIN is bounded -- the `asyncio.wait(..., timeout=10.0)` in `lifespan()`
    must give up and log a warning rather than await a stuck report forever.

    Deliberately bypasses `TestClient` and `asyncio.to_thread` entirely and drives
    `lifespan()` directly, seeding `_audit_report_tasks` with a plain asyncio Task
    that awaits an `Event` nobody sets. First attempt at this test went through
    `TestClient` + a real `to_thread`-blocked call and measured `with` block exit
    time -- that conflated the drain's own bound with `asyncio.to_thread`'s
    executor-thread join, which is a SEPARATE mechanism: confirmed directly by a
    standalone repro that an orphaned `to_thread` call delays `asyncio.run()`'s
    own cleanup (`loop.shutdown_default_executor()`) regardless of what the
    awaiting coroutine already gave up on. That is real and is documented as a
    known residual limit in `lifespan()`'s comment -- daemon threads would trade
    it for reports killed mid-write, worse for an evidence path -- but it is not
    what this test is for. A pending asyncio Task (no OS thread involved) isolates
    exactly the code path this fix changed.
    """
    # Isolation from the (unrelated) score-sync background task: no real network
    # call should happen just because this test entered lifespan().
    monkeypatch.setattr(main_module.default_settings, "score_sync_enabled", False)

    never_set = asyncio.Event()
    hung_task = asyncio.ensure_future(never_set.wait())
    main_module._audit_report_tasks.add(hung_task)

    try:
        with caplog.at_level(logging.WARNING, logger="bcc_middleware"):
            started = time.monotonic()
            async with main_module.lifespan(main_module.app):
                pass  # enter and immediately exit -> runs the shutdown drain
            drain_elapsed = time.monotonic() - started
    finally:
        hung_task.cancel()
        main_module._audit_report_tasks.discard(hung_task)

    assert any("still in flight" in r.message for r in caplog.records), (
        "the drain never logged its give-up warning -- either it isn't running, "
        "or it isn't bounded"
    )
    assert 9.5 <= drain_elapsed <= 11.5, (
        f"drain returned at {drain_elapsed:.2f}s, expected close to its 10s bound"
    )
