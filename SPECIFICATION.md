# INTEGRITY-LATEST Repository Specification

**Updated:** 2026-08-06
**Status:** Strong testnet protocol prototype; not production-ready.

## 1. Purpose

INTEGRITY-LATEST is the protocol trust backend for the Integrity Protocol. It owns the on-chain primitives, off-chain scoring services, Behavioral Commitment Chain middleware, SDK/CLI surfaces, user API, dashboard package, ZKP package, canonical wiki, and versioned protocol specifications.

The repository defines how AI agents establish identity, commit to behavior before execution, submit signed telemetry, receive Agent Integrity Scores, interact with compliance and market primitives, and expose evidence that downstream applications can present without inventing trust claims.

## 2. Authority

| Document | Role |
|---|---|
| README.md | Repo overview, package map, and source-of-truth precedence. |
| IMPLEMENTATION_PLAN.md | Closed/planned/blocked implementation ledger. |
| PRODUCTION_GAPS.md | Detailed production-readiness gap register. |
| docs/INTERFACE_CONTRACT.md | Internal package ports, schemas, environment variables, and coordination rules. |
| spec/integrity-protocol-v0.4.md | Normative protocol specification. |
| spec/README.md and spec/ais-api/v1 | Versioned externally-supported wire surfaces. |
| docs/audits/2026-08-06-cross-repository-status.md | Current audit evidence and production posture. |
| docs/wiki/ | Canonical long-term project memory and downstream wiki source. |

## 3. Ownership Boundary

INTEGRITY-LATEST owns protocol primitives and public protocol interfaces. It must not import or depend on integrity-mvp, xibalba-shield, or xibalba-graph-memory. Those repositories consume public Integrity interfaces and own their own presentation, endpoint, or local-memory implementation details.

## 4. Components

| Component | Responsibility | Current posture |
|---|---|---|
| contracts/ | EVM identity, reputation, staking, slashing, governance, health, market, and verification contracts. | Broadly tested on local/testnet paths; deployment verification remains open. |
| integrity-oracle/ | Rust/Axum telemetry intake, AIS derivation, chain reads, markets, VC/verification reads, and OpenAPI surface. | Tested prototype; production controls and live deployment review remain open. |
| bcc_middleware/ | FastAPI/OPA pre-execution intent gate, commitment verification, Merkle batching, and reputation sync. | Implemented and tested; policy/domain generalization remains partial. |
| integrity-sdk/ | Python agent SDK for registration, wallet, BCC, telemetry, markets, metrology, and redaction. | Implemented; clean-main audit found SDK test drift that must be reconciled. |
| integrity-cli/ | Typer CLI for developer and operator protocol workflows. | Implemented with passing package tests in audit evidence. |
| integrity-userapi/ | User accounts/auth, API keys, JWT revocation, demo run completion, and non-chain fan-out. | Implemented; strictly non-chain. |
| integrity-dashboard/ | React dashboard and demo scenario engine inside this monorepo. | Implemented prototype; dashboard lint/test evidence must stay commit-scoped. |
| integrity-zkp/ | Noir/Barretenberg off-chain circuit/proving pipeline. | Real off-chain proving exists; deployed on-chain verifier placeholder is not production ZK verification. |
| docs/wiki/ | Canonical wiki memory and publication source. | Validates structurally; several stale pages remain audit findings. |

## 5. Public Interfaces

- Contracts expose agent primitive deployment, state anchoring, reputation, governance, health/compliance, market, token, and verifier surfaces defined in spec/integrity-protocol-v0.4.md.
- Oracle APIs expose AIS, agent, telemetry, market, wallet, XNS/governance, and versioned AIS API surfaces defined in docs/INTERFACE_CONTRACT.md and spec/ais-api/v1.
- BCC middleware exposes pre-execution policy/commitment checks and evidence paths; versioned BCC intent schema remains a planned wire-surface closure item.
- SDK and CLI consume public contract/API surfaces and must not bypass protocol verification rules.
- Wiki publication flows downstream to integrity-mvp and GitHub Wiki; downstream copies are read-only projections.

## 6. Trust And Evidence Model

Every trust claim must name its evidence class: code, tests, direct chain read, deployment artifact, signature, Merkle proof, telemetry row, audit log row, CI run, or manual review. A passing test proves only the tested behavior under the tested command and commit. A deployed address proves bytecode exists at that address, not ownership, role correctness, source matching, or production readiness.

## 7. Production Readiness Requirements

- Clean CI must pass on the protected branch, including SDK drift closure.
- Base Sepolia deployment records must be checked against chain state, bytecode, roles, ownership, and source.
- Automatic merge authority must be reconciled with human-review policy.
- Public schemas must have generated artifacts and conformance vectors.
- Operational runbooks must cover deploy, rollback, incident diagnosis, evidence export, and secret handling.
- Normative partial/planned gaps must remain visible in README, PRODUCTION_GAPS, specs, and wiki.

## 8. Non-Goals

- This repository does not own endpoint enforcement behavior; xibalba-shield owns that.
- This repository does not own MVP presentation behavior; integrity-mvp owns that.
- This repository does not own local agent memory storage; xibalba-graph-memory owns that.
- This repository does not certify production deployment without fresh CI/deployment/security evidence.

## 9. Acceptance Criteria

- README, IMPLEMENTATION_PLAN, PRODUCTION_GAPS, interface contract, protocol spec, and wiki agree on status and source-of-truth rules.
- Every public wire surface has a versioned schema or explicit planned/blocker status.
- Downstream repositories consume only documented public interfaces.
- Canonical wiki lint reports zero orphans and zero dead index links.
- Production claims are backed by current evidence, not historical intent.
