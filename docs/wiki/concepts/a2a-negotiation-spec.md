---
title: A2A Negotiation Protocol [PLANNED]
created: 2026-07-09
updated: 2026-07-09
type: concept
tags: [infrastructure]
confidence: low
source_files:
  - README.md
---

**`[PLANNED]` — not built.** The root `README.md`'s "Advanced primitives"
section names this explicitly so it's tracked, not forgotten, and so
nothing in this repo is mistaken for having built it: a peer-to-peer
capability-broadcast + bid-negotiation protocol (over a gossip layer like
libp2p/Waku) landing in a signed on-chain deal.

## Table of contents

- [Not the same thing as today's A2ACapitalPool](#not-the-same-thing-as-today-s-a2acapitalpool)
- [Old design sketch (not implemented against current contracts)](#old-design-sketch-not-implemented-against-current-contracts)

## Not the same thing as today's `A2ACapitalPool`

Easy to conflate with the real, live `A2ACapitalPool.sol` — documented in
[Integrity Market](integrity-market.md) — they are not the same mechanism. `A2ACapitalPool` is a simpler, **direct
allocation** primitive: an allocator unilaterally escrows funds to a target
agent gated on live AIS, no negotiation. The A2A negotiation protocol
described here is a genuinely different, unbuilt design: agents
autonomously broadcasting capabilities and bidding against each other's
task requests, with no human/allocator initiating the transfer.

## Old design sketch (not implemented against current contracts)

The old wiki's `a2a-negotiation-spec.md` sketched capability broadcast
(`DATA_ANALYSIS`, `CLINICAL_SCRIBE`, etc. over a P2P gossip layer), a task
request schema (`task_type`/`max_price`/`deadline`/`min_ais`), a signed
`BidProposal` response, and extensions to an `AgentMarketplace.sol`
contract that does not exist in this rewrite's `contracts/` at all (it was
part of the old singleton-era prototype). None of this — the P2P layer,
the message schemas, or the contract extensions — has been built against
the current [IntegrityMarket](integrity-market.md)/`XibalbaAgentRegistry`
architecture. Any future implementation should extend
[Interface Contract §6.8](../../INTERFACE_CONTRACT.md#68-agent-contract-ownership-a-formal-protocol-primitive)'s
agent-contract-ownership pattern rather than reviving the old contract.

Related: [Integrity Market](integrity-market.md), [agent primitives](agent-primitives.md).
