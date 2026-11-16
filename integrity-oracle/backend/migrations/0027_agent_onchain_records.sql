-- Registration v3 (spec Parts 2-3, phase 4 plan PR 4.3): the Oracle's read cache of an
-- agent's `AgentRegistry` record.
--
-- Written ONLY by `POST /v1/agent/{id}/onchain/sync`, which reads `AgentRegistry.resolve` and
-- copies the chain's answer. The chain is the source of truth; a row is never written from a
-- request body, and a fingerprint with no on-chain record writes nothing.
--
-- Keyed by (agent_id, chain_id), the same rule as `agent_primitives` (E11): a row is only
-- served when it was read from the chain this Oracle is configured for, so repointing the
-- Oracle at another network cannot leak the old network's actor.
--
-- No foreign key to `agents`: a record created directly on-chain (without this Oracle's
-- off-chain route) can still be synced and shown.
--
-- Additive only. `agent_primitives` and `POST /v1/agent/register` are untouched (PR 4.6).
CREATE TABLE agent_onchain_records (
    agent_id TEXT NOT NULL,
    chain_id BIGINT NOT NULL,
    registry_address TEXT NOT NULL,
    pubkey BYTEA NOT NULL CHECK (octet_length(pubkey) = 32),
    guardian TEXT NOT NULL,
    -- NULL = no actor bound (an existence-only record). Never the zero address.
    actor TEXT,
    domain_id TEXT NOT NULL,
    uri TEXT NOT NULL DEFAULT '',
    -- Unix seconds, as `AgentRecord.registeredAt` / `retiredAt` store them. NULL = active.
    registered_at BIGINT NOT NULL,
    retired_at BIGINT,
    proof_kind SMALLINT NOT NULL,
    -- The block the record was read at. A sync never moves a row to an older block.
    synced_block BIGINT NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_id, chain_id)
);

-- Settlement and the Shield/XNS side look agents up by their bound actor.
CREATE INDEX agent_onchain_records_actor_idx ON agent_onchain_records (chain_id, actor)
    WHERE actor IS NOT NULL;
