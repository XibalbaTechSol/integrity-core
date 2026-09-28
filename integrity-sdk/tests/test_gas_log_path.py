"""Gas records go to one per-user file, never to the current working directory.

Regression: chain.py appended to the bare relative path ``gas_usage.jsonl``, so every
directory a tool ran from grew its own copy (four were committed to the repo).
"""

from __future__ import annotations

from pathlib import Path

from integrity_sdk.chain import gas_log_path


def test_default_is_the_user_state_root_not_the_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("INTEGRITY_GAS_LOG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path / ".." )
    path = gas_log_path()
    assert path == tmp_path / ".integrity" / "gas_usage.jsonl"
    assert path.is_absolute()


def test_env_override_wins(monkeypatch, tmp_path):
    target = tmp_path / "custom" / "gas.jsonl"
    monkeypatch.setenv("INTEGRITY_GAS_LOG", str(target))
    assert gas_log_path() == target


def test_blank_override_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("INTEGRITY_GAS_LOG", "   ")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert gas_log_path() == Path(tmp_path) / ".integrity" / "gas_usage.jsonl"
