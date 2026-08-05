---
title: Identity Ceiling & Verification Ladder [BUILT]
created: 2026-07-09
updated: 2026-08-04
type: concept
tags: [identity, metrics, compliance]
confidence: high
source_files:
  - README.md
  - integrity-oracle/scoring-core/src/lib.rs
  - integrity-oracle/backend/src/handlers.rs
  - integrity-oracle/backend/src/verification.rs
  - integrity-oracle/backend/src/attestation.rs
  - integrity-oracle/backend/src/kyc.rs
  - integrity-oracle/backend/migrations/0011_identity_verifications.sql
  - bcc_middleware/app/chain.py
  - bcc_middleware/policies/bcc.rego
---

**`[BUILT]`** — tier is server-derived from evidence and enforced in both AIS
scoring and sensitive BCC policy decisions.

1. **Tier assignment is server-verified, not client-asserted.** Registration
   establishes tier 1. Active, unexpired, unrevoked evidence raises the effective
   tier; the compatibility request field is ignored.
2. **`bcc_middleware`'s OPA policy consults tier for a subset of actions.**
   `bcc.rego`'s `min_tier_by_intent_type` rule denies clinical intent-types
   (`EMR_WRITE`, `DISPENSE_MEDICATION`, `BILLING_SUBMISSION`,
   `SECURE_EMR_WRITE`, `CLINICAL_DATA_ACCESS`) from any agent whose
   server-verified tier is below the required minimum.
3. **The AIS identity ceiling is enforced.**
   `scoring-core` provides `AisEngine::ceiling_for_tier` and `AisEngine::score_with_tier`
   which cap calculated scores per tier: Tier 0 (300), Tier 1 (600), and Tier 2 (850).
   Tier 3 returns the raw post-boost score without an additional clamp.
   `handlers::compute_ais_for_agent` passes `agent.verification_tier` into `score_with_tier`.

## The design

The idea: an agent's [AIS](ais.md) *ceiling* (not just its measured score)
is tied to how strongly its identity is verified, so a freshly
created, unverified agent can never simply out-score a hardware-attested
institutional one.

| Tier | Verification | AIS ceiling | Status |
|---|---|---|---|
| 1 — Sovereign | Software-key possession plus on-chain primitive match | 600 | Assigned at registration |
| 2 — Linked | Dual-resolver DNS TXT proof or GitHub repository proof | 850 | Built; evidence expires after 90 days |
| 3 — Institutional | Nonce-bound AWS Nitro attestation with AWS-root certificate validation | No post-boost cap | Built; evidence expires after 30 days |
| 3 — Institutional KYC | Trusted receipt asserting document authenticity, liveness, and sanctions/PEP screening | No post-boost cap | Built; provider-neutral and expiring |
| Developer API key (testnet convenience) | Issued by `integrity-userapi` | Capped at 300 | Score ceiling enforced in `scoring-core` (300) |

KYC uses a provider-neutral signed-receipt boundary. A commercial provider or
self-hosted open-source verifier holds an Ed25519 key configured independently in
`KYC_PROVIDER_KEYS`. The `open_source_kyc_v1` profile grants Tier 3 only when the
signed receipt affirms document authenticity, biometric liveness, and sanctions/PEP
screening. The Oracle stores only the provider, opaque reference, check flags,
timestamps, and receipt hash—never raw PII. This records technical assurance; legal
equivalence still depends on deployment jurisdiction and operator policy.

## Evidence lifecycle

DNS, GitHub, TEE, and KYC proofs are challenge-bound and stored in
`identity_verifications`. Agents can revoke one row through a fresh Ed25519-signed
challenge; the signed message binds DID, row ID, nonce, and UTF-8 reason. Evidence
is retained with `revoked_at` and `revoked_reason` for auditability. Because every
tier read filters expired and revoked rows, revocation immediately lowers the
effective tier and its AIS ceiling.

## Correcting the old wiki's mechanism

The old wiki's `identity-ceiling.md`/`hardware-fingerprinting.md` described
Tier 1 as "hardware-tethered" and Tier 2/3 verification building on a
`did:xibalba:<hardware_hash>` derived by hashing CPU model, MAC address,
and OS `machine-id`. **This does not match the current design.** Identity
in this rewrite is a software-held Ed25519/secp256k1 keypair (see
[DID](did.md)) — there is no hardware fingerprint anywhere in
`integrity-sdk`/`integrity-cli` today, and the corrected long-term roadmap
(README's "Identity & hardware trust" table) points at a different, more
credible mechanism: keys tethered to a real TEE/SGX enclave or an HSM (AWS
KMS, FIPS 140-2 Level 3), verified via genuine remote attestation
(AWS Nitro/Intel SGX), not a locally-computed hardware hash a host could
freely fabricate. [integrity-sdk](../entities/integrity-sdk.md)'s
`security/attestation.py` and the Oracle's `attestation.rs` implement real AWS
Nitro document and certificate-chain verification — proof *generation* needs
real enclave hardware this environment doesn't have. Treat any
mention of MAC-address/CPU-serial hashing as never-built product ideation,
not a superseded-but-once-real mechanism.

## EIP-712 legal-controller binding (`[PLANNED]`)

The old wiki proposed an `EntityBinding` EIP-712 typed-data schema binding
an agent's wallet to a named legal `controller`. No such schema or
verification code exists in `contracts/` or `integrity-sdk/` today — noted
here only because it is a plausible additional institutional binding, not
because it's built.

Related: [DID](did.md), [AIS](ais.md), [agent primitives](agent-primitives.md).
