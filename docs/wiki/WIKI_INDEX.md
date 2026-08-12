# Integrity Protocol Wiki — Index

> Content catalog. Every page represents something that actually exists in
> the codebase right now — see the schema's "no aspirational content" rule.
> Last updated: 2026-08-06 | Total pages: 35 (24 concepts, 8 entities, 2 architecture, 1 query)

## Acronym glossary
- [AIS](concepts/ais.md) — Agent Integrity Score
- [BAA](concepts/smart-baa.md) — Business Associate Agreement
- [BCC](concepts/bcc.md) — Behavioral Commitment Chain
- [DID](concepts/did.md) — Decentralized Identifier
- [VTL](concepts/observability-vtl.md) — (old term) Verifiable Trust Layer — see [Observability & PHI Safety](concepts/observability-vtl.md) for what's actually built
- [ZKP](concepts/zkp.md) — Zero-Knowledge Proof(ing pipeline)

## Concepts
- [Integrity Protocol Specification](concepts/integrity-specification.md) — current normative v0.4 living specification and the archived v0.3 PDF
- [The Four Foundational Primitives](concepts/foundational-primitives.md) — memory, agent-owned contracts, authority, reputation: the **concepts**; **start here**
- [Agent Primitives (Self-Sovereign Identity)](concepts/agent-primitives.md) — the 7 per-agent **contracts** (`PrimitiveSet`) — a different sense of "primitive", see the note at the top of both pages
- [ComplianceGate & Integrity Health](concepts/compliance-gate.md) — the HIPAA/healthcare vertical
- [Agent Integrity Score](concepts/ais.md)
- [Telemetry Ingestion Pipeline](concepts/telemetry-ingestion.md) — end-to-end: SDK collection, batching, signing, the oracle's 11-step ordered request pipeline, AIS scoring, the separate unauthenticated OTLP path (built)
- [Behavioral Commitment Chain](concepts/bcc.md)
- [Merkle Batching & Anchoring Convention](concepts/merkle-batching.md)
- [Decentralized Identifier](concepts/did.md)
- [Zero-Knowledge Proving Pipeline](concepts/zkp.md)
- [Integrity Market](concepts/integrity-market.md) — prediction markets, binary options, A2A capital allocation (built, live on Base Sepolia)
- [Smart BAA](concepts/smart-baa.md) — on-chain Business Associate Agreement escrow (built)
- [On-Chain Governance](concepts/governance.md) — `IntegrityGovernance`: lock-to-vote, timelocked propose→vote→queue→execute (built + 26 tests; Base Sepolia deploy deferred)
- [Local Metrology](concepts/local-metrology.md) — client-side AIS signal derivation in the SDK (built)
- [Observability & PHI Safety](concepts/observability-vtl.md) — the `Redactor` (built) + LLM-as-judge design (`[PLANNED]`)
- [Identity Ceiling & Verification Ladder](concepts/identity-ceiling.md) — `[BUILT]`: DNS/GitHub/Nitro evidence, signed revocation, clinical OPA gate, and AIS ceiling clamp
- [Cross-Chain Reputation Sync](concepts/cross-chain-spec.md) — `[PLANNED]`
- [A2A Negotiation Protocol](concepts/a2a-negotiation-spec.md) — `[PLANNED]`
- [ZK-ML Model-Inference Verification](concepts/zk-ml-spec.md) — `[PLANNED]`
- [Persistent Memory, Genesis Root & Lineage](concepts/agent-memory.md) — **foundational primitive** (spec v0.3 §4.1): Trust Vault anchored on the agent's existing `StateAnchor` (no 8th primitive), agent-authorized genesis root, `400 MemoryNotInitialized` registration gate. `[PARTIALLY BUILT]` — gate + SDK anchoring enforced; contract-level epoch-1 restriction and lineage open
- [Persistent Memory Configuration Guide](concepts/persistent-memory.md) — how users/agents can config memory systems.
- [Xibalba Agent Operating Model](concepts/xibalba-agent-operating-model.md) — identity, closed-loop execution, graph memory, wiki compilation, interface design, and approval-gated operations.
- [Testing Strategy](concepts/testing-strategy.md) — the 3-layer test pyramid, incl. new Playwright E2E (built)
- [AIS API — Versioned Wire Spec](concepts/ais-api-spec.md) — the generated, externally-supported `/v1/*` spec at `spec/ais-api/` (built)

## Entities (built)
- [contracts](entities/contracts.md) — Solidity/Foundry: the 7 primitives, factory, registries, XNS, IntegrityGovernance, Integrity Health, market layer, $ITK, reworked CCIPReputationBridge (198 tests, live on Base Sepolia — XNS/governance/CCIP not yet broadcast)
- [integrity-oracle](entities/integrity-oracle.md) — Rust/Axum AIS scoring (incl. server-side telemetry-signal re-derivation, `derive.rs`) + on-chain verification + markets/leaderboard/wallet/contracts/BAA/VC/benchmarks/XNS/governance reads + PHI-rejection backstop + unauthenticated OTLP/gRPC trace receiver, ASCII-escaping canonical-JSON fix (80 lib tests + 9 e2e)
- [integrity-sdk](entities/integrity-sdk.md) — Python agent library: registration, BCC, markets, telemetry (widened OpenAI/LangChain integration metadata, opt-in `redact_phi`), PHI redaction, pre-execution intent-capture (`invoke_intent`), fixed telemetry-signing wire bug (135 tests, 1 skipped + 1 opt-in oracle e2e)
- [integrity-cli](entities/integrity-cli.md) — developer CLI, real on-chain register incl. real oracle re-verification, new `xns` command group (57 tests, incl. 1 opt-in oracle e2e)
- [bcc_middleware](entities/bcc_middleware.md) — FastAPI + OPA policy gate, incl. verification-tier gate, the reputation-sync/slashing signer loop (`app/reputation.py`, `app/scoring_loop.py`), a real async-hot-path fix (`asyncio.to_thread`) plus the per-signer nonce lock and Merkle-batcher thread-safety it required, and a real HMAC-signed verification token (91 pytest + 28 OPA tests)
- [integrity-dashboard](entities/integrity-dashboard.md) — the dashboard app, wired to the real oracle and userapi reads and writes throughout, with full test coverage (9 vitest + 20 Playwright e2e tests run against a live backend+chain), plus the integrated demo/ Python scenario engine.
- [integrity-zkp](entities/integrity-zkp.md) — real Noir/Barretenberg circuit, compiled & proven
- [integrity-userapi](entities/integrity-userapi.md) — FastAPI + Postgres user accounts/auth, strictly non-chain (API keys now authenticate requests, JWT revocation, login rate-limiting, demo_runs completion path — 51 tests, real Postgres, real CORS for integrity-dashboard)

## Guides
- [Smart Contract Development](../guides/smart-contract-development.md) — how to write, test, and deploy a new contract in `contracts/`: repo conventions (AccessControl, custom errors, NatSpec), Foundry test patterns (`vm.prank`/`makeAddr`/`vm.expectRevert(...selector)`), wiring into `Deploy.s.sol`/`DeployMarkets.s.sol` + `make sync-abis`, local/Base Sepolia deploy walkthrough, and the `SovereignAgent.execute` vs. direct-EOA auth convention.
- [Multi-Domain Guardrails Design](../guides/multi-domain-guardrails-design.md) — `[DESIGN, PARTIALLY BUILT]`: how `bcc_middleware`'s HIPAA-only OPA policy gate generalizes to pluggable, domain-scoped guardrail bundles (industry survey + concrete design against this repo's existing `bcc.rego`/`HIPAAGuardrailRegistry.sol` pattern). A real worked-example bundle (`bcc_middleware/policies/general.rego`, 12 passing OPA tests) is built as a stretch goal; the domain-aware `GuardrailRegistry.sol` and `bcc_middleware` wiring are still design-only.

## Architecture
- [Ecosystem Dependencies](architecture/ecosystem-dependencies.md) — cross-repository ownership and dependency direction for integrity-core, Xibalba Graph Memory, Xibalba Shield, and Integrity MVP.
- [Repository Implementation Plans](architecture/repository-implementation-plans.md) — closed/planned/blocked implementation ledger for integrity-core, Integrity MVP, Xibalba Shield, and Xibalba Graph Memory.

## Open queries
- No LLM-as-judge rubric exists anywhere in this repo or the cross-checked
  Desktop spec docs ("Xibalba Solutions defines" it, per the plan notes) —
  the `judge_evaluations` ingestion schema is designed but the actual
  scoring rubric is an open product question, not an engineering one. See
  [Observability & PHI Safety](concepts/observability-vtl.md).

- [Gas Tracking](queries/gas-tracking.md) — Automated SDK gas optimization loop
