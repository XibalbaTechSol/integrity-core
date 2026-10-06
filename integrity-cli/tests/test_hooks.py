from __future__ import annotations

import json
import stat

import pytest

from integrity_cli import hooks


@pytest.fixture(autouse=True)
def _isolated_sdk_identity_env(tmp_path, monkeypatch):
    # hooks.py imports integrity_sdk.did, which resolves its key store from
    # harness-root env vars this session may genuinely have set
    # (HERMES_HOME/CLAUDE_CONFIG_DIR/...). Clear them and pin
    # INTEGRITY_DID_HOME outside any profile_root used below so a test can
    # never reach this machine's real ~/.integrity/did store.
    for var in ("HERMES_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "INTEGRITY_PROFILE_ROOT", "INTEGRITY_DID_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did_home"))


@pytest.fixture
def profile_root(tmp_path):
    root = tmp_path / "harness_root"
    root.mkdir()
    return root


def test_install_writes_did_file_and_key_outside_root(profile_root):
    result = hooks.install(harness="claude-code", gate="bcc", profile_root=profile_root)

    did_file = profile_root / "agent.did.json"
    assert did_file.exists()
    doc = json.loads(did_file.read_text())
    assert doc["did"] == result["did"]
    assert "private" not in json.dumps(doc).lower()

    # The key lives outside profile_root entirely, mode 0600.
    key_paths = list((profile_root.parent / "did_home").rglob("private_key.pem"))
    assert len(key_paths) == 1
    key_path = key_paths[0]
    assert not str(key_path).startswith(str(profile_root))
    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_install_writes_marked_pretooluse_hook_only_for_gate(profile_root):
    hooks.install(harness="claude-code", gate="bcc", profile_root=profile_root)
    settings = json.loads((profile_root / "settings.json").read_text())
    pre_tool = settings["hooks"]["PreToolUse"]
    assert len(pre_tool) == 1
    assert hooks.HOOK_MARKER in pre_tool[0]["hooks"][0]["command"]
    assert "--gate bcc" in pre_tool[0]["hooks"][0]["command"]
    assert "PostToolUse" not in settings["hooks"]


def test_install_writes_marked_posttooluse_hook_when_memory_given(profile_root):
    hooks.install(harness="claude-code", gate="bcc", memory="cortex", profile_root=profile_root)
    settings = json.loads((profile_root / "settings.json").read_text())
    post_tool = settings["hooks"]["PostToolUse"]
    assert len(post_tool) == 1
    assert hooks.HOOK_MARKER in post_tool[0]["hooks"][0]["command"]
    assert "--memory cortex" in post_tool[0]["hooks"][0]["command"]


def test_install_is_idempotent(profile_root):
    hooks.install(harness="claude-code", gate="bcc", memory="cortex", profile_root=profile_root)
    first_settings = (profile_root / "settings.json").read_text()
    first_did = (profile_root / "agent.did.json").read_text()

    hooks.install(harness="claude-code", gate="bcc", memory="cortex", profile_root=profile_root)
    second_settings = (profile_root / "settings.json").read_text()
    second_did = (profile_root / "agent.did.json").read_text()

    assert json.loads(first_settings) == json.loads(second_settings)
    assert first_did == second_did
    key_paths = list((profile_root.parent / "did_home").rglob("private_key.pem"))
    assert len(key_paths) == 1  # no second key was ever minted


def test_install_preserves_pre_existing_user_hooks(profile_root):
    user_settings = {
        "hooks": {
            "PreToolUse": [{"matcher": "Glob", "hooks": [{"type": "command", "command": "echo user-hook"}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "echo session-start"}]}],
        },
        "someOtherTopLevelKey": "unchanged",
    }
    (profile_root / "settings.json").write_text(json.dumps(user_settings, indent=2))

    hooks.install(harness="claude-code", gate="bcc", profile_root=profile_root)

    settings = json.loads((profile_root / "settings.json").read_text())
    assert settings["someOtherTopLevelKey"] == "unchanged"
    assert settings["hooks"]["SessionStart"] == user_settings["hooks"]["SessionStart"]
    pre_tool_commands = [h["hooks"][0]["command"] for h in settings["hooks"]["PreToolUse"]]
    assert "echo user-hook" in pre_tool_commands
    assert any(hooks.HOOK_MARKER in c for c in pre_tool_commands)
    assert len(pre_tool_commands) == 2


def test_install_refuses_an_unknown_gate_and_writes_nothing(profile_root):
    with pytest.raises(hooks.HookInstallError, match="unsupported --gate"):
        hooks.install(harness="claude-code", gate="bogus", profile_root=profile_root)
    assert not (profile_root / "agent.did.json").exists()
    assert not (profile_root / "settings.json").exists()


def test_supported_gates_match_the_runner_the_installed_hooks_invoke():
    """This package deliberately keeps its own list rather than importing the runner's at module
    scope, so two lists exist. If they ever differ, install would accept a gate the runner then
    refuses at every tool call -- or the reverse. Pin them together."""
    from integrity_sdk import hook_runner

    assert hooks.SUPPORTED_GATES == hook_runner.SUPPORTED_GATES


@pytest.fixture
def shield_socket(tmp_path, monkeypatch):
    """Point the installer's probe at a path under this test's control."""
    path = tmp_path / "gate.sock"
    monkeypatch.setenv("XIBALBA_SHIELD_GATE_SOCKET", str(path))
    return path


def test_install_accepts_the_shield_gate_and_writes_its_hook(profile_root, shield_socket):
    result = hooks.install(harness="claude-code", gate="shield", profile_root=profile_root)

    settings = json.loads((profile_root / "settings.json").read_text())
    (entry,) = settings["hooks"]["PreToolUse"]
    command = entry["hooks"][0]["command"]
    assert "--gate shield" in command
    assert hooks.HOOK_MARKER in command
    assert result["gate"] == "shield"


def test_shield_install_reports_not_listening_when_no_daemon_is_running(profile_root, shield_socket):
    """The reason the old install-time refusal existed was that a hook with nothing behind it
    would silently do nothing. The runner fails open, so that is still true -- the report is what
    keeps it from being silent."""
    report = hooks.install(harness="claude-code", gate="shield", profile_root=profile_root)["shield_gate"]
    assert report["listening"] is False
    assert report["socket"] == str(shield_socket)


def test_shield_install_reports_the_dids_to_register_with_the_daemon(profile_root, shield_socket):
    """Every shipped Shield pack denies an unregistered agent's tool calls, so the DID this
    install created is the one thing the operator must give the daemon."""
    result = hooks.install(harness="claude-code", gate="shield", profile_root=profile_root)
    assert result["shield_gate"]["register_agent"] == result["did"]
    assert result["did"].startswith("did:")


def test_shield_install_reports_listening_only_for_a_live_daemon(profile_root, shield_socket):
    import socket as _socket

    server = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    server.bind(str(shield_socket))
    server.listen(1)
    try:
        live = hooks.install(harness="claude-code", gate="shield", profile_root=profile_root)["shield_gate"]
    finally:
        server.close()
    assert live["listening"] is True


def test_shield_install_does_not_mistake_a_stale_socket_file_for_a_daemon(profile_root, shield_socket):
    """A crashed daemon leaves its socket file behind. `is_socket()` would call that listening
    while every hook silently failed open -- hence a connect probe."""
    import socket as _socket

    stale = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    stale.bind(str(shield_socket))  # the file now exists, but nothing ever listen()s
    try:
        assert shield_socket.exists()
        report = hooks.install(harness="claude-code", gate="shield", profile_root=profile_root)["shield_gate"]
    finally:
        stale.close()
    assert report["listening"] is False


def test_bcc_install_has_no_shield_report(profile_root):
    assert "shield_gate" not in hooks.install(harness="claude-code", gate="bcc", profile_root=profile_root)


def test_install_refuses_unsupported_harness(profile_root):
    with pytest.raises(hooks.HookInstallError, match="unsupported --harness"):
        hooks.install(harness="codex", gate="bcc", profile_root=profile_root)


def test_install_refuses_unsupported_memory(profile_root):
    with pytest.raises(hooks.HookInstallError, match="unsupported --memory"):
        hooks.install(harness="claude-code", gate="bcc", memory="redis", profile_root=profile_root)


def test_install_refuses_mismatched_existing_did(profile_root, tmp_path, monkeypatch):
    hooks.install(harness="claude-code", gate="bcc", agent_id="agent-a", profile_root=profile_root)

    # A different agent_id under the SAME did_home produces a different DID;
    # installing it into the same profile_root must fail closed rather than
    # overwrite the existing agent.did.json.
    with pytest.raises(hooks.HookInstallError, match="different identity"):
        hooks.install(harness="claude-code", gate="bcc", agent_id="agent-b", profile_root=profile_root)


def test_uninstall_removes_only_marked_entries_and_restores_original_shape(profile_root):
    original = {
        "hooks": {
            "PreToolUse": [{"matcher": "Glob", "hooks": [{"type": "command", "command": "echo user-hook"}]}],
        },
        "someOtherTopLevelKey": "unchanged",
    }
    (profile_root / "settings.json").write_text(json.dumps(original, indent=2) + "\n")

    hooks.install(harness="claude-code", gate="bcc", memory="cortex", profile_root=profile_root)
    result = hooks.uninstall(harness="claude-code", profile_root=profile_root)

    assert result["removed_hook_entries"] == 2  # PreToolUse + PostToolUse
    settings = json.loads((profile_root / "settings.json").read_text())
    assert settings == original
    # Identity is untouched by uninstall.
    assert (profile_root / "agent.did.json").exists()
    assert list((profile_root.parent / "did_home").rglob("private_key.pem"))


def test_uninstall_with_nothing_installed_is_a_noop(profile_root):
    result = hooks.uninstall(harness="claude-code", profile_root=profile_root)
    assert result["removed_hook_entries"] == 0
    assert not (profile_root / "settings.json").exists()


def test_uninstall_refuses_unsupported_harness(profile_root):
    with pytest.raises(hooks.HookInstallError, match="unsupported --harness"):
        hooks.uninstall(harness="codex", profile_root=profile_root)
