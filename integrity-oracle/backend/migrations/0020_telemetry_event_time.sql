-- Signed event time is distinct from database receipt time. Existing rows are
-- conservatively assigned their receipt time; new signed batches provide the
-- authoritative event_time used by AIS reporting-window queries.
ALTER TABLE telemetry_events
    ADD COLUMN IF NOT EXISTS event_time TIMESTAMPTZ;

UPDATE telemetry_events
   SET event_time = created_at
 WHERE event_time IS NULL;

ALTER TABLE telemetry_events
    ALTER COLUMN event_time SET NOT NULL,
    ALTER COLUMN event_time SET DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_telemetry_events_agent_event_time
    ON telemetry_events (agent_id, event_time);
