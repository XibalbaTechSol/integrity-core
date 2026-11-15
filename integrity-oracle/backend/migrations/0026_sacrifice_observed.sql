-- Whether a telemetry event's sacrifice (contributed compute) is attested.
--
-- Authoritative sacrifice must be attested by a staked validator or a TEE
-- (docs/WHITEPAPER.md §S_sacrifice, docs/SPEC.md §AIS). No ingest path writes attested
-- compute yet: since derive.rs demoted token counts to an audit-only proxy, every event
-- has been stored with an authoritative sacrifice of 0. Under the weighted geometric
-- mean that observed-looking zero annihilated the AIS of every agent, so honest signed
-- telemetry with strong entropy and grounding scored exactly 0.0.
--
-- From this migration on an event records `sacrifice_observed`. It stays FALSE until an
-- attestation path sets it. A window with no observed event scores with the sacrifice
-- weight set to 0 and the other weights renormalized, the same rule migration 0025
-- applies to compliance. An observed zero still annihilates.
--
-- Existing rows default to FALSE: none was attested (no attestation path has ever
-- existed), and their gpu_hours_verified values predate the proxy demotion, so they are
-- self-reported token counts rather than evidence. The aggregates sum
-- gpu_hours_verified only over observed rows, so those legacy values stop counting.
ALTER TABLE telemetry_events
    ADD COLUMN sacrifice_observed BOOLEAN NOT NULL DEFAULT FALSE;
