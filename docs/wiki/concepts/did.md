---
title: Decentralized Identifier (DID)
acronyms: [DID]
created: 2026-07-07
updated: 2026-08-29
type: concept
tags: [identity, cryptography]
confidence: high
source_files:
  - docs/INTERFACE_CONTRACT.md
  - integrity-cli/integrity_cli/identity.py
---

## Table of contents

- [Overview](#overview)

## Overview

An agent's on-protocol identity: a real Ed25519 keypair (no HMAC
pseudo-signature fallback — the old prototype had one, explicitly documented
as fake, and it was removed in this rewrite) expressed as a `did:key`-style
document:

```json
{
  "id": "did:integrity:<hex-pubkey-fingerprint>",
  "controller": "did:integrity:<hex-pubkey-fingerprint>",
  "created": "<ISO8601>",
  "verificationMethod": [{
    "id": "did:integrity:<fingerprint>#key-1",
    "type": "Ed25519VerificationKey2020",
    "publicKeyMultibase": "<base58btc/multicodec-encoded pubkey>"
  }]
}
```

**Fingerprint (load-bearing).** The `<fingerprint>` is the **full**
`sha256(pubkey)` (64 hex chars) — not the raw key and not a truncation. This is
consistent across [integrity-sdk](../entities/integrity-sdk.md) and
[integrity-cli](../entities/integrity-cli.md), and it's why a
[BCC commitment](bcc.md) must carry the public key separately (a hash can't be
reversed to the key): the verifier binds the carried key by re-checking
`sha256(pubkey) == fingerprint`.

**EVM binding.** An agent also holds a separate secp256k1 EVM wallet (used to
[deploy its own contracts](agent-primitives.md)). The SDK/CLI bind it to the DID
by adding a CAIP-10 `blockchainAccountId` verification method
(`eip155:<chainId>:<0xADDRESS>`, type `EcdsaSecp256k1RecoveryMethod2020`), so
resolving the DID yields the agent's on-chain address.

Implemented for real in [integrity-cli](../entities/integrity-cli.md)
(`identity.py` — hand-rolled base58, verified against the reference `base58`
package) and [integrity-sdk](../entities/integrity-sdk.md) (`did.py`).

See [Interface Contract §4.1](../../INTERFACE_CONTRACT.md#41-did-document-producedconsumed-by-integrity-sdk-integrity-oracle).
