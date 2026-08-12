# integrity-core Implementation Plan

**Updated:** 2026-08-06
**Repository:** integrity-core
**Role:** Protocol trust backend: contracts, SDK, CLI, BCC middleware, Oracle/AIS, user API, dashboard, ZKP, canonical wiki, and protocol specs.

This plan merges README.md, SPECIFICATION.md, PRODUCTION_GAPS.md, docs/INTERFACE_CONTRACT.md, spec/README.md, spec/integrity-protocol-v0.4.md, spec/xibalba-shield-v1.md, docs/MAINNET_READINESS.md, docs/ENTERPRISE_ADOPTION.md, docs/audits/2026-08-06-cross-repository-status.md, package READMEs, and the canonical wiki into one implementation task ledger.

## Specification Authority

| Source | Authority |
|---|---|
| README.md | Repo-wide source of truth and package status. |
| SPECIFICATION.md | Repository-level system specification and ownership boundary. |
| docs/INTERFACE_CONTRACT.md | Internal package schemas, ports, environment, and coordination rules. |
| spec/integrity-protocol-v0.4.md | Normative protocol design specification. |
| spec/README.md and spec/ais-api/v1 | Externally-supported versioned wire surfaces. |
| docs/MAINNET_READINESS.md | Consequence-ordered mainnet blockers. |
| PRODUCTION_GAPS.md | Production-readiness gap register and risk-control backlog. |
| docs/audits/2026-08-06-cross-repository-status.md | Current audit evidence, CI/deployment findings, and production posture. |
| docs/wiki/ | Canonical wiki memory and downstream source for MVP/GitHub wiki. |

## Audit checkpoint — 2026-08-06

Current observed status is [`docs/audits/2026-08-06-cross-repository-status.md`](docs/audits/2026-08-06-cross-repository-status.md). The clean default-branch audit confirms broad tested prototype capability, but main CI is red on SDK test/implementation drift ([run 31087969036](https://github.com/XibalbaTechSol/integrity-core/actions/runs/31087969036)); PR #48 is green but unmerged. Deployment, identity, role, bytecode, production-control, and automatic-merge claims remain open review items. This plan's `[x]` entries mean the artifact exists or the scoped behavior was locally verified; they do not mean production readiness.

## Closed

- [x] Core Solidity primitive suite exists and is tested.
- [x] Agent factory and per-agent primitive contracts exist.
- [x] Integrity Health/SmartBAA/ComplianceGate stack exists as healthcare vertical proof.
- [x] Integrity Oracle computes AIS and serves protocol read APIs.
- [x] Telemetry ingestion includes signed telemetry path and unauthenticated OTel path with explicit evidentiary separation.
- [x] BCC middleware provides pre-execution policy gate, OPA integration, commitment handling, and Merkle batching path.
- [x] integrity-sdk supports registration, BCC, telemetry, markets, local metrology, and PHI redaction pathways.
- [x] integrity-cli provides developer-facing workflows including real on-chain registration flows.
- [x] integrity-userapi owns user accounts/auth and remains non-chain.
- [x] integrity-zkp contains real Noir/Barretenberg proving pipeline.
- [x] Canonical docs/wiki exists and feeds downstream MVP/GitHub wiki projections.
- [x] Protocol spec v0.4 is version-controlled Markdown and supersedes archived v0.3 PDF.
- [x] Spec conformance vocabulary exists: VERIFIED, PARTIAL, PLANNED, BLOCKED, DEPRECATED, REMOVED.

## Planned And Todo

### Protocol Correctness And Mainnet Readiness

- [ ] Close docs/MAINNET_READINESS.md blockers in consequence order.
- [ ] Enforce agent-only genesis anchoring at the contract level for epoch-1 memory roots.
- [ ] Implement uniform minimum stake/tier elevation constraints.
- [ ] Generalize Delegation instrument and chain-side/gate-side authority resolution.
- [ ] Apply identity-ceiling clamp consistently in scoring and public reads.
- [ ] Implement lineage attestation and on-chain record.
- [ ] Add silence-as-signal handling for observability obligations.
- [ ] Add counterparty symmetry to BCC where required by spec roadmap.
- [ ] Add optional ERC-8004 registration adapter when discovery scope is ready.

### Wire Surfaces And External Contracts

- [ ] Create versioned BCC intent schema under spec/bcc/v1.
- [ ] Keep AIS API generated from source and changeloged for wire-visible changes.
- [ ] Add conformance vectors for every externally-supported wire surface.
- [ ] Document deprecation windows for any v2 migration.

### Evidence And Compliance Exports

- [ ] Complete evidence-export Phase B/C: control mapping and export endpoint.
- [ ] Add Shield security evidence to evidence export only after Oracle consumes Shield evidence intentionally.
- [ ] Keep Integrity Health reports distinct from Shield endpoint evidence while sharing protocol proofs.
- [ ] Add report examples that join BCC decision, anchor event, AIS context, policy version, and verification token.

### Audit Reconciliation And Production Controls

- [ ] Complete SDK test/implementation reconciliation through PR #48 review; do not merge automatically.
- [ ] Re-run aggregate `make test` after SDK remediation because the clean-main audit timed out during SDK tests.
- [ ] Verify Base Sepolia deployment records directly against chain state, bytecode, roles, ownership, and configuration.
- [ ] Resolve or explicitly preserve `.github/workflows/auto-merge-jules.yml` after human-review/no-automatic-merge policy review.
- [ ] Audit generated ABI/API/schema artifacts for source drift.
- [ ] Verify CI workflow action pins, permissions, secrets, and recent run outcomes.
- [ ] Label clean-main, active-branch, and dirty-worktree evidence separately in README, PRODUCTION_GAPS, specs, and wiki.

### Shield And MVP Boundaries

- [ ] Keep spec/xibalba-shield-v1.md as protocol-facing boundary only.
- [ ] Do not import or depend on xibalba-shield or integrity-mvp from integrity-core.
- [ ] Expose only public SDK/API/contract surfaces consumed by those repos.
- [ ] Keep ecosystem-dependencies wiki page aligned with repo READMEs.

### Wiki And Documentation

- [ ] Keep WIKI_INDEX counts and categories current.
- [ ] Run wiki lint/TOC tooling after canonical wiki page changes.
- [ ] Sync canonical wiki into integrity-mvp and GitHub Wiki after documentation changes.
- [ ] Keep package READMEs aligned with interface contract and spec status.

## Blocked

- [ ] Full Shield evidence scoring is blocked until Oracle-side mapping is designed and implemented.
- [ ] Compliance evidence export polish remains blocked until docs/design/evidence-export.md Phase B/C are built.
- [ ] Mainnet launch remains blocked by docs/MAINNET_READINESS.md open items.

- [ ] Production certification is blocked until CI, deployment/source matching, identity/authorization review, rollback, monitoring, secret handling, replay/origin controls, and normative-gap review are complete.

## Acceptance Criteria

- [ ] Mainnet readiness blockers are closed or explicitly deferred with risk sign-off.
- [ ] Every public wire surface has generated schema and tests.
- [ ] Protocol spec, interface contract, README, and wiki agree on status vocabulary.
- [ ] MVP and Shield consume only public interfaces.
- [ ] Canonical wiki validates and downstream wiki projections are regenerated.
- [ ] Operational runbooks exist for deploy, rollback, evidence export, and incident diagnosis.

## Update Rule

Update this file whenever a package status, protocol spec status, mainnet blocker, public wire surface, or cross-repo dependency changes.
