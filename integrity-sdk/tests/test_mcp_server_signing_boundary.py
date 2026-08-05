"""Signing/on-chain-write MCP tools must be disabled by default -- both undiscoverable and
unexecutable. Security fix, 2026-08-05: see integrity_sdk/mcp_server.py's module docstring and
xibalba-graph-memory/docs/session-log/2026-08-05-integrity-coupling-session.md for the full
account of the gap this closes (integrity_register_agent was a live, callable tool loading a
real identity key with no gate covering it).
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from integrity_sdk import mcp_server


def _build_server_capturing_handlers(agent_id="test-agent", oracle_url="http://localhost:8080"):
    """build_server() constructs a real mcp.server.Server and hands it closures we can't
    reach from outside -- intercept the constructor call to capture on_list_tools/on_call_tool
    directly, the standard pattern for testing handlers passed to a constructor.
    """
    captured = {}

    class _FakeServer:
        def __init__(self, *args, **kwargs):
            captured["on_list_tools"] = kwargs["on_list_tools"]
            captured["on_call_tool"] = kwargs["on_call_tool"]

    with patch("mcp.server.Server", _FakeServer):
        mcp_server.build_server(agent_id, oracle_url)
    return captured


def test_signing_tools_constant_matches_the_four_dangerous_tools():
    assert mcp_server._SIGNING_TOOLS == {
        "integrity_flush_telemetry",
        "integrity_invoke_intent",
        "integrity_register_agent",
        "integrity_commit_memory",
    }


def test_signing_tools_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INTEGRITY_MCP_ALLOW_SIGNING_TOOLS", raising=False)
    # Reimport-free: the module reads the env var once at import time into
    # _SIGNING_TOOLS_ENABLED, so exercise the same logic the module itself uses.
    assert mcp_server._SIGNING_TOOLS_ENABLED is False


@pytest.mark.parametrize("env_value,expected", [("1", True), ("0", False), (None, False)])
def test_signing_tools_enabled_flag_reads_env_var(monkeypatch, env_value, expected):
    if env_value is None:
        monkeypatch.delenv("INTEGRITY_MCP_ALLOW_SIGNING_TOOLS", raising=False)
    else:
        monkeypatch.setenv("INTEGRITY_MCP_ALLOW_SIGNING_TOOLS", env_value)
    import importlib
    importlib.reload(mcp_server)
    assert mcp_server._SIGNING_TOOLS_ENABLED is expected
    monkeypatch.delenv("INTEGRITY_MCP_ALLOW_SIGNING_TOOLS", raising=False)
    importlib.reload(mcp_server)  # restore default state for subsequent tests


def test_signing_tools_are_not_advertised_by_default(monkeypatch):
    monkeypatch.delenv("INTEGRITY_MCP_ALLOW_SIGNING_TOOLS", raising=False)
    import importlib
    importlib.reload(mcp_server)
    handlers = _build_server_capturing_handlers()

    result = asyncio.run(handlers["on_list_tools"](None, None))
    advertised_names = {tool.name for tool in result.tools}

    assert advertised_names.isdisjoint(mcp_server._SIGNING_TOOLS)
    assert "integrity_agent_info" in advertised_names  # safe tools still advertised
    assert "integrity_resolve_did" in advertised_names
    assert "integrity_log_telemetry" in advertised_names


def test_signing_tool_call_is_refused_even_if_called_directly(monkeypatch):
    """Defense in depth: even bypassing discovery, dispatch itself refuses to execute."""
    monkeypatch.delenv("INTEGRITY_MCP_ALLOW_SIGNING_TOOLS", raising=False)
    import importlib
    importlib.reload(mcp_server)
    handlers = _build_server_capturing_handlers()

    class _Params:
        name = "integrity_register_agent"
        arguments = {"alias": "should-not-run"}

    result = asyncio.run(handlers["on_call_tool"](None, _Params()))
    assert result.is_error is True
    payload_text = result.content[0].text
    assert "disabled" in payload_text
    assert "integrity-cli" in payload_text
