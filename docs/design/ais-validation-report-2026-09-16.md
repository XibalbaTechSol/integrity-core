# AIS validation report — 2026-09-16

## Verdict

AIS is **mathematically implemented and implementation-consistent locally**,
but is **not yet validated as a real-world risk/trust predictor**. No claim of
predictive validity is made: the repository does not currently contain enough
time-separated, independently labeled production outcomes to estimate AUROC,
AUPRC, calibration, lift, subgroup behavior, or gaming resistance honestly.

## Gates completed in this pass

- Authority and version reconciliation: completed; active baseline is
  `docs/SPEC.md` v1.0.0-draft and active score profile is `ais/v1-geometric-1`.
- Canonical geometric implementation: completed in `scoring-core`; aggregation
  remains Oracle-owned.
- Finite/config hardening: completed for weights, floors, transfer functions,
  and log-domain aggregation.
- Client-claim boundary: top-level derived claims remain audit-only; Oracle
  entropy/grounding now derive from signed text rather than span-provided
  precomputed values.
- History tier consistency: fixed to use the same effective expiry-aware tier as
  current AIS.
- API/dashboard metadata: profile, base/post-boost/final values, ceiling,
  evidence tier, sufficiency, proxies, and missing axes are exposed and typed.
- Middleware: continues to consume Oracle AIS and divide out only the reported
  boost; it does not reconstruct the formula. Added response ceiling validation
  and fail-closed rejection when a migrated registry's on-chain assurance tier
  disagrees with the Oracle tier or is unavailable in a modern response.
- OpenAPI regeneration is now complete and idempotent: a second generation run
  produced the same SHA-256 (`bf652b129f95077b300e7051a94960933f40a7bdf85863b5af2559bd07dc01d4`).
- Rust tests: `scoring-core` passed 22 unit tests and doc tests after changes;
  backend passed 153 library tests, including active-envelope freshness tests.
- Full Foundry suite now passes: 526 tests passed, 0 failed, 1 skipped. The
  previously failing registry test was a Foundry harness-ordering defect
  (`expectRevert` was installed before an external helper call), not a protocol
  behavior failure.
- Dashboard TypeScript/Vite build passed; wiki synchronization passed.
- Rendered browser validation was attempted through the available in-app
  Browser integration, but no browser was available. No DOM, console, or
  screenshot claim is made from the build alone.

## Red-team findings that remain blockers

1. The ingestion path now binds the ZK public identity commitment (read from
   the agent's on-chain ReputationRegistry), nonce, chain, resolved registry,
   and computed Merkle leaf before verification, with unit coverage. The
   parser remains circuit-profile-specific, so adding a new circuit still
   requires an explicit ABI binding profile.
2. Semantic duplicate batches are now rejected by an agent/content hash, and
   new SDK submissions carry signed `observed_at` used by reporting windows.
   Legacy envelopes without event time remain receipt-time evidence and should
   be excluded from claims requiring historical freshness.
3. Token usage remains an audit-only sacrifice proxy; the Oracle now supplies
   zero sacrifice to authoritative AIS until independently attested compute is
   available. This closes proxy promotion but does not create an attested
   compute source. Compliance also fails closed when no independent gate or
   attestation evidence exists; client-controlled flags remain audit-only.
4. New factory-created ReputationRegistry clones now enforce identity-tier
   ceilings through a separate governance-held `ASSURANCE_TIER_ROLE`; the
   Oracle exposes the on-chain tier/ceiling cross-check, and middleware rejects
   configured mismatches. Existing deployed clones were not mutated and require
   an explicit migration before they gain that contract-side enforcement.
   Focused contract coverage is 20 ReputationRegistry tests and 10 factory tests;
   middleware coverage now includes the unavailable-cap fail-closed case.
5. No completeness signal distinguishes selective reporting from low activity.

## Deployment-state check — Base Sepolia, 2026-09-17

Read-only RPC calls against chain ID 84532 confirmed the deployment record's
`XibalbaAgentRegistry` reports 15 registered agents and the deployed
`AgentPrimitivesFactory.reputationRegistryImpl()` still resolves to
`0xd362eC37F74bfef79184dB3bBC16E2EC0272a2Ef`. The deployed factory also
reports governance `0x7530bd7Cb142C50d5cC742EdF02263f368e89E2f`. Direct calls to
`assuranceTierConfigured()`, `assuranceTier()`, and `assuranceTierCeiling()` on
that template each reverted, so the live factory is not proven to use the new
assurance-tier implementation; it must be treated as legacy pending a selector
and clone-level migration audit. No migration transaction was sent.

The existing registry stores each agent's primitive addresses in a one-time
registration record and exposes no primitive-replacement method. Reputation
registries are EIP-1167 clones, so replacing the shared implementation does not
change already-created clone code. A future migration must preserve base score,
identity commitment, monotonic ZK nonce, used-attestation replay state, boost
expiry/coverage, and every integration's resolved registry address, and must
disable Oracle writes to the superseded clone. Those mappings cannot be safely
copied by enumerating storage from the existing clone. Therefore this is not a
safe one-call implementation migration: it requires an explicit protocol
migration design (or agent opt-in to a versioned registry with replay-safe
state transition), followed by separately authorized deployment and readback.

## Empirical validation plan (not a production claim)

The runnable harness is `scripts/validate_ais_predictive.py`. It accepts only
operator-supplied labeled CSV data, rejects missing/invalid timestamps and
outcome leakage, performs chronological 60/20/20 splits, bootstrap intervals,
AUROC/AUPRC, fixed-FPR recall, threshold precision/recall, subgroup metrics,
baseline comparisons, geometric/arithmetic/leave-one-axis-out ablations, and
volume/volatility gaming diagnostics. Calibration is intentionally reported as
not estimable unless a separately declared calibrated `risk_probability` is
provided; AIS itself is not treated as a probability. The harness was syntax
checked and its CLI help was exercised, but no production dataset was supplied
and no predictive metrics were generated.

The required dataset must contain signed event provenance, effective profile,
component/evidence metadata, and outcomes recorded strictly after each score
window. Candidate labels include policy violation, quarantine/denial, BCC
mismatch, harmful evaluator decision, dispute/remediation, and capital loss.
Use time-based train/validation/test splits, bootstrap intervals, minimum-volume
strata, calibration/reliability plots, AUROC/AUPRC, recall at fixed FPR,
precision at operational thresholds, lift, score volatility, recovery time,
drift, subgroup analysis, leakage checks, and component/geometric-vs-arithmetic
ablations against event-count, violation-ratio, recent-incident, random, and
reviewer-prior baselines. Synthetic data may exercise code paths only and must
be excluded from real-world conclusions.

Until those labels and windows exist, the correct conclusion is: **implemented
protocol metric; predictive usefulness unvalidated; operational usefulness
partially evidenced by local fail-closed and synchronization tests.**
