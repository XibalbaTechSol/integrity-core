"""Explicit Cortex transport for canonical SDK envelopes.

The Cortex API authenticates the principal and derives the writable agent
partition from that principal. This adapter therefore sends the exact agent
identity as provenance, but never treats a payload agent_id as authority.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

import requests


class CortexTransport:
    def __init__(self, base_url: str, bearer_token: str, *, timeout: float = 10.0) -> None:
        if not bearer_token:
            raise ValueError("Cortex bearer_token is required; anonymous writes are refused")
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout

    def export(self, events: Iterable[Mapping[str, Any]], *, session_id: str | None = None) -> dict[str, Any]:
        rows = list(events)
        resolved_session = session_id or next((str(e.get("session_id")) for e in rows if e.get("session_id")), None)
        if not resolved_session:
            raise ValueError("Cortex export requires session_id for agent-scoped persistence")
        payload = {
            "session_id": resolved_session,
            "events": [
                {
                    "kind": "log",
                    "name": "integrity.sdk.event",
                    "trace_id": event.get("trace_id") or event.get("event_id"),
                    "span_id": event.get("span_id") or event.get("invocation_id") or event.get("event_id"),
                    "parent_span_id": event.get("parent_event_id"),
                    "prompt_id": event.get("invocation_id"),
                    "attributes": dict(event),
                    "idempotency_key": event.get("event_id"),
                }
                for event in rows
            ],
        }
        response = requests.post(
            f"{self.base_url}/api/otel/batch",
            json=payload,
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {"response": body}
