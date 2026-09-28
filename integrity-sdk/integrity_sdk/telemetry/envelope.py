"""Versioned, privacy-aware Integrity telemetry envelopes.

This is the SDK's language-neutral boundary.  The Oracle's signed ingestion
request remains a separate protocol envelope; this record is the canonical
event shape used by local transports and adapters before projection to Oracle,
Cortex, Shield, or the dashboard.
"""
from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..core.jcs import canonical_bytes as _jcs_canonical_bytes
from ..security.redactor import redact_text

#: Bumped 1 -> 2 (docs/EXECUTION_PLAN.md A3) when `canonical_bytes` below switched
#: from the ad-hoc `json.dumps(sort_keys=True, ensure_ascii=False)` encoding to
#: RFC 8785 (JCS). `content_hash`/`payload_hash` computed under schema_version 1
#: do not match the same payload hashed under 2 -- JCS sorts keys by UTF-16 code
#: unit (ASCII-equivalent here) but formats numbers per ECMAScript's
#: `Number.prototype.toString`, which can differ from Python's `repr` for floats.
SCHEMA_VERSION = 2
SECRET_KEY = re.compile(r"(private.?key|seed|password|api.?key|token|cookie|authorization|credential|keystore|recovery)", re.I)

EVENT_TYPES = frozenset({
    "agent_initialized", "agent_identity_loaded", "agent_identity_mismatch",
    "session_started", "session_ended", "prompt_received", "context_assembled",
    "model_request_started", "model_response_received", "token_usage_recorded",
    "tool_call_started", "tool_result_received", "tool_call_failed",
    "memory_read", "memory_write", "memory_superseded", "memory_forgotten",
    "retrieval_started", "retrieval_completed", "retrieval_degraded",
    "contract_read", "contract_write_requested", "transaction_submitted",
    "transaction_confirmed", "transaction_failed", "bcc_intent_created",
    "bcc_intent_signed", "bcc_intent_verified", "merkle_root_observed",
    "proof_generated", "proof_verified", "security_decision_received",
    "shield_action_allowed", "shield_action_denied", "agent_registration_started",
    "agent_registration_completed", "agent_registration_failed", "configuration_changed",
    "provider_unavailable", "telemetry_delivery_failed",
})


def _safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): ("<redacted:secret-key>" if SECRET_KEY.search(str(k)) else _safe(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, str):
        return redact_text(value).text
    return value


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    """RFC 8785 (JCS) canonical bytes -- the SDK's one hashed encoding (contract C1).

    Delegates to `integrity_sdk.core.jcs`; kept as a local wrapper so this module's
    existing call sites (and any external importer of this name) are unaffected by
    where the implementation lives.
    """
    return _jcs_canonical_bytes(value)


@dataclass(frozen=True)
class TelemetryEnvelope:
    event_type: str
    agent_id: str
    did: str | None = None
    harness: str | None = None
    principal: str | None = None
    device_id: str | None = None
    session_id: str | None = None
    invocation_id: str | None = None
    parent_event_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    timestamp_source: str = "wall_clock"
    monotonic_ns: int = field(default_factory=time.monotonic_ns)
    payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    privacy_classification: str = "internal"
    redaction_status: str = "applied"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"unsupported Integrity event_type: {self.event_type}")
        if not self.agent_id:
            raise ValueError("agent_id is required")

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION, "event_id": self.event_id,
            "event_type": self.event_type, "agent_id": self.agent_id, "did": self.did,
            "harness": self.harness, "principal": self.principal, "device_id": self.device_id,
            "session_id": self.session_id, "invocation_id": self.invocation_id,
            "parent_event_id": self.parent_event_id, "trace_id": self.trace_id,
            "span_id": self.span_id, "timestamp": self.timestamp,
            "timestamp_source": self.timestamp_source, "monotonic_ns": self.monotonic_ns,
            "payload": _safe(self.payload), "metadata": _safe(self.metadata),
            "privacy_classification": self.privacy_classification,
            "redaction_status": self.redaction_status,
        }
        body["content_hash"] = hashlib.sha256(canonical_bytes(body["payload"])).hexdigest()
        body["payload_hash"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
        return body
