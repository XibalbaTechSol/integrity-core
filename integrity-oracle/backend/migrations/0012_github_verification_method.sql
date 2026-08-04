-- Record GitHub identity proofs under their own method name.
--
-- The first implementation reused `'dns_txt'` because the proof shape is identical
-- (oracle-issued nonce, agent signs, oracle independently reads the artefact). But
-- the METHOD is not identical, and an audit row reading
-- `method='dns_txt', subject='github:xibalbatechsol'` is self-contradictory — it
-- says DNS was consulted when GitHub's API was. In a system whose whole product is
-- verifiable claims, a verification record that misdescribes how it was obtained is
-- exactly the wrong thing to ship.
ALTER TABLE identity_verifications DROP CONSTRAINT identity_verifications_method_check;

ALTER TABLE identity_verifications
    ADD CONSTRAINT identity_verifications_method_check
    CHECK (method IN ('dns_txt', 'github', 'kyc'));

-- Backfill: any row whose subject is namespaced `github:` was a GitHub proof
-- recorded under the old label.
UPDATE identity_verifications
SET method = 'github'
WHERE method = 'dns_txt' AND subject LIKE 'github:%';
