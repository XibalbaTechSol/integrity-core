-- Durable, user-owned policy-pack drafts and revisions.
-- Rules are structured JSON, not raw Rego. Compilation/activation is a
-- separate step so saving a draft never changes runtime behavior.

CREATE TABLE policy_packs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    description         TEXT NOT NULL DEFAULT '',
    agent_did           TEXT,
    mode                TEXT NOT NULL DEFAULT 'observe' CHECK (mode IN ('observe', 'enforce')),
    active_revision     INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_policy_packs_user_id ON policy_packs(user_id);
CREATE INDEX idx_policy_packs_agent_did ON policy_packs(user_id, agent_did);

CREATE TABLE policy_revisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pack_id         UUID NOT NULL REFERENCES policy_packs(id) ON DELETE CASCADE,
    version         INTEGER NOT NULL CHECK (version > 0),
    rules           JSONB NOT NULL DEFAULT '[]'::jsonb,
    mode            TEXT NOT NULL DEFAULT 'observe' CHECK (mode IN ('observe', 'enforce')),
    change_note     TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pack_id, version)
);

CREATE INDEX idx_policy_revisions_pack_id ON policy_revisions(pack_id, version DESC);
