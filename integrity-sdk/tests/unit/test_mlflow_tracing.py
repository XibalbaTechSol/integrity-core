"""
Tests for the MLflow + OpenTelemetry unified tracing module. These exercise
real MLflow span creation and the real bridge into IntegrityClient — no
mocked MLflow — but avoid asserting on MLflow's file-store trace *retrieval*
(unreliable in MLflow 3.x, documented in the module), testing the bridge
against directly-constructed spans instead.
"""

from __future__ import annotations

import pytest

# MLflow is the opt-in `mlflow` extra; skip (not error) where it is not installed.
mlflow = pytest.importorskip("mlflow")

from integrity_sdk.telemetry import mlflow_tracing


def test_trace_and_start_span_are_reexported():
    assert mlflow_tracing.trace is mlflow.trace
    assert mlflow_tracing.start_span is mlflow.start_span


def test_configure_tracing_otlp_sink_reports_capability(monkeypatch, tmp_path):
    summary = mlflow_tracing.configure_tracing(
        agent_id="test-agent",
        otlp_endpoint="http://localhost:4317",
        enable_autolog=False,
    )
    assert summary["sink"] == "otlp:http://localhost:4317"
    assert summary["autolog_enabled"] == []


def test_configure_tracing_file_sink_when_no_otlp(monkeypatch, tmp_path):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    summary = mlflow_tracing.configure_tracing(
        agent_id="test-agent",
        mlflow_tracking_uri=f"file://{tmp_path}/mlflow",
        enable_autolog=False,
    )
    assert summary["sink"].startswith("file://")


def test_configure_tracing_autolog_reports_skipped_frameworks(monkeypatch, tmp_path):
    # openai/langchain (+pandas) aren't installed in the base test env, so
    # autolog must be honestly reported as skipped, not silently "enabled".
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    summary = mlflow_tracing.configure_tracing(
        agent_id="test-agent",
        mlflow_tracking_uri=f"file://{tmp_path}/mlflow",
        enable_autolog=True,
    )
    # Every framework either enabled or explicitly skipped — never silently dropped.
    accounted = set(summary["autolog_enabled"]) | set(summary["autolog_skipped"].keys())
    assert accounted == set(mlflow_tracing._AUTOLOG_FRAMEWORKS)


def test_real_span_creation_via_decorator(tmp_path, monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    mlflow_tracing.configure_tracing(
        agent_id="test-agent",
        mlflow_tracking_uri=f"file://{tmp_path}/mlflow",
        enable_autolog=False,
    )

    @mlflow_tracing.trace(name="work", span_type="LLM")
    def work(x: int) -> int:
        return x * 2

    # The decorator must actually run the function and capture a span without
    # raising — the core tracing path works regardless of backend retrieval.
    assert work(21) == 42


def test_span_to_telemetry_entry_extracts_llm_completion_and_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    mlflow_tracing.configure_tracing(
        agent_id="test-agent",
        mlflow_tracking_uri=f"file://{tmp_path}/mlflow",
        enable_autolog=False,
    )

    with mlflow.start_span(name="llm_call", span_type="LLM") as span:
        span.set_outputs({"completion": "the answer is 42"})
        span.set_attributes(
            {
                "gen_ai.usage.total_tokens": 100,
                "gen_ai.usage.input_tokens": 60,
                "gen_ai.usage.output_tokens": 40,
            }
        )
        entry = mlflow_tracing.span_to_telemetry_entry(span)

    assert entry is not None
    assert entry["metadata"]["text_output"] == "the answer is 42"
    assert entry["metadata"]["token_usage"]["total_tokens"] == 100
    assert entry["metadata"]["provider"] == "mlflow-trace"


def test_span_to_telemetry_entry_skips_non_llm_spans(tmp_path, monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    mlflow_tracing.configure_tracing(
        agent_id="test-agent",
        mlflow_tracking_uri=f"file://{tmp_path}/mlflow",
        enable_autolog=False,
    )
    with mlflow.start_span(name="db_query", span_type="RETRIEVER") as span:
        span.set_outputs({"docs": ["a", "b"]})
        assert mlflow_tracing.span_to_telemetry_entry(span) is None


def test_bridged_llm_span_feeds_derivation(tmp_path, monkeypatch):
    """The end-to-end point: an MLflow LLM span's data, once bridged into
    IntegrityClient, actually produces non-trivial AIS signals via derive.py."""
    from integrity_sdk.client import IntegrityClient
    from integrity_sdk.telemetry import derive

    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    mlflow_tracing.configure_tracing(
        agent_id="bridge-agent",
        mlflow_tracking_uri=f"file://{tmp_path}/mlflow",
        enable_autolog=False,
    )

    client = IntegrityClient("bridge-agent", auto_flush=False)
    with mlflow.start_span(name="llm_call", span_type="LLM") as span:
        span.set_outputs({"completion": "yes yes yes yes"})
        span.set_attributes({"gen_ai.usage.total_tokens": 5000})
        entry = mlflow_tracing.span_to_telemetry_entry(span)

    client.log_telemetry(entry["metadata"])
    batch = client._batcher.get_batch_and_clear()
    signals = derive.derive_ais_signals(batch)
    # Repetitive completion -> max stability (entropy signal 1.0); real tokens
    # -> nonzero sacrifice.
    assert signals["entropy"] == 1.0
    assert signals["sacrifice"] > 0.0
