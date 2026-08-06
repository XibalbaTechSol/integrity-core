"""Reliability of the telemetry queue and the flush cadence — F2 and F3 from
`docs/design/sdk-data-collection-strategy.md`.

These are the properties that turn from cosmetic into load-bearing once collection widens:
an unbounded queue becomes a memory leak with a network trigger, and an interval that only
elapses when the next event arrives means a quiet agent never reports its tail.
"""

from __future__ import annotations

import time

import pytest

from integrity_sdk.batcher import TelemetryBatcher
from integrity_sdk.client import IntegrityClient


# --- F2: bounded queue -------------------------------------------------------------------


def test_queue_is_bounded_and_drops_oldest_first() -> None:
    b = TelemetryBatcher(batch_size_limit=2, flush_interval_sec=999, max_queue_size=3)
    for i in range(5):
        b.add_telemetry({"i": i})

    assert b.queue_depth() == 3, "the queue must not grow past max_queue_size"
    # Oldest-first: entries 0 and 1 are gone, the most recent window survives. Recency is
    # what scoring wants, and the newest events describe whatever is going wrong now.
    assert [e["i"] for e in b.queue] == [2, 3, 4]


def test_dropped_count_is_reported_exactly_once() -> None:
    b = TelemetryBatcher(batch_size_limit=2, flush_interval_sec=999, max_queue_size=2)
    for i in range(6):
        b.add_telemetry({"i": i})

    assert b.drain_dropped_count() == 4, "every dropped entry must be counted"
    assert b.drain_dropped_count() == 0, "draining resets, so a loss is never double-reported"


def test_max_queue_below_batch_size_is_rejected_at_construction() -> None:
    """A cap under one batch could never deliver a full batch, so it fails loudly rather
    than silently under-delivering forever."""
    with pytest.raises(ValueError, match="max_queue_size"):
        TelemetryBatcher(batch_size_limit=50, flush_interval_sec=5.0, max_queue_size=10)


def test_client_reports_dropped_entries_as_a_metric(captured_posts) -> None:
    """A shortened history must be explained, not just shorter — otherwise the score looks
    legitimate while resting on data that was silently discarded."""
    client = IntegrityClient(
        "agent-drop",
        auto_flush=False,
        background_flush=False,
        batch_size_limit=2,
        max_queue_size=2,
    )
    for i in range(5):
        client.log_telemetry({"text_output": f"entry-{i}"})

    client.flush_telemetry()

    spans = captured_posts[0]["json"]["otel_spans"]
    metric_blocks = [s for s in spans if s.get("kind") == "custom_metrics"]
    assert metric_blocks, f"expected a custom_metrics block carrying the drop count: {spans}"
    # `metrics` is a name -> aggregate mapping (see MetricsRegistry.drain), not a list.
    recorded = metric_blocks[0]["metrics"]
    assert "integrity.telemetry.dropped_entries" in recorded, f"drop count must reach the oracle: {recorded}"
    # 5 entries logged into a queue capped at 2 means 3 were dropped — assert the VALUE, not
    # merely that the key exists, or a wrong count would pass.
    assert recorded["integrity.telemetry.dropped_entries"]["value"] == 3.0


# --- F3: the interval flush must be driven by a clock ------------------------------------


def test_background_flusher_flushes_without_any_further_events(captured_posts) -> None:
    """The regression this exists for: previously `should_flush()` was only consulted from
    `log_telemetry`, so an agent that logged once and went quiet never flushed at all."""
    client = IntegrityClient(
        "agent-quiet",
        auto_flush=True,
        background_flush=True,
        batch_size_limit=1000,     # far above what we log, so only the INTERVAL can trigger
        flush_interval_sec=0.2,
    )
    try:
        client.log_telemetry({"text_output": "one event, then silence"})

        deadline = time.time() + 5.0
        while not captured_posts and time.time() < deadline:
            time.sleep(0.05)

        assert captured_posts, "a quiet agent must still flush its tail on the interval"
    finally:
        client.close()


def test_close_is_idempotent_and_flushes_remaining(captured_posts) -> None:
    client = IntegrityClient(
        "agent-close",
        auto_flush=True,
        background_flush=True,
        batch_size_limit=1000,
        flush_interval_sec=999,   # the interval will never fire; close() must do the work
    )
    client.log_telemetry({"text_output": "must not be lost"})

    client.close()
    assert captured_posts, "close() must flush what is still queued"

    before = len(captured_posts)
    client.close()  # second call must be a no-op, not a duplicate send or an error
    assert len(captured_posts) == before


def test_no_background_thread_when_auto_flush_is_off() -> None:
    """Opting out of implicit flushing must not silently get a thread anyway — unit tests
    and callers wanting deterministic batches depend on that."""
    client = IntegrityClient("agent-manual", auto_flush=False)
    assert client._flusher is None
