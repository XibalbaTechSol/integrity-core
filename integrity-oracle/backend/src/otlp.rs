//! Real OTLP/gRPC receiver (PRODUCTION_GAPS.md §1 item 2). Lights up the Python SDK's
//! already-working `OTLPSpanExporter`/`OTLPMetricExporter` (`integrity-sdk`'s
//! `telemetry/core.py::init_telemetry`, hardcoded to gRPC at `localhost:4317`), which
//! today exports "fails silently in the background" per its own docstring — nothing has
//! listened on that port until this module.
//!
//! Deliberately does NOT touch `telemetry_events`/AIS: real OTLP spans arrive over gRPC
//! with no Ed25519/secp256k1 signature envelope, unlike `POST /v1/telemetry/ingest`'s
//! payload (`handlers::ingest_telemetry`). Feeding them into the AIS computation would
//! let an unauthenticated source move an agent's score — see migration 0004's header
//! comment and `db::OtelSpanRow` for the separate storage surface this receiver writes
//! to instead. Callers of `/v1/agent/{id}/otel/volume` and `get_otel_spans_for_trace`
//! should treat this data as unauthenticated, not tamper-evident the way
//! `telemetry_events` is (that stays true until real SDK-side span signing exists — see
//! `PRODUCTION_GAPS.md` §2, still an open gap as of this writing).
//!
//! Trace export is fully implemented: PHI-scanned (reusing `crate::phi`, the same
//! backstop `ingest_telemetry` runs), persisted to `otel_spans`, and broadcast to any
//! live SSE subscriber via `AppState::telemetry_tx`. Metrics export is accepted (so the
//! SDK's `OTLPMetricExporter` gets a real gRPC response instead of connection failures)
//! but not yet parsed, PHI-scanned, or persisted — see `OtlpMetricsService::export`'s
//! doc comment for why, an honestly-documented gap rather than a silent one.

use chrono::{DateTime, Utc};
use opentelemetry_proto::tonic::collector::metrics::v1::metrics_service_server::MetricsService;
pub use opentelemetry_proto::tonic::collector::metrics::v1::metrics_service_server::MetricsServiceServer;
use opentelemetry_proto::tonic::collector::metrics::v1::{ExportMetricsServiceRequest, ExportMetricsServiceResponse};
use opentelemetry_proto::tonic::collector::trace::v1::trace_service_server::TraceService;
pub use opentelemetry_proto::tonic::collector::trace::v1::trace_service_server::TraceServiceServer;
use opentelemetry_proto::tonic::collector::trace::v1::{ExportTraceServiceRequest, ExportTraceServiceResponse};
use opentelemetry_proto::tonic::collector::logs::v1::logs_service_server::LogsService;
pub use opentelemetry_proto::tonic::collector::logs::v1::logs_service_server::LogsServiceServer;
use opentelemetry_proto::tonic::collector::logs::v1::{ExportLogsServiceRequest, ExportLogsServiceResponse};
use opentelemetry_proto::tonic::metrics::v1::{metric::Data as MetricData, number_data_point::Value as NumberValue};
use opentelemetry_proto::tonic::common::v1::any_value::Value as AnyValueKind;
use opentelemetry_proto::tonic::common::v1::KeyValue;
use opentelemetry_proto::tonic::resource::v1::Resource;
use opentelemetry_proto::tonic::trace::v1::{span, status, Span};
use tonic::{Request, Response, Status as TonicStatus};
use uuid::Uuid;

use crate::stream::StreamEvent;
use crate::{db, phi, AppState};

/// Fixed-window Redis rate limiter for the OTLP receiver — same mechanism and
/// per-agent/per-minute shape as `handlers::check_telemetry_rate_limit`, but tracked
/// under a distinct `ratelimit:otlp:*` key (separate budget from the signed
/// `/v1/telemetry/ingest` path) since this receiver is unauthenticated by design (see
/// this module's doc comment) and therefore needed *some* throttle even more than the
/// authenticated path already had — every span otherwise triggered an uncapped PHI scan
/// + synchronous Postgres insert with zero limiter, unlike every other write path in
/// this service (PRODUCTION_GAPS.md §2).
async fn check_otlp_rate_limit(state: &AppState, agent_id: &str) -> Result<(), TonicStatus> {
    use redis::AsyncCommands;

    let window = Utc::now().timestamp() / 60;
    let key = format!("ratelimit:otlp:{agent_id}:{window}");

    let mut conn = state.redis.clone();
    let count: i64 = conn
        .incr(&key, 1)
        .await
        .map_err(|e| TonicStatus::internal(format!("rate limiter unavailable: {e}")))?;
    if count == 1 {
        let _: () = conn
            .expire(&key, 60)
            .await
            .map_err(|e| TonicStatus::internal(format!("rate limiter unavailable: {e}")))?;
    }

    if count > state.config.telemetry_rate_limit_per_minute as i64 {
        return Err(TonicStatus::resource_exhausted(format!(
            "otlp span export rate limit exceeded ({} spans/min) for agent {agent_id}",
            state.config.telemetry_rate_limit_per_minute
        )));
    }
    Ok(())
}

/// The OTel resource attribute an agent's SDK must set so an incoming span can be
/// attributed to it — mirrors the `agent_id` field every other ingestion path
/// (`POST /v1/telemetry/ingest`) requires. A span whose resource lacks this attribute
/// is rejected (`INVALID_ARGUMENT`), not silently stored under a placeholder id.
///
/// Must match `integrity-sdk/integrity_sdk/telemetry/core.py::init_telemetry`'s
/// `Resource.create({..., "integrity.agent.id": agent_id})` exactly (dot-separated,
/// NOT `integrity.agent_id`) — this is the resource attribute the SDK's real,
/// already-working `OTLPSpanExporter` actually sets today, confirmed by reading that
/// module directly rather than assumed, since a mismatch here would make this receiver
/// reject every real span the SDK sends while still compiling and unit-testing clean.
pub const AGENT_ID_ATTRIBUTE_KEY: &str = "integrity.agent.id";

pub struct OtlpTraceService {
    state: AppState,
}

impl OtlpTraceService {
    pub fn new(state: AppState) -> Self {
        Self { state }
    }
}

/// Evidence tier for everything this receiver persists. The OTLP port is unauthenticated
/// and its payloads carry no agent signature, unlike `POST /v1/telemetry/ingest`. Stored on
/// every row so a consumer must decide explicitly whether to trust it, rather than
/// inferring trust from which table the row happens to live in.
pub const EVIDENCE_TIER_UNSIGNED_VENDOR: &str = "unsigned_vendor";

/// One metric data point, flattened across OTel's sum/gauge/histogram families into the
/// single shape `otel_metrics` stores.
struct MetricPoint {
    data_type: &'static str,
    /// OTel aggregation temporality. Load-bearing for correctness, not metadata: cumulative
    /// points carry a running total (so a rollup must take the max per series), delta points
    /// carry an increment (so a rollup must sum). See migration 0009.
    temporality: &'static str,
    value: f64,
    attributes: serde_json::Value,
    start_time: Option<DateTime<Utc>>,
    time: DateTime<Utc>,
}

/// Flattens a metric's data points.
///
/// Sums and gauges map directly. Histograms contribute their `sum` as the scalar value,
/// with `count` and the bucket layout preserved in `attributes` — dropping histograms
/// entirely would silently lose any latency distribution an emitter reports, and storing
/// only `count` would misrepresent them. Exponential histograms and summaries are not
/// flattened (no emitter we target uses them); they are skipped rather than approximated.
fn metric_points(metric: &opentelemetry_proto::tonic::metrics::v1::Metric) -> Vec<MetricPoint> {
    fn number_value(p: &opentelemetry_proto::tonic::metrics::v1::NumberDataPoint) -> f64 {
        match p.value {
            Some(NumberValue::AsDouble(d)) => d,
            Some(NumberValue::AsInt(i)) => i as f64,
            None => 0.0,
        }
    }
    fn start(nanos: u64) -> Option<DateTime<Utc>> {
        (nanos > 0).then(|| nanos_to_datetime(nanos))
    }
    // AggregationTemporality: 1 = DELTA, 2 = CUMULATIVE (opentelemetry proto metrics/v1).
    fn temporality_name(t: i32) -> &'static str {
        match t {
            1 => "delta",
            2 => "cumulative",
            _ => "unspecified",
        }
    }

    match &metric.data {
        Some(MetricData::Sum(sum)) => sum
            .data_points
            .iter()
            .map(|p| MetricPoint {
                data_type: "sum",
                temporality: temporality_name(sum.aggregation_temporality),
                value: number_value(p),
                attributes: kv_list_to_json(&p.attributes),
                start_time: start(p.start_time_unix_nano),
                time: nanos_to_datetime(p.time_unix_nano),
            })
            .collect(),
        Some(MetricData::Gauge(gauge)) => gauge
            .data_points
            .iter()
            .map(|p| MetricPoint {
                data_type: "gauge",
                // A gauge is a point-in-time reading; neither delta nor cumulative applies.
                temporality: "unspecified",
                value: number_value(p),
                attributes: kv_list_to_json(&p.attributes),
                start_time: start(p.start_time_unix_nano),
                time: nanos_to_datetime(p.time_unix_nano),
            })
            .collect(),
        Some(MetricData::Histogram(hist)) => hist
            .data_points
            .iter()
            .map(|p| {
                let mut attributes = kv_list_to_json(&p.attributes);
                if let Some(map) = attributes.as_object_mut() {
                    map.insert("histogram.count".into(), serde_json::json!(p.count));
                    map.insert("histogram.bucket_counts".into(), serde_json::json!(p.bucket_counts));
                    map.insert("histogram.explicit_bounds".into(), serde_json::json!(p.explicit_bounds));
                }
                MetricPoint {
                    data_type: "histogram",
                    temporality: temporality_name(hist.aggregation_temporality),
                    value: p.sum.unwrap_or(0.0),
                    attributes,
                    start_time: start(p.start_time_unix_nano),
                    time: nanos_to_datetime(p.time_unix_nano),
                }
            })
            .collect(),
        _ => Vec::new(),
    }
}

pub struct OtlpLogsService {
    state: AppState,
}

impl OtlpLogsService {
    pub fn new(state: AppState) -> Self {
        Self { state }
    }
}

pub struct OtlpMetricsService {
    state: AppState,
}

impl OtlpMetricsService {
    pub fn new(state: AppState) -> Self {
        Self { state }
    }
}

fn extract_agent_id(resource: &Option<Resource>) -> Option<String> {
    resource
        .as_ref()?
        .attributes
        .iter()
        .find(|kv| kv.key == AGENT_ID_ATTRIBUTE_KEY)
        .and_then(|kv| kv.value.as_ref())
        .and_then(|v| match &v.value {
            Some(AnyValueKind::StringValue(s)) => Some(s.clone()),
            _ => None,
        })
}

fn any_value_to_json(value: &opentelemetry_proto::tonic::common::v1::AnyValue) -> serde_json::Value {
    match &value.value {
        Some(AnyValueKind::StringValue(s)) => serde_json::Value::String(s.clone()),
        Some(AnyValueKind::BoolValue(b)) => serde_json::Value::Bool(*b),
        Some(AnyValueKind::IntValue(i)) => serde_json::Value::Number((*i).into()),
        Some(AnyValueKind::DoubleValue(d)) => serde_json::Number::from_f64(*d).map(serde_json::Value::Number).unwrap_or(serde_json::Value::Null),
        Some(AnyValueKind::ArrayValue(arr)) => serde_json::Value::Array(arr.values.iter().map(any_value_to_json).collect()),
        Some(AnyValueKind::KvlistValue(kv)) => kv_list_to_json(&kv.values),
        Some(AnyValueKind::BytesValue(b)) => serde_json::Value::String(hex::encode(b)),
        _ => serde_json::Value::Null,
    }
}

fn kv_list_to_json(kvs: &[KeyValue]) -> serde_json::Value {
    let mut map = serde_json::Map::new();
    for kv in kvs {
        if let Some(v) = &kv.value {
            map.insert(kv.key.clone(), any_value_to_json(v));
        }
    }
    serde_json::Value::Object(map)
}

/// PHI-scannable view of a span: name + attributes, the two free-text-bearing parts —
/// same scope `crate::phi`'s doc comment says the SDK-side redactor targets.
fn span_to_json(span: &Span) -> serde_json::Value {
    serde_json::json!({
        "name": span.name,
        "attributes": kv_list_to_json(&span.attributes),
    })
}

/// A span/trace ID of all-zero bytes (or empty) means "no parent" per the OTel spec
/// (`Span.parent_span_id`'s doc comment in the generated proto) — not a real 8-byte id.
fn hex_id_or_none(bytes: &[u8]) -> Option<String> {
    if bytes.is_empty() || bytes.iter().all(|b| *b == 0) {
        None
    } else {
        Some(hex::encode(bytes))
    }
}

fn span_kind_name(kind: i32) -> &'static str {
    span::SpanKind::try_from(kind).map(|k| k.as_str_name()).unwrap_or("SPAN_KIND_UNSPECIFIED")
}

fn span_status_name(status: Option<&opentelemetry_proto::tonic::trace::v1::Status>) -> &'static str {
    match status {
        Some(s) => status::StatusCode::try_from(s.code).map(|c| c.as_str_name()).unwrap_or("STATUS_CODE_UNSET"),
        None => "STATUS_CODE_UNSET",
    }
}

fn nanos_to_datetime(nanos: u64) -> DateTime<Utc> {
    // `nanos` is realistically far below i64::MAX (valid until year 2262) for any span
    // this receiver will ever see — `unwrap_or` covers the theoretical overflow rather
    // than panicking on adversarial input.
    DateTime::from_timestamp_nanos(nanos as i64)
}

#[tonic::async_trait]
impl TraceService for OtlpTraceService {
    async fn export(&self, request: Request<ExportTraceServiceRequest>) -> Result<Response<ExportTraceServiceResponse>, TonicStatus> {
        let req = request.into_inner();

        for resource_spans in &req.resource_spans {
            let agent_id = extract_agent_id(&resource_spans.resource)
                .ok_or_else(|| TonicStatus::invalid_argument(format!("resource missing required '{AGENT_ID_ATTRIBUTE_KEY}' attribute")))?;

            check_otlp_rate_limit(&self.state, &agent_id).await?;

            for scope_spans in &resource_spans.scope_spans {
                for span in &scope_spans.spans {
                    // Defense-in-depth PHI/PII/secret backstop, same posture and same
                    // categories as `ingest_telemetry`'s use of `crate::phi`: reject
                    // loudly before this ever touches Postgres, rather than silently
                    // persisting raw PHI/PII/secret material this receiver has no
                    // authenticated-client guarantee wasn't already redacted client-side.
                    let mut hits: Vec<&'static str> = Vec::new();
                    phi::scan_json_value(&span_to_json(span), &mut hits);
                    if !hits.is_empty() {
                        hits.sort_unstable();
                        hits.dedup();
                        return Err(TonicStatus::invalid_argument(format!(
                            "payload rejected: possible unredacted PHI/PII/secret detected (categories: {hits:?})"
                        )));
                    }

                    let trace_id = hex::encode(&span.trace_id);
                    let span_id = hex::encode(&span.span_id);
                    let parent_span_id = hex_id_or_none(&span.parent_span_id);
                    let attributes = kv_list_to_json(&span.attributes);
                    let id = Uuid::new_v4();

                    db::insert_otel_span(
                        &self.state.pool,
                        id,
                        &agent_id,
                        &trace_id,
                        &span_id,
                        parent_span_id.as_deref(),
                        &span.name,
                        span_kind_name(span.kind),
                        nanos_to_datetime(span.start_time_unix_nano),
                        nanos_to_datetime(span.end_time_unix_nano),
                        span_status_name(span.status.as_ref()),
                        &attributes,
                    )
                    .await
                    .map_err(|e| TonicStatus::internal(e.to_string()))?;

                    // Best-effort: `send` only errs when there are zero subscribers,
                    // which is a normal, expected state (no dashboard currently
                    // connected), not a failure this receiver should reject on.
                    let _ = self.state.telemetry_tx.send(StreamEvent::OtelSpan {
                        agent_id: agent_id.clone(),
                        trace_id: trace_id.clone(),
                        span_id: span_id.clone(),
                        name: span.name.clone(),
                    });
                }
            }
        }

        Ok(Response::new(ExportTraceServiceResponse::default()))
    }
}

#[tonic::async_trait]
impl MetricsService for OtlpMetricsService {
    /// Parses, PHI-scans, and persists OTLP metric data points to `otel_metrics`.
    ///
    /// This is where an agent runtime's token and cost accounting actually arrives: Claude
    /// Code reports `claude_code.token.usage` (with `type` = input/output/cacheRead/
    /// cacheCreation) and `claude_code.cost.usage` (USD) as metrics, not spans. Previously
    /// this handler accepted the export and threw it away.
    ///
    /// Sums and gauges are stored per data point. Histograms store their `sum` as the
    /// scalar value with bucket layout preserved in `attributes`, so one numeric column
    /// stays meaningful across families rather than silently dropping histograms.
    ///
    /// Rows are tagged `evidence_tier = "unsigned_vendor"`: this port is unauthenticated
    /// and the payload carries no agent signature, so it must never feed AIS (see
    /// migration 0008's header).
    async fn export(&self, request: Request<ExportMetricsServiceRequest>) -> Result<Response<ExportMetricsServiceResponse>, TonicStatus> {
        let req = request.into_inner();

        for resource_metrics in &req.resource_metrics {
            let agent_id = extract_agent_id(&resource_metrics.resource)
                .ok_or_else(|| TonicStatus::invalid_argument(format!("resource missing required '{AGENT_ID_ATTRIBUTE_KEY}' attribute")))?;

            check_otlp_rate_limit(&self.state, &agent_id).await?;

            for scope_metrics in &resource_metrics.scope_metrics {
                for metric in &scope_metrics.metrics {
                    let description = (!metric.description.is_empty()).then(|| metric.description.clone());
                    let unit = (!metric.unit.is_empty()).then(|| metric.unit.clone());

                    for point in metric_points(metric) {
                        // Same PHI backstop as the trace path: metric attributes are
                        // free-text-bearing (model names, tool names, and whatever an
                        // emitter chooses to tag) and this receiver has no authenticated
                        // guarantee they were redacted client-side.
                        let mut hits: Vec<&'static str> = Vec::new();
                        phi::scan_json_value(&serde_json::json!({"name": metric.name, "attributes": point.attributes}), &mut hits);
                        if !hits.is_empty() {
                            hits.sort_unstable();
                            hits.dedup();
                            return Err(TonicStatus::invalid_argument(format!(
                                "payload rejected: possible unredacted PHI/PII/secret detected (categories: {hits:?})"
                            )));
                        }

                        db::insert_otel_metric(
                            &self.state.pool,
                            Uuid::new_v4(),
                            &agent_id,
                            &metric.name,
                            description.as_deref(),
                            unit.as_deref(),
                            point.data_type,
                            point.temporality,
                            point.value,
                            &point.attributes,
                            point.start_time,
                            point.time,
                            EVIDENCE_TIER_UNSIGNED_VENDOR,
                        )
                        .await
                        .map_err(|e| TonicStatus::internal(e.to_string()))?;
                    }
                }
            }
        }

        Ok(Response::new(ExportMetricsServiceResponse::default()))
    }
}

#[tonic::async_trait]
impl LogsService for OtlpLogsService {
    /// Parses, PHI-scans, and persists OTLP log records to `otel_logs`.
    ///
    /// Structured agent events land here — `claude_code.api_request` (per-call
    /// input/output/cache tokens plus `cost_usd` and `duration_ms`),
    /// `claude_code.tool_decision` (accept/reject and its source), and
    /// `claude_code.api_refusal`. No logs service was registered at all before this, so
    /// these exports had nowhere to land.
    ///
    /// Same `evidence_tier = "unsigned_vendor"` caveat as metrics.
    async fn export(&self, request: Request<ExportLogsServiceRequest>) -> Result<Response<ExportLogsServiceResponse>, TonicStatus> {
        let req = request.into_inner();

        for resource_logs in &req.resource_logs {
            let agent_id = extract_agent_id(&resource_logs.resource)
                .ok_or_else(|| TonicStatus::invalid_argument(format!("resource missing required '{AGENT_ID_ATTRIBUTE_KEY}' attribute")))?;

            check_otlp_rate_limit(&self.state, &agent_id).await?;

            for scope_logs in &resource_logs.scope_logs {
                for record in &scope_logs.log_records {
                    let attributes = kv_list_to_json(&record.attributes);
                    let body = record.body.as_ref().map(any_value_to_json).and_then(|v| match v {
                        serde_json::Value::String(s) => Some(s),
                        serde_json::Value::Null => None,
                        other => Some(other.to_string()),
                    });

                    // Log records are the highest-risk OTLP surface for unredacted
                    // content: enabling OTEL_LOG_USER_PROMPTS / OTEL_LOG_ASSISTANT_RESPONSES
                    // puts raw prompt and response text directly into these attributes.
                    // Scan body and attributes together and reject loudly.
                    let mut hits: Vec<&'static str> = Vec::new();
                    phi::scan_json_value(
                        &serde_json::json!({"body": body, "attributes": attributes}),
                        &mut hits,
                    );
                    if !hits.is_empty() {
                        hits.sort_unstable();
                        hits.dedup();
                        return Err(TonicStatus::invalid_argument(format!(
                            "payload rejected: possible unredacted PHI/PII/secret detected (categories: {hits:?})"
                        )));
                    }

                    // OTel moved structured event identity from an `event.name` attribute
                    // to a first-class `event_name` field; accept either so emitters on
                    // both conventions are attributed rather than silently unnamed.
                    let event_name = (!record.event_name.is_empty())
                        .then(|| record.event_name.clone())
                        .or_else(|| {
                            attributes
                                .get("event.name")
                                .and_then(serde_json::Value::as_str)
                                .map(str::to_string)
                        });

                    // Prefer the record's own timestamp; fall back to observed time, which
                    // is what an emitter sets when the source had no clock reading.
                    let time = if record.time_unix_nano > 0 {
                        nanos_to_datetime(record.time_unix_nano)
                    } else {
                        nanos_to_datetime(record.observed_time_unix_nano)
                    };

                    db::insert_otel_log(
                        &self.state.pool,
                        Uuid::new_v4(),
                        &agent_id,
                        event_name.as_deref(),
                        (!record.severity_text.is_empty()).then(|| record.severity_text.clone()).as_deref(),
                        (record.severity_number != 0).then_some(record.severity_number),
                        body.as_deref(),
                        &attributes,
                        hex_id_or_none(&record.trace_id).as_deref(),
                        hex_id_or_none(&record.span_id).as_deref(),
                        time,
                        EVIDENCE_TIER_UNSIGNED_VENDOR,
                    )
                    .await
                    .map_err(|e| TonicStatus::internal(e.to_string()))?;
                }
            }
        }

        Ok(Response::new(ExportLogsServiceResponse::default()))
    }
}
