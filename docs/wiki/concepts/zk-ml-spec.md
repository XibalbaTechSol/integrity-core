---
title: ZK-ML Model-Inference Verification [PLANNED]
created: 2026-07-09
updated: 2026-07-09
type: concept
tags: [cryptography]
confidence: low
source_files:
  - README.md
  - integrity-zkp/src/main.nr
---

**`[PLANNED]` — not built.** The root `README.md`'s "Advanced primitives"
section names this explicitly: proving an agent's output came from a
*specific, authorized* model — without revealing the model's weights — via
a dedicated Noir inference circuit plus a `ZKModelRegistry.sol` contract.
Neither exists in this repo.

## Table of contents

- [Not the same thing as today's ZK layer](#not-the-same-thing-as-today-s-zk-layer)
- [Why it's out of scope for now](#why-it-s-out-of-scope-for-now)

## Not the same thing as today's ZK layer

Easy to conflate with the real, built [ZKP pipeline](zkp.md) — they prove
different things. Today's circuit
([integrity-zkp](../entities/integrity-zkp.md), real Noir/Barretenberg,
proven end-to-end) proves *possession of a secret behind a published
identity/intent commitment* — it says nothing about which model produced a
given output. Model-inference verification would need to prove
*correctness of a specific computation* (a forward pass through specific,
committed weights), a fundamentally larger circuit — the old wiki's sketch
proposed a simple multi-layer-perceptron inference circuit as a starting
point, with private `weights`/`input` and public `model_hash`/`output`.

## Why it's out of scope for now

Circuit complexity for real model inference (even a small MLP) is far
beyond the identity/intent-binding circuit's constraint count; the old
design explicitly proposed restricting it to "Institutional Tier"
(see [identity-ceiling](identity-ceiling.md), itself unbuilt) tasks only,
given the cost. No `ZKModelRegistry.sol`, no inference circuit, and no SDK
proof-generation hook for this exist anywhere in `contracts/` or
`integrity-zkp/` today — nothing here should be read as in progress.

Related: [ZKP pipeline](zkp.md), [integrity-zkp](../entities/integrity-zkp.md).
