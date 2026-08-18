---
title: Ecosystem Dependencies
acronyms: []
created: 2026-08-06
updated: 2026-08-12
type: architecture
tags: [infrastructure]
confidence: high
source_files:
  - docs/architecture/ecosystem-dependencies.md
  - README.md
  - spec/xibalba-shield-v1.md
---

# Ecosystem Dependencies

This page is the wiki-facing cross-repository dependency map for integrity-core (including its
`integrity-dashboard/` component), Xibalba Cortex, and Xibalba Shield. It reflects the canonical
architecture note in [docs/architecture/ecosystem-dependencies.md](../../architecture/ecosystem-dependencies.md), the root README stack description, and the Shield v1 specification.

**Corrected 2026-08-12:** this page previously described a four-project ecosystem with a separate
`integrity-mvp` repository as the presentation layer. `integrity-dashboard/` (inside this
repository) is now the actively developed operator-dashboard/presentation layer; the standalone
`integrity-mvp` repository it supersedes is stale rather than deleted — see the canonical
architecture note linked above for the full correction note.

## Table of contents

- [Ownership and runtime boundaries](#ownership-and-runtime-boundaries)
- [Dependency direction](#dependency-direction)
- [Project responsibilities](#project-responsibilities)
- [Source of truth](#source-of-truth)

## Ownership and runtime boundaries

`integrity-core` is the protocol trust backend. It owns the SDK, Behavioral Commitment Chain policy and commitment pipeline, Oracle/AIS scoring, user API, protocol contracts, chain conventions, wiki memory source of truth, and — as its `integrity-dashboard/` component — the web presentation/operator-workflow layer.

`xibalba-shield` is a separate endpoint-security product and evidence producer. It discovers AI agents and tools running on devices or networks, enforces local security policy, and feeds signed evidence into the Integrity Protocol trust pipeline. It is not a second reputation backend, not the Integrity Health vertical, and not an on-chain scoring layer.

`xibalba-cortex` is the local profile-isolated cognitive store. It owns recall, provenance, session roots, and graph traversal; local memory evidence may be cited or anchored through public Integrity interfaces, but recalled text is not protocol authority.

`integrity-dashboard/` (inside `integrity-core`) is the web presentation and operator-workflow layer. It consumes integrity-core's own services directly for protocol identity, reputation, telemetry, BCC, user, and chain data, while also surfacing Cortex workflows, Shield workflows, and endpoint-security evidence — with no privileged path over any other consumer of those same public interfaces.

## Dependency direction

The intended stack is:

`integrity-core/integrity-dashboard -> xibalba-cortex -> integrity-core`

`integrity-core/integrity-dashboard -> xibalba-shield -> integrity-core`

`integrity-dashboard/` also consumes integrity-core's own APIs directly.

The dependency boundary is one-way: integrity-core's protocol packages must not import, call, or require Cortex or Shield. A Cortex or Shield implementation failure must not alter AIS computation, Merkle batching conventions, chain schemas, or protocol anchoring. An `integrity-dashboard/` failure must not interrupt either backend layer.

## Project responsibilities

| Project | Owns | Consumes |
|---|---|---|
| `integrity-core` | SDK, BCC, Oracle/AIS, user API, contracts, chain conventions, canonical wiki, plus `integrity-dashboard/` (web presentation, operator workflows, generated read-only wiki browser) | No Cortex or Shield code in its protocol packages |
| `xibalba-cortex` | Local memories, provenance, session roots, graph traversal, read-only evidence links | Public integrity-core anchoring interfaces only; no protocol authority |
| `xibalba-shield` | Endpoint discovery, local policy enforcement, guardrail hooks, endpoint evidence | Public integrity-core SDK/BCC/telemetry/Oracle/chain interfaces |

## Source of truth

The normative Shield product boundary is [spec/xibalba-shield-v1.md](../../../spec/xibalba-shield-v1.md). Current Shield implementation status lives in the separate `xibalba-shield` repository README. Cross-package wire shapes inside integrity-core remain governed by [docs/INTERFACE_CONTRACT.md](../../INTERFACE_CONTRACT.md).

The canonical wiki content source remains [WIKI_SCHEMA.md](../WIKI_SCHEMA.md): integrity-core/docs/wiki is authored directly; `integrity-dashboard/`'s `/wiki` route and the GitHub Wiki are generated, read-only projections.
