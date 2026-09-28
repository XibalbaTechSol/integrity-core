"""Aggregate-only usage and audit metrics for local-first products."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


class UsageMetricError(ValueError):
    """A metric contains an unsafe or malformed dimension."""


_DIMENSION_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_DECISIONS = frozenset({"permit", "deny", "log_only", "shadow"})


def _dimension(value: str, field: str) -> str:
    if not isinstance(value, str) or not _DIMENSION_RE.fullmatch(value):
        raise UsageMetricError(f"{field} must be a bounded metric dimension")
    return value


@dataclass(frozen=True)
class UsageSummary:
    tenant_id: str
    total_events: int
    total_duration_ms: float
    decisions: dict[str, int]
    event_classes: dict[str, int]
    audit: dict[str, int]
    redaction_status: str = "aggregate_only"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "integrity.usage-summary/1",
            "tenant_id": self.tenant_id,
            "total_events": self.total_events,
            "total_duration_ms": self.total_duration_ms,
            "decisions": dict(self.decisions),
            "event_classes": dict(self.event_classes),
            "audit": dict(self.audit),
            "redaction_status": self.redaction_status,
        }


class RedactedUsageMeter:
    """Collect only aggregate dimensions; raw payloads are not accepted by design."""

    def __init__(self, tenant_id: str):
        self.tenant_id = _dimension(tenant_id, "tenant_id")
        self._events = 0
        self._duration_ms = 0.0
        self._decisions: Counter[str] = Counter()
        self._event_classes: Counter[str] = Counter()
        self._audit: Counter[str] = Counter()

    @staticmethod
    def _count(value: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise UsageMetricError("count must be a positive integer")
        return value

    def record_usage(self, event_class: str, decision: str, *, count: int = 1, duration_ms: float = 0.0) -> None:
        event_class = _dimension(event_class, "event_class")
        if decision not in _DECISIONS:
            raise UsageMetricError(f"decision must be one of {sorted(_DECISIONS)}")
        count = self._count(count)
        if not isinstance(duration_ms, (int, float)) or isinstance(duration_ms, bool) or not math.isfinite(duration_ms) or duration_ms < 0:
            raise UsageMetricError("duration_ms must be a finite non-negative number")
        self._events += count
        self._duration_ms += float(duration_ms)
        self._decisions[decision] += count
        self._event_classes[event_class] += count

    def record_audit(self, operation: str, outcome: str, *, count: int = 1) -> None:
        operation = _dimension(operation, "operation")
        outcome = _dimension(outcome, "outcome")
        count = self._count(count)
        self._audit[f"{operation}.{outcome}"] += count

    def summary(self) -> UsageSummary:
        return UsageSummary(
            tenant_id=self.tenant_id,
            total_events=self._events,
            total_duration_ms=self._duration_ms,
            decisions=dict(sorted(self._decisions.items())),
            event_classes=dict(sorted(self._event_classes.items())),
            audit=dict(sorted(self._audit.items())),
        )
