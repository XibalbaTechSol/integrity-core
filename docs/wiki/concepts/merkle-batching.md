---
title: Merkle Batching & Anchoring Convention
created: 2026-07-07
updated: 2026-07-07
type: concept
tags: [cryptography, layer-2]
confidence: high
source_files:
  - docs/INTERFACE_CONTRACT.md
---

## Table of contents

- [Overview](#overview)

## Overview

Batches of approved [BCC](bcc.md) commitments are anchored on-chain as a
single Merkle root, verified by `StateAnchor.sol` in [contracts](../entities/contracts.md).

- Hash function: **keccak256** (not SHA-256) — cheap and native in the EVM,
  since the root is verified on-chain.
- Leaf: `keccak256(abi.encodePacked(leafData))`.
- Parent: sort the pair of child hashes ascending before concatenating —
  `keccak256(a < b ? a,b : b,a)` — the standard OpenZeppelin `MerkleProof`
  convention. This lets on-chain verification use `MerkleProof.verify`
  directly instead of a bespoke verifier.

This is the one hashing convention every package touching Merkle
trees/proofs (`contracts`, `integrity-oracle`, `bcc_middleware`) must share
exactly — a mismatch here silently breaks proof verification. See
[Interface Contract §4.4](../../INTERFACE_CONTRACT.md#44-merkle-tree-convention-must-match-between-integrity-oracle-and-contracts).
