-- Semantic duplicate protection for signed telemetry.
-- The monotonic nonce rejects transport replay; this content hash rejects an
-- identical signed span batch submitted again under a fresh nonce. Historical
-- rows remain nullable because their original payloads are not rewritten.
ALTER TABLE telemetry_events
    ADD COLUMN IF NOT EXISTS content_hash BYTEA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetry_events_agent_content_hash
    ON telemetry_events (agent_id, content_hash)
    WHERE content_hash IS NOT NULL;
