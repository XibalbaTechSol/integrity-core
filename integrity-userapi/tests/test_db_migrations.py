"""app/db.py's run_migrations against a real Postgres: applies once, is
idempotent on a second call, and actually creates the real tables from
migrations/0001_init.sql -- not a faked/hand-written schema."""

from __future__ import annotations

from pathlib import Path

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
    # Compare against what is actually on disk rather than a hardcoded set. The previous
    # literal set went stale the moment 0003_user_wallets.sql was added (commit e68343c)
    # and failed on every run afterwards; the property worth asserting is "every migration
    # file was applied", which stays true as migrations are added.
    expected_filenames = {
        path.name for path in (Path(db.__file__).parent.parent / "migrations").glob("*.sql")
    }
    assert expected_filenames, "no migration files found — the glob path is wrong"
    assert applied_filenames == expected_filenames

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
