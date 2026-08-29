"""
MLflow GenAI tracing, unified with this SDK's existing OpenTelemetry pipeline.

Why both MLflow *and* OpenTelemetry rather than one or the other: they solve
different halves of "advanced traces, spans, and data".

  - OpenTelemetry (telemetry/core.py) is the transport/wire standard — it's
    what lets spans flow to any collector/backend (Jaeger, Grafana Tempo, a
    vendor) in a vendor-neutral format. But raw OTel gives you spans, not
    GenAI-*shaped* spans; you'd hand-instrument every prompt/completion/
    tool-call/token-count yourself (which is exactly what
    integrations/openai_integrity.py does today, by hand).

  - MLflow's tracing layer is the GenAI-*semantics* half: `@mlflow.trace` and
    `mlflow.<framework>.autolog()` automatically capture LLM/tool/retriever
    spans with the right span types, inputs/outputs, and token-usage
    attributes — the rich structure the old hand-instrumentation approximated.

The important part: MLflow does NOT replace OTel here, it rides on it. When an
OTLP endpoint is configured, MLflow exports its spans *through* OpenTelemetry
(via `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`), so a single OTel collector sees
both this SDK's own hand-rolled spans and MLflow's auto-captured GenAI spans
as one unified trace stream. No second backend, no split observability.

And a third consumer: `bridge_trace_to_client` pulls the LLM spans out of a
finished MLflow trace and feeds them into `IntegrityClient` so the same rich
data also drives AIS-signal derivation (telemetry/derive.py) — the traces
aren't just for a human looking at Grafana, they're load-bearing input to the
agent's on-chain reputation.

Autolog for specific frameworks (openai, langchain) needs those frameworks
(and pandas) installed; this module enables what's available and honestly
reports what isn't, rather than pretending. MLflow's own core tracing
(`trace`/`start_span`) works with no framework at all.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import mlflow

from .core import init_telemetry

logger = logging.getLogger("integrity_sdk.telemetry.mlflow_tracing")

# Re-exported so callers do `from integrity_sdk.telemetry.mlflow_tracing import
# trace, start_span` rather than reaching into mlflow directly — keeps the
# GenAI-tracing entrypoint in one place and lets us swap the backing library
# later without touching agent code.
trace = mlflow.trace
start_span = mlflow.start_span

# Frameworks MLflow can autolog. Each is attempted independently; a missing
# framework (or its heavier deps like pandas) is skipped with a logged note,
# never a crash — an agent using only OpenAI shouldn't fail because LangChain
# isn't installed, and vice versa.
_AUTOLOG_FRAMEWORKS = ("openai", "langchain")


def configure_tracing(
    *,
    agent_id: str,
    otlp_endpoint: Optional[str] = None,
    mlflow_tracking_uri: Optional[str] = None,
    experiment: Optional[str] = None,
    enable_autolog: bool = True,
) -> Dict[str, Any]:
    """
    Wire up the unified tracing pipeline.

    Precedence for where spans go:
      1. If `otlp_endpoint` (or the standard `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
         env var) is set, MLflow exports spans via OTLP — the production path,
         unified with this SDK's own OTel spans (telemetry/core.py). This is
         the recommended configuration.
      2. Otherwise, MLflow logs to `mlflow_tracking_uri` (defaulting to a local
         file store, gated by MLFLOW_ALLOW_FILE_STORE for `mlflow ui`
         inspection during local dev). Note MLflow 3.x's file store is in
         maintenance mode and its trace *retrieval* is unreliable — local
         inspection is best-effort; the OTLP path (1) is what production uses.

    Returns a summary dict of what was actually enabled (which autolog
    frameworks succeeded, which sink is active), so a caller/test can assert on
    real capability rather than assume.
    """
    summary: Dict[str, Any] = {"sink": None, "autolog_enabled": [], "autolog_skipped": {}}

    resolved_otlp = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if resolved_otlp:
        # Make MLflow export through the same OTel/OTLP endpoint the SDK's own
        # spans use. Setting the standard env var is MLflow's documented switch
        # for "export traces to an OpenTelemetry Collector instead of the
        # MLflow backend".
        os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = resolved_otlp
        # Also stand up this SDK's own OTel providers pointed at the same place
        # (idempotent — see core.init_telemetry), so hand-rolled and MLflow
        # spans share one exporter.
        endpoint_hostport = resolved_otlp.replace("http://", "").replace("https://", "").rstrip("/")
        init_telemetry(agent_id=agent_id, endpoint=endpoint_hostport)
        summary["sink"] = f"otlp:{resolved_otlp}"
    else:
        tracking_uri = mlflow_tracking_uri or f"file://{os.path.expanduser('~/.integrity/mlflow')}"
        # The file store refuses to run in MLflow 3.x without this opt-out; set
        # it so local-dev `mlflow ui` at least captures spans (retrieval caveat
        # noted above).
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        mlflow.set_tracking_uri(tracking_uri)
        summary["sink"] = tracking_uri

    if experiment:
        mlflow.set_experiment(experiment)

    if enable_autolog:
        for framework in _AUTOLOG_FRAMEWORKS:
            try:
                autolog_fn = getattr(mlflow, framework).autolog
                autolog_fn(log_traces=True, disable=False, silent=True)
                summary["autolog_enabled"].append(framework)
            except Exception as exc:  # noqa: BLE001 — any failure = "not available", skip honestly
                # Most commonly a missing framework or its pandas dependency.
                # Recorded, not raised: partial autolog coverage is a real,
                # honest state, not an error.
                summary["autolog_skipped"][framework] = str(exc).splitlines()[0] if str(exc) else type(exc).__name__

    logger.info("MLflow tracing configured: sink=%s autolog=%s", summary["sink"], summary["autolog_enabled"])
    return summary


def _span_type_of(span: Any) -> str:
    # MLflow stores span type both as a top-level attr and under the
    # `mlflow.spanType` attribute key depending on version — check both.
    span_type = getattr(span, "span_type", None)
    if span_type:
        return str(span_type)
    try:
        return str(span.get_attribute("mlflow.spanType") or "UNKNOWN")
    except Exception:
        return "UNKNOWN"


def span_to_telemetry_entry(span: Any) -> Optional[Dict[str, Any]]:
    """
    Convert one MLflow LLM/CHAT span into the dict shape
    `IntegrityClient.log_telemetry` / `derive.py` expect, or None if the span
    carries nothing derivation can use.

    Extracts the completion text (from the span's outputs) and token usage
    (from the span's attributes) — the two things derive.py's entropy and
    sacrifice signals read. Returns None for non-LLM spans (a retriever or
    plain function span has no completion to score), so a caller can filter.
    """
    span_type = _span_type_of(span).upper()
    if span_type not in ("LLM", "CHAT_MODEL", "CHAT"):
        return None

    outputs = getattr(span, "outputs", None) or {}
    completion_text = ""
    if isinstance(outputs, dict):
        # MLflow/OpenAI autolog nests the completion under a few possible
        # shapes across versions; take the first string-y one we find.
        for key in ("completion", "content", "output", "text"):
            value = outputs.get(key)
            if isinstance(value, str) and value:
                completion_text = value
                break
        if not completion_text:
            # Fall back to the raw outputs repr so entropy still has *something*
            # real to measure rather than silently scoring an empty string.
            completion_text = str(outputs)

    token_usage: Dict[str, int] = {}
    for attr_key, usage_key in (
        ("gen_ai.usage.total_tokens", "total_tokens"),
        ("gen_ai.usage.input_tokens", "prompt_tokens"),
        ("gen_ai.usage.output_tokens", "completion_tokens"),
    ):
        try:
            value = span.get_attribute(attr_key)
        except Exception:
            value = None
        if isinstance(value, (int, float)):
            token_usage[usage_key] = int(value)

    return {
        "metadata": {
            "text_output": completion_text,
            "token_usage": token_usage,
            "provider": "mlflow-trace",
            "span_type": span_type,
        }
    }


def bridge_trace_to_client(trace_id: str, client: Any) -> int:
    """
    Pull the LLM spans out of a finished MLflow trace and feed them into
    `client` (an IntegrityClient) via `log_telemetry`, so MLflow's rich
    auto-captured GenAI data also drives AIS-signal derivation — not just a
    Grafana dashboard.

    Returns the number of spans bridged. Best-effort: a failure to load the
    trace (MLflow file-store flakiness, async-export lag) logs a warning and
    returns 0 rather than raising — telemetry is observability, not a security
    gate.
    """
    try:
        mlflow_trace = mlflow.get_trace(trace_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not load MLflow trace %s to bridge: %s", trace_id, exc)
        return 0

    if mlflow_trace is None or not getattr(mlflow_trace, "data", None):
        return 0

    bridged = 0
    for span in mlflow_trace.data.spans:
        entry = span_to_telemetry_entry(span)
        if entry is not None:
            client.log_telemetry(entry["metadata"])
            bridged += 1
    return bridged
