"""
Telemetry batching: aggregates per-inference telemetry at the edge so we
proof/transmit in batches rather than one network+ZK-proof round trip per
event. Real, working code carried over from the old prototype unchanged in
behavior (it was never one of the mocked pieces).

The queue is **bounded**. It used to be an unbounded list, which turned an oracle outage
into a memory leak with a network trigger: `IntegrityClient.flush_telemetry` re-queues a
failed batch while new entries keep arriving, so the queue grew for as long as the oracle
stayed unreachable. Tolerable at low volume; not once collection widens (see
`docs/design/sdk-data-collection-strategy.md` F2).

Overflow drops the **oldest** entries. Recency is what scoring cares about, and the newest
events are also the ones describing whatever is going wrong right now. Every drop is counted
so the loss is reportable rather than silent — a collector that quietly discards data is
worse than one that fails loudly, because the resulting score still looks legitimate.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List


class TelemetryBatcher:
    def __init__(
        self,
        batch_size_limit: int = 50,
        flush_interval_sec: float = 5.0,
        max_queue_size: int = 10_000,
    ):
        """
        `max_queue_size` caps retained entries. The default holds roughly 200 full batches at
        the default `batch_size_limit` — a long outage's worth of telemetry while staying
        bounded in memory. Raise it for an agent whose telemetry matters more than its
        resident size; lower it on a memory-constrained host.
        """
        if max_queue_size < batch_size_limit:
            # A cap below one batch would drop entries faster than a flush could drain them,
            # so the queue could never deliver a full batch. Fail at construction rather than
            # silently under-delivering forever.
            raise ValueError(
                f"max_queue_size ({max_queue_size}) must be >= batch_size_limit ({batch_size_limit})"
            )
        self.batch_size_limit = batch_size_limit
        self.flush_interval_sec = flush_interval_sec
        self.max_queue_size = max_queue_size
        self.queue: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._dropped_total = 0

    def add_telemetry(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self.queue.append(data)
            overflow = len(self.queue) - self.max_queue_size
            if overflow > 0:
                # Drop from the front: oldest-first, keeping the most recent window.
                del self.queue[:overflow]
                self._dropped_total += overflow

    def should_flush(self) -> bool:
        with self._lock:
            if len(self.queue) >= self.batch_size_limit:
                return True
            return time.time() - self._last_flush >= self.flush_interval_sec and len(self.queue) > 0

    def get_batch_and_clear(self) -> List[Dict[str, Any]]:
        """Drains up to batch_size_limit items, leaving any overflow queued
        for the next cycle rather than growing the batch unboundedly."""
        with self._lock:
            drain_count = min(len(self.queue), self.batch_size_limit)
            batch = self.queue[:drain_count]
            self.queue = self.queue[drain_count:]
            self._last_flush = time.time()
            return batch

    def drain_dropped_count(self) -> int:
        """Entries dropped to overflow since the last call, resetting the counter.

        Draining rather than merely reading lets the caller report each loss exactly once
        (see `IntegrityClient.flush_telemetry`, which records it as a real metric so the
        oracle learns data went missing instead of receiving a quietly shorter history).
        """
        with self._lock:
            dropped = self._dropped_total
            self._dropped_total = 0
            return dropped

    def queue_depth(self) -> int:
        """Current retained entry count — for a health check or backpressure gauge."""
        with self._lock:
            return len(self.queue)
