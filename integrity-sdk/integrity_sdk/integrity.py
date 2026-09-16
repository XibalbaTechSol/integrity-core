"""One-line and explicit entry points for the Integrity SDK."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Mapping

from .agent_runtime import IntegrityAgent
from .telemetry.envelope import TelemetryEnvelope
from .telemetry.local_store import LocalEventStore
from .integrations.cortex import CortexTransport
from .integrations.shield import action_context, decision_event


class SDKAgent:
    """Developer façade over the canonical identity runtime and local event boundary."""
    def __init__(self, runtime: IntegrityAgent, store: LocalEventStore | None = None) -> None:
        self.runtime, self.store = runtime, store

    @property
    def agent_id(self) -> str: return self.runtime.agent_slug
    @property
    def did(self) -> str: return self.runtime.did

    def emit(self, event_type: str, *, payload: Mapping[str, Any] | None = None, metadata: Mapping[str, Any] | None = None, **ids: Any) -> dict[str, Any]:
        event = TelemetryEnvelope(event_type=event_type, agent_id=self.runtime.agent_slug, did=self.did, harness=self.runtime.harness, principal=self.runtime.principal, device_id=self.runtime.device_id, payload=payload or {}, metadata=metadata or {}, session_id=ids.pop("session_id", getattr(self.runtime, "_session_id", None)), **ids).to_dict()
        if self.store is not None: self.store.append(event)
        self.runtime.emit(event_type, telemetry_envelope=event)
        return event

    def flush(self) -> bool: return self.runtime.flush()
    def start_session(self, session_id: str, **fields: Any) -> dict[str, Any]:
        self.runtime.start_session(session_id, emit=False, **fields)
        return self.emit("session_started", session_id=session_id, payload=fields)

    def end_session(self, session_id: str | None = None, **fields: Any) -> dict[str, Any]:
        sid = session_id or getattr(self.runtime, "_session_id", None)
        event = self.emit("session_ended", session_id=sid, payload=fields)
        self.runtime.end_session(sid, emit=False, **fields)
        return event

    def prompt(self, content: str | None = None, *, metadata: Mapping[str, Any] | None = None,
               session_id: str | None = None, **fields: Any) -> dict[str, Any]:
        """Record prompt content or metadata according to the active collection policy."""
        payload = dict(fields)
        if content is not None:
            payload["content"] = content
        return self.emit("prompt_received", payload=payload, metadata=metadata,
                         session_id=session_id or getattr(self.runtime, "_session_id", None))

    def response(self, content: str | None = None, *, metadata: Mapping[str, Any] | None = None,
                 session_id: str | None = None, **fields: Any) -> dict[str, Any]:
        """Record a model response while keeping response metadata distinct."""
        payload = dict(fields)
        if content is not None:
            payload["content"] = content
        return self.emit("model_response_received", payload=payload, metadata=metadata,
                         session_id=session_id or getattr(self.runtime, "_session_id", None))

    def model_request(self, *, metadata: Mapping[str, Any] | None = None,
                      session_id: str | None = None, **fields: Any) -> dict[str, Any]:
        return self.emit("model_request_started", payload=fields, metadata=metadata,
                         session_id=session_id or getattr(self.runtime, "_session_id", None))

    def token_usage(self, usage: Mapping[str, Any], *, metadata: Mapping[str, Any] | None = None,
                    session_id: str | None = None) -> dict[str, Any]:
        return self.emit("token_usage_recorded", payload={"usage": dict(usage)}, metadata=metadata,
                         session_id=session_id or getattr(self.runtime, "_session_id", None))

    def tool_call(self, tool_name: str, *, arguments: Any = None,
                  metadata: Mapping[str, Any] | None = None, session_id: str | None = None,
                  **fields: Any) -> dict[str, Any]:
        payload = {"tool_name": tool_name, "arguments": arguments, **fields}
        return self.emit("tool_call_started", payload=payload, metadata=metadata,
                         session_id=session_id or getattr(self.runtime, "_session_id", None))

    def tool_result(self, tool_name: str, *, result: Any = None, error: Any = None,
                    metadata: Mapping[str, Any] | None = None, session_id: str | None = None,
                    **fields: Any) -> dict[str, Any]:
        payload = {"tool_name": tool_name, "result": result, "error": error, **fields}
        event_type = "tool_call_failed" if error is not None else "tool_result_received"
        return self.emit(event_type, payload=payload, metadata=metadata,
                         session_id=session_id or getattr(self.runtime, "_session_id", None))

    def memory_event(self, operation: str, *, reference: str | None = None,
                     metadata: Mapping[str, Any] | None = None, session_id: str | None = None,
                     **fields: Any) -> dict[str, Any]:
        event_map = {
            "read": "memory_read", "write": "memory_write", "supersede": "memory_superseded",
            "forget": "memory_forgotten",
        }
        try:
            event_type = event_map[operation]
        except KeyError as exc:
            raise ValueError("operation must be read, write, supersede, or forget") from exc
        payload = {"reference": reference, **fields}
        return self.emit(event_type, payload=payload, metadata=metadata,
                         session_id=session_id or getattr(self.runtime, "_session_id", None))

    @contextmanager
    def session(self, session_id: str, **fields: Any):
        """Open and close one session, preserving the original exception."""
        self.start_session(session_id, **fields)
        try:
            yield self
        finally:
            self.end_session(session_id)

    def export_cortex(self, *, base_url: str, bearer_token: str, events: list[Mapping[str, Any]] | None = None, session_id: str | None = None) -> dict[str, Any]:
        """Export already-redacted canonical events through Cortex's authenticated boundary."""
        rows = events or []
        return CortexTransport(base_url, bearer_token).export(rows, session_id=session_id)

    def record_shield_decision(self, *, device_id: str | None = None, invocation_id: str, action: str, decision: str, reason: str, enforcement: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Record a Shield decision; this does not evaluate or bypass Shield policy."""
        context = action_context(agent_id=self.agent_id, device_id=device_id or self.runtime.device_id or "", invocation_id=invocation_id, action=action, metadata=metadata)
        result = decision_event(context, decision=decision, reason=reason, enforcement=enforcement)
        event_type = "shield_action_denied" if decision == "deny" else "shield_action_allowed"
        return self.emit(event_type, payload=result, invocation_id=invocation_id)
    def close(self) -> bool:
        result = self.runtime.close()
        if self.store is not None: self.store.close()
        return result


class _IntegrityFacade:
    def init(self, *, agent_id: str, harness: str = "custom", memory: str = "optional", telemetry: str = "auto", identity: str = "persistent", memory_home: str | None = None, **kwargs: Any) -> SDKAgent:
        if identity != "persistent": raise ValueError("only identity='persistent' is supported; refusing ephemeral attribution")
        if memory not in {"optional", "required", "disabled", "none"}:
            raise ValueError("memory must be 'optional', 'required', or 'disabled'")
        if telemetry not in {"auto", "local", "jsonl", "sqlite", "disabled", "off", "none"}:
            raise ValueError("telemetry must be auto, local, jsonl, sqlite, or disabled")
        runtime = IntegrityAgent.open(agent_id, harness=harness, client_kwargs=kwargs.pop("client_kwargs", None), **kwargs)
        store = _store_for(agent_id, telemetry)
        if memory == "required":
            from .readiness import assess_local_readiness
            readiness = assess_local_readiness(agent_id, cortex_home=memory_home)
            if not any(check.name == "persistent_memory" and check.status == "pass" for check in readiness.checks):
                runtime.close(flush=False)
                raise ValueError("memory='required' but no persistent agent-scoped memory store was detected")
        return SDKAgent(runtime, store)

    def auto(self, **kwargs: Any) -> SDKAgent:
        agent_id = kwargs.pop("agent_id", None) or os.getenv("INTEGRITY_AGENT_ID", "xibalba")
        harness = kwargs.pop("harness", None) or os.getenv("INTEGRITY_HARNESS", "generic-python")
        return self.init(agent_id=agent_id, harness=harness, **kwargs)


def _store_for(agent_id: str, telemetry: str) -> LocalEventStore | None:
    if telemetry in ("disabled", "off", "none"): return None
    path = os.getenv("INTEGRITY_LOCAL_EVENTS", str(__import__("pathlib").Path.home() / ".integrity" / "telemetry" / f"{agent_id}.jsonl"))
    return LocalEventStore(path, jsonl=telemetry != "sqlite")


integrity = _IntegrityFacade()
