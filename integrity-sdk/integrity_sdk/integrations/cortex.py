"""Explicit Cortex transport for canonical SDK envelopes.

The Cortex API authenticates the principal and derives the writable agent
partition from that principal. This adapter therefore sends the exact agent
identity as provenance, but never treats a payload agent_id as authority.
"""
from __future__ import annotations

import time
import json
from typing import Any, Iterable, Mapping

import requests


from ..collection import CONTENT_KEYS

_MAX_EVENT_ATTRIBUTE_BYTES = 16_384
_CONTENT_MARKER = "<content reduced: event byte cap>"


class CortexTransport:
    def __init__(self, base_url: str, bearer_token: str, *, timeout: float = 10.0) -> None:
        if not bearer_token:
            raise ValueError("Cortex bearer_token is required; anonymous writes are refused")
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.last_attempts: list[dict[str, Any]] = []
        self.last_exported_event_ids: list[str] = []

    def export(self, events: Iterable[Mapping[str, Any]], *, session_id: str | None = None,
               max_attempts: int = 3, backoff_seconds: float = 0.2) -> dict[str, Any]:
        # SDKAgent applies the shared collection policy before persisting or
        # dispatching the canonical envelope. The adapter enforces only the
        # final per-row byte ceiling and preserves every event class.
        rows = [dict(event) for event in events]
        self.last_exported_event_ids = [str(event["event_id"]) for event in rows if event.get("event_id")]
        if not rows:
            raise ValueError("Cortex export requires at least one event")
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
                    "attributes": _bounded_attributes(event),
                    "idempotency_key": event.get("event_id"),
                }
                for event in rows
            ],
        }
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        last_error: Exception | None = None
        self.last_attempts = []
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/api/otel/batch", json=payload,
                    headers={"Authorization": f"Bearer {self.bearer_token}"},
                    timeout=self.timeout,
                )
                # Retry transient server/rate-limit responses, but surface
                # client/auth failures immediately rather than hammering a
                # boundary that has already rejected the request.
                status = getattr(response, "status_code", 200)
                if status >= 500 or status == 429:
                    response.raise_for_status()
                response.raise_for_status()
                body = response.json()
                self.last_attempts.append({"attempt": attempt, "status": "acknowledged", "error": None})
                return body if isinstance(body, dict) else {"response": body}
            except requests.RequestException as exc:
                last_error = exc
                self.last_attempts.append({"attempt": attempt, "status": "failed", "error": str(exc)})
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = status is None or status >= 500 or status == 429
                if not retryable or attempt == max_attempts:
                    raise
                if backoff_seconds:
                    time.sleep(backoff_seconds * (2 ** (attempt - 1)))
        assert last_error is not None
        raise last_error


def _bounded_attributes(event: Mapping[str, Any]) -> dict[str, Any]:
    """Keep every event class and its sanitized context under a hard per-row cap."""
    attributes = dict(event)
    if len(json.dumps(attributes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= _MAX_EVENT_ATTRIBUTE_BYTES:
        return attributes

    def candidates(node: Any, path: tuple[str, ...] = ()) -> list[tuple[int, tuple[str, ...]]]:
        found: list[tuple[int, tuple[str, ...]]] = []
        if isinstance(node, Mapping):
            for key, value in node.items():
                child_path = (*path, str(key))
                if str(key).lower() in CONTENT_KEYS:
                    found.append((len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")), child_path))
                else:
                    found.extend(candidates(value, child_path))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found.extend(candidates(value, (*path, str(index))))
        return found

    def parent(path: tuple[str, ...]) -> tuple[Any, str]:
        node: Any = attributes
        for key in path[:-1]:
            node = node[int(key)] if isinstance(node, list) else node[key]
        return node, path[-1]

    for _, path in sorted(candidates(attributes), reverse=True):
        container, key = parent(path)
        old = container[int(key)] if isinstance(container, list) else container[key]
        if isinstance(old, str) and len(old) > 256:
            replacement: Any = old[:128] + "…[content capped]"
        else:
            replacement = _CONTENT_MARKER
        if isinstance(container, list):
            container[int(key)] = replacement
        else:
            container[key] = replacement
        if len(json.dumps(attributes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= _MAX_EVENT_ATTRIBUTE_BYTES:
            return attributes

    # A pathological structural payload still must not create an unbounded SQLite row.
    return {
        key: event[key]
        for key in ("schema_version", "event_id", "event_type", "timestamp", "agent_id", "did", "session_id", "invocation_id")
        if event.get(key) is not None
    } | {"payload": _CONTENT_MARKER, "metadata": _CONTENT_MARKER}
