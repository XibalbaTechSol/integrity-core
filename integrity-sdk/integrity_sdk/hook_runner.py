"""Connects a harness's PreToolUse/memory hooks to BCC and Cortex (B3).

This is a connector module: it does real network I/O (``requests``, imported lazily
inside each function, never at module scope) and must never be imported from
``integrity_sdk.core`` or any core-safe module. Nothing in this package's eager
``__init__`` imports it; it is invoked directly, normally as
``python -m integrity_sdk.hook_runner`` from a harness's hook configuration (see
``integrity-cli``'s ``hooks install`` command, the installer for this module).

C5's hook contract is "the runner calls the local Shield gate if present, otherwise
BCC." ``--gate shield`` speaks to ``xibalba-shield``'s ``shield gate-daemon`` over a Unix
socket (docs/INTERFACE_CONTRACT.md 15.5). It never falls back to BCC on its own: the caller
names one gate, and a missing Shield daemon is reported as an *unchecked* allow rather than
quietly re-routed to a different policy engine, per this repository's "no silent mocks"
rule. Only a digest of ``tool_input`` crosses that socket, never the input itself -- the
same rule as the BCC path, and Shield's evaluation reads no tool content anyway.

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
import hashlib
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Mapping

from . import bcc, did
from .core.jcs import canonical_bytes

SUPPORTED_GATES = ("bcc", "shield")
SUPPORTED_MEMORY = ("cortex",)

# --- Shield gate socket client (docs/INTERFACE_CONTRACT.md 15.5) ------------------------
SHIELD_GATE_PROTOCOL_VERSION = 1

# A PreToolUse hook sits on the harness's critical path, so an unresponsive daemon must not
# stall the session for long. Five seconds is far above a warm OPA query and far below
# "the user thinks the harness hung".
SHIELD_GATE_TIMEOUT_SECONDS = 5.0

# A well-formed response is a few hundred bytes. This only bounds a daemon that has gone
# wrong, so a runaway cannot make every hook allocate without limit.
MAX_SHIELD_RESPONSE_BYTES = 64 * 1024

#: Marker used when a tool input cannot be canonicalized (for example a NaN, which JCS
#: rejects). An input that cannot be hashed must not turn into a failed tool call.
UNCANONICALIZABLE_DIGEST = "uncanonicalizable"


class HookRunnerError(RuntimeError):
    """A gate/memory target this runner does not (yet) support, or a malformed call."""


def default_shield_socket_path() -> Path:
    """Where ``shield gate-daemon`` listens when no path is given.

    This is the **same rule** as ``xibalba-shield``'s ``gate_daemon.default_socket_path``,
    deliberately duplicated because the SDK must not import Shield. Both repositories pin it
    with a test against the three cases below, and 15.5 of docs/INTERFACE_CONTRACT.md is the
    single statement of it; change all three together or a hook will look for a socket the
    daemon is not listening on.

    ``XIBALBA_SHIELD_GATE_SOCKET`` wins; otherwise ``$XDG_RUNTIME_DIR/xibalba-shield/gate.sock``;
    otherwise ``~/.xibalba-shield/gate.sock``.
    """
    override = os.environ.get("XIBALBA_SHIELD_GATE_SOCKET")
    if override:
        return Path(override)
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "xibalba-shield" / "gate.sock"
    return Path.home() / ".xibalba-shield" / "gate.sock"


def tool_input_digest(tool_input: Mapping[str, Any]) -> str:
    """JCS (RFC 8785) SHA-256 of ``tool_input`` as lowercase hex.

    Uses the SDK's own canonicalizer, the same one Shield wraps, so the digest a daemon logs
    is comparable with one computed anywhere else in the ecosystem. Returns
    ``UNCANONICALIZABLE_DIGEST`` rather than raising for an input JCS rejects.
    """
    try:
        return hashlib.sha256(canonical_bytes(dict(tool_input))).hexdigest()
    except (TypeError, ValueError):
        return UNCANONICALIZABLE_DIGEST


def query_shield_gate(
    request: Mapping[str, Any], *, socket_path: Path, timeout: float = SHIELD_GATE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """One request/response exchange with ``shield gate-daemon``.

    Raises ``OSError`` (including ``TimeoutError``) for any transport failure and
    ``ValueError`` for a response that is not a well-formed v1 verdict. The caller decides
    what an unreachable or incoherent daemon means; this function only reports it.
    """
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(socket_path))
        client.sendall(json.dumps(dict(request)).encode("utf-8") + b"\n")
        line = client.makefile("rb").readline(MAX_SHIELD_RESPONSE_BYTES + 1)
    finally:
        client.close()

    if not line:
        raise ValueError("daemon closed the connection without answering")
    if len(line) > MAX_SHIELD_RESPONSE_BYTES:
        raise ValueError(f"response exceeds {MAX_SHIELD_RESPONSE_BYTES} bytes")
    try:
        response = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"response is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(response, Mapping):
        raise ValueError("response is not a JSON object")
    if response.get("v") != SHIELD_GATE_PROTOCOL_VERSION:
        raise ValueError(
            f"unsupported response protocol version {response.get('v')!r}; "
            f"this runner speaks v{SHIELD_GATE_PROTOCOL_VERSION}"
        )
    if response.get("decision") not in ("allow", "deny"):
        raise ValueError(f"response decision is {response.get('decision')!r}, not allow or deny")
    return dict(response)


def _evaluate_shield(
    payload: Mapping[str, Any], *, agent_did: str, socket_path: Path, timeout: float,
) -> dict[str, Any]:
    """Ask Shield's local gate daemon. Fails OPEN, loudly, exactly like the BCC path.

    The daemon itself fails closed; this shim is the dev-shell-facing layer whose ratified
    posture is to let the harness proceed rather than brick the session when its gate is
    unreachable. ``checked`` is the distinction a caller must preserve: an unchecked allow is
    never an authorized one.
    """
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, Mapping):
        tool_input = {}

    request = {
        "v": SHIELD_GATE_PROTOCOL_VERSION,
        "event": "pre_tool_use",
        "agent_id": agent_did,
        "tool_name": tool_name,
        # Only the digest crosses the socket -- see the module docstring.
        "tool_input_sha256": tool_input_digest(tool_input),
    }
    try:
        response = query_shield_gate(request, socket_path=socket_path, timeout=timeout)
    except (OSError, ValueError) as exc:
        return {
            "decision": "allow",
            "checked": False,
            "reason": f"shield gate unreachable or incoherent at {socket_path}: {exc!r}",
        }

    result = {
        "decision": str(response["decision"]),
        "checked": True,
        "reason": str(response.get("reason") or "no reason given"),
    }
    # Carried through so the caller can record WHICH policy ruled, and what an observe-mode
    # daemon would have enforced.
    for key in ("rule_id", "policy_hash", "action", "enforced"):
        if key in response:
            result[key] = response[key]
    return result


def evaluate_pre_tool_use(
    payload: Mapping[str, Any],
    *,
    gate: str,
    profile_root: Path,
    agent_id: str = "default",
    bcc_middleware_url: str | None = None,
    chain_id: int | None = None,
    verifying_contract: str | None = None,
    shield_socket: str | Path | None = None,
    shield_timeout: float = SHIELD_GATE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Evaluate one PreToolUse payload against ``gate`` and return a decision.

    Returns ``{"decision": "allow"|"deny", "checked": bool, "reason": str}``.
    ``checked`` is False exactly when no policy engine actually rendered a verdict
    (gate unreachable) -- callers must not treat an unchecked allow the same as an
    authorized one in logs/evidence, the same distinction
    ``~/.claude/xibalba/pretool_gate.py``'s ``GateOutcome.checked`` makes.
    """
    if gate not in SUPPORTED_GATES:
        raise HookRunnerError(f"unsupported gate {gate!r}; supported: {SUPPORTED_GATES}")
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, Mapping):
        tool_input = {}

    store_home = did.key_store_for_profile(Path(profile_root))
    agent_did, keypair, _ = did.load_or_create_did(agent_id, did_home_root=store_home)

    if gate == "shield":
        return _evaluate_shield(
            payload,
            agent_did=agent_did,
            socket_path=Path(shield_socket) if shield_socket is not None else default_shield_socket_path(),
            timeout=shield_timeout,
        )

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
            elif not result["checked"]:
                # This module's docstring promises a fail-open allow is "always logged to
                # stderr, never silently swallowed", but until now only exceptions were. An
                # unreachable gate allowed the call and left no trace -- which for a gate that
                # may simply not be running means silently unenforced.
                sys.stderr.write(
                    f"integrity hook_runner: {args.gate} gate UNCHECKED, allowing "
                    f"{payload.get('tool_name', 'tool')}: {result['reason']}\n"
                )
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
