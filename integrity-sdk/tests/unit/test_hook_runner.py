from __future__ import annotations

import io
import json
import subprocess
import sys

import pytest

from integrity_sdk import hook_runner


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    # The same trap noted during Shield's own test failures: this session's real
    # HERMES_HOME/CLAUDE_CONFIG_DIR/INTEGRITY_PROFILE_ROOT would otherwise redirect
    # key resolution onto this machine's live ~/.integrity/did store. INTEGRITY_DID_HOME
    # is pinned OUTSIDE profile_root (a sibling, not a child) -- key_store_for_profile
    # refuses a store located inside the harness root either way.
    for var in ("HERMES_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "INTEGRITY_PROFILE_ROOT", "INTEGRITY_DID_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "did_home"))


@pytest.fixture
def profile_root(tmp_path):
    root = tmp_path / "harness_root"
    root.mkdir()
    return root


def test_evaluate_pre_tool_use_rejects_unsupported_gate(profile_root):
    with pytest.raises(hook_runner.HookRunnerError, match="unsupported gate"):
        hook_runner.evaluate_pre_tool_use({"tool_name": "Bash"}, gate="shield", profile_root=profile_root)


def test_evaluate_pre_tool_use_fails_open_when_middleware_unreachable(profile_root):
    # Real NonceStore/signing path, no mocked gate behavior -- only the network call
    # (an unused port) is the "unreachable" condition under test.
    result = hook_runner.evaluate_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        gate="bcc",
        profile_root=profile_root,
        bcc_middleware_url="http://127.0.0.1:1",
        chain_id=1,
        verifying_contract="0x0000000000000000000000000000000000000000",
    )
    assert result["checked"] is False
    assert result["decision"] == "allow"
    assert "unreachable" in result["reason"]


def test_evaluate_pre_tool_use_honors_authorized_response(profile_root, monkeypatch):
    def fake_submit(commitment, url):
        assert commitment["intent_type"] == "claude_tool:Bash"
        return {"authorized": True, "reason": "ok"}

    monkeypatch.setattr(hook_runner.bcc, "submit_commitment", fake_submit)
    result = hook_runner.evaluate_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "echo hi"}},
        gate="bcc",
        profile_root=profile_root,
        chain_id=1,
        verifying_contract="0x0000000000000000000000000000000000000000",
    )
    assert result == {"decision": "allow", "checked": True, "reason": "ok"}


def test_evaluate_pre_tool_use_honors_denied_response(profile_root, monkeypatch):
    monkeypatch.setattr(hook_runner.bcc, "submit_commitment", lambda c, u: {"authorized": False, "reason": "no active BAA"})
    result = hook_runner.evaluate_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
        gate="bcc",
        profile_root=profile_root,
        chain_id=1,
        verifying_contract="0x0000000000000000000000000000000000000000",
    )
    assert result == {"decision": "deny", "checked": True, "reason": "no active BAA"}


def test_evaluate_pre_tool_use_never_sends_raw_tool_input(profile_root, monkeypatch):
    captured = {}

    def fake_submit(commitment, url):
        captured["commitment"] = commitment
        return {"authorized": True}

    monkeypatch.setattr(hook_runner.bcc, "submit_commitment", fake_submit)
    hook_runner.evaluate_pre_tool_use(
        {"tool_name": "Bash", "tool_input": {"command": "echo a-very-specific-secret-string"}},
        gate="bcc",
        profile_root=profile_root,
        chain_id=1,
        verifying_contract="0x0000000000000000000000000000000000000000",
    )
    serialized = json.dumps(captured["commitment"])
    assert "a-very-specific-secret-string" not in serialized
    assert "intended_state_hash" in captured["commitment"]


def test_record_memory_event_rejects_unsupported_memory():
    with pytest.raises(hook_runner.HookRunnerError, match="unsupported memory target"):
        hook_runner.record_memory_event({}, memory="other", cortex_url="http://x", token="t", event_name="e")


def test_main_emits_deny_json_on_stdout(profile_root, monkeypatch, capsys):
    monkeypatch.setattr(hook_runner.bcc, "submit_commitment", lambda c, u: {"authorized": False, "reason": "no active BAA"})
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    exit_code = hook_runner.main(["pre_tool_use", "--gate", "bcc", "--profile-root", str(profile_root)])
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "no active BAA" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_main_emits_nothing_on_allow(profile_root, monkeypatch, capsys):
    monkeypatch.setattr(hook_runner.bcc, "submit_commitment", lambda c, u: {"authorized": True, "reason": "ok"})
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo hi"}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    exit_code = hook_runner.main(["pre_tool_use", "--gate", "bcc", "--profile-root", str(profile_root)])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_main_never_raises_on_unhandled_error(profile_root, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(hook_runner, "evaluate_pre_tool_use", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    exit_code = hook_runner.main(["pre_tool_use", "--gate", "bcc", "--profile-root", str(profile_root)])
    assert exit_code == 0
    assert capsys.readouterr().out == ""


def test_main_as_a_subprocess_module_entrypoint(profile_root, tmp_path, monkeypatch):
    # Exercises `python -m integrity_sdk.hook_runner` exactly as a harness would
    # invoke it, with no --gate/--memory so it's a pure no-op (nothing to reach
    # over the network), confirming the module is importable and runnable standalone.
    # A fresh, explicit env (not the parent's) so this subprocess can never resolve
    # onto this machine's live ~/.integrity/did store regardless of this session's
    # real HERMES_HOME/CLAUDE_CONFIG_DIR.
    env = {"PATH": __import__("os").environ.get("PATH", ""), "INTEGRITY_DID_HOME": str(tmp_path / "did_home")}
    completed = subprocess.run(
        [sys.executable, "-m", "integrity_sdk.hook_runner", "post_tool_use", "--profile-root", str(profile_root)],
        input="{}", capture_output=True, text=True, timeout=10, env=env,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
