# AIS API — Changelog

All notable wire-visible changes to this surface are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/) — one entry per change an
integrator would actually observe, not one per commit.

## Unreleased

- **Removed (exception to the v1 additive-only policy):** `GET /v1/markets`,
  `GET /v1/markets/{id}`, `GET /v1/stats`, `GET /v1/governance/proposals`,
  `GET /v1/agent/{id}/stake`, `GET /v1/agent/{id}/credit` and `GET /v1/agent/{id}/contracts`.
  Their backing contracts (markets, A2ACapitalPool, IntegrityGovernance) were cut from the
  protocol (docs/EXECUTION_PLAN.md A1), so the routes could only have served stale or empty
  data. `GET /v1/agent/{id}/wallet` drops `open_positions` (market positions) and keeps the
  `$ITK` balance. The policy calls for a `/v2` prefix on any removal; this is recorded as a
  deliberate exception because the only known consumer is the operator console, updated in the
  same change. The routes now return 404, verified by the oracle e2e test.
- **Behavior:** telemetry `zk_proof` is still accepted but is never verified (ZK proving was
  retired and the on-chain verifier rejects every proof). `zk_verified` is always `false`, so
  the ZK boost input `zk_verified_event_ratio` stays 0.
- Regenerated the spec, which also picks up the previously unpublished
  `GET /v1/xns/available/{handle}` and `POST /v1/xns/claim` routes.
- Added nullable on-chain assurance-tier metadata to AIS responses. New factory clones
  expose the contract-read tier/ceiling and an Oracle/chain consistency flag; legacy
  clones return `null` until migrated. Middleware now fails closed on a missing or
  mismatched modern cap, preventing synchronization to an uncapped legacy clone.
- Added signed telemetry event time, semantic duplicate protection, and explicit
  audit-only handling for unattested sacrifice/compliance proxies.
- Documented the authoritative `ais/v1-geometric-1` scoring profile and added
  explicit base, post-boost, tier-ceiling, evidence-tier, sufficiency, proxy,
  and missing-axis fields to the AIS response. The proposed v0.5 gated-floor
  profile remains shadow-only and is not emitted as the active profile.
- Added provider-neutral KYC challenge and receipt-verification endpoints. The
  `open_source_kyc_v1` receipt is nonce-bound, Ed25519-signed by a configured provider,
  time-limited, and explicitly records document, liveness, and sanctions/PEP checks
  without transmitting raw PII to the Oracle.
- Fixed the OpenAPI generator so output is anchored to `CARGO_MANIFEST_DIR`; invoking it
  from the workspace root or backend crate now updates the same repository file.

## v1.0.0 — initial published surface

- First versioned, generated spec for the AIS API, covering all 10 `/v1/*` endpoints
  served by `integrity-oracle`'s backend.
- Fixed a real gap as part of this freeze: `GET /v1/agent/{id}` now returns
  `did_document` (previously accepted on `POST /v1/agent/register` and silently
  dropped — never persisted, never returned).
- `verification_tier` ships marked **RESERVED (partially enforced)**. Also fixed a
  real security-relevant gap in the same pass: this field was previously
  self-asserted by the *client* at registration with no server-side verification —
  any client could claim `verification_tier: 3`. `register_agent` now always
  computes and stores a server-verified value (currently always `1`, the only tier
  with a built verification path); the client-supplied value is accepted on the
  wire for shape compatibility but ignored.
- `A2ACapitalPool` has no read endpoint yet — deferred to a future minor version as
  net-new additive surface, not a v1 blocker.
