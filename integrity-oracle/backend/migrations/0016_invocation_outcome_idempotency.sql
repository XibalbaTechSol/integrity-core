-- One attempted action may produce at most one authoritative post-tool outcome.
--
-- `invocation_id` remains inside metadata because audit_log is an append-only generic
-- event ledger, but the protocol now gives that JSON member first-class uniqueness
-- semantics for posttool_effect rows. The matching INSERT uses the same expression and
-- predicate in its ON CONFLICT clause so retries return the original row id.
CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_log_posttool_effect_invocation
    ON audit_log ((metadata->>'invocation_id'))
    WHERE event_type = 'posttool_effect'
      AND metadata ? 'invocation_id';

