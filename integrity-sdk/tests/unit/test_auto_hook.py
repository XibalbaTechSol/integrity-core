from __future__ import annotations

import pytest
from integrity_sdk.integrations.auto_hook import enable_auto_hooks
from integrity_sdk import enable_auto_hooks as root_enable_auto_hooks


def test_enable_auto_hooks(monkeypatch):
    monkeypatch.setenv("INTEGRITY_AGENT_ID", "test-auto-agent")
    monkeypatch.setenv("ORACLE_URL", "http://localhost:8080")

    client = enable_auto_hooks(auto_patch_antigravity=False)
    assert client.agent_id == "test-auto-agent"
    assert root_enable_auto_hooks is enable_auto_hooks
