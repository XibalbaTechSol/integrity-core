-- Verification Ladder, rungs 2 and 3: evidence for a tier ABOVE the one registration alone
-- can establish.
--
-- Until now `agents.verification_tier` was written once at registration from a hardcoded
-- `SERVER_VERIFIED_TIER = 1` (handlers.rs) because tiers 2/3 had no verification path
-- implemented anywhere. That constant was not a placeholder for missing data — it was the
-- ONLY value the system could produce, which made the tier ceiling bind at the only
-- achievable rung. Measured consequence: an agent with raw AIS 704 reported 600, and the ZK
-- boost (x1.15 -> 810) was entirely absorbed by the clamp, so the protocol's flagship
-- cryptographic feature bought exactly zero score. See PRODUCTION_GAPS.md §23.
--
-- This table holds the evidence. `agents.verification_tier` stays the REGISTRATION floor;
-- an agent's effective tier is that floor unioned with its active verifications here, so
-- revoking or expiring a verification lowers the tier without rewriting registration state.
CREATE TABLE identity_verifications (
    id            BIGSERIAL PRIMARY KEY,
    agent_id      TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,

    -- 'dns_txt'  -> proves CONTROL OF A NAMESPACE. Machine-verifiable by anyone, no third
    --               party, no PII, re-checkable at any time. Rung 2 ("Linked").
    -- 'kyc'      -> proves A LEGAL PERSON IS ACCOUNTABLE. Needs a provider, carries
    --               regulated PII, and is what a covered entity actually wants before
    --               signing a BAA. Rung 3 ("Institutional").
    -- These are different KINDS of claim, not competing implementations of one claim,
    -- which is why they sit at different rungs rather than being alternatives.
    method        TEXT NOT NULL CHECK (method IN ('dns_txt', 'kyc')),
    tier_granted  INTEGER NOT NULL CHECK (tier_granted BETWEEN 0 AND 3),

    -- The verified subject: a domain for dns_txt, an opaque provider reference for kyc.
    subject       TEXT NOT NULL,

    -- HOW it was verified, for audit. NEVER raw PII.
    --
    -- This is load-bearing for the kyc method and stated here rather than left to
    -- convention: a KYC provider returns name/DOB/document images, and none of that may
    -- land in this database. Store the provider name, an opaque reference id, and a hash
    -- of the verification receipt — enough to re-query the provider and to prove the
    -- record was not altered, and nothing that turns the oracle's DB into a regulated
    -- PII store. The oracle is already a HIPAA-adjacent system (see the PHI backstop in
    -- 0010); it must not acquire a second class of sensitive data by accident.
    evidence      JSONB NOT NULL DEFAULT '{}'::jsonb,

    verified_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Namespace control is a claim about the PRESENT, not a permanent fact: domains lapse
    -- and change hands. A dns_txt verification therefore expires and must be re-proved.
    -- NULL means "does not expire" (kyc, which is re-verified by provider lifecycle, not
    -- by us re-resolving something).
    expires_at    TIMESTAMPTZ,

    -- Set instead of deleting, so a revoked verification stays auditable.
    revoked_at    TIMESTAMPTZ,
    revoked_reason TEXT
);

-- One active verification per (agent, method, subject). A re-proof updates the existing
-- row's expiry rather than accumulating duplicates that would each need revoking.
CREATE UNIQUE INDEX idx_identity_verifications_active
    ON identity_verifications (agent_id, method, subject)
    WHERE revoked_at IS NULL;

-- The effective-tier lookup runs on every AIS computation, so index the hot path.
CREATE INDEX idx_identity_verifications_agent_active
    ON identity_verifications (agent_id)
    WHERE revoked_at IS NULL;

-- Outstanding DNS challenges. A challenge is issued, the operator publishes it as a TXT
-- record, then verification resolves the record and checks the signature over THIS nonce.
--
-- The nonce is what makes the proof fresh rather than replayable: without it, a TXT record
-- published once (or captured from a domain the agent no longer controls) would verify
-- forever. Short-lived by construction.
CREATE TABLE dns_verification_challenges (
    agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    domain      TEXT NOT NULL,
    nonce       TEXT NOT NULL,
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,

    PRIMARY KEY (agent_id, domain)
);

CREATE INDEX idx_dns_challenges_expiry ON dns_verification_challenges (expires_at)
    WHERE consumed_at IS NULL;
