from __future__ import annotations

import pytest

from integrity_sdk.core import RedactedUsageMeter, UsageMetricError


def test_usage_summary_is_aggregate_only():
    meter = RedactedUsageMeter("tenant-lab")
    meter.record_usage("agent.tool_call", "deny", count=2, duration_ms=4.5)
    meter.record_usage("device.sensor", "permit")
    meter.record_audit("receipt.verify", "ok", count=3)

    result = meter.summary().to_dict()
    assert result["redaction_status"] == "aggregate_only"
    assert result["total_events"] == 3
    assert result["decisions"] == {"deny": 2, "permit": 1}
    assert result["audit"] == {"receipt.verify.ok": 3}
    assert "prompt" not in result and "content" not in result


def test_unsafe_dimensions_and_values_are_refused():
    meter = RedactedUsageMeter("tenant-lab")
    with pytest.raises(UsageMetricError):
        meter.record_usage("raw prompt text", "deny")
    with pytest.raises(UsageMetricError):
        meter.record_usage("agent.tool_call", "permit", duration_ms=float("nan"))
    with pytest.raises(UsageMetricError):
        meter.record_audit("receipt", "ok", count=0)
