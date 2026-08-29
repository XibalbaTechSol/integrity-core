-- Real, durable audit trail (PRODUCTION_GAPS.md request: "fix audit logs to be a genuine
-- source of truth"). Before this migration, the single most audit-worthy event type --
-- bcc_middleware's real per-request OPA ALLOW/DENY policy decisions -- had ZERO durable
-- storage anywhere in the stack (confirmed by grep: no sqlite/psycopg/sqlalchemy/CREATE
-- TABLE anywhere under bcc_middleware/). Deny reasons only ever existed in the HTTP
-- response body; allow-decisions only existed as an opaque 32-byte Merkle leaf hash
-- on-chain. `audit_log` gives bcc_middleware a durable write path (via POST
-- /v1/audit/ingest, best-effort/fire-and-forget from run_intercept -- see
-- bcc_middleware/app/audit.py) so every intercept decision, not just approved ones, is
-- queryable after the fact.
--
-- `agent_id` has no FK to `agents(id)`: a forged-signature or unknown-agent deny (the
-- most security-relevant kind of event to keep!) may reference an agent_id that never
-- resolves to a row in `agents` at all -- mirrors `otel_spans`' same no-FK choice for the
-- same reason (see migrations/0004's header note).
CREATE TABLE IF NOT EXISTS audit_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id     TEXT,
    source       TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    decision     TEXT NOT NULL,
    reason_code  TEXT,
    detail       TEXT,
    intent_type  TEXT,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_agent_created ON audit_log (agent_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log (created_at DESC);
