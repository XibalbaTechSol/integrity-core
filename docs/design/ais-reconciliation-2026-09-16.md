# AIS definition reconciliation — 2026-09-16

## Authority decision

`docs/DOCUMENT_STATUS.yaml` identifies `docs/SPEC.md` v1.0.0-draft as the active
normative specification. `docs/WHITEPAPER.md` v3.2 and the archived v0.5/v3.2
documents are informative or proposed and cannot silently change the deployed
wire semantics. The generated AIS API remains `/v1`; its OpenAPI is generated
from the Oracle DTOs.

The accepted implementation profile is `ais/v1-geometric-1`:

```text
AIS_base = S_entropy^0.30 * S_grounding^0.30
         * S_sacrifice^0.20 * S_compliance^0.20
AIS_post_boost = AIS_base * (1 + 0.15 * verified_event_ratio)
AIS_final = min(AIS_post_boost, tier_ceiling)
```

The trailing reporting window is 30 days by default. Tier ceilings are 300,
600, 850, and 1000 for tiers 0, 1, 2, and 3+. Exact zero on any positive-weight
axis annihilates the geometric score. Non-finite or unavailable authoritative
inputs fail closed to zero; bounded positive infinity is treated as saturation
only for a bounded, high-is-good raw input (grounding or contribution), never
for stability, compliance, or proof coverage.

## Reconciliation table

| Source | Definition/status | Authority | Required change / affected consumers |
|---|---|---|---|
| `docs/SPEC.md` §10 | Evidence-derived AIS; geometric implementation, shadow floor result, pre-boost constraint score, ZK boost, tier cap marked built/partial | Active normative baseline | Keep accepted geometry; disclose partial evidence and non-enforcement |
| `docs/INTERFACE_CONTRACT.md` §4.3 | `S_E^.30 S_G^.30 S_S^.20 S_C^.20 * ZK_boost`; ratio-based boost; Oracle is sole calculator | Internal interface authority | Add explicit profile and component transfer semantics |
| `docs/WHITEPAPER.md` §3.1.1 | Proposed gated geometric mean with floors and admissible evidence | Informative; not accepted | Keep `shadow_gate` observational; do not enable chain/dispute enforcement |
| `docs/archive/2026-08/integrity-protocol-v0.5-proposed.md` | Proposed `ais/v0.5-gated-geometric-1` migration | Archived proposal | Do not emit v0.5 semantics; preserve as migration reference |
| `integrity-oracle/scoring-core/src/lib.rs` | Canonical formula, transfer functions, tier cap | Authoritative implementation | Validate finite config, use log-domain product, expose base/post-boost/final values |
| `integrity-oracle/backend/src/derive.rs` | Oracle recomputation from signed span content | Authoritative input derivation | Ignore client precomputed entropy/grounding claims; retain them only for audit |
| `integrity-oracle/backend/src/handlers.rs` | REST/SSE AIS response and telemetry ingestion | Authoritative API producer | Expose profile, evidence tier, sufficiency, proxy/missing-axis metadata |
| `bcc_middleware/app/scoring_loop.py` | Consumes Oracle final AIS and removes only reported boost before chain sync | Downstream consumer | Preserve; never reconstruct components/formula |
| `integrity-dashboard/src/services/oracle.ts` | API type mirror | Generated/consumer type boundary | Add new explanatory fields; dashboard remains non-authoritative |
| `integrity-dashboard/src/components/shared/AisSimulator.tsx` | Hypothetical client-side explorer | Non-authoritative | Label profile and hypothetical evidence; no live claim |

## Evidence and limitations

Signed telemetry authenticates the sender, not the truth of every field. The
Oracle excludes unsigned OTLP from AIS and does not trust top-level
`derived_signals`. The contribution field remains a token-usage proxy rather
than independently attested compute, and compliance fails closed for agents
without an independently readable gate or attestation. The Oracle keeps the
client value as `compliance_proxy` and supplies zero to authoritative AIS.
These are explicit proxy limitations, not verified evidence claims.

The Oracle now keeps the token-derived value as `sacrifice_proxy` in the audit
payload only and supplies `sacrifice = 0` to authoritative AIS until validator
or TEE-backed compute evidence is available.

The following remain blockers to claiming AIS is a validated real-world risk or
trust predictor: no sufficiently large time-separated labeled-outcome dataset.
Legacy-envelope freshness equivalence is deliberately not claimed: schema
version 2+ requires signed observation time, while pre-versioning/version-1
evidence is receipt-timed and explicitly marked. New factory-created registries
now enforce the tier cap through a separate governance-held assurance-tier role;
legacy already-deployed clones still require migration before they have that
contract-side enforcement.
The score is mathematically implemented and locally tested, but predictive
validity is not established by synthetic fixtures.

The generated OpenAPI was regenerated after the DTO changes and verified
idempotent by SHA-256. The canonical scoring-core rerun completed independently
of the prior build lock: 22 tests passed. New factory clones now expose and
enforce the assurance tier on chain; the Oracle reports that state when readable,
and middleware fails closed on a configured mismatch. Legacy clones remain a
deployment migration item.
