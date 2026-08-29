-- JWT revocation table. Every access token now carries a `jti` claim
-- (app/security.py::create_access_token); logging out inserts that `jti`
-- here, and `get_current_token` (app/deps.py) rejects any presented token
-- whose `jti` shows up in this table, even though it's still within its
-- natural `exp` window.
--
-- `expires_at` mirrors the token's own `exp` claim so a revoked row can be
-- swept once the token it revokes could never have been valid anyway
-- (POST /auth/logout opportunistically deletes expired rows on every call --
-- see app/main.py -- so this table doesn't grow unbounded without needing a
-- separate cron/worker process).
CREATE TABLE revoked_tokens (
    jti         UUID PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    revoked_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_revoked_tokens_expires_at ON revoked_tokens (expires_at);
