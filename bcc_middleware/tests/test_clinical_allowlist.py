"""The hot-reloaded clinical allowlist fails CLOSED (app/clinical_allowlist.py).

The list grants authority, so every way it can be wrong must mean fewer authorized agents, never more.
The test that matters most is `test_a_bad_edit_does_not_keep_the_revoked_agent`: "keep the last good list"
is the usual hot-reload behaviour, and here it would leave a revoked agent authorized.
"""

from __future__ import annotations

import json
import logging
import os

import pytest

import app.clinical_allowlist as module
from app.clinical_allowlist import ClinicalAllowlist


def _write(path, agents) -> None:
    """Atomic replace: a temp file renamed over the target, as the module docstring recommends."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"agents": agents}))
    os.replace(temporary, path)


def test_no_file_configured_means_no_extra_agents():
    allowlist = ClinicalAllowlist(None)
    assert allowlist.current() == []
    assert allowlist.configured is False
    assert allowlist.status()["ok"] is True


def test_a_valid_file_is_loaded_sorted_and_deduplicated(tmp_path):
    path = tmp_path / "allow.json"
    _write(path, ["did:b", "did:a", "did:a"])
    allowlist = ClinicalAllowlist(path)
    assert allowlist.current() == ["did:a", "did:b"]
    assert allowlist.status() == {"configured": True, "ok": True, "error": None, "agents": 2}


def test_the_returned_list_is_a_copy(tmp_path):
    path = tmp_path / "allow.json"
    _write(path, ["did:a"])
    allowlist = ClinicalAllowlist(path)
    allowlist.current().append("did:attacker")
    assert allowlist.current() == ["did:a"]


def test_an_edit_takes_effect_without_a_restart(tmp_path):
    path = tmp_path / "allow.json"
    _write(path, ["did:a"])
    allowlist = ClinicalAllowlist(path)
    assert allowlist.current() == ["did:a"]
    _write(path, ["did:a", "did:c"])
    assert allowlist.current() == ["did:a", "did:c"]
    _write(path, [])
    assert allowlist.current() == []


def test_a_rewrite_that_keeps_inode_size_and_mtime_is_still_picked_up_within_the_stale_bound(tmp_path, monkeypatch):
    """Atomic replace changes the inode, but an in-place edit that happens to keep size and mtime does not."""
    path = tmp_path / "allow.json"
    path.write_text(json.dumps({"agents": ["did:a1"]}))
    stamp = path.stat().st_mtime_ns
    allowlist = ClinicalAllowlist(path, max_stale_seconds=5.0)
    assert allowlist.current() == ["did:a1"]
    path.write_text(json.dumps({"agents": ["did:b1"]}))  # same length
    os.utime(path, ns=(stamp, stamp))
    now = [1000.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: now[0])
    allowlist._loaded_at = now[0]  # a load just happened
    assert allowlist.current() == ["did:a1"], "within the bound the cached list may be served"
    now[0] += 5.1
    assert allowlist.current() == ["did:b1"]


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        "",
        '{"agents": "did:a"}',
        '{"agents": [1, 2]}',
        '{"agents": ["did:a", ""]}',
        '{"agents": [" did:a"]}',
        '{"agents": ["did:a"], "extra": true}',
        '["did:a"]',
        "null",
    ],
)
def test_an_invalid_file_authorizes_no_one_and_says_why(tmp_path, content, caplog):
    path = tmp_path / "allow.json"
    path.write_text(content)
    allowlist = ClinicalAllowlist(path)
    with caplog.at_level(logging.ERROR, logger="app.clinical_allowlist"):
        assert allowlist.current() == []
    status = allowlist.status()
    assert status["ok"] is False and status["error"]
    assert "authorizing NO extra agents" in caplog.text


def test_a_missing_file_authorizes_no_one(tmp_path):
    allowlist = ClinicalAllowlist(tmp_path / "does-not-exist.json")
    assert allowlist.current() == []
    assert allowlist.status()["ok"] is False


def test_a_bad_edit_does_not_keep_the_revoked_agent(tmp_path):
    """An operator removes a revoked agent and, in the same edit, breaks the JSON. 'Keep the last good list'
    would leave the revoked agent authorized and say nothing. Failing closed denies instead, loudly."""
    path = tmp_path / "allow.json"
    _write(path, ["did:revoked", "did:fine"])
    allowlist = ClinicalAllowlist(path)
    assert "did:revoked" in allowlist.current()

    path.write_text('{"agents": ["did:fine"')  # the intended removal, with a typo
    assert allowlist.current() == [], "the revoked agent must NOT survive a broken edit"
    assert allowlist.status()["ok"] is False

    _write(path, ["did:fine"])  # the operator fixes the typo
    assert allowlist.current() == ["did:fine"]
    assert allowlist.status()["ok"] is True


def test_deleting_the_file_revokes_everyone(tmp_path):
    path = tmp_path / "allow.json"
    _write(path, ["did:a"])
    allowlist = ClinicalAllowlist(path)
    assert allowlist.current() == ["did:a"]
    path.unlink()
    assert allowlist.current() == []
