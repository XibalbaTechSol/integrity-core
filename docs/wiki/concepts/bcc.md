---
title: Behavioral Commitment Chain (BCC)
acronyms: [BCC]
created: 2026-07-07
updated: 2026-07-15
type: concept
tags: [compliance, cryptography]
confidence: high
source_files:
  - integrity-sdk/integrity_sdk/bcc.py
  - integrity-cli/integrity_cli/bcc.py
  - bcc_middleware/app/canonical.py
  - docs/INTERFACE_CONTRACT.md
---

## Table of contents

- [Overview](#overview)

## Overview

The intent-locking protocol: before an agent executes an action, it signs a
commitment to that action's hash and submits it to
[BCC Middleware](../entities/bcc_middleware.md) for pre-execution policy
gating, via `POST /v1/bcc/intercept`.

Wire schema (field names are load-bearing across packages):
```json
{
  "agent_id": "did:integrity:<sha256(pubkey) fingerprint>",
  "intent_type": "string",
  "intended_state_hash": "0x<sha256 of canonical intent payload>",
  "nonce": "monotonic per-agent integer",
  "timestamp": "<unix ms>",
  "covered_entity_address": "0x<hospital, for healthcare intents> | null",
  "agent_public_key": "z<multibase Ed25519 pubkey>",
  "chain_id": "<EVM chain ID, int>",
  "verifying_contract": "0x<target chain's XibalbaAgentRegistry address>",
  "signature": "0x<Ed25519 sig over the above, canonical JSON>"
}
```

Canonicalization: sorted-key JSON, no whitespace, `ensure_ascii=True`, sign all
fields except `signature` itself. Agreed byte-for-byte across
[integrity-sdk](../entities/integrity-sdk.md),
[integrity-cli](../entities/integrity-cli.md), and
[bcc_middleware](../entities/bcc_middleware.md), verified by cross-package
round-trip tests.

**Self-certifying key (reconciliation).** The DID fingerprint is `sha256(pubkey)`,
not the raw key — so a verifier cannot recover the key from `agent_id`. The
commitment therefore carries `agent_public_key` (multibase); the middleware
*binds* it by checking `sha256(pubkey) == fingerprint` before verifying the
signature, blocking key substitution. `covered_entity_address` is signed so the
target hospital of a healthcare intent can't be swapped post-signature.

**Canonical intent encoding (2026-08-18).** `chain_id`/`verifying_contract`
are both required and both signed — without them a commitment signed once
was valid against any chain or deployment sharing the signing agent's DID.
`bcc_middleware` denies a `chain_id` mismatch unconditionally; it denies a
`verifying_contract` mismatch only when it has a configured
`XibalbaAgentRegistry` address, so local/dev/test topologies with no
deployments file configured aren't turned into a blanket deny — a disclosed
limitation, not a silent downgrade. See
`docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md` for the
full design and residual gaps (the experimental kernel's own replay-domain
binding, and the ZK circuit's `intent_commitment` not yet binding `chain_id`
— both separate, unattempted here).

If the intent passes policy, an [Integrity SDK](../entities/integrity-sdk.md)
or [integrity-cli](../entities/integrity-cli.md) client can additionally
attach a real [ZK proof](zkp.md) that it knows the secret behind its
identity commitment before the middleware anchors the commitment into a
[Merkle batch](merkle-batching.md).

```mermaid
sequenceDiagram
    participant Agent as Agent (SDK/CLI)
    participant MW as bcc_middleware
    Agent->>Agent: sign commitment (canonical JSON,<br/>ensure_ascii=True)
    Agent->>MW: POST /v1/bcc/intercept
    MW->>MW: bind agent_public_key to agent_id<br/>(sha256(pubkey) == fingerprint)
    MW->>MW: verify Ed25519 signature
    alt signature/binding invalid
        MW-->>Agent: deny
    else valid
        MW->>MW: policy + BAA checks<br/>(see bcc_middleware entity page)
        MW-->>Agent: authorized
        opt agent has a ZK proof
            Agent->>MW: attach proof of identity/intent binding
        end
        MW->>MW: admit to Merkle batch
    end
```

See [Interface Contract §4.2](../../INTERFACE_CONTRACT.md#42-bcc-commitment-the-behavioral-commitment-chain-intent-lock-object).
