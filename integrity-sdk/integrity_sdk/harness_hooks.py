"""Harness-neutral hook adapter.

Harnesses own callback registration and payload translation. This module owns the
shared lifecycle vocabulary, immutable SDK attribution, and bounded telemetry
fields so adapter behavior does not drift between Claude, Hermes, Codex, and Agy.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .agent_runtime import IntegrityAgent


def _hash(value: Any) -> str | None:
    if value is None:
        return None
    raw = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _hook_key(name: str) -> str:
    value = name.strip().replace("-", "_").replace(".", "_")
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return value.lower()


class IntegrityHookAdapter:
    """Translate a configured harness callback into SDK-owned telemetry."""

    def __init__(self, agent: IntegrityAgent):
        self.agent = agent

    @staticmethod
    def _session(payload: Mapping[str, Any]) -> str | None:
        value = next((payload.get(key) for key in
                      ("session_id", "sessionId", "conversation_id", "conversationId")
                      if payload.get(key)), None)
        return str(value) if value is not None else None

    def ingest(self, hook_name: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = dict(payload or {})
        session_id = self._session(data)
        if not session_id:
            return {"recorded": False, "reason": "missing session_id"}
        hook = _hook_key(hook_name)
        turn_id = data.get("turn_id", data.get("turnId"))
        invocation_id = data.get("invocation_id", data.get("invocationId", data.get("tool_call_id")))
        tool = data.get("tool_name", data.get("toolName"))
        if tool is None and isinstance(data.get("toolCall"), Mapping):
            tool = data["toolCall"].get("name")
        args = data.get("tool_input", data.get("toolInput", data.get("args")))
        result = data.get("tool_output", data.get("toolOutput", data.get("result")))
        fields = {
            "session_id": session_id,
            "turn_id": str(turn_id) if turn_id is not None else None,
            "invocation_id": str(invocation_id) if invocation_id is not None else None,
            "hook": hook_name,
            "status": data.get("status", data.get("outcome")),
            "tool_name": str(tool) if tool is not None else None,
            "tool_input_hash": _hash(args),
            "result_hash": _hash(result),
            "result_chars": len(result) if isinstance(result, str) else None,
            "error_present": bool(data.get("error") or hook in {"error", "on_tool_error", "api_request_error"}),
        }
        if hook in {"session_start", "on_session_start", "start"}:
            self.agent.start_session(session_id, emit=True, hook=hook_name)
        elif hook in {"session_end", "on_session_end", "end", "session_finalize", "on_session_finalize"}:
            self.agent.end_session(emit=True, **fields)
        elif hook in {"post_llm_call", "post_invocation", "complete", "stop"}:
            self.agent.complete(**fields)
        elif hook in {"pre_llm_call", "pre_invocation", "model_call"}:
            self.agent.model_call(**fields)
        elif hook in {"post_tool_call", "post_tool_use", "tool_result"}:
            self.agent.tool_result(**fields)
        elif hook in {"pre_tool_call", "pre_tool_use", "tool_call"}:
            self.agent.tool_call(**fields)
        else:
            self.agent.emit("hook_observed", **fields)
        return {"recorded": True, "session_id": session_id, "hook": hook_name}


def normalize_hook(hook_name: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Normalize common native harness field names without retaining raw payloads.

    This is the adapter boundary for harness bridges that write to another local
    destination. The returned mapping contains correlation and bounded metadata;
    callers must hash or discard raw tool arguments/results before persistence.
    """
    data = dict(payload or {})
    tool = data.get("toolCall") if isinstance(data.get("toolCall"), Mapping) else {}
    session = IntegrityHookAdapter._session(data)
    turn = data.get("turn_id", data.get("turnId", data.get("invocationNum")))
    invocation = data.get("invocation_id", data.get("invocationId", data.get("tool_call_id")))
    if invocation is None and data.get("stepIdx") is not None:
        invocation = f"step:{data['stepIdx']}"
    tool_name = data.get("tool_name", data.get("toolName", tool.get("name")))
    upstream_id = data.get("event_id", data.get("eventId"))
    if upstream_id is None:
        for key in ("stepIdx", "invocationNum", "executionNum"):
            if data.get(key) is not None:
                upstream_id = f"{key}:{data[key]}"
                break
    return {
        "hook": hook_name,
        "session_id": session,
        "turn_id": str(turn) if turn is not None else None,
        "invocation_id": str(invocation) if invocation is not None else None,
        "tool_call_id": str(data["tool_call_id"]) if data.get("tool_call_id") is not None else None,
        "tool_name": str(tool_name) if tool_name is not None else None,
        "event_id": str(upstream_id) if upstream_id is not None else None,
        "status": data.get("status", "error" if data.get("error") else None),
        "traceparent": data.get("traceparent"),
    }


__all__ = ["IntegrityHookAdapter", "normalize_hook"]
