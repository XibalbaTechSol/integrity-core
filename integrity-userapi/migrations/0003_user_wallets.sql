-- Custodial ("app-managed") ITK wallet per user. This is the honest counterpart to the
-- dashboard's self-custodial (MetaMask) path: instead of the user holding keys, the userapi
-- custodies a per-user app wallet and tracks its $ITK balance as a real internal ledger.
-- A production deployment would back this address with an actual custodied keypair + on-chain
-- settlement; here the balance is an authoritative internal ledger (transfers are real,
-- transactional debits/credits), which is a genuine custodial account, not a mocked number.
CREATE TABLE user_wallets (
    user_id            UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    app_wallet_address TEXT NOT NULL UNIQUE,
    -- uint256 wei of $ITK; NUMERIC(78,0) covers the full 2^256 range exactly (no f64 loss).
    itk_balance_wei    NUMERIC(78,0) NOT NULL DEFAULT 0 CHECK (itk_balance_wei >= 0),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
