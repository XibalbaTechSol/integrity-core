# Oracle on Render (free) + Supabase Postgres

Status: **prepared, not deployed.** Nothing here has touched Render or the Supabase project.
Files: `integrity-oracle/Dockerfile.render`, `deploy/render/oracle.render.yaml`,
`deploy/render/supabase_timescale_shim.sql`, `deploy/render/apply_migrations_supabase.sh`.

## What changes vs. the local Oracle

| Local (docker compose) | Render free + Supabase |
|---|---|
| TimescaleDB hypertables, retention policies | Plain tables + `pg_cron` hourly DELETE (shim). Supabase has no `timescaledb`. |
| `time_bucket()` from Timescale | Shim over `date_bin` (same default origin) |
| Redis container | Render Key Value (free), LRU eviction; only a rate-limit counter lives there. **Optional since 2026-11-12:** if it is suspended or unreachable the Oracle starts anyway (≤10s wait) and counts limits in-process |
| OTLP gRPC on :4317 | **Not reachable** (Render exposes `$PORT` only). Use the HTTP telemetry endpoints. |
| Always on | **Free web services sleep after ~15 min idle**; first request cold-starts (~30-60 s). Shared ~750 h/month pool across free services. |

Consequences to accept before switching: a sleeping Oracle delays the first telemetry flush
(Shield and the SDK re-queue on failure, so nothing is lost, only late), and a Rust cold start
plus Supabase pooler connect can exceed short client timeouts.

## Migration approach (why not just run the Oracle's own migrator)

Migration 0004 runs `CREATE EXTENSION timescaledb`, which fails on Supabase. The migrations are
checksummed by sqlx, so they cannot be edited. `apply_migrations_supabase.sh` therefore applies
the **unmodified** files minus that one line, after installing the shim functions, and writes
`_sqlx_migrations` rows with sqlx's own checksum (sha384 of the file). At boot the Oracle's
`sqlx::migrate!().run()` sees 23/23 applied and does nothing.

Verified 2026-11-06 against a Supabase-image Postgres 17 without Timescale: all 23 checksums
identical to the local database, identical table set, 3 retention jobs scheduled.

Boot test passed 2026-11-06: the image built from `Dockerfile.render` started against the shimmed
schema (migrations skipped, Redis + chain client connected, `/healthz` 200 and `/v1/leaderboard`
200 on `$PORT`). Note the Oracle exits if port 4317 is already taken, so never run two on one host.

Not verified: `time_bucket` equivalence on week-sized buckets against real Timescale, and the
volume endpoints that call it.

## Steps (each needs your explicit go; none are run by this branch)

1. **Schema + role** (Supabase SQL editor or MCP, as `postgres`):
   ```sql
   CREATE ROLE oracle_app LOGIN PASSWORD '<generate>';
   CREATE SCHEMA IF NOT EXISTS oracle AUTHORIZATION oracle_app;
   ALTER ROLE oracle_app SET search_path = oracle, public;
   ```
   Then `ORACLE_ADMIN_URL=<postgres session-pooler URL> deploy/render/apply_migrations_supabase.sh oracle`
   and `GRANT ALL ON ALL TABLES IN SCHEMA oracle TO oracle_app;`.
   The shim functions and cron jobs are created as `postgres` in schema `oracle`; the
   `DELETE` jobs run as the job owner, so retention keeps working.
2. **Data copy (optional, one-way):** `pg_dump --data-only --exclude-table=_sqlx_migrations
   --schema=public` from the local Oracle DB, restore into `oracle`. Do this with the local
   Oracle stopped, or nonce-ordered telemetry replay will see a gap. Skip it for a fresh start.
3. **Render:** point a Blueprint at `deploy/render/oracle.render.yaml`. Set `DATABASE_URL`
   (Supabase **session** pooler, role `oracle_app`) and `ORACLE_API_KEY` in the dashboard.
4. **Repoint clients** (Shield `device.json`/env, BCC `ORACLE_URL`, userapi, SDK) to the Render
   URL. Change one client first, confirm `/healthz` and a telemetry round-trip, then the rest.
5. **Rollback:** repoint clients back to `http://127.0.0.1:8080` and keep the local container
   running (`docker compose up -d oracle-backend`) until the Render copy has been stable for a
   few days. The local DB is never modified by this procedure.

## Boot test (local, before any deploy)

```bash
docker build -f integrity-oracle/Dockerfile.render -t oracle-render-test .
docker run --rm -e PORT=9090 -e DATABASE_URL=... -e REDIS_URL=... -e RPC_URL=https://sepolia.base.org \
  -e ORACLE_API_KEY=test -p 9090:9090 oracle-render-test
curl -fsS localhost:9090/healthz
```

## Cutover log

- 2026-11-06: Oracle live at https://integrity-oracle.onrender.com (service `srv-dbmpcn8m7kps73c0jfp0`,
  Key Value `red-dbmpcms9v7es73adj630`). Data snapshot copied (agents, telemetry_events, merkle_roots,
  identity tables); `audit_log` (~1M rows, 837 MB) deliberately NOT copied (free-tier 500 MB cap);
  leaderboard/markets caches rebuild from chain. Snapshot lagged local by ~50 telemetry events.
- 2026-11-06: Console userapi (`integrity-userapi-test`) repointed: `ORACLE_URL` +
  `ORACLE_TIMEOUT_SECONDS=45` (cold start). Rollback: delete those two env vars and redeploy.
  Shield, BCC and the SDK still use the local Oracle; before moving them, stop the local Oracle and
  copy telemetry rows with `nonce > <Render last_nonce>` so nonce order does not gap.
- Verified in situ: `/v1/agent/<id>`, `/ais`, `/telemetry`, `/telemetry/volume` (exercises the
  `time_bucket` shim) all 200 on the Render Oracle.

## Outage 2026-11-07 → 2026-11-12: suspended Key Value

`integrity-oracle-kv` was suspended on 2026-11-07. The Oracle then waited minutes for Redis at
start-up, failed with `Connection refused`, and restart-looped, so every endpoint timed out.
`render ea kv resume red-dbmpcms9v7es73adj630` returned HTTP 500 on 2026-11-12. The fix made Redis
optional (`backend/src/ratelimit.rs`): the limiter falls back to an in-process fixed window, which is
the same budget on this single-instance deployment. It neither fails open (no limit on the
unauthenticated OTLP receiver) nor fails closed (500s).

