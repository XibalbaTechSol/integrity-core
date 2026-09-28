-- Index every audit_log row's signed `invocation_id` for lookup, not only posttool rows.
--
-- `get_audit_log_by_invocation_id` (GET /v1/audit/invocation/{id}) and the invocation
-- correlation join filter on `metadata->>'invocation_id' = $1` across ALL event types.
-- The only index on that expression was 0016's partial UNIQUE index (posttool_effect
-- rows only), which the planner cannot use for those queries, so each lookup was a
-- parallel sequential scan of the whole table: 9.4 s at 774k rows (measured 2026-09-28).
-- Concurrent dashboard lookups then held every pool connection and the Oracle answered
-- 500 "pool timed out while waiting for an open connection".
--
-- Non-partial, so rows without the key index as NULL; that keeps the equality lookups
-- index-eligible without rewriting their SQL. Measured on the same data inside a
-- rolled-back transaction: index build 4.9 s, lookup 9,362 ms -> 38 ms (Index Scan).
CREATE INDEX IF NOT EXISTS idx_audit_log_invocation_id
    ON audit_log ((metadata->>'invocation_id'));
