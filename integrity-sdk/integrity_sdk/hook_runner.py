"""Connects a harness's PreToolUse/memory hooks to BCC and Cortex (B3).

This is a connector module: it does real network I/O (``requests``, imported lazily
inside each function, never at module scope) and must never be imported from
``integrity_sdk.core`` or any core-safe module. Nothing in this package's eager
``__init__`` imports it; it is invoked directly, normally as
``python -m integrity_sdk.hook_runner`` from a harness's hook configuration (see
``integrity-cli``'s ``hooks install`` command, the installer for this module).

C5's hook contract is "the runner calls the local Shield gate if present, otherwise
BCC." Shield's local gate daemon (a Unix socket for PreToolUse, B2) does not exist
yet, so ``SUPPORTED_GATES`` below names only ``bcc`` -- this module refuses a
``shield`` gate explicitly rather than silently falling back to BCC or (worse) a
no-op allow, per this repository's "no silent mocks" rule.

Fail-open posture for PreToolUse, deliberately, same ratified tradeoff as the
single-operator Claude-Code hook this module generalizes
(``~/.claude/xibalba/pretool_gate.py`` on the owner's own machine): an unreachable
``bcc_middleware`` or an unhandled runner bug lets the tool proceed rather than
bricking the harness session, and is always logged to stderr, never silently
swallowed. ``bcc_middleware`` itself remains fail-closed; only this dev-shell-facing
layer fails open. Memory recording (``--memory cortex``) is unconditionally
best-effort: a failure there must never block or deny a tool call, since memory is
observability, not enforcement.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

from . import bcc, did

SUPPORTED_GATES = ("bcc",)
SUPPORTED_MEMORY = ("cortex",)


class HookRunnerError(RuntimeError):
    """A gate/memory target this runner does not (yet) support, or a malformed call."""


def evaluate_pre_tool_use(
    payload: Mapping[str, Any],
    *,
    gate: str,
    profile_root: Path,
    agent_id: str = "default",
    bcc_middleware_url: str | None = None,
    chain_id: int | None = None,
    verifying_contract: str | None = None,
) -> dict[str, Any]:
    """Evaluate one PreToolUse payload against ``gate`` and return a decision.

    Returns ``{"decision": "allow"|"deny", "checked": bool, "reason": str}``.
    ``checked`` is False exactly when no policy engine actually rendered a verdict
    (gate unreachable) -- callers must not treat an unchecked allow the same as an
    authorized one in logs/evidence, the same distinction
    ``~/.claude/xibalba/pretool_gate.py``'s ``GateOutcome.checked`` makes.
    """
    if gate not in SUPPORTED_GATES:
        raise HookRunnerError(
            f"unsupported gate {gate!r}; supported today: {SUPPORTED_GATES}. "
            "'shield' is not available until Shield's local gate daemon (B2) ships."
        )
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, Mapping):
        tool_input = {}

    store_home = did.key_store_for_profile(Path(profile_root))
    agent_did, keypair, _ = did.load_or_create_did(agent_id, did_home_root=store_home)

    bcc_middleware_url = (bcc_middleware_url or os.getenv("BCC_MIDDLEWARE_URL", "http://localhost:8000")).rstrip("/")
    chain_id = chain_id if chain_id is not None else int(os.getenv("CHAIN_ID", "84532"))
    verifying_contract = verifying_contract or os.getenv("VERIFYING_CONTRACT", "")

    nonce_path = did.agent_dir(agent_id, did_home_root=store_home) / "bcc_nonce"
    nonce = bcc.NonceStore(nonce_path).next()

    # Only this payload's sha256 (via build_bcc_commitment's hash_intent_payload)
    # crosses the wire -- the raw tool_input, which may contain file contents,
    # commands, or PHI, never does.
    commitment = bcc.build_bcc_commitment(
        agent_id=agent_did,
        intent_type=f"claude_tool:{tool_name}",
        intent_payload=dict(tool_input),
        nonce=nonce,
        keypair=keypair,
        chain_id=chain_id,
        verifying_contract=verifying_contract,
    )

    try:
        result = bcc.submit_commitment(commitment, bcc_middleware_url)
    except Exception as exc:  # noqa: BLE001 -- fail-open is this layer's ratified posture
        return {"decision": "allow", "checked": False, "reason": f"bcc_middleware unreachable: {exc!r}"}

    authorized = bool(result.get("authorized"))
    return {
        "decision": "allow" if authorized else "deny",
        "checked": True,
        "reason": str(result.get("reason") or ("authorized" if authorized else "no reason given")),
    }


def record_memory_event(
    payload: Mapping[str, Any],
    *,
    memory: str,
    cortex_url: str,
    token: str,
    event_name: str,
) -> dict[str, Any]:
    """POST one bounded, redacted event to Cortex's ``/api/otel/batch``.

    Carries correlation metadata and a tool name only -- never tool_input/output
    content. This is memory, not enforcement: callers must swallow any exception
    from this function rather than let a Cortex outage affect the gate decision.
    """
    if memory not in SUPPORTED_MEMORY:
        raise HookRunnerError(f"unsupported memory target {memory!r}; supported today: {SUPPORTED_MEMORY}")
    import requests  # connector-only; never at module scope (see module docstring)

    session_id = str(payload.get("session_id") or "unknown-session")
    tool_name = payload.get("tool_name")
    attributes: dict[str, Any] = {"hook": event_name}
    if tool_name is not None:
        attributes["tool_name"] = str(tool_name)
    body = {"session_id": session_id, "events": [{"kind": "log", "name": event_name, "attributes": attributes}]}
    resp = requests.post(
        f"{cortex_url.rstrip('/')}/api/otel/batch",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()


def _read_stdin_json() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _emit_deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m integrity_sdk.hook_runner")
    parser.add_argument("event", choices=["pre_tool_use", "post_tool_use"])
    parser.add_argument("--gate", choices=SUPPORTED_GATES, default=None)
    parser.add_argument("--memory", choices=SUPPORTED_MEMORY, default=None)
    parser.add_argument("--profile-root", required=True)
    parser.add_argument("--agent-id", default="default")
    args = parser.parse_args(argv)

    payload = _read_stdin_json()
    try:
        if args.event == "pre_tool_use" and args.gate:
            result = evaluate_pre_tool_use(payload, gate=args.gate, profile_root=Path(args.profile_root), agent_id=args.agent_id)
            if result["decision"] == "deny":
                reason = result["reason"] if result["checked"] else f"policy unavailable; {result['reason']}"
                _emit_deny(f"Integrity {args.gate} gate denied this {payload.get('tool_name', 'tool')} action: {reason}")
        elif args.event == "post_tool_use" and args.memory:
            token = os.getenv("XIBALBA_CORTEX_TOKEN", "")
            if token:
                cortex_url = os.getenv("XIBALBA_CORTEX_URL", "http://127.0.0.1:8420")
                try:
                    record_memory_event(payload, memory=args.memory, cortex_url=cortex_url, token=token, event_name="integrity_hook.post_tool_use")
                except Exception as exc:  # noqa: BLE001 -- memory recording never blocks the session
                    sys.stderr.write(f"integrity hook_runner: memory recording failed: {exc!r}\n")
    except HookRunnerError as exc:
        sys.stderr.write(f"integrity hook_runner: {exc}\n")
    except Exception as exc:  # noqa: BLE001 -- a runner bug must not brick the session
        sys.stderr.write(f"integrity hook_runner: unhandled error {exc!r} -- allowing unchecked\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
