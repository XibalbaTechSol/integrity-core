"""app/db.py's run_migrations against a real Postgres: applies once, is
idempotent on a second call, and actually creates the real tables from
migrations/0001_init.sql -- not a faked/hand-written schema."""

from __future__ import annotations

import asyncpg

from app import db


async def test_run_migrations_creates_real_tables(db_pool: asyncpg.Pool) -> None:
    await db.run_migrations(db_pool)
    # Assert on actual applied state rather than this one call's return value
    # -- the return value is only the *delta* applied by this specific call,
    # so it depends on whether an earlier test in this session already
    # applied some/all migrations (schema persists across tests, see
    # conftest.py's `client` fixture) and isn't a stable thing to assert on.
    applied_filenames = {
        row["filename"] for row in await db_pool.fetch("SELECT filename FROM schema_migrations")
    }
    assert applied_filenames == {"0001_init.sql", "0002_jwt_revocation.sql", "0003_user_wallets.sql"}

    tables = {
        row["table_name"]
        for row in await db_pool.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
    }
    assert {
        "users",
        "api_keys",
        "user_agents",
        "demo_runs",
        "revoked_tokens",
        "schema_migrations",
    } <= tables


async def test_run_migrations_is_idempotent(db_pool: asyncpg.Pool) -> None:
    await db.run_migrations(db_pool)
    second_pass = await db.run_migrations(db_pool)
    assert second_pass == []
