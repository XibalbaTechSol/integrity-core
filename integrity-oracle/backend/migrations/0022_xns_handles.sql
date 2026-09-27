-- XNS handles: a unique, human-chosen username per agent, deliberately independent of
-- on-chain state. An agent can hold a handle without ever registering on-chain (no
-- SovereignAgent, no gas, no wallet needed) -- this is an Oracle-local directory, not the
-- on-chain XibalbaNameService contract (which remains a separate, optional "list as an
-- on-chain alias" step for agents that want their handle independently verifiable).
--
-- Every agent inserted into `agents` (i.e. every agent that completes the full on-chain
-- POST /v1/agent/register flow) must also hold exactly one row here -- enforced at the
-- application layer in the same transaction as the `agents` insert, not by a foreign key,
-- since a handle can legitimately exist before (or entirely without) an `agents` row.
--
-- One handle per agent, one agent per handle: both sides are UNIQUE. Handles are
-- case-insensitive (a case-preserving `handle` column plus a unique index on its
-- lowercased form), matching how a chat app username is usually compared.
CREATE TABLE xns_handles (
    agent_id    TEXT PRIMARY KEY,
    handle      TEXT NOT NULL,
    claimed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX xns_handles_handle_lower_idx ON xns_handles (lower(handle));
