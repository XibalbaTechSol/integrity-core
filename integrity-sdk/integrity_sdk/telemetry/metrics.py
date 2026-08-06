"""
Custom metrics API.

The Agent Integrity Score (AIS) formula is fixed by
docs/INTERFACE_CONTRACT.md §4.3 — `entropy/grounding/sacrifice/compliance`
with pinned default weights — and is computed *only* by
`integrity-oracle/scoring-core`. This SDK does not, and must not,
recompute AIS locally (every other package calls the oracle's
`/v1/agent/{id}/ais` endpoint rather than each reimplementing the formula).

But agents/operators routinely want to track other numbers alongside that —
p99 tool latency, retry counts, a task-specific quality score, whatever —
without waiting for the oracle's scoring formula to grow a new dimension
every time someone needs one. This module is the escape hatch: an
open-ended, named-metric recording API. Recorded values are aggregated
client-side and attached to the outgoing telemetry envelope under
`custom_metrics`, alongside (never mixed into) the fixed AIS inputs.
Whether/how integrity-oracle scores on `custom_metrics` is explicitly out of
scope here — that's separate, not-yet-decided oracle-side work. Our job is
only to capture and transmit them reliably.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_VALID_AGGREGATIONS = {"last", "sum", "avg", "min", "max", "count"}


@dataclass
class MetricDefinition:
    """Declarative metric metadata. Defining a metric ahead of recording is
    optional — `record_metric` auto-registers an implicit `last`-aggregated,
    unitless definition the first time it sees a new name — but explicit
    definitions let a caller pin the aggregation semantics (e.g. "this is a
    p99 latency, average the per-flush samples" vs. "this is a counter, sum
    the samples")."""

    name: str
    aggregation: str = "last"
    unit: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self) -> None:
        if self.aggregation not in _VALID_AGGREGATIONS:
            raise ValueError(
                f"Unknown aggregation {self.aggregation!r} for metric {self.name!r}; "
                f"expected one of {sorted(_VALID_AGGREGATIONS)}"
            )


@dataclass
class _MetricSample:
    value: float
    tags: Dict[str, str]
    timestamp: float


class MetricsRegistry:
    """
    Per-client buffer of metric definitions + recorded samples, drained on
    every telemetry flush (see client.py's `_process_and_send`) the same way
    the telemetry batcher drains its queue. Thread-safe: agents commonly
    record metrics from multiple worker threads / tool-call callbacks.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._definitions: Dict[str, MetricDefinition] = {}
        self._samples: Dict[str, List[_MetricSample]] = {}

    def define(self, definition: MetricDefinition) -> None:
        with self._lock:
            self._definitions[definition.name] = definition

    def record(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            self._definitions.setdefault(name, MetricDefinition(name=name))
            self._samples.setdefault(name, []).append(
                _MetricSample(value=float(value), tags=tags or {}, timestamp=time.time())
            )

    def drain(self) -> Dict[str, Any]:
        """
        Aggregate every metric's samples recorded since the last drain
        according to its definition's `aggregation`, clear the buffer, and
        return a JSON-serializable dict keyed by metric name — this is what
        gets attached to the telemetry envelope as `custom_metrics`.
        """
        with self._lock:
            result: Dict[str, Any] = {}
            for name, samples in self._samples.items():
                if not samples:
                    continue
                definition = self._definitions[name]
                values = [s.value for s in samples]
                aggregated = self._aggregate(definition.aggregation, values)
                result[name] = {
                    "value": aggregated,
                    "aggregation": definition.aggregation,
                    "unit": definition.unit,
                    "sample_count": len(values),
                    "samples": [
                        {"value": s.value, "tags": s.tags, "timestamp": s.timestamp}
                        for s in samples
                    ],
                }
            self._samples.clear()
            return result

    @staticmethod
    def _aggregate(aggregation: str, values: List[float]) -> float:
        if aggregation == "sum":
            return sum(values)
        if aggregation == "avg":
            return sum(values) / len(values)
        if aggregation == "min":
            return min(values)
        if aggregation == "max":
            return max(values)
        if aggregation == "count":
            return float(len(values))
        return values[-1]  # "last"
