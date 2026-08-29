-- ERC-8004 is a portable public discovery record, never a replacement for the
-- Integrity DID. This table stores only a verified projection of that public record.
CREATE TABLE erc8004_identity_bindings (
    agent_id TEXT PRIMARY KEY REFERENCES agents(id) ON DELETE CASCADE,
    chain_id BIGINT NOT NULL CHECK (chain_id > 0),
    identity_registry_address TEXT NOT NULL,
    agent_token_id TEXT NOT NULL,
    registration_uri TEXT NOT NULL,
    registration_sha256 TEXT NOT NULL CHECK (registration_sha256 ~ '^[0-9a-f]{64}$'),
    nft_owner_address TEXT NOT NULL,
    agent_wallet_address TEXT,
    binding_status TEXT NOT NULL CHECK (binding_status IN ('verified', 'stale', 'transfer_conflict')),
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chain_id, identity_registry_address, agent_token_id)
);

CREATE INDEX erc8004_identity_bindings_status_idx
    ON erc8004_identity_bindings (binding_status, last_checked_at DESC);
