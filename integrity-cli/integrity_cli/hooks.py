"""Install/uninstall marker-tagged PreToolUse/memory hooks for a harness (B3).

This is the one module in this package that imports `integrity_sdk` --
specifically `integrity_sdk.did`, never the connector stack (requests/web3).
`identity.py`'s module docstring states this package's longstanding rule
against depending on integrity_sdk: it was written to decouple the CLI's
on-chain registration/wallet code from the SDK's build order while both were
still in flux. That rationale does not apply here: this command's entire job
is to install the SDK's own harness-root DID layout (a public
`agent.did.json` in the root, the private key outside it via
`key_store_for_profile`) -- reimplementing that a third time would create
exactly the "same agent label, two different DIDs" drift `identity.py`
already warns happened once before. Owner-approved exception, 2026-10-05.

The actual gate/memory logic this command's hooks invoke lives in
`integrity_sdk.hook_runner`, out-of-process, via
`python -m integrity_sdk.hook_runner`; this module only ever writes that
invocation into `settings.json`, it never calls BCC or Cortex itself.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Marks every hook entry this command owns. Carried in the command string
# itself (a trailing shell comment, harmless when the string is run via
# `sh -c`) rather than a side-car manifest file, so it can never drift from
# what settings.json actually contains if a user hand-edits that file.
HOOK_MARKER = "# integrity-hooks:v1"

SUPPORTED_HARNESSES = ("claude-code",)
# "shield" is refused below, not listed here: Shield's local gate daemon (a Unix
# socket for PreToolUse, B2) does not exist yet. Installing a hook that invokes
# a gate with nothing listening would either hang or silently no-op -- refusing
# at install time is the honest behavior, per this repository's "no silent
# mocks" rule.
SUPPORTED_GATES = ("bcc",)
SUPPORTED_MEMORY = ("cortex",)


class HookInstallError(RuntimeError):
    """Install/uninstall cannot proceed as asked."""


def default_profile_root(harness: str) -> Path:
    if harness == "claude-code":
        override = os.getenv("CLAUDE_CONFIG_DIR")
        return Path(override).expanduser() if override else Path.home() / ".claude"
    raise HookInstallError(f"no default profile root known for harness {harness!r}")


def _settings_path(profile_root: Path) -> Path:
    return profile_root / "settings.json"


def _load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HookInstallError(f"{path} is not valid JSON; refusing to touch it: {exc}") from exc
    except OSError as exc:
        raise HookInstallError(f"cannot read {path}: {exc}") from exc


def _write_settings_atomic(path: Path, settings: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd_dir = os.open(path.parent, os.O_RDONLY) if path.parent.exists() else None
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
        if fd_dir is not None:
            try:
                os.fsync(fd_dir)
            finally:
                os.close(fd_dir)


def _marked_command(event: str, *, profile_root: Path, agent_id: str, gate: Optional[str] = None, memory: Optional[str] = None) -> str:
    parts = [f'"{sys.executable}" -m integrity_sdk.hook_runner', event, "--profile-root", f'"{profile_root}"', "--agent-id", agent_id]
    if gate:
        parts += ["--gate", gate]
    if memory:
        parts += ["--memory", memory]
    return " ".join(parts) + "  " + HOOK_MARKER


def _hook_entry(matcher: Optional[str], command: str) -> dict[str, Any]:
    entry: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        entry["matcher"] = matcher
    return entry


def _is_marked(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    hook_list = entry.get("hooks")
    if not isinstance(hook_list, list):
        return False
    return any(isinstance(h, dict) and HOOK_MARKER in str(h.get("command", "")) for h in hook_list)


_PRE_TOOL_MATCHER = "Bash|Write|Edit|MultiEdit|NotebookEdit"
_POST_TOOL_MATCHER = "Bash|Write|Edit|MultiEdit|NotebookEdit"


def install(
    *,
    harness: str,
    gate: str,
    memory: Optional[str] = None,
    profile_root: Optional[str | Path] = None,
    agent_id: str = "default",
) -> dict[str, Any]:
    """Idempotently install the DID file and marker-tagged hooks.

    Running this twice with the same arguments leaves `settings.json`
    JSON-equal to the first run: no duplicate hook entries, no new key, no
    DID change.
    """
    if harness not in SUPPORTED_HARNESSES:
        raise HookInstallError(f"unsupported --harness {harness!r}; supported: {sorted(SUPPORTED_HARNESSES)}")
    if gate not in SUPPORTED_GATES:
        raise HookInstallError(
            f"--gate {gate!r} is not available yet. Only {sorted(SUPPORTED_GATES)} is wired today; "
            "Shield's local gate daemon (Unix socket PreToolUse, B2) has not been built. Refusing "
            "rather than installing a hook with nothing real to call."
        )
    if memory is not None and memory not in SUPPORTED_MEMORY:
        raise HookInstallError(f"unsupported --memory {memory!r}; supported: {sorted(SUPPORTED_MEMORY)}")

    from integrity_sdk import did  # see module docstring for why this import exists here

    root = Path(profile_root).expanduser().resolve() if profile_root is not None else default_profile_root(harness).resolve()
    root.mkdir(parents=True, exist_ok=True)

    store_home = did.key_store_for_profile(root)
    agent_did, keypair, _ = did.load_or_create_did(agent_id, did_home_root=store_home)

    existing_doc = did.read_did_file(root)
    if existing_doc is not None and existing_doc.get("did") != agent_did:
        raise HookInstallError(
            f"{root} already has agent.did.json for a different identity "
            f"({existing_doc.get('did')!r} != {agent_did!r}); refusing to overwrite it. "
            "Use a different --profile-root or --agent-id."
        )
    did_path = did.write_did_file(
        root, did=agent_did, public_key=keypair.public_bytes(), agent_id=agent_id, harness=harness, profile=None,
    )

    settings_path = _settings_path(root)
    settings = _load_settings(settings_path)
    hooks = settings.setdefault("hooks", {})

    pre_tool = hooks.setdefault("PreToolUse", [])
    pre_tool[:] = [entry for entry in pre_tool if not _is_marked(entry)]
    pre_tool.append(_hook_entry(_PRE_TOOL_MATCHER, _marked_command("pre_tool_use", profile_root=root, agent_id=agent_id, gate=gate)))

    if memory:
        post_tool = hooks.setdefault("PostToolUse", [])
        post_tool[:] = [entry for entry in post_tool if not _is_marked(entry)]
        post_tool.append(_hook_entry(_POST_TOOL_MATCHER, _marked_command("post_tool_use", profile_root=root, agent_id=agent_id, memory=memory)))

    _write_settings_atomic(settings_path, settings)
    return {
        "did": agent_did,
        "did_file": str(did_path),
        "settings_file": str(settings_path),
        "profile_root": str(root),
        "gate": gate,
        "memory": memory,
    }


def uninstall(*, harness: str, profile_root: Optional[str | Path] = None) -> dict[str, Any]:
    """Remove exactly the marker-tagged hook entries this command wrote.

    Leaves `agent.did.json` and the private key untouched -- identity outlives
    hook configuration, and deleting a signing key as a side effect of
    uninstalling a hook would be a surprising, hard-to-reverse action. A
    no-op (nothing marked, or no settings file at all) writes nothing.
    """
    if harness not in SUPPORTED_HARNESSES:
        raise HookInstallError(f"unsupported --harness {harness!r}; supported: {sorted(SUPPORTED_HARNESSES)}")
    root = Path(profile_root).expanduser().resolve() if profile_root is not None else default_profile_root(harness).resolve()
    settings_path = _settings_path(root)
    settings = _load_settings(settings_path)

    removed = 0
    hooks = settings.get("hooks")
    if isinstance(hooks, dict):
        for event_name in list(hooks.keys()):
            entries = hooks[event_name]
            if not isinstance(entries, list):
                continue
            kept = [entry for entry in entries if not _is_marked(entry)]
            removed += len(entries) - len(kept)
            if kept:
                hooks[event_name] = kept
            else:
                del hooks[event_name]
        if not hooks:
            settings.pop("hooks", None)

    if removed:
        _write_settings_atomic(settings_path, settings)
    return {"removed_hook_entries": removed, "settings_file": str(settings_path), "profile_root": str(root)}
