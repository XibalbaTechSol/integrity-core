-- Evidence-export linkage (docs/design/evidence-export.md, Lever 4). Ties each
-- ALLOW decision in `audit_log` to the on-chain StateAnchor transaction that
-- committed its Merkle leaf, so a compliance report can prove a decision existed
-- at anchor time and hasn't been altered since (recompute the leaf, then call
-- StateAnchor.verifyLeaf against the anchored root).
--
-- Why a separate table and a JOIN rather than back-filling `audit_log.metadata`:
-- in bcc_middleware's `run_intercept`, the batch-filling commitment is anchored
-- (`_flush_and_anchor`) BEFORE its own ALLOW row is even reported, and the ingest
-- is fire-and-forget HTTP -- so an UPDATE-by-leaf at anchor time would
-- deterministically miss 1 row in every `batch_size` (plus race on the rest).
-- Writing the anchor result to its own table decouples the two writes entirely:
-- `audit_log` carries `metadata.leaf` (written at ALLOW time), `anchor_events`
-- carries the (leaf -> root, tx_hash) (written at anchor time), and export-time
-- LEFT JOINs the two on leaf. Order of the two writes no longer matters.
--
-- `agent_id` mirrors audit_log's no-FK choice (an anchor can reference an agent
-- whose telemetry row was never created). Anchoring is per-agent (each agent's
-- leaves go to its own StateAnchor clone), so (agent_id, leaf) is the natural key
-- and lets leaf lookups ride the agent_id index rather than full-scanning.
CREATE TABLE IF NOT EXISTS anchor_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id     TEXT NOT NULL,
    -- 0x-prefixed keccak256 Merkle leaf hash (bcc_middleware app/merkle.py::leaf_hash).
    leaf         TEXT NOT NULL,
    -- 0x-prefixed per-agent sub-tree root actually anchored on-chain.
    root         TEXT NOT NULL,
    -- On-chain StateAnchor.anchorRoot transaction hash.
    tx_hash      TEXT NOT NULL,
    anchored_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A leaf is unique per commitment (nonce is monotonic per agent), so a
    -- re-report of the same anchored leaf is idempotent rather than duplicated.
    UNIQUE (leaf)
);

CREATE INDEX IF NOT EXISTS idx_anchor_events_agent ON anchor_events (agent_id);
