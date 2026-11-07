#!/usr/bin/env bash
# Apply the Oracle's sqlx migrations to a Supabase schema WITHOUT TimescaleDB.
#
# Usage: ORACLE_ADMIN_URL=postgresql://postgres...  deploy/render/apply_migrations_supabase.sh [schema]
#
# Writes _sqlx_migrations rows with the checksums sqlx itself computes (sha384 of the file),
# so the Oracle's startup `sqlx::migrate!().run()` sees all 23 as applied and does nothing.
set -euo pipefail
SCHEMA=${1:-oracle}
HERE=$(cd "$(dirname "$0")" && pwd)
MIG=$HERE/../../integrity-oracle/backend/migrations
: "${ORACLE_ADMIN_URL:?set ORACLE_ADMIN_URL to the Supabase postgres (admin) connection string}"
P() { psql "$ORACLE_ADMIN_URL" -v ON_ERROR_STOP=1 -q "$@"; }

P -c "CREATE SCHEMA IF NOT EXISTS $SCHEMA"
export PGOPTIONS="-c search_path=$SCHEMA,public,extensions"
P -f "$HERE/supabase_timescale_shim.sql"
P -c "CREATE TABLE IF NOT EXISTS _sqlx_migrations (
  version BIGINT PRIMARY KEY, description TEXT NOT NULL, installed_on TIMESTAMPTZ NOT NULL DEFAULT now(),
  success BOOLEAN NOT NULL, checksum BYTEA NOT NULL, execution_time BIGINT NOT NULL)"

for f in "$MIG"/*.sql; do
  b=$(basename "$f" .sql); v=$((10#${b%%_*})); d=${b#*_}; d=${d//_/ }
  # The only line we drop is the extension create; everything else runs verbatim.
  grep -v '^CREATE EXTENSION IF NOT EXISTS timescaledb;' "$f" | P -1 -f -
  sum=$(openssl dgst -sha384 -binary "$f" | xxd -p -c 200)
  P -c "INSERT INTO _sqlx_migrations(version,description,success,checksum,execution_time)
        VALUES ($v,'${d//\'/}',true,decode('$sum','hex'),0) ON CONFLICT DO NOTHING"
  echo "applied $b"
done
