-- Make oracle_app own every relation in the Oracle's schema. Run as postgres (admin URL).
--
-- Why: apply_migrations_supabase.sh applies the migrations as postgres, so postgres owned the
-- tables while the Oracle connects as oracle_app. The Oracle's own startup migrator then failed on
-- the first ALTER of an existing table (migration 25, 2026-11-14: "must be owner of table
-- telemetry_events"). Render rolled the deploy back, and the old build kept serving.
--
-- postgres keeps full access by inheriting oracle_app, so the pg_cron retention jobs (which run
-- as postgres) keep working. Supabase's postgres is not a superuser, and on PG16+
-- `ALTER ... OWNER TO oracle_app` also needs SET on oracle_app, hence the GRANT.
-- Idempotent: it only touches relations postgres still owns.
--
-- Usage: psql "$ORACLE_ADMIN_URL" -v schema=oracle -f deploy/render/oracle_ownership.sql
\set ON_ERROR_STOP on
SELECT set_config('xb.schema', :'schema', false);

BEGIN;
GRANT oracle_app TO postgres WITH INHERIT TRUE, SET TRUE;

DO $$
DECLARE
  s text := current_setting('xb.schema');
  r record;
BEGIN
  EXECUTE format('ALTER SCHEMA %I OWNER TO oracle_app', s);
  FOR r IN
    SELECT c.relname, c.relkind
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = s AND pg_get_userbyid(c.relowner) = 'postgres'
       AND c.relkind IN ('r','p','v','m','f')
  LOOP
    EXECUTE format('ALTER %s %I.%I OWNER TO oracle_app',
      CASE r.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                     WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END, s, r.relname);
  END LOOP;
  -- standalone sequences; sequences owned by a column moved with their table
  FOR r IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = s AND c.relkind = 'S' AND pg_get_userbyid(c.relowner) = 'postgres'
  LOOP
    EXECUTE format('ALTER SEQUENCE %I.%I OWNER TO oracle_app', s, r.relname);
  END LOOP;
END $$;
COMMIT;

-- Verify: nothing left owned by postgres (expect zero rows).
SELECT c.relname, c.relkind
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = current_setting('xb.schema')
   AND c.relkind IN ('r','p','v','m','S','f')
   AND pg_get_userbyid(c.relowner) <> 'oracle_app';
