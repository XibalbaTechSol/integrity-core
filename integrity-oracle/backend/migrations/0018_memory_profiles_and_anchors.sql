-- DID-bound Cortex profile aliases and session Merkle anchors.
CREATE TABLE IF NOT EXISTS memory_profiles (
    profile_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agents(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id)
);

CREATE TABLE IF NOT EXISTS memory_anchors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id TEXT NOT NULL REFERENCES memory_profiles(profile_id),
    agent_id TEXT NOT NULL REFERENCES agents(id),
    session_id TEXT NOT NULL,
    root_hash TEXT NOT NULL,
    leaf_count INTEGER NOT NULL CHECK (leaf_count >= 0),
    idempotency_key TEXT NOT NULL UNIQUE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    anchored_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (profile_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_anchors_profile_time
    ON memory_anchors (profile_id, anchored_at DESC);
