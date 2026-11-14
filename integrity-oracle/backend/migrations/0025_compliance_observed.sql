-- Whether a telemetry event's compliance verdict came from independent evidence.
--
-- `oracle_compliance` only has evidence when it can read a live compliance gate:
-- today, an on-chain healthcare agent's ComplianceGate + SmartBAA. Every other event
-- (off-chain agents, non-healthcare verticals) used to be stored as `flagged = true`,
-- a fabricated violation that zeroed the compliance axis and, through the geometric
-- mean, the whole AIS. From this migration on, such events are stored with
-- `compliance_observed = false`, are excluded from `penalty_ratio`, and an agent with
-- no observed events in the window is scored with the compliance weight set to 0 and
-- the other three renormalized (the rule integrity_sdk.core.ais_local already uses
-- for axes a receipt log cannot observe).
--
-- Existing rows default to TRUE: they keep the verdict they were scored with rather
-- than being rewritten. They age out of the AIS reporting window.
ALTER TABLE telemetry_events
    ADD COLUMN compliance_observed BOOLEAN NOT NULL DEFAULT TRUE;
