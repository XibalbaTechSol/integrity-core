# Integrity MVP Implementation Plan

**Updated:** 2026-08-06
**Repository:** integrity-mvp
**Role:** React/Vite presentation and operator-workflow layer for the Integrity Protocol product stack.

This document merges the repo README, SPECIFICATION.md, PRODUCTION_GAPS.md, docs/audits/2026-08-06-status.md, archived product plans, current wiki work, and cross-repo specifications into one implementation task ledger. Each capability is marked Closed, Planned, Blocked, or Todo.

## Specification Authority

| Source | Authority |
|---|---|
| README.md | Repo source of truth, app boundaries, current status, commands. |
| SPECIFICATION.md | Current UI/product behavior specification. |
| docs/archive/2026-08-06/integrity_mvp_plan.md | Historical product/architecture blueprint. |
| docs/archive/2026-08-06/landing_page_strategy.md | Historical landing narrative and conversion flow. |
| PRODUCTION_GAPS.md | Production-readiness gap register and historical/stale claim register. |
| docs/audits/2026-08-06-status.md | Current audit evidence, CI/E2E findings, and production posture. |
| INTEGRITY-LATEST docs/INTERFACE_CONTRACT.md | Backend ports, schemas, chain conventions, env boundaries. |
| INTEGRITY-LATEST docs/wiki/ | Canonical wiki content rendered by this app. |
| xibalba-shield README.md and SPECIFICATION.md | Shield implementation status displayed by this app. |

## Audit checkpoint — 2026-08-06

Current observed status is [`docs/audits/2026-08-06-status.md`](docs/audits/2026-08-06-status.md). The TypeScript build and 68 dashboard unit tests passed; `npm audit` reports 4 vulnerabilities (1 moderate, 3 high), and `npm run lint` cannot run because ESLint is absent. Main E2E run [31085241115](https://github.com/XibalbaTechSol/integrity-mvp/actions/runs/31085241115) fails before tests because the private sibling checkout receives no token. `[x]` means the scoped repository artifact exists, not that live backend, chain, or production behavior has been independently verified.

## Closed

- [x] React/Vite/TypeScript application shell exists.
- [x] Routes exist for landing, dashboard, identity, intelligence, health, Shield, financials, memory, settings, docs/privacy/terms, and wiki.
- [x] Service clients exist for INTEGRITY-LATEST Oracle, user API, and BCC middleware.
- [x] Generated /wiki route renders the canonical INTEGRITY-LATEST wiki snapshot.
- [x] Wiki renders Markdown tables, Mermaid diagrams, relative wiki links, repository links, article TOC, and ordered Protocol TOC.
- [x] Wiki header uses Xibalba Solutions logo linked to /.
- [x] Focused Playwright wiki suite validates table rendering, TOC behavior, logo navigation, and mobile search placement.
- [x] Memory graph UI/service surface exists for xibalba graph memory integration.
- [x] Source-of-truth README documents repo role, stack boundaries, current status, commands, and docs map.

## Planned And Todo

### Backend Truth Integration

- [ ] Replace remaining static/demonstration panels with explicit live-service reads where INTEGRITY-LATEST endpoints exist.
- [ ] Add visible unavailable/error states for every backend-dependent panel.
- [ ] Align all route labels with current INTEGRITY-LATEST vocabulary: Integrity Health, Shield, AIS, BCC, XNS, Governance, Markets.
- [ ] Add environment validation for Oracle, User API, BCC middleware, graph memory, and Shield evidence endpoints.

### Shield Presentation

- [ ] Surface Shield evidence from INTEGRITY-LATEST telemetry/BCC results, not invented local mock data.
- [ ] Add Shield status panels keyed to Shield spec statuses: verified process/file sensors, blocked TCP sensor, planned DNS/Windows/macOS.
- [ ] Add operator copy that distinguishes Shield local logs from Integrity-anchored evidence.
- [ ] Add E2E coverage for Shield route once the backend evidence contract is stable.

### Graph Memory Presentation

- [ ] Confirm graph-memory service endpoint and runtime adapter contract.
- [ ] Render recall, graph traversal, provenance, contradiction, forgetting, and verification states.
- [ ] Display untrusted-memory warnings where retrieved memories can be confused with instructions.
- [ ] Add E2E coverage for memory view with a controlled fixture server.

### Wiki And Documentation

- [ ] Keep npm run sync-wiki deterministic against INTEGRITY-LATEST docs/wiki.
- [ ] Add a regression for the new implementation-plan wiki page after sync.
- [ ] Keep root IMPLEMENTATION_PLAN.md aligned with README and route-level behavior.
- [ ] Publish wiki updates after canonical wiki changes are merged.

### Audit Reconciliation And CI

- [ ] Add or declare ESLint, or remove the broken `lint` script so the documented lint command is truthful.
- [ ] Triage the 4 reported npm vulnerabilities without blindly applying forced major upgrades.
- [ ] Fix private sibling checkout handling for `INTEGRITY_LATEST_PAT` and ensure the E2E failure handler tolerates a missing checkout directory.
- [ ] Complete and archive the real Playwright suite against a booted local stack.
- [ ] Verify frontend hosting/release path; the current Dockerfile starts a Vite development server, not a production bundle server.
- [ ] Mark Zero-Knowledge, Trusted Execution Environment, healthcare interoperability, financial-market, and Shield claims with direct evidence or `[PLANNED]`/`[UNVERIFIED]`.
- [ ] Review E2E workflow permissions and private-repository credential exposure.

### Production Readiness

- [ ] Reduce large Vite chunks where it improves perceived load.
- [ ] Add broader Playwright coverage for identity, Shield, memory, and financial workflows.
- [ ] Define deployment target, env-var contract, and release checklist.
- [ ] Add operational smoke tests against a live local stack.

## Blocked

- [ ] Full live Shield evidence display is blocked until Shield exports with a registered DID and INTEGRITY-LATEST exposes stable readback/reporting paths.
- [ ] Full graph-memory parity is blocked until the runtime controller/adapter contract is finalized and service endpoint is stable.
- [ ] Production deployment automation is blocked until backend service availability and environment contracts are stable.

- [ ] Hosted main E2E is blocked until private sibling repository access is configured and the failure path no longer assumes the checkout exists.

## Acceptance Criteria

- [ ] Every visible trust/security claim is backed by INTEGRITY-LATEST, Shield, or graph-memory data with a documented source.
- [ ] All backend outages show explicit degraded states.
- [ ] Wiki, Shield, memory, identity, and financial routes have targeted Playwright coverage.
- [ ] /wiki is generated from canonical docs and has no direct authoring drift.
- [ ] The app can be built from a clean checkout and configured from documented environment variables.

## Update Rule

Update this file whenever a route becomes real, a mock is removed, a backend contract changes, or a planned route moves to verified behavior.
