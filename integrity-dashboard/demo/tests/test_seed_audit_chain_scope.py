from __future__ import annotations

from integrity_demo.seed_audit import Agent, purge, seed_identity, seed_leaderboard


class RecordingCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple | None]] = []

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.calls.append((" ".join(sql.split()), params))


def _agent() -> Agent:
    return Agent(
        name="chain-scoped",
        keystore="unused",
        vertical=0,
        profile="steady",
        did="did:integrity:chain-scoped",
        pubkey=b"p" * 32,
        eth_address="0x0000000000000000000000000000000000000010",
        primitives={
            "sovereign_agent": "0x0000000000000000000000000000000000000001",
            "state_anchor": "0x0000000000000000000000000000000000000002",
            "reputation_registry": "0x0000000000000000000000000000000000000003",
            "slasher": "0x0000000000000000000000000000000000000004",
            "verifier_registry": "0x0000000000000000000000000000000000000005",
            "compliance_gate": "0x0000000000000000000000000000000000000006",
            "agent_profile": "0x0000000000000000000000000000000000000007",
        },
    )


def test_seed_identity_writes_explicit_primitive_chain_provenance() -> None:
    cursor = RecordingCursor()

    seed_identity(cursor, _agent(), chain_id=31337)

    primitive_sql, primitive_params = cursor.calls[1]
    assert "chain_id, resolved_at" in primitive_sql
    assert "chain_id = EXCLUDED.chain_id" in primitive_sql
    assert primitive_params is not None
    assert primitive_params[-1] == 31337


def test_seed_leaderboard_uses_migrated_chain_scoped_conflict_keys() -> None:
    cursor = RecordingCursor()

    seed_leaderboard(cursor, [_agent()], chain_id=84532)

    cache_sql, cache_params = cursor.calls[0]
    assert "(agent_id, chain_id, sovereign_agent_address" in cache_sql
    assert "ON CONFLICT (agent_id, chain_id)" in cache_sql
    assert cache_params is not None
    assert cache_params[1] == 84532

    sync_sql, sync_params = cursor.calls[1]
    assert "(id, chain_id, agent_count" in sync_sql
    assert "ON CONFLICT (chain_id)" in sync_sql
    assert sync_params == (84532, 1)


def test_purge_preserves_other_chains_leaderboard_rows() -> None:
    cursor = RecordingCursor()
    dids = ["did:integrity:chain-scoped"]

    purge(cursor, dids, chain_id=31337)

    purge_sql, purge_params = cursor.calls[-1]
    assert "agent_id = ANY(%s) AND chain_id = %s" in purge_sql
    assert purge_params == (dids, 31337)