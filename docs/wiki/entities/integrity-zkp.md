---
title: integrity-zkp
created: 2026-07-07
updated: 2026-07-15
type: entity
tags: [cryptography]
confidence: high
source_files:
  - integrity-zkp/circuit/src/main.nr
  - integrity-zkp/README.md
  - integrity-zkp/Makefile
---

## Table of contents

- [Overview](#overview)

## Overview

The zero-knowledge attestation circuit: proves an agent knows the secret
behind its published identity commitment, and that it committed to a
specific intent hash under a given nonce — without revealing the secret or
full intent payload. Written in Noir, proven with Barretenberg (real
toolchain, real proofs — not a mock).

**Hash function: Pedersen** (`std::hash::pedersen_hash`), not SHA-256, for
in-circuit commitments — cheaper in-circuit, and the convention already used
by comparable circuits. The outer [BCC](../concepts/bcc.md) wire object's
`intended_state_hash` stays SHA-256 (a different, unrelated hash used for the
Ed25519 signature over the wire payload) — **this two-hash split is a
load-bearing decision every consumer of this circuit must replicate exactly**
(byte→Field reduction, Pedersen array ordering, domain-separation tags
`DOMAIN_IDENTITY=1` / `DOMAIN_INTENT=2` — see the package README for the
precise formula).

Circuit constraints (`src/main.nr`):
1. `pedersen_hash([1, secret_key]) == agent_id_commitment` — identity binding.
2. `pedersen_hash([2, secret_key, intent_payload_hash, nonce]) == intent_commitment` — intent binding.
3. `nonce != 0` — defensive.

Explicitly out of scope (documented, not silently skipped): this is not a
full Ed25519 signature-verification circuit — that needs non-native
Curve25519 field arithmetic. This circuit proves *possession* of the secret
behind a published commitment, not a full signature check in-circuit.

Real, run commands (`nargo test` — 4/4 pass, including 3 negative
`should_fail` cases; `nargo compile` → `bb write_vk` → `bb prove` → `bb
verify` — verified success and a negative-control failure; `bb
write_solidity_verifier` → 2465-line generated Honk verifier). Full
transcripts in the package's own `README.md`.

**Flagged for [contracts](contracts.md) to reconcile**: `bb` 5.0.0-nightly's
default proving scheme is UltraHonk, not classic UltraPlonk — the generated
verifier file is still named `UltraPlonkVerifier.sol` to match the path the
[interface contract](../../INTERFACE_CONTRACT.md) expects, but it has
`NUMBER_OF_PUBLIC_INPUTS=11` (Honk's internal accumulator inputs), not 3.

Related: [ZKP pipeline](../concepts/zkp.md), [BCC](../concepts/bcc.md).
