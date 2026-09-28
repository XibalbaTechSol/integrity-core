# AIS cross-repository consistency matrix — 2026-09-16

| Surface | Authority/role | Profile and values | Synchronization result | Validation |
|---|---|---|---|---|
| `integrity-oracle/scoring-core` | Canonical calculation | `ais/v1-geometric-1`; weights `0.30/0.30/0.20/0.20`; log-domain weighted geometric mean; zero annihilates; ceilings `300/600/850/1000` | Authoritative | 22 unit tests passed |
| Oracle backend | Evidence derivation, aggregation, API | 30-day event-time window; signed telemetry only; client claims audit-only; base/post-boost/final/constraint fields; optional on-chain assurance cross-check | Matches core; exposes evidence and sufficiency metadata; reports legacy uncapped clones as null | 153 library tests passed |
| AIS OpenAPI + contract docs | Wire and integration contract | Includes profile, base/post-boost/final AIS, on-chain base, ceiling, on-chain assurance metadata, ratio, proxies, missing axes, observed time | Generated OpenAPI updated from DTOs; docs reconciled to fail-closed proxy semantics | Generator exit 0; diff check clean for changed AIS files |
| Middleware | Downstream chain synchronizer | Consumes `onchain_base_score`; does not reconstruct components/formula; rejects missing or mismatched modern on-chain assurance state; legacy fallback validates ceiling | Matches Oracle post-adjustment inverse exactly where response field exists; fail-closed before uncapped legacy pushes | 19 targeted middleware tests passed; chain-backed fixture blocked by sandbox socket policy |
| SDK | Collection and signing only | Emits signed `observed_at`; `derived_signals` remain claims/proxies | Cannot make client values authoritative | 23 client unit tests passed |
| Dashboard service/types | Observational consumer | Uses Oracle response fields and profile metadata | No live authoritative formula path | Dashboard build passed |
| Dashboard simulator/radar | Hypothetical/explanatory UI | Simulator explicitly labels hypothetical/profile and consumes centralized `src/services/aisProfile.ts`; radar labels tier ceiling, proxies, and non-probabilistic risk indicators | No policy decision authority or live scoring engine | Build passed; rendered browser proof unavailable because Browser runtime was unavailable |
| On-chain ReputationRegistry | Score storage/boost consumer | Receives Oracle base and coverage; new factory clones bind ceilings to governance-held `ASSURANCE_TIER_ROLE` | New registrations enforce the cap; live Base Sepolia factory still points at a template whose assurance getters revert; 15 registry entries; migration remains required and was not broadcast | Full Foundry suite: 526 passed, 0 failed, 1 skipped; focused ReputationRegistry: 20 passed; factory: 10 passed; read-only Base Sepolia RPC checked 2026-09-17 |
| Empirical validation | Risk/trust claim | Requires real, time-separated outcome labels | **Not validated:** no adequate labeled dataset in workspace | `scripts/validate_ais_predictive.py` implemented and syntax/CLI checked; no production metrics claimed |

## Interpretation

The score definition is consistent across the implemented off-chain path and
newly created on-chain clones. This does not establish that AIS predicts future
incidents. Legacy deployed clones still require a migration to the new
assurance-tier initialization path before the contract-side cap is universal.
