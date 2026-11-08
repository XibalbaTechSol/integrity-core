-- Shield's independent witness stream for anchoring coverage (reconciliation Phase 1).
--
-- docs/design/shield-observation-reconciliation.md (#201) + the Phase 1 scope
-- (docs/design/shield-observation-phase1-implementation.md): an agent host that can skip the
-- SDK-side intent commitment (INTERFACE_CONTRACT.md §6.10) can also suppress its own outcome
-- report, so a self-reported denominator cannot detect a full bypass. Shield -- an OS-level
-- sensor the unprivileged agent does not control -- witnesses executions regardless. These rows
-- are that witness stream: per-agent/window COUNTS (not per-tree; the per-tree join is Phase 2),
-- signed with Shield's DEVICE key and per-device sequenced so a gap is detectable.
--
-- Phase 1 is the "aggregate floor": `executions_witnessed` and `executions_suppressed` are
-- computed ON THE DEVICE, where both the eBPF witness stream and `gate_receipts` coexist (so the
-- comparison is tree<->gate-receipt, compatible units -- never the vacuous Oracle-side
-- trees-minus-invocations). The Oracle verifies the signature + sequence, stores the counts, and
-- exposes them through `agent_anchoring_coverage`; a sequence gap flips `witness_complete=false`
-- so coverage reads `None`, never a falsely-high ratio.
--
-- Low volume (one row per agent/window/device), so a plain table -- deliberately NOT a
-- create_hypertable (keeps this migration free of the Supabase timescale shim). Retention is a
-- periodic delete (see the Oracle's retention worker), not a hypertable policy.
--
-- Privacy: a `tree_fingerprint` digest (root exe hash + cmdline digest + tree-shape digest),
-- never a raw command line or file content -- the same posture gate_receipts holds.

CREATE TABLE IF NOT EXISTS shield_observations (
    device_id               TEXT        NOT NULL,
    -- Monotonic per-device counter; with prev_hash it forms the gap-detectable chain.
    sequence                BIGINT      NOT NULL,
    -- The observed agent (AgentRegistry/DeviceContext attribution on the device).
    agent_id                TEXT        NOT NULL,
    window_start            TIMESTAMPTZ NOT NULL,
    window_end              TIMESTAMPTZ NOT NULL,
    -- Gate-ATTRIBUTED trees only (instrumentation/hooks/statusline/gate-client excluded on-device).
    executions_witnessed    BIGINT      NOT NULL,
    -- Attributed trees with NO gate receipt -- the full-bypass count, a subset of witnessed.
    executions_suppressed   BIGINT      NOT NULL,
    -- Device-local process->agent attribution is a heuristic; low confidence is surfaced, never
    -- auto-counted as a bypass (enforced in the coverage read, carried here for the operator).
    attribution_confidence  REAL        NOT NULL,
    tree_fingerprint        TEXT        NOT NULL,
    -- Optional reference to the gate-receipt chain position when the tree's root call was gated.
    gate_receipt_ref        TEXT,
    -- The per-device hash chain: this record's content hash and the previous one (NULL on first).
    record_hash             TEXT        NOT NULL,
    prev_hash               TEXT,
    -- Signature over record_hash with Shield's device key (verified on ingest).
    device_signature        TEXT        NOT NULL,
    received_at             TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- (device_id, sequence) is the natural key: enforces monotonicity, makes replay idempotent,
    -- and makes a gap detectable as a missing sequence number.
    PRIMARY KEY (device_id, sequence),
    CONSTRAINT shield_observations_counts_nonneg
        CHECK (executions_witnessed >= 0 AND executions_suppressed >= 0),
    -- Suppressed is a subset of witnessed -- a device reporting suppressed > witnessed is malformed.
    CONSTRAINT shield_observations_suppressed_subset
        CHECK (executions_suppressed <= executions_witnessed),
    CONSTRAINT shield_observations_confidence_unit
        CHECK (attribution_confidence >= 0.0 AND attribution_confidence <= 1.0),
    CONSTRAINT shield_observations_window_order
        CHECK (window_end >= window_start)
);

-- The coverage read selects the most recent windows for one agent; index that access path.
CREATE INDEX IF NOT EXISTS idx_shield_observations_agent_window
    ON shield_observations (agent_id, window_end DESC);
