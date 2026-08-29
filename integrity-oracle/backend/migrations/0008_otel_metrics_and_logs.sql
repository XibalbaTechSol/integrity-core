-- OTLP metrics + logs storage.
--
-- Until now the OTLP receiver persisted only traces (`otel_spans`, migration 0004);
-- `OtlpMetricsService::export` accepted metric exports and discarded them, and no logs
-- service was registered at all. That left the richest agent data unreachable: Claude Code
-- (and any OTel-emitting agent runtime) reports token usage and cost as *metrics*
-- (`claude_code.token.usage` with type=input/output/cacheRead/cacheCreation,
-- `claude_code.cost.usage` in USD) and per-call detail as *log records*
-- (`claude_code.api_request` carrying input/output/cache tokens + cost_usd + duration).
--
-- Both tables follow `otel_spans`' shape deliberately: same `integrity.agent.id`
-- attribution, same TimescaleDB hypertable treatment, same composite primary key including
-- the partitioning column (a hypertable mechanical requirement — see 0004's note).
--
-- EVIDENCE TIER: rows here arrive over the UNAUTHENTICATED OTLP port and are NOT signed by
-- the agent's key, unlike `telemetry_events` (POST /v1/telemetry/ingest). They must never
-- feed AIS. `evidence_tier` is stored explicitly rather than implied by which table a row
-- landed in, so any future consumer has to make a deliberate choice about trusting it.

CREATE TABLE otel_metrics (
    id UUID NOT NULL,
    agent_id TEXT NOT NULL,
    -- e.g. 'claude_code.token.usage', 'claude_code.cost.usage'
    name TEXT NOT NULL,
    description TEXT,
    unit TEXT,
    -- 'sum' | 'gauge' | 'histogram' — the OTel data-point family this row came from.
    data_type TEXT NOT NULL,
    -- Numeric value of one data point. Histograms store their sum here and the full
    -- bucket layout in `attributes`, so a single scalar column stays meaningful.
    value DOUBLE PRECISION NOT NULL,
    -- Data-point attributes: for claude_code.token.usage this carries
    -- {"type":"cacheRead","model":"...","agent.name":"...","mcp_tool.name":"..."}.
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    start_time TIMESTAMPTZ,
    time TIMESTAMPTZ NOT NULL,
    evidence_tier TEXT NOT NULL DEFAULT 'unsigned_vendor',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
);

SELECT create_hypertable('otel_metrics', 'created_at');

CREATE INDEX idx_otel_metrics_agent_created ON otel_metrics (agent_id, created_at);
CREATE INDEX idx_otel_metrics_name ON otel_metrics (name);
-- Token/cost rollups filter on the data-point attributes (type, model), so index them.
CREATE INDEX idx_otel_metrics_attributes ON otel_metrics USING GIN (attributes);

CREATE TABLE otel_logs (
    id UUID NOT NULL,
    agent_id TEXT NOT NULL,
    -- OTel `LogRecord.event_name` where present, else the `event.name` attribute —
    -- e.g. 'claude_code.api_request', 'claude_code.tool_decision'.
    event_name TEXT,
    severity_text TEXT,
    severity_number INTEGER,
    -- Rendered log body. May be empty for structured events that carry everything in
    -- attributes, which is the common case for the events we care about.
    body TEXT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Present when the emitter correlates a log record to a span; lets a log join
    -- `otel_spans` without a separate correlation table.
    trace_id TEXT,
    span_id TEXT,
    time TIMESTAMPTZ NOT NULL,
    evidence_tier TEXT NOT NULL DEFAULT 'unsigned_vendor',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
);

SELECT create_hypertable('otel_logs', 'created_at');

CREATE INDEX idx_otel_logs_agent_created ON otel_logs (agent_id, created_at);
CREATE INDEX idx_otel_logs_event_name ON otel_logs (event_name);
CREATE INDEX idx_otel_logs_trace ON otel_logs (trace_id);
CREATE INDEX idx_otel_logs_attributes ON otel_logs USING GIN (attributes);
