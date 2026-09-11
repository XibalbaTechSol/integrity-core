---
title: Agent Integrity Score (AIS)
acronyms: [AIS]
created: 2026-07-07
updated: 2026-09-08
type: concept
tags: [metrics]
confidence: high
source_files:
  - integrity-oracle/scoring-core/src/lib.rs
  - integrity-oracle/backend/src/derive.rs
  - integrity-sdk/integrity_sdk/telemetry/derive.py
  - docs/INTERFACE_CONTRACT.md
---

The composite trust score for an agent, computed by [Integrity Oracle](../entities/integrity-oracle.md):

`AIS = (S_entropy^wE * S_grounding^wG * S_sacrifice^wS * S_compliance^wC) * ZK_boost`

Default weights (sum to 1.0): `wE=0.30, wG=0.30, wS=0.20, wC=0.20`.
`ZK_boost = 1.0 + 0.15 * verified_event_ratio`, where the ratio counts events
carrying a real Barretenberg proof (see [ZKP](zkp.md)) verified by the oracle.

This formula is computed in exactly one place (`integrity-oracle/scoring-core`)
— other packages read the final, tier-capped result via the oracle's
`GET /v1/agent/{id}/ais` endpoint rather than recomputing it. The on-chain sync
removes only the response's reported ZK multiplier before calling
`ReputationRegistry.updateScoreWithCoverage`; it does not reconstruct the mean from
`components`/`weights`. See
[Interface Contract §4.3](../../INTERFACE_CONTRACT.md#43-agent-integrity-score-ais)
for the canonical definition. The four component *inputs* the SDK derives
client-side before the oracle applies this formula are documented
separately — see [Local Metrology](local-metrology.md), which also
supersedes an old, inconsistent 3-component draft formula (no compliance
term, weights not summing to 1.0) that never matched this one.

## Table of contents

- [Where the four inputs actually come from (trust model)](#where-the-four-inputs-actually-come-from-trust-model)
- [Constraint score and component floors](#constraint-score-and-component-floors)

## Where the four inputs actually come from (trust model)

A client's `POST /v1/telemetry/ingest` signature proves *who* sent a request, never
*whether its numbers were honest*. The oracle does not trust the client's
`derived_signals` claim for entropy/grounding/sacrifice — it independently recomputes
all three server-side, from the raw `otel_spans` content already inside the same signed
request (`backend/src/derive.rs`, mirroring `integrity_sdk/telemetry/derive.py`'s
algorithms so results agree), and does the on-chain `ComplianceGate` "wins" check itself
rather than trusting an SDK-side opt-in call. `derived_signals` stays in the signed
envelope (so the wire format hasn't changed) and is still stored, but only as an audit
trail alongside the oracle's own recomputation — it does not feed the formula.

```mermaid
flowchart LR
    Agent["Agent (SDK/CLI)"] -->|"signed POST /v1/telemetry/ingest<br/>(otel_spans + derived_signals)"| Oracle["integrity-oracle"]
    Oracle -->|"re-derive from otel_spans<br/>(same posture as the PHI backstop)"| Recompute["entropy / grounding / sacrifice /<br/>compliance (oracle-recomputed;<br/>some source evidence remains<br/>self-asserted or proxy-derived)"]
    Recompute --> Formula["AIS = Π(S^w) · ZK_boost<br/>(scoring-core, geometric volume model)"]
    ZK["Real Barretenberg ZK proof<br/>(bb verify)"] -.->|"up to 1.15× by<br/>verified-event ratio"| Formula
    Formula --> API["GET /v1/agent/{id}/ais<br/>+ live SSE push (/v1/stream)"]
```

Verified end-to-end, not just unit-tested: a client claiming an inflated grounding score
while its own signed `otel_spans` contain hallucination markers gets the oracle's real,
low recomputation stored and scored — see
`oracle_e2e_recomputed_grounding_overrides_inflated_client_claim` in
`integrity-oracle/backend/tests/e2e.rs`.

**Still open** (see `PRODUCTION_GAPS.md` §1a for the full list): the oracle scales the
boost by proof-bearing event coverage. The source on-chain registry now receives the
same coverage ratio through its oracle-only score-sync path and applies a proportional
boost after exact event-bound proof validation; TEE/Tier-3 attestation
verification is real but unwired. The oracle-to-chain score push that used to be missing
here now exists — `bcc_middleware`'s `app/reputation.py`/`scoring_loop.py` periodically
pushes each agent's recomputed AIS to `ReputationRegistry.updateScoreWithCoverage` and raises
`Slasher.raiseDispute` on a flagged-telemetry threshold (see `PRODUCTION_GAPS.md` §1 and
`docs/INTERFACE_CONTRACT.md` §7a) — this AIS trust hardening now has a live economic
consumer.

## Constraint score and component floors

`AisBreakdown.constraint_score` is now built as the tier-capped, normalized
pre-boost geometric mean in `[0,1]`. It deliberately excludes `ZK_boost`, so a
constraint consumer cannot treat the same proof as both evidence and a score
multiplier. Configurable component floors and the conjunctive floor result are
also implemented in `AisEngine`, but only as shadow/observational output. No path
currently uses that result to gate score pushes, disputes, or execution. These
mechanisms do not make self-asserted span content independently admissible, and
they do not establish a production deployment.

`AIS_final = min(S_calculated, Tier_ceiling)` — an identity-verification
ceiling clamp — is **`[BUILT]`** and enforced in `integrity-oracle/scoring-core`
via `AisEngine::score_with_tier` (Tier 0: 300, Tier 1: 600, Tier 2: 850, Tier 3: 1000);
see [Identity Ceiling](identity-ceiling.md).

Related: [Telemetry Ingestion Pipeline](telemetry-ingestion.md) (the full
collection→batching→signing→oracle-pipeline writeup; this page covers only
the formula + the server-side re-derivation trust model in depth),
[Behavioral Commitment Chain](bcc.md), [Integrity Oracle](../entities/integrity-oracle.md),
[Local Metrology](local-metrology.md), [AIS API — Versioned Wire Spec](ais-api-spec.md),
[Identity Ceiling & Verification Ladder](identity-ceiling.md).
