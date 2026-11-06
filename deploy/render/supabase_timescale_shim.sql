-- TimescaleDB stand-ins for Supabase (which does not ship the extension).
--
-- Why: Oracle migrations 0004/0008/0021 call create_hypertable() and add_retention_policy(),
-- and db.rs uses time_bucket(). Without them the Oracle cannot migrate or serve its volume
-- queries on Supabase. These shims let the UNMODIFIED migrations run (minus the single
-- `CREATE EXTENSION timescaledb` line, see apply_migrations_supabase.sh), so the sqlx
-- checksums stay identical to the local database.
--
-- Semantics, stated plainly (no silent mocks):
--   create_hypertable   -> no-op. The otel_* tables are ordinary heap tables here. Fine at the
--                          1-day retention below; not a substitute for Timescale at scale.
--   add_retention_policy-> hourly pg_cron DELETE of rows older than the interval.
--   time_bucket         -> date_bin with Timescale's default origin (Monday 2000-01-03).
--                          Only the (interval, timestamptz) overload is shimmed because that is
--                          all db.rs uses; add others if a query starts needing them.
-- Run once, as postgres, in the Oracle schema (search_path must resolve to it).

CREATE EXTENSION IF NOT EXISTS pg_cron;

CREATE OR REPLACE FUNCTION create_hypertable(rel regclass, time_col name)
RETURNS void LANGUAGE sql AS $$ SELECT $$;

CREATE OR REPLACE FUNCTION time_bucket(bucket interval, ts timestamptz)
RETURNS timestamptz LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT date_bin(bucket, ts, TIMESTAMPTZ '2000-01-03 00:00:00+00') $$;

CREATE OR REPLACE FUNCTION add_retention_policy(rel regclass, drop_after interval, if_not_exists boolean DEFAULT false)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
  v_job text := 'oracle-retention-' || rel::text;
BEGIN
  PERFORM cron.unschedule(jobid) FROM cron.job WHERE jobname = v_job;
  PERFORM cron.schedule(v_job, '17 * * * *',
    format('DELETE FROM %s WHERE created_at < now() - interval %L', rel::text, drop_after::text));
  RETURN 1;
END $$;
