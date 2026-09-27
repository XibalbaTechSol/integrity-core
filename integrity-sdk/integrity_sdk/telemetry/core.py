"""
OpenTelemetry wiring: real TracerProvider/MeterProvider with OTLP/gRPC
export. This was already-working code in the old prototype (not one of the
mocked pieces) — kept largely as-is, with initialization made idempotent
(safe to call more than once, e.g. from multiple `IntegrityClient` instances
in the same process) since OTel raises if you try to set a global provider
twice.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("integrity_sdk.telemetry.core")

_initialized = False


def init_telemetry(agent_id: str, endpoint: str = "localhost:4317", insecure: bool = True) -> None:
    """
    Initialize global OTel Tracer/Meter providers pointed at an OTLP/gRPC
    endpoint. Safe to call multiple times — only the first call actually
    installs providers; later calls are no-ops. If no collector is
    listening at `endpoint`, span/metric export fails silently in the
    background (BatchSpanProcessor's own behavior) rather than raising —
    OTel telemetry is best-effort observability, not a piece of the trust
    chain (unlike the BCC/OPA/ZK/attestation paths, which fail closed).
    """
    global _initialized
    if _initialized:
        return

    resource = Resource.create(
        {
            "service.name": "integrity-agent",
            "service.version": "0.1.0",
            "integrity.agent.id": agent_id,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
    # Keep the SDK's in-memory retry queue and each export batch bounded even
    # when the collector is slow or unavailable.
    tracer_provider.add_span_processor(BatchSpanProcessor(
        trace_exporter, max_queue_size=2048, max_export_batch_size=512,
        export_timeout_millis=5000,
    ))
    trace.set_tracer_provider(tracer_provider)

    metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
    export_interval = max(1000, int(os.environ.get("INTEGRITY_METRIC_EXPORT_INTERVAL_MILLIS", "60000")))
    reader = PeriodicExportingMetricReader(metric_exporter, export_interval_millis=export_interval)
    meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(meter_provider)

    _initialized = True


def get_tracer(name: str = "integrity_sdk"):
    return trace.get_tracer(name)


def get_meter(name: str = "integrity_sdk"):
    return metrics.get_meter(name)
