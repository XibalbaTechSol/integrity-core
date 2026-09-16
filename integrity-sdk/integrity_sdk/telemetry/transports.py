"""Generic authenticated telemetry transports.

These adapters intentionally expose transport capabilities without making a
remote projection canonical. Each request carries the exact event IDs as
idempotency keys and retries only transient failures.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

import requests


def _timestamp_ns(value: Any) -> str:
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
        return str(int(stamp.timestamp() * 1_000_000_000))
    except (TypeError, ValueError, OverflowError):
        return str(int(time.time() * 1_000_000_000))


def _records(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(event) for event in events]
    if not rows:
        raise ValueError("telemetry transport requires at least one event")
    missing = [str(event.get("event_id")) for event in rows if not event.get("event_id")]
    if missing:
        raise ValueError("every telemetry event requires event_id")
    return rows


class HttpTelemetryTransport:
    def __init__(self, base_url: str, *, bearer_token: str | None = None,
                 path: str = "/v1/telemetry", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.path = "/" + path.lstrip("/")
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.last_attempts: list[dict[str, Any]] = []

    def export(self, events: Iterable[Mapping[str, Any]], *, max_attempts: int = 3,
               backoff_seconds: float = 0.2) -> dict[str, Any]:
        rows = _records(events)
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        headers = {"Idempotency-Key": ",".join(event["event_id"] for event in rows)}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        request = {"schema_version": 1, "events": rows}
        self.last_attempts = []
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(f"{self.base_url}{self.path}", json=request,
                                         headers=headers, timeout=self.timeout)
                status = getattr(response, "status_code", 200)
                if status >= 500 or status == 429:
                    response.raise_for_status()
                response.raise_for_status()
                self.last_attempts.append({"attempt": attempt, "status": "acknowledged", "error": None})
                body = response.json()
                return body if isinstance(body, dict) else {"response": body}
            except requests.RequestException as exc:
                self.last_attempts.append({"attempt": attempt, "status": "failed", "error": str(exc)})
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status < 500 and status != 429:
                    raise
                if attempt == max_attempts:
                    raise
                if backoff_seconds:
                    time.sleep(backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError("unreachable")


class OTLPHttpTransport(HttpTelemetryTransport):
    """OTLP/HTTP JSON log transport for collectors exposing `/v1/logs`."""

    def __init__(self, base_url: str, *, bearer_token: str | None = None,
                 timeout: float = 10.0) -> None:
        super().__init__(base_url, bearer_token=bearer_token, path="/v1/logs", timeout=timeout)

    def export(self, events: Iterable[Mapping[str, Any]], **kwargs: Any) -> dict[str, Any]:
        rows = _records(events)
        # Use the OTLP JSON shape while retaining the complete envelope in
        # attributes. The collector is an observability projection, not the
        # protocol's signed telemetry authority.
        self._otlp_rows = {"resourceLogs": [{"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "integrity-agent"}}]}, "scopeLogs": [{"logRecords": [{"timeUnixNano": _timestamp_ns(event.get("timestamp")), "body": {"stringValue": event["event_type"]}, "attributes": [{"key": "integrity.event", "value": {"stringValue": str(event)}}]} for event in rows]}]}]}
        return self._export_payload(self._otlp_rows, rows, **kwargs)

    def _export_payload(self, payload: Any, rows: list[dict[str, Any]], *, max_attempts: int = 3, backoff_seconds: float = 0.2) -> dict[str, Any]:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        headers = {"Content-Type": "application/json", "Idempotency-Key": ",".join(event["event_id"] for event in rows)}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        self.last_attempts = []
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(f"{self.base_url}{self.path}", json=payload, headers=headers, timeout=self.timeout)
                status = getattr(response, "status_code", 200)
                if status >= 500 or status == 429:
                    response.raise_for_status()
                response.raise_for_status()
                self.last_attempts.append({"attempt": attempt, "status": "acknowledged", "error": None})
                if not getattr(response, "content", b""):
                    return {"accepted": True}
                body = response.json()
                return body if isinstance(body, dict) else {"response": body}
            except requests.RequestException as exc:
                self.last_attempts.append({"attempt": attempt, "status": "failed", "error": str(exc)})
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status < 500 and status != 429 or attempt == max_attempts:
                    raise
                if backoff_seconds:
                    time.sleep(backoff_seconds * (2 ** (attempt - 1)))
        raise RuntimeError("unreachable")


class MCPTelemetryTransport:
    """Transport for an installed MCP client supplied by the host harness."""

    def __init__(self, call_tool: Callable[[str, Mapping[str, Any]], Any], *, tool_name: str = "integrity_ingest_telemetry") -> None:
        self.call_tool = call_tool
        self.tool_name = tool_name

    def export(self, events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        rows = _records(events)
        result = self.call_tool(self.tool_name, {"schema_version": 1, "events": rows, "idempotency_keys": [event["event_id"] for event in rows]})
        return result if isinstance(result, dict) else {"response": result}
