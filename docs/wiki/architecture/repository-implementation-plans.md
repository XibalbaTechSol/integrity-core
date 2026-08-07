---
title: Repository Implementation Plans
acronyms: [AIS, BCC, DID, MVP]
created: 2026-08-06
updated: 2026-08-06
type: architecture
tags: [infrastructure, planning, roadmap, documentation]
confidence: high
source_files:
  - IMPLEMENTATION_PLAN.md
  - SPECIFICATION.md
  - README.md
  - docs/INTERFACE_CONTRACT.md
  - spec/integrity-protocol-v0.4.md
  - spec/xibalba-shield-v1.md
  - docs/audits/2026-08-06-cross-repository-status.md
---

# Repository Implementation Plans

This page is the cross-repository implementation and specification ledger for the Integrity Protocol product stack. It summarizes the root `IMPLEMENTATION_PLAN.md` and `SPECIFICATION.md` files that now exist in each project root:

- `INTEGRITY-LATEST/IMPLEMENTATION_PLAN.md` and `INTEGRITY-LATEST/SPECIFICATION.md`
- `integrity-mvp/IMPLEMENTATION_PLAN.md` and `integrity-mvp/SPECIFICATION.md`
- `xibalba-shield/IMPLEMENTATION_PLAN.md` and `xibalba-shield/SPECIFICATION.md`
- `xibalba-graph-memory/IMPLEMENTATION_PLAN.md` and `xibalba-graph-memory/SPECIFICATION.md`

The root implementation plans and root specifications are the repo-local implementation/specification source of truth. The permanent audit ledger at `/home/xibalba/Documents/INTEGRITY — Cross-Repository Audit and Implementation Plan.md` and the repo-local `docs/audits/2026-08-06*.md` files provide the current verification evidence. This wiki page is the canonical cross-repo map used to see dependency direction, closed work, open work, and blockers in one place.

## Table of contents

- [Dependency order](#dependency-order)
- [Audit evidence boundary](#audit-evidence-boundary)
- [INTEGRITY-LATEST](#integrity-latest)
- [Integrity MVP](#integrity-mvp)
- [Xibalba Shield](#xibalba-shield)
- [Xibalba Graph Memory](#xibalba-graph-memory)
- [Cross-repository task list](#cross-repository-task-list)
- [Update rule](#update-rule)

## Dependency order

```mermaid
flowchart LR
    Latest["INTEGRITY-LATEST<br/>protocol backend, contracts, APIs, canonical wiki"]
    Shield["xibalba-shield<br/>endpoint evidence producer"]
    Graph["xibalba-graph-memory<br/>local provenance memory service"]
    MVP["integrity-mvp<br/>presentation and operator workflows"]

    Shield -->|DID, BCC, telemetry, evidence export| Latest
    MVP -->|reads public API/SDK/wiki surfaces| Latest
    MVP -->|renders Shield status/evidence| Shield
    MVP -->|renders recall, graph, provenance states| Graph
    Graph -.->|future one-way citation boundary| Latest
```

INTEGRITY-LATEST remains the protocol authority. Shield and graph memory do not become dependencies of INTEGRITY-LATEST unless a public interface explicitly adds that boundary. The MVP is a consumer and presentation layer.

## Audit evidence boundary

- `DONE` means implemented and verified by the audit's cited command, direct read, or deployment evidence.
- `PARTIAL` means some implementation exists, but the required scope or control is incomplete.
- `PLANNED` means specified or designed with no verified implementation found.
- `BLOCKED` means required work exists but depends on a documented environment, dependency, or decision.
- `UNVERIFIED` and `REQUIRES REVIEW` claims must not be promoted to production status.
- Dirty worktree evidence and clean default-branch evidence stay labeled separately until reviewed.

## INTEGRITY-LATEST

**Role:** Protocol trust backend: contracts, SDK, CLI, BCC middleware, Oracle/AIS, user API, dashboard, ZKP, canonical wiki, and protocol specs.

**Specification authority:** `README.md`, `SPECIFICATION.md`, `PRODUCTION_GAPS.md`, `docs/INTERFACE_CONTRACT.md`, `spec/integrity-protocol-v0.4.md`, `spec/README.md`, `spec/ais-api/v1`, `docs/MAINNET_READINESS.md`, `docs/audits/2026-08-06-cross-repository-status.md`, and `docs/wiki/`.

**Audit checkpoint:** Clean main has broad test evidence but main CI is red on SDK drift; PR #48 is green and unmerged. Base Sepolia deployment, source/role matching, production controls, and automatic-merge authority remain review items.

**Closed:**

- [x] Solidity primitive suite, factory, and per-agent primitive contracts exist.
- [x] Integrity Health, SmartBAA, ComplianceGate, Oracle/AIS, telemetry, BCC, SDK, CLI, user API, and ZKP packages exist.
- [x] Canonical wiki exists and feeds downstream MVP/GitHub wiki projections.
- [x] Protocol spec v0.4 is version-controlled Markdown and supersedes the archived v0.3 PDF.
- [x] Status vocabulary exists: VERIFIED, PARTIAL, PLANNED, BLOCKED, DEPRECATED, REMOVED.

**Planned / todo:**

- [ ] Close `docs/MAINNET_READINESS.md` blockers in consequence order.
- [ ] Enforce agent-only genesis anchoring at the contract level.
- [ ] Implement uniform minimum stake/tier elevation constraints.
- [ ] Generalize Delegation instrument and authority resolution.
- [ ] Apply identity-ceiling clamp consistently in scoring and public reads.
- [ ] Implement lineage attestation, silence-as-signal handling, and required counterparty symmetry.
- [ ] Add versioned BCC intent schema and conformance vectors.
- [ ] Complete evidence-export Phase B/C and report examples.
- [ ] Complete SDK test/implementation reconciliation through PR #48 review; do not merge automatically.
- [ ] Verify Base Sepolia deployment records against chain state, bytecode, roles, ownership, and configuration.
- [ ] Resolve or explicitly preserve the automatic-merge workflow after human-review policy review.
- [ ] Label clean-main, active-branch, and dirty-worktree evidence separately in docs.

**Blocked:**

- [ ] Shield evidence scoring is blocked until Oracle-side mapping is designed.
- [ ] Compliance evidence export polish is blocked until Phase B/C are built.
- [ ] Mainnet launch remains blocked by open readiness items.

## Integrity MVP

**Role:** React/Vite presentation and operator-workflow layer for the Integrity Protocol product stack.

**Specification authority:** `README.md`, `SPECIFICATION.md`, `PRODUCTION_GAPS.md`, `docs/audits/2026-08-06-status.md`, archived historical plans under `docs/archive/2026-08-06/`, INTEGRITY-LATEST interface/wiki docs, and Shield README/spec status.

**Audit checkpoint:** Clean-main production build passed, but `npm audit` reports 4 vulnerabilities, the documented ESLint command is broken, and hosted main E2E fails before tests when the private sibling checkout token is missing.

**Closed:**

- [x] React/Vite/TypeScript shell exists with routes for landing, dashboard, identity, intelligence, health, Shield, financials, memory, settings, legal docs, and wiki.
- [x] Service clients exist for Oracle, user API, and BCC middleware.
- [x] Generated `/wiki` renders the canonical INTEGRITY-LATEST wiki snapshot.
- [x] Wiki renders Markdown tables, Mermaid diagrams, relative links, repo links, article TOC, and ordered protocol TOC.
- [x] Wiki header uses the Xibalba Solutions logo linked to `/`.
- [x] Focused Playwright wiki suite validates current wiki behavior.

**Planned / todo:**

- [ ] Replace remaining static panels with live reads where endpoints exist.
- [ ] Add visible unavailable/error states for backend-dependent panels.
- [ ] Align route labels with current Integrity vocabulary.
- [ ] Surface Shield evidence from stable backend/exporter data.
- [ ] Render graph-memory recall, traversal, provenance, contradiction, forgetting, and verification states.
- [ ] Add broader Playwright coverage for identity, Shield, memory, and financial workflows.
- [ ] Add or declare ESLint, or remove the broken `lint` script.
- [ ] Triage npm vulnerabilities without forced major upgrades.
- [ ] Fix private sibling checkout handling for `INTEGRITY_LATEST_PAT` and archive a real local-stack Playwright run.
- [ ] Verify frontend hosting/release path instead of treating the Vite dev-server Dockerfile as production hosting.

**Blocked:**

- [ ] Live Shield evidence display is blocked until exporter readback/reporting paths are stable.
- [ ] Graph-memory parity is blocked until runtime controller/API contracts are stable.
- [ ] Production automation is blocked until backend availability and env contracts stabilize.

## Xibalba Shield

**Role:** Endpoint security agent for AI-agent discovery, local policy enforcement, guardrail hooks, and Integrity-backed evidence export.

**Specification authority:** `SPECIFICATION.md`, `README.md`, `SECURITY.md`, `docs/audits/2026-08-06-status.md`, `shield/sensors/ebpf/README.md`, and INTEGRITY-LATEST protocol specs.

**Audit checkpoint:** Root-free tests pass at 62 passed and 7 skipped. Process-exec and file-write eBPF verification are historical documented evidence; the audit did not reproduce live eBPF/exporter verification. TCP-connect remains blocked.

**Closed:**

- [x] Event and policy schemas exist.
- [x] Policy engine is table-driven, local/offline, first-match, and tested.
- [x] Agent Core exists: DeviceContext, AgentRegistry, EventRouter, EventLog.
- [x] Integrity Exporter uses real `integrity-sdk` BCC signing and telemetry submission.
- [x] Exporter has historically documented live-stack proof against `bcc_middleware`; current audit did not reproduce the live exporter path.
- [x] Six guardrail hooks exist and are tested.
- [x] CLI supports status, events, validate, and run commands.
- [x] Process-exec and file-write Linux eBPF sensors are live-verified.
- [x] Root-free test suite passes: 62 passed, 7 skipped.

**Planned / todo:**

- [ ] Unblock TCP-connect eBPF verification.
- [ ] Design DNS observation via uprobe or packet parsing.
- [ ] Add config-loadable sensitive-path filtering.
- [ ] Register Shield exporter DID with Integrity Oracle.
- [ ] Verify Shield decisions through the intended evidence/audit surface.
- [ ] Design signed policy bundle format, managed service packaging, and pilot runbooks.
- [ ] Plan Windows ETW, macOS endpoint, and SIEM/SOAR integrations.
- [ ] Reconcile protocol-facing Shield spec status with the observed implementation map.
- [ ] Resolve the specification wording inconsistency between five and six guardrail hooks.
- [ ] Add free GitHub Actions CI and pin the `integrity-sdk` dependency to a reviewed release or commit.

**Blocked:**

- [ ] TCP-connect sensor is blocked by current BCC/kernel version skew.
- [ ] Windows/macOS sensors are blocked until target platforms are available.
- [ ] Tenant cloud policy API is blocked until a real server contract exists.

## Xibalba Graph Memory

**Role:** Local, provenance-aware graph memory MCP server and runtime-controller substrate for Xibalba agent memory.

**Specification authority:** `SPECIFICATION.md`, `spec/xibalba-graph-memory-v1.md`, `README.md`, `docs/audits/2026-08-06-status.md`, archived historical plans under `docs/archive/2026-08-06/`, `docs/architecture/runtime-controller-contract.md`, `docs/architecture/event-hash-chain.md`, and `docs/integrity/xibalba-graph-crypto-profile-v1.md`.

**Audit checkpoint:** The suite passes with `uv sync --extra drive && uv run pytest -q`; plain default test collection fails because Drive tests import optional Google dependencies without the Drive extra. Runtime adapters, controller/session synchronization, tests, and viewer changes are present in the dirty worktree and require separate review.

**Closed:**

- [x] SQLite is specified as the canonical local store.
- [x] Provenance-first memory model is specified.
- [x] Event hash chain, entity/relation graph, contradiction/supersession, and forgetting lifecycle are specified.
- [x] Integrity DAG citation boundary is specified as one-way/read-only.
- [x] Runtime adapter checklist exists for Claude, agy, and Codex.
- [x] Viewer scaffold and tests exist in the current worktree.
- [x] Core package test suite passes when installed with the Drive extra.

**Planned / todo:**

- [ ] Confirm schema version and migrations against the implementation.
- [ ] Finish tests for bootstrap, WAL, FTS5, idempotency, and profile isolation.
- [ ] Finalize lexical recall, optional vector path, bounded traversal, and contradiction visibility.
- [ ] Expose MCP tools for store, recall, link, neighbors, path, contradict, forget, verify, status, and backup.
- [ ] Finalize runtime controller contract and adapter boundaries.
- [ ] Finish viewer integration for recall, graph traversal, provenance, contradiction, forgetting, and verification.
- [ ] Decide whether Drive ingestion dependencies are supported by default, optional test extras, or skipped cleanly when absent.
- [ ] Review and commit or discard runtime adapter, controller, session synchronization, test, and viewer work as a separate change set.
- [ ] Expand README with installation, current status, privacy, retention, backup/restore, profile isolation, and MCP operations.
- [ ] Verify MCP discovery and direct tool calls through an isolated Hermes profile.

**Blocked:**

- [ ] Full runtime parity is blocked by Codex and agy hook-surface limits until wrappers are verified.
- [ ] Integrity DAG anchoring is blocked on consuming the Integrity Memory DAG once available.
- [ ] Viewer production readiness is blocked until API contract stabilizes.

## Cross-repository task list

- [x] Add root `IMPLEMENTATION_PLAN.md` to INTEGRITY-LATEST.
- [x] Add root `SPECIFICATION.md` to INTEGRITY-LATEST.
- [x] Add root `IMPLEMENTATION_PLAN.md` to integrity-mvp.
- [x] Add root `SPECIFICATION.md` to integrity-mvp.
- [x] Add root `IMPLEMENTATION_PLAN.md` to xibalba-shield.
- [x] Update root `SPECIFICATION.md` in xibalba-shield.
- [x] Add root `IMPLEMENTATION_PLAN.md` to xibalba-graph-memory.
- [x] Add root `SPECIFICATION.md` to xibalba-graph-memory.
- [x] Add this canonical wiki rollup page.
- [x] Sync canonical wiki into integrity-mvp after this page is accepted.
- [x] Merge permanent audit docs into implementation plans without duplicate task entries.
- [x] Archive superseded historical plan/handoff files under dated `docs/archive/2026-08-06/` folders.
- [ ] Push each root implementation plan to its owning remote branch.
- [ ] Add CI/documentation checks that fail when WIKI_INDEX page counts drift.

## Update rule

Update the owning repo root `IMPLEMENTATION_PLAN.md` first, then update this wiki page when a closed/planned/blocked status changes, a public interface changes, or a cross-repo dependency changes.
