"""Synthetic third-party adapter used by the local conformance kit."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from ..core.jcs import canonical_bytes


def adapt_event(event: Mapping[str, Any]) -> dict[str, str]:
    """Project a local event to identity plus a content commitment, never content."""
    payload = event.get("payload")
    return {
        "schema_version": "integrity.adapter-event/1",
        "idempotency_key": str(event["event_id"]),
        "event_type": str(event["event_type"]),
        "tenant_id": str(event["tenant_id"]),
        "agent_id": str(event["agent_id"]),
        "payload_hash": "sha256:" + hashlib.sha256(canonical_bytes(payload)).hexdigest(),
    }
