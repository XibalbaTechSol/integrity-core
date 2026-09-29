"""Dependency-light conformance checks for deterministic third-party adapters."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any


class AdapterConformanceError(ValueError):
    """An adapter does not satisfy the local deterministic contract."""


def run_adapter_conformance(adapter: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> dict[str, Any]:
    """Run the no-network, no-filesystem adapter contract against a fixed vector."""
    vector = {
        "event_id": "evt-conformance-001",
        "event_type": "tool_call_started",
        "tenant_id": "tenant-a",
        "agent_id": "did:integrity:adapter-agent",
        "payload": {"tool_name": "synthetic-search", "content": "must not be exported"},
    }
    first = dict(adapter(vector))
    second = dict(adapter(vector))
    if json.dumps(first, sort_keys=True, separators=(",", ":")) != json.dumps(second, sort_keys=True, separators=(",", ":")):
        raise AdapterConformanceError("adapter output is not deterministic")
    required = {"schema_version", "idempotency_key", "event_type", "tenant_id", "agent_id", "payload_hash"}
    if set(first) != required:
        raise AdapterConformanceError("adapter output does not match the required bounded schema")
    if first["idempotency_key"] != vector["event_id"] or first["tenant_id"] != vector["tenant_id"]:
        raise AdapterConformanceError("adapter changed identity or idempotency scope")
    if "content" in json.dumps(first):
        raise AdapterConformanceError("adapter exported raw content")
    return first
