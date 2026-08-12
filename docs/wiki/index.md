# Integrity Protocol Wiki

Compiled knowledge base for the Integrity Protocol monorepo — a trust/
compliance layer for AI agents on Base L2. This page is the map; every
section below links to the real page. Governance/conventions:
`WIKI_SCHEMA.md` (page format), `WIKI_INDEX.md` (the full catalog with
one-line descriptions — the canonical index this page summarizes),
`WIKI_LOG.md` (chronological history, append-only). Cross-package
decisions live in `../INTERFACE_CONTRACT.md`; how this wiki gets kept in
sync with the code is `../../.agents/AGENTS.md`.

**Start here** if you're new: [The Four Foundational Primitives](concepts/foundational-primitives.md)
(the concepts), then [Agent Primitives](concepts/agent-primitives.md)
(the 7 per-agent contracts every other page assumes you understand) and
[Persistent Memory](concepts/agent-memory.md) (the continuity primitive that
gates registration), then [AIS](concepts/ais.md) (the trust score) and
[Telemetry Ingestion Pipeline](concepts/telemetry-ingestion.md) (how
agent behavior becomes that score).

## Current cross-repository audit — 2026-08-06

The four-repository implementation plan and audit ledger are maintained outside the generated wiki at `/home/xibalba/Documents/INTEGRITY — Cross-Repository Audit and Implementation Plan.md`. Repository-local status pages are:

- [`integrity-core` audit status](../audits/2026-08-06-cross-repository-status.md): strong testnet prototype; SDK has 2 failing tests; production readiness not established.
- [`integrity-mvp` audit status](https://github.com/XibalbaTechSol/integrity-mvp/blob/main/docs/audits/2026-08-06-status.md): frontend build and unit tests pass; lint and dependency-security gaps remain.
- [`xibalba-shield` audit status](https://github.com/XibalbaTechSol/xibalba-shield/blob/main/docs/audits/2026-08-06-status.md): Linux-first prototype; 2 of 3 eBPF probes verified; TCP-connect blocked.
- [`xibalba-cortex` audit status](https://github.com/XibalbaTechSol/xibalba-cortex/blob/main/docs/audits/2026-08-06-status.md): local MCP memory prototype; tests pass with Drive extras; active worktree changes require review.

These pages distinguish `DONE`, `PARTIAL`, `PLANNED`, `BLOCKED`, `UNVERIFIED`, and `REQUIRES REVIEW`. Historical wiki log entries and design records remain historical evidence.

## System at a glance

```mermaid
flowchart TB
    Wallet["Agent's own wallet"]
    Factory["AgentPrimitivesFactory"]

    subgraph OnChain["On-chain (EVM / Base Sepolia + anvil)"]
        SA["SovereignAgent<br/>(identity account)"]
        StA["StateAnchor<br/>(per-agent audit root)"]
        subgraph Clones["5 EIP-1167 minimal-proxy clones"]
            RR["ReputationRegistry"]
            SL["Slasher"]
            VR["VerifierRegistry"]
            CG["ComplianceGate"]
            AP["AgentProfile"]
        end
    end

    SDK["integrity-sdk / integrity-cli"]
    BCC["bcc_middleware<br/>(FastAPI + OPA)"]
    Oracle["integrity-oracle<br/>(Rust/Axum)"]
    Dashboard["integrity-dashboard<br/>(React + Python)"]
    UserAPI["integrity-userapi<br/>(FastAPI + Postgres)"]

    Wallet -->|signs direct deploys| SA
    Wallet -->|signs direct deploys| StA
    Factory -->|clones| RR
    Factory -->|clones| SL
    Factory -->|clones| VR
    Factory -->|clones| CG
    Factory -->|clones| AP

    SDK --> Wallet
    SDK -->|pre-execution gate| BCC
    SDK -->|signed telemetry| Oracle
    BCC -->|reads AIS, pushes score on-chain| Oracle
    Oracle -->|resolve + score| OnChain
    Oracle --> Dashboard
    UserAPI -->|read-only fan-out, never chain| Oracle
    Dashboard --> UserAPI
```

## Table of contents

### Concepts — identity & on-chain primitives
- [The Four Foundational Primitives](concepts/foundational-primitives.md) — the concepts the protocol rests on; **start here**
- [Agent Primitives (Self-Sovereign Identity)](concepts/agent-primitives.md) — the 7 per-agent *contracts* (a different sense of the word)
- [Persistent Memory, Genesis Root & Lineage](concepts/agent-memory.md) — **foundational primitive**: no agent registers without an anchored genesis memory root (`[PARTIALLY BUILT]`)
- [Decentralized Identifier (DID)](concepts/did.md)
- [Identity Ceiling & Verification Ladder](concepts/identity-ceiling.md) — `[PARTIALLY BUILT]`

### Concepts — trust & scoring
- [Agent Integrity Score (AIS)](concepts/ais.md) — the formula + oracle's server-side re-derivation trust model
- [Telemetry Ingestion Pipeline](concepts/telemetry-ingestion.md) — end-to-end: SDK collection → batching → signing → the oracle's 11-step ordered pipeline → AIS
- [Local Metrology](concepts/local-metrology.md) — the exact entropy/grounding/sacrifice/compliance formulas
- [Observability & PHI Safety Pipeline](concepts/observability-vtl.md) — the `Redactor`, `redact_phi`, the oracle-side PHI backstop

### Concepts — behavioral gating & cryptography
- [Behavioral Commitment Chain (BCC)](concepts/bcc.md) — the pre-execution signed-intent gate
- [Merkle Batching & Anchoring Convention](concepts/merkle-batching.md)
- [Zero-Knowledge Proving Pipeline (ZKP)](concepts/zkp.md)

### Concepts — compliance & markets
- [ComplianceGate & Integrity Health](concepts/compliance-gate.md) — the HIPAA/healthcare vertical
- [Smart BAA](concepts/smart-baa.md) — on-chain Business Associate Agreement escrow
- [Integrity Market](concepts/integrity-market.md) — prediction markets, binary options, A2A capital allocation

### Concepts — wire spec & testing
- [AIS API — Versioned Wire Spec](concepts/ais-api-spec.md) — the generated, externally-supported `/v1/*` spec
- [Testing Strategy](concepts/testing-strategy.md) — the 3-layer test pyramid

### Concepts — planned / design-only
- [Identity Ceiling & Verification Ladder](concepts/identity-ceiling.md) — `[PARTIALLY BUILT]`
- [Cross-Chain Reputation Sync](concepts/cross-chain-spec.md) — `[PLANNED]`
- [A2A Negotiation Protocol](concepts/a2a-negotiation-spec.md) — `[PLANNED]`
- [ZK-ML Model-Inference Verification](concepts/zk-ml-spec.md) — `[PLANNED]`

### Entities — one page per real package
- [contracts](entities/contracts.md) — Solidity/Foundry: the 7 primitives, factory, registries, XNS, Integrity Health, market layer, $ITK
- [integrity-oracle](entities/integrity-oracle.md) — Rust/Axum: AIS scoring, server-side telemetry re-derivation, on-chain reads, markets/leaderboard
- [integrity-sdk](entities/integrity-sdk.md) — Python agent library: identity, BCC, markets, telemetry, PHI redaction
- [integrity-cli](entities/integrity-cli.md) — developer CLI, independent reimplementation of the SDK's core flows
- [bcc_middleware](entities/bcc_middleware.md) — FastAPI + OPA pre-execution policy gate + reputation-sync loop
- [integrity-userapi](entities/integrity-userapi.md) — FastAPI + Postgres user accounts/auth, strictly non-chain
- [integrity-dashboard](entities/integrity-dashboard.md) — the React/Vite dashboard + `demo/` scenario engine
- [integrity-zkp](entities/integrity-zkp.md) — the real Noir/Barretenberg circuit

### Architecture
- [Ecosystem Dependencies](architecture/ecosystem-dependencies.md) — cross-repository ownership and dependency direction for integrity-core, Xibalba Cortex, Xibalba Shield, and Integrity MVP.
- [Repository Implementation Plans](architecture/repository-implementation-plans.md) — closed/planned/blocked implementation ledger for integrity-core, Integrity MVP, Xibalba Shield, and Xibalba Cortex.

### Guides
- [Smart Contract Development](../guides/smart-contract-development.md) — writing/testing/deploying a new contract
- [Multi-Domain Guardrails Design](../guides/multi-domain-guardrails-design.md) — `[DESIGN, PARTIALLY BUILT]`

### Reference
- [WIKI_INDEX.md](WIKI_INDEX.md) — full catalog, one-line description per page (the canonical index)
- [WIKI_LOG.md](WIKI_LOG.md) — chronological record of every wiki change, append-only
- [WIKI_SCHEMA.md](WIKI_SCHEMA.md) — page format, frontmatter, tag taxonomy

### Open queries
- No LLM-as-judge rubric exists anywhere in this repo — the `judge_evaluations`
  ingestion schema is built but the scoring rubric is an open product
  question. See [Observability & PHI Safety](concepts/observability-vtl.md).

## Acronym glossary
- **AIS** — Agent Integrity Score → [concepts/ais.md](concepts/ais.md)
- **BAA** — Business Associate Agreement → [concepts/smart-baa.md](concepts/smart-baa.md)
- **BCC** — Behavioral Commitment Chain → [concepts/bcc.md](concepts/bcc.md)
- **DID** — Decentralized Identifier → [concepts/did.md](concepts/did.md)
- **VTL** — (old term) Verifiable Trust Layer → see [Observability & PHI Safety](concepts/observability-vtl.md) for what's actually built
- **ZKP** — Zero-Knowledge Proof(ing pipeline) → [concepts/zkp.md](concepts/zkp.md)

## No aspirational content

Every page here documents what exists in the code right now. A feature
described in a spec but not yet implemented is explicitly marked
`[PLANNED]` or `[DESIGN, PARTIALLY BUILT]` in its title/index entry — never
written as if it's real. See `WIKI_SCHEMA.md` for the full convention.
