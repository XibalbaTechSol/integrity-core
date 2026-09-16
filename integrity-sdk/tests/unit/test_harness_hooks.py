from integrity_sdk import IntegrityAgent, IntegrityHookAdapter, normalize_hook


def test_normalize_hook_is_the_shared_native_field_boundary():
    normalized = normalize_hook("PostToolUse", {
        "conversationId": "c1", "stepIdx": 4,
        "toolCall": {"name": "run_command", "args": {"secret": "omit"}},
    })
    assert normalized == {
        "hook": "PostToolUse", "session_id": "c1", "turn_id": None,
        "invocation_id": "step:4", "tool_call_id": None,
        "tool_name": "run_command", "event_id": "stepIdx:4",
        "status": None, "traceparent": None,
    }
    assert "secret" not in str(normalized)


def test_camel_case_hook_names_share_the_tool_result_family(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    agent = IntegrityAgent.open(
        "camel-hook-agent", harness="agy",
        client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    IntegrityHookAdapter(agent).ingest("PostToolUse", {
        "conversationId": "c1", "toolCall": {"name": "view_file"}, "status": "ok",
    })
    row = agent.client._batcher.get_batch_and_clear()[0]
    assert row["metadata"]["event"] == "tool_result"
    agent.close(flush=False)


def test_shared_hook_adapter_preserves_identity_and_bounds_payloads(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    agent = IntegrityAgent.open(
        "hook-agent", harness="hermes",
        client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    adapter = IntegrityHookAdapter(agent)
    adapter.ingest("on_session_start", {"session_id": "s1"})
    adapter.ingest("post_tool_call", {
        "session_id": "s1", "tool_name": "shell", "args": {"secret": "private"},
        "result": "done", "status": "ok", "tool_call_id": "call-1",
    })
    rows = agent.client._batcher.get_batch_and_clear()
    assert {row["metadata"]["event"] for row in rows} == {"session_started", "tool_result"}
    tool = next(row for row in rows if row["metadata"]["event"] == "tool_result")
    assert tool["metadata"]["tool_input_hash"].startswith("sha256:")
    assert "private" not in str(tool)
    assert tool["metadata"]["agent_did"] == agent.did
    agent.close(flush=False)


def test_shared_hook_adapter_accepts_camel_case_session_and_nested_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    agent = IntegrityAgent.open(
        "agy-hook-agent", harness="agy",
        client_kwargs={"auto_flush": False, "enable_otel_export": False},
    )
    result = IntegrityHookAdapter(agent).ingest(
        "PostToolUse", {"conversationId": "c1", "toolCall": {"name": "view_file", "args": {"x": 1}}}
    )
    assert result["recorded"] is True
    row = agent.client._batcher.get_batch_and_clear()[0]
    assert row["metadata"]["tool_name"] == "view_file"
    agent.close(flush=False)
