# AIS implementation handoff — 2026-09-17

## Executive status

The `ais/v1-geometric-1` profile is implemented in scoring-core, independently
aggregated by the Oracle, described by the generated v1 API, consumed by
middleware, and presented by the dashboard as an explanatory signal. Local
mathematical and integration checks pass. AIS is **not validated as a
real-world predictor of risk or trust**: no suitable, time-separated labeled
production outcome dataset was available. Treat it as an implemented protocol
metric, not a calibrated probability or universal safety judgment.

## Canonical profile and evidence boundary

For component values `E,G,S,C ∈ [0,1]` and weights
`(wE,wG,wS,wC)=(0.30,0.30,0.20,0.20)`, scoring-core computes the weighted
geometric product in the log domain. A zero positive-weight component
annihilates the base score. The post-boost value is
`AIS_base × (1 + 0.15 × verified_event_ratio)`; final AIS is capped by the
Oracle-derived verification tier (0/1/2/3+: 300/600/850/1000). The configured
30-day reporting period is the default; signed event time is required for
schema v2+ and legacy receipt time is not equivalent evidence of event time.
See [the mathematical profile](ais-mathematical-spec-v1.md),
[reconciliation](ais-reconciliation-2026-09-16.md), and
[interface contract §4.3](../INTERFACE_CONTRACT.md#43-agent-integrity-score-ais).

The sender signature authenticates the sender, not the truth of all supplied
metrics. Oracle-recomputed entropy/grounding are distinguished from client
claims. Unsigned OTLP and client-derived fields are non-authoritative. Token
usage is an audit-only proxy, not independently verified compute; sacrifice
therefore contributes zero absent admissible evidence. Compliance likewise
fails closed without independent evidence. Sparse/no evidence must not be read
as good behavior. The API's evidence tiers and sufficiency flags are categorical
metadata, not calibrated confidence.

## Implementation and verification record

- Rust scoring-core: 22 tests passed; backend: 153 tests passed.
- BCC middleware full suite: 152 passed, 1 failed. The failure is
  `test_full_intercept_flow_denies_via_real_opa`: its real Oracle lookup used
  the default `localhost:8080`, returned 404 for the generated test DID, and
  correctly took the fail-closed quarantine path before reaching the asserted
  OPA rejection. The focused `tests/test_scoring_loop.py` suite passed 19/19.
- SDK: 23 tests passed (prior validation run).
- Foundry: 526 passed, 0 failed, 1 skipped.
- Dashboard TypeScript/Vite build passed. A browser runtime was unavailable;
  no DOM, interaction, console, responsive, or screenshot acceptance is claimed.
- OpenAPI generation was repeated and was byte-identical (SHA-256
  `bf652b129f95077b300e7051a94960933f40a7bdf85863b5af2559bd07dc01d4`).
- Predictive validation harness syntax/CLI checks passed, but no labeled
  production dataset was supplied and no predictive metrics were produced.
  Synthetic fixtures, if used for tests, are not evidence of real-world utility.

Detailed methodology and gate-by-gate status are in
[the validation report](ais-validation-report-2026-09-16.md) and
[cross-repository matrix](ais-cross-repo-consistency-2026-09-16.md).

## Chain deployment boundary

Base Sepolia read-only RPC checks on 2026-09-17 confirmed chain ID 84532,
15 registered agents, and the factory implementation/governance addresses in
the checked-in deployment record. Calls for assurance-tier selectors on the
recorded implementation reverted. Therefore live tier-cap enforcement is
**unverified and must be treated as legacy**, despite local tests proving the
new factory/template behavior. No transaction was sent.

Existing ReputationRegistry instances are EIP-1167 clones and the existing
registry has no primitive-replacement path. A safe migration cannot be inferred
from changing the factory template: it must preserve base score, identity
commitment, monotonic ZK nonce, replay-protection state, boost coverage/expiry,
and every consumer's resolved registry address. No migration was performed or
authorized by this work. Middleware intentionally fails closed for modern
responses where Oracle and on-chain assurance metadata are missing or disagree.

## Risk/trust conclusion

| Dimension | Status |
|---|---|
| Mathematical correctness | Locally implemented and unit-tested for the active profile |
| Implementation consistency | Local Rust/API/middleware/dashboard alignment tested; browser evidence unavailable |
| Evidence integrity | Improved fail-closed handling; independent compute and some compliance evidence remain unavailable; selective reporting is unresolved |
| Predictive usefulness | Not validated: no real labeled, time-separated evaluation |
| Operational usefulness | Partially supported by local sync/contract tests; live tier-cap deployment unverified |
| Production readiness | Not established; no production traffic or end-to-end live deployment claim |

## Next gates

1. Obtain privacy-reviewed, provenance-preserving outcomes recorded strictly
   after score windows; pre-register cohort, exclusions, labels, and thresholds.
2. Run chronological train/validation/test evaluation with baselines,
   calibration/reliability, uncertainty intervals, subgroup analysis,
   leakage controls, ablations, and gaming diagnostics. Keep AIS distinct from
   any calibrated probability.
3. Resolve the Base Sepolia legacy-clone migration through an explicit
   replay-safe protocol design, governance approval, separately authorized
   transaction, and readback. Do not mutate deployed state as part of this
   handoff.
4. Run browser acceptance with DOM, console, responsive, interaction, and
   screenshot evidence when a supported browser is available.
5. Verify independent compute and compliance evidence sources before promoting
   either proxy/zero axis into authoritative positive evidence.

## Publication hygiene

The working tree contained an untracked prover configuration with a populated
`secret_key`; it is intentionally excluded from staging and publication and
left untouched in place. Review any other local-only artifacts before sharing
them. The predictive harness does not embed labels or claim a positive result.
