-- Diagnostic OTLP data is deliberately separate from signed telemetry_events.
-- Keep one day of spans, metrics, and logs; do not expire canonical protocol evidence.
SELECT add_retention_policy('otel_spans', INTERVAL '1 day', if_not_exists => TRUE);
SELECT add_retention_policy('otel_metrics', INTERVAL '1 day', if_not_exists => TRUE);
SELECT add_retention_policy('otel_logs', INTERVAL '1 day', if_not_exists => TRUE);
