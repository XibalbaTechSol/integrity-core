"""Pair-bound Shield correlation helpers.

This module deliberately does not make policy decisions. Shield remains the
enforcement authority; the SDK records the exact decision and identifiers.
"""
from __future__ import annotations

from typing import Any, Mapping


def action_context(*, agent_id: str, device_id: str, invocation_id: str, action: str, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    values = {"agent_id": agent_id, "device_id": device_id, "invocation_id": invocation_id, "action": action, "metadata": dict(metadata or {})}
    if not all(values[k] for k in ("agent_id", "device_id", "invocation_id", "action")):
        raise ValueError("agent_id, device_id, invocation_id, and action are required for Shield correlation")
    return values


def decision_event(context: Mapping[str, Any], *, decision: str, reason: str, enforcement: str | None = None) -> dict[str, Any]:
    if decision not in {"allow", "deny", "contain", "escalate"}:
        raise ValueError("unsupported Shield decision")
    required = ("agent_id", "device_id", "invocation_id", "action")
    if any(not context.get(key) for key in required):
        raise ValueError("incomplete Shield action context")
    return {**dict(context), "decision": decision, "reason": reason, "enforcement_outcome": enforcement or decision}
