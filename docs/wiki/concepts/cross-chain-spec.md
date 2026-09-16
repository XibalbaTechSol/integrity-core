---
title: Cross-Chain Reputation Sync [PLANNED]
created: 2026-07-09
updated: 2026-09-15
type: concept
tags: [layer-2]
confidence: low
source_files:
  - contracts/src/oracle/CCIPReputationBridge.sol
  - README.md
---

**`[PLANNED]` — not built, not deployed, not wired in.** The root
`README.md`'s "Decentralization path" lists cross-chain reputation
(syncing [AIS](ais.md) across Base/Arbitrum/Ethereum) as a real future
step, not a current capability. This page replaces the old wiki's
`cross-chain-spec.md`, which described a "Canonical Reputation Registry" +
"Satellite Synchronizers" design assuming the pre-rewrite singleton
`ReputationRegistry` model — that model is gone (see
[agent primitives](agent-primitives.md)), so the old design doesn't apply
as written.

## Table of contents

- [Current state: an honest, documented gap](#current-state-an-honest-documented-gap)
- [What a real design would need to solve](#what-a-real-design-would-need-to-solve)

## Current state: an honest, documented gap

`contracts/src/oracle/CCIPReputationBridge.sol` exists in the codebase and its
per-agent clone resolution has been reworked: both send and receive resolve
the agent's `ReputationRegistry` through `XibalbaAgentRegistry`, and an
unregistered agent fails closed. The bridge remains **explicitly unwired for
production**: it is not deployed by `Deploy.s.sol`, and each agent must
opt-in by granting the bridge `BRIDGE_ROLE` on its own clone while operators
configure trusted peer bridges and a real CCIP lane. The contract and its
tests are therefore implemented but still `[PLANNED]` as a deployed
cross-chain capability.

## What a real design would need to solve

Not built, but the shape a working version would have to address:
per-agent clone resolution (above) instead of a single hub registry;
a bridge-agnostic messaging layer (CCIP, the contract's namesake, or an
alternative) rather than vendor lock-in; a minimum confirmation delay to
mitigate bridge-reorg risk before a synced score is trusted on the
destination chain. None of this has an implementation to point at.

Related: [AIS](ais.md), [agent primitives](agent-primitives.md),
[contracts](../entities/contracts.md).
