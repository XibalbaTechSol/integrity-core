-- PHI backstop: record WHICH categories matched when the backstop runs in `flag` mode.
--
-- The backstop used to have exactly one behaviour: reject (AppError::PhiDetected -> 400).
-- That is correct for a regulated deployment and useless for development, where the operator
-- deliberately collects unredacted content (integrity-sdk's collection profiles) and every
-- such payload was refused at the boundary.
--
-- `flag` mode stores the payload AND the matched categories, so the data is usable while the
-- risk stays visible in the row itself rather than living only in a log line. NULL means the
-- backstop found nothing (or ran in `off` mode) — an empty array would falsely assert "scanned
-- and clean".
ALTER TABLE telemetry_events ADD COLUMN phi_flags TEXT[];
ALTER TABLE otel_spans      ADD COLUMN phi_flags TEXT[];
ALTER TABLE otel_logs       ADD COLUMN phi_flags TEXT[];
ALTER TABLE otel_metrics    ADD COLUMN phi_flags TEXT[];

-- Finding flagged rows is an audit operation, so index for it. Partial: the overwhelming
-- majority of rows are NULL and indexing those wastes space.
CREATE INDEX idx_telemetry_events_phi_flagged ON telemetry_events (agent_id) WHERE phi_flags IS NOT NULL;
CREATE INDEX idx_otel_spans_phi_flagged      ON otel_spans (agent_id)      WHERE phi_flags IS NOT NULL;
CREATE INDEX idx_otel_logs_phi_flagged       ON otel_logs (agent_id)       WHERE phi_flags IS NOT NULL;
