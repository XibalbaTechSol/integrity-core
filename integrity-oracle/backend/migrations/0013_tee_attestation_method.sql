-- Verification Ladder rung 3: remote TEE attestation.
--
-- `docs/wiki/concepts/identity-ceiling.md` specifies rung 3 as "Remote TEE
-- attestation + institutional audit", and explicitly rejects the old
-- did:xibalba:<hardware_hash> idea (CPU model + MAC + machine-id) as never-built
-- ideation -- a host can fabricate all of those freely. Real remote attestation
-- against AWS's hardware root of trust is the credible mechanism.
--
-- Rungs 2 and 3 differ in KIND, not degree. Rung 2 proves control of an
-- identifier (a domain, a GitHub account) -- transferable, phishable. Rung 3
-- proves the agent's key lives inside genuine enclave hardware running a
-- measured code image (PCRs), which cannot be forged without breaking the
-- hardware root.
ALTER TABLE identity_verifications DROP CONSTRAINT identity_verifications_method_check;

ALTER TABLE identity_verifications
    ADD CONSTRAINT identity_verifications_method_check
    CHECK (method IN ('dns_txt', 'github', 'tee_nitro', 'kyc'));
