---
title: Identity Ceiling & Verification Ladder [BUILT]
created: 2026-07-09
updated: 2026-07-30
type: concept
tags: [identity, metrics, compliance]
confidence: high
source_files:
  - README.md
  - integrity-oracle/scoring-core/src/lib.rs
  - integrity-oracle/backend/src/handlers.rs
  - bcc_middleware/app/chain.py
  - bcc_middleware/policies/bcc.rego
---

**`[BUILT]`** — updated 2026-07-30: three real enforcement mechanisms exist:

1. **Tier assignment is server-verified, not client-asserted.**
   `integrity-oracle`'s `register_agent` handler (`SERVER_VERIFIED_TIER`
   constant) always computes the tier itself — a client can no longer send
   `verification_tier: 3` and have it stored as-is. Today the constant is
   always `1`, because Tier 1 is the only tier with a real verification path
   (see the ladder table below); this becomes a real per-agent computation
   once Tier 2/3 verification exists.
2. **`bcc_middleware`'s OPA policy consults tier for a subset of actions.**
   `bcc.rego`'s `min_tier_by_intent_type` rule denies clinical intent-types
   (`EMR_WRITE`, `DISPENSE_MEDICATION`, `BILLING_SUBMISSION`,
   `SECURE_EMR_WRITE`, `CLINICAL_DATA_ACCESS`) from any agent whose
   server-verified tier is below the required minimum.
3. **`AIS_final = min(S_calculated, Tier_ceiling)` score clamp is enforced.**
   `scoring-core` provides `AisEngine::ceiling_for_tier` and `AisEngine::score_with_tier`
   which cap calculated scores per tier: Tier 0 (300), Tier 1 (600), Tier 2 (850), Tier 3 (1000).
   `handlers::compute_ais_for_agent` passes `agent.verification_tier` into `score_with_tier`.

## The design

The idea: an agent's [AIS](ais.md) *ceiling* (not just its measured score)
is tied to how strongly its identity is verified, so a freshly
created, unverified agent can never simply out-score a hardware-attested
institutional one.

| Tier | Verification | AIS ceiling | Status |
|---|---|---|---|
| 1 — Sovereign | Proof-of-possession of a software key (what every agent has today) | 600 | **Server-verified and assigned at registration**; **enforced as an AIS score ceiling (600)**; **consulted by `bcc_middleware`'s OPA gate** |
| 2 — Linked | DNS TXT record or social-account attestation | 850 | Score ceiling enforced in `scoring-core` (850); verification path planned |
| 3 — Institutional | Remote TEE attestation + institutional audit | 1000 (uncapped credit) | Score ceiling uncapped (1000); verification path planned |
| Developer API key (testnet convenience) | Issued by `integrity-userapi` | Capped at 300 | Score ceiling enforced in `scoring-core` (300) |

`AIS_final = min(S_calculated, Tier_ceiling)` is fully implemented in `scoring-core::AisEngine::score_with_tier`.

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
`security/attestation.py` already implements real *verification* of AWS
Nitro attestation documents against a published test fixture — proof
*generation* needs real enclave hardware this environment doesn't have,
which is why the ladder above is entirely unenforced today. Treat any
mention of MAC-address/CPU-serial hashing as never-built product ideation,
not a superseded-but-once-real mechanism.

## EIP-712 binding (design detail, not implemented)

The old wiki proposed an `EntityBinding` EIP-712 typed-data schema binding
an agent's wallet to a named legal `controller`. No such schema or
verification code exists in `contracts/` or `integrity-sdk/` today — noted
here only because it's a plausible future shape for Tier 2/3 binding, not
because it's built.

Related: [DID](did.md), [AIS](ais.md), [agent primitives](agent-primitives.md).
