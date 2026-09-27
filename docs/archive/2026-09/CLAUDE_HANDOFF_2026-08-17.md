# Claude Handoff — Integrity Protocol Phase 0 closure and Phase I entry

Generated: 2026-08-17T11:52:06-05:00
Repository: `/home/xibalba/Projects/integrity-core`
Branch: `audit/harness-loop-2026-07-30` tracking `origin/audit/harness-loop-2026-07-30`
Worktree: intentionally dirty; no commit, push, external deployment, or specification acceptance was performed.

---

**STALE re: Phase I, as of 2026-08-17 (same day, later).** §12's "No Phase I kernel/account/
constraint production code was written... Do not resume Phase I without a new user directive"
is no longer current — the user gave that directive later the same day, and a real Phase I
tracer-bullet slice was subsequently built, tested, and extended four times (budget adapter,
reputation-floor adapter, assurance-tier adapter, then a timelocked kernel-swap module-governance
mechanism). This file is left otherwise unmodified below per the "preserve every existing
change" instruction it itself states, and per this session's own append-only documentation
discipline — read it as a snapshot of Phase 0 closure only, not as current Phase I status.
Current, canonical Phase I state lives in:
- `docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md` and its three follow-on proposal docs
  (`-phase1-reputation-adapter-proposal.md`, `-phase1-assurance-tier-adapter-proposal.md`,
  `-phase1-module-governance-proposal.md`)
- `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` — the precise, currently-accurate
  guarantee statement
- `PRODUCTION_GAPS.md` §29 (search for "Phase I tracer-bullet slice")
- `HANDOFF.md`'s dated sections from 2026-08-17e onward

This file remains untracked and must not be committed.

---

## 1. Executive state

Phase 0 is complete locally. The added criterion to reconcile all living documentation with Whitepaper v3.2 and the proposed specification is also complete locally after two delayed independent audits were fully dispositioned.

Phase I entered architecture discovery only. No Phase I kernel/account/constraint production code was written. A focused Devil's Advocate review completed after the user returned the active goal to Phase 0; its findings are preserved below, and all Phase I execution tasks were cancelled. Do not resume Phase I without a new user directive.

Do not reset, clean, stash, broadly reformat, or overwrite this worktree. Preserve every existing tracked and untracked change, especially the pre-existing untracked ecosystem-adoption plan.

## 2. Authority hierarchy — do not collapse these layers

1. Accepted normative authority: `spec/integrity-protocol-v0.4.md`.
2. Proposed, non-authoritative amendment: `spec/integrity-protocol-v0.5-proposed.md`.
3. Explanatory, non-normative source: `spec/integrity-protocol-v3.2.md`.
4. Generated publication artifact: `spec/Integrity_Protocol_Whitepaper_v3.2.pdf`.

The Whitepaper and v0.5-proposed document contain proposed normative language. They do not amend v0.4 until clause-level acceptance, implementation/interface updates, migration and conformance coverage, and explicit acceptance are recorded.

## 3. Phase 0 implementation delivered

### 3.1 Identity facade

Created:

- `contracts/src/kernel/IntegrityIdentityReadV1.sol`
- `contracts/test/IntegrityIdentityReadV1.t.sol`

`IntegrityIdentityReadV1` is a custom, versioned, read-only Xibalba identity-discovery facade over `XibalbaAgentRegistry`.

Required boundaries:

- `XibalbaAgentRegistry` remains the sole identity source of truth.
- Agent Integrity Score (AIS) remains the sole reputation authority through the existing Oracle/ReputationRegistry path.
- The facade is explicitly not ERC-8004 or ERC-721 conformant.
- `isERC8004Conformant()` returns `false`.
- No token identifier, `ownerOf`, `tokenURI`, transfers, approvals, wallet proofs, metadata writes, reputation feedback, validation, events, or ERC-165 behavior is fabricated.
- Existing agents require no migration.
- Fixed identity resolution is separate from dynamic `profileURI()` access.
- Dynamic profile metadata is descriptive only and must never become execution-authoritative.
- Unknown, malformed, stale, ambiguous, reverting, or inconsistent identity mappings fail closed.
- Forward DID mapping, reverse subject mapping, and the subject's declared DID must agree.
- Controller checks use the subject's live role state rather than a registration-time snapshot.

Focused identity suite last verified: 10 passed, 0 failed.

### 3.2 Deployment wiring

`contracts/script/Deploy.s.sol` now includes `IntegrityIdentityReadV1` for future genesis deployments under:

`singletons.IntegrityIdentityReadV1`

The following incremental deployment-file reserializers preserve the optional singleton rather than dropping it:

- `contracts/script/DeployEHRGate.s.sol`
- `contracts/script/DeployMarkets.s.sol`
- `contracts/script/DeployXnsGovernance.s.sol`
- `contracts/script/FixComplianceGateFactory.s.sol`
- `contracts/script/RotateOperatorKeyGrant.s.sol`

A local script simulation succeeded. No Base Sepolia transaction was broadcast. Any external deployment remains separately approval-gated.

## 4. Whitepaper v3.2 and proposed-spec reconciliation

### 4.1 Proposed specification

Created/expanded `spec/integrity-protocol-v0.5-proposed.md` as a traceable, non-authoritative delta over v0.4. It maps the substantive v3.2 proposal set while marking implementation state as `[PROPOSED]`, `[PARTIAL]`, or `[PLANNED]`.

Mapped proposal areas include:

- Integrity identity interface obligation without false ERC-8004 compatibility;
- AIS evidence admissibility, fail-closed defaults, floors, conjunctive gate, pre-boost constraint input, profile migration, and verified-evidence monotonicity;
- injective memory encoding and typed evidence classes;
- memory availability and supersession;
- complete mediation;
- host-observability limits;
- telemetry-prover decentralization;
- exposure-scaled availability escrow, anti-grief deposit, forced AIS reduction, deterministic redress, and burn;
- hard/soft grace-mode partition, all value movement as hard invariants, typed degradation events, staging limits, and AIS-floor precedence;
- locked-budget state channels, highest mutually signed state, monotone depletion, value conservation, unilateral settlement, and compiler trust;
- per-transaction enclave attestation with explicit side-channel, rollback, and microarchitectural residual risks.

These are not represented as accepted or deployed behavior.

### 4.2 Whitepaper source corrections

`spec/integrity-protocol-v3.2.md` now:

- identifies itself as explanatory and non-normative;
- uses `PROPOSED NORMATIVE CHANGE` rather than `SPEC CHANGE`;
- does not call itself implementer authority;
- marks complete mediation as proposed rather than active authority;
- uses “proposed normative” language for grace-mode and adapter rules;
- distinguishes local source, tested behavior, Base Sepolia deployment, mainnet evidence, planned profiles, and research horizons;
- describes the Phase 0 identity facade as a selected Integrity identity profile, not an ERC-8004 registry;
- does not claim AIS floors solve evidence admissibility or Oracle trust;
- corrects Phase III to §10.3 and the enabler paradigm to §10.4;
- preserves historical v3.1 artifacts as history rather than rewriting them.

### 4.3 Publication builder and artifact

Created `scripts/build_whitepaper_v32.py`.

External pinned assets live outside the repository at:

`/home/xibalba/.cache/integrity-whitepaper-v32`

Pinned package versions:

- Mermaid 11.16.1
- KaTeX 0.16.47

The builder verifies installed package metadata before rendering.

Final generated PDF:

`spec/Integrity_Protocol_Whitepaper_v3.2.pdf`

Final SHA-256:

`d7d3135007f118f174be3a5bcde247198a8fb6f5dbf821c2825fca8508c63552`

Verified publication properties:

- 59 A4 pages;
- unencrypted;
- 13/13 Mermaid diagrams rendered;
- normalized extracted-text assertions passed for authority, proposal markers, identity boundary, and corrected section references;
- visual inspection passed on representative pages 3, 10, 18, 24, 31, 38, 56, and 59;
- no clipping, overlap, browser header, broken glyph, or raw markup was observed.

## 5. Documentation and validation reconciliation

Living documentation was reconciled across public, developer, package, testing, planning, readiness, specification, interface, wiki, and handoff surfaces.

Important corrections:

- Removed the invented dashboard Vitest/component-test layer. The dashboard has no unit/component test script or Vitest dependency.
- Root `make test` and hosted Continuous Integration use `npm run build && npm run lint` for dashboard validation.
- Playwright remains a separate browser layer and requires a separately prepared backend stack; its config starts Vite only.
- Local generated Solidity verifier, real-proof Foundry coverage, Oracle-side `bb verify`, the separate Software Development Kit proof-of-concept circuit, absent runtime on-chain submission, and the older Base Sepolia placeholder verifier are documented as distinct states.
- `scripts/wiki_linter.py` was fixed so canonical `docs/wiki/index.md` can be linked from the legacy catalog without being counted as an article or falsely reported dead.
- Canonical wiki table-of-contents files were regenerated where needed; `docs/wiki/WIKI_LOG.md` was appended, never rewritten.

Final documentation checks before Phase I entry:

- 108 living Markdown files;
- 544 local links;
- 0 missing living links;
- 36 canonical wiki pages;
- 0 wiki orphans;
- 0 dead catalog links;
- Python compilation passed;
- `git diff --check` passed.

The wiki linter still emits age-based staleness advisories for unrelated pages; those are advisory and were not “fixed” by falsifying update dates.

## 6. Contract and package verification evidence

Last full Solidity verification after Phase 0 implementation:

- `forge build`: passed;
- `forge test`: 209 passed, 0 failed, 0 skipped across 23 suites;
- focused identity tests: 10 passed;
- targeted `forge fmt --check` over all changed Solidity files: passed.

Repository-wide formatting may include unrelated legacy drift; targeted formatting of changed Solidity files is the accepted signal.

Dashboard verification:

- `npm run build && npm run lint`: passed;
- 0 errors;
- 56 existing warnings.

No external deployment or live-chain postcondition was claimed.

## 7. Independent review history

### 7.1 Three-lane documentation audit

A delayed three-agent read-only audit surfaced current and stale findings. Every finding was compared against the newer worktree rather than applied blindly. Live findings were corrected in developer/testing guidance, package READMEs, AIS/ZKP wiki status, implementation ledgers, production-gap rollups, Whitepaper wording, and PDF output.

Audit summaries:

- `/home/xibalba/.hermes/cache/delegation/subagent-summary-0-20260817_100540_189903.txt`
- `/home/xibalba/.hermes/cache/delegation/subagent-summary-1-20260817_100540_193312.txt`
- `/home/xibalba/.hermes/cache/delegation/subagent-summary-2-20260817_100540_194857.txt`

### 7.2 Final adversarial Whitepaper/proposal audit

The first closure was correctly rejected because residual authority wording, two section-reference errors, and five load-bearing v0.5 mapping omissions remained. All were corrected and directly asserted in source and generated PDF extraction.

Review summary:

`/home/xibalba/.hermes/cache/delegation/subagent-summary-0-20260817_102600_744742.txt`

Do not restore the older PDF hashes recorded in append-only history. The current hash is the `d7d313...` value above.

## 8. Phase I entry — current state

The user said “let's continue,” so work moved to Phase I discovery after Phase 0 closure.

Authoritative active phase plan:

`/home/xibalba/.claude/plans/where-are-we-with-dapper-gem.md`

That external plan was corrected immediately before this handoff:

- v3.0 authority wording was replaced with the correct v3.2 explanatory/v0.5-proposed boundary;
- the superseded “adopt ERC-8004 as the real identity layer” decision was replaced with the completed custom Phase 0 facade decision;
- the documentation checklist now preserves v0.4 as accepted rather than calling it historical/superseded.

`PRODUCTION_GAPS.md` was also corrected:

- stale Phase III reference §10.2 → §10.3;
- hybrid attestation requirement “transaction/session” → “specific transaction.”

### 8.1 Proposed Phase I scope from the active plan

1. `IntegrityAccount.sol`: new account with no ungated execute path; legacy `SovereignAgent` accounts remain outside the guarantee.
2. `IntegrityKernel.sol`: proposed ERC-7579 type-4 hook using `preCheck`/`postCheck` and projected post-state checks.
3. `ConstraintTypes.sol`: constraint grammar and margin telemetry; value conservation, monotone depletion, replay-domain monotonicity.
4. Timelocked, multi-party kernel removal/module governance.
5. Spend/velocity, reputation-floor, and assurance-tier reference adapters.
6. Canonical intent encoding binding `chain_id` and verifier address.
7. Foundry proposition tests, formal constraint grammar, independent audit, and machine-checked invariance gate.

This scope is architectural and security-sensitive. Do not implement it as accepted v0.4 behavior. Keep proposed v0.5 interfaces explicitly planned until accepted.

### 8.2 Dependency/source inventory observed so far

- No Phase I account or kernel source exists yet under `contracts/src/kernel/`; only `IntegrityIdentityReadV1.sol` exists.
- No repository-authored ERC-7579 implementation was found.
- Installed OpenZeppelin package paths include:
  - `node_modules/@openzeppelin/contracts/account/extensions/draft-AccountERC7579.sol`
  - `node_modules/@openzeppelin/contracts/account/extensions/draft-AccountERC7579Hooked.sol`
  - corresponding upgradeable draft account files.
- `contracts/package.json` declares `@openzeppelin/contracts` `^5.3.0` and `@openzeppelin/contracts-upgradeable` `^5.6.1`; inspect the lockfile/installed exact versions before pinning an interface.
- `XibalbaAgentRegistry.PrimitiveSet.sovereignAgent` is the canonical downstream subject address and `registerPrimitives` is factory/registrar-gated.
- `ReputationRegistry.effectiveScore(agent)` is post-boost; `isZkBoosted(agent)` reports current boost state. Phase I must not invent a second reputation authority.
- `IntegrityGovernance` provides an existing token-weighted timelocked single-call pattern, but reusing it for module removal requires explicit deadlock, bypass, guardian, and complete-mediation review.

## 9. Completed Phase I Devil's Advocate review — preserved, not authorized for implementation

Hermes delegation ID:

`deleg_f07f2fd0`

Live transcript:

`/home/xibalba/.hermes/cache/delegation/live/deleg_f07f2fd0/task-0.log`

Complete summary:

`/home/xibalba/.hermes/cache/delegation/subagent-summary-0-20260817_115552_536069.txt`

The review found the architecture defensible only under a much narrower claim: an ERC-7579 hook can preserve explicitly enumerated post-state predicates over a deliberately restricted execution grammar; it cannot generally compute or prove arbitrary EVM projected post-state.

Principal blockers and required mitigations:

- OpenZeppelin 5.6.1 supplies draft account/hook foundations, not a turnkey account. The manifest range, lockfile version, EntryPoint version, validator/signature model, and draft Application Binary Interface must be pinned and characterized.
- EntryPoint prefunding, passive ingress, forced Ether, nonce state, and validator-side state changes are outside the type-4 execution hook; any guarantee must enumerate its exact mediated transition set.
- Delegatecall must be disabled initially because it can mutate account, hook, authorization, and module storage.
- Batch and `EXECTYPE_TRY` must be disabled initially because one aggregate hook frame does not expose per-subcall results or preserve simple spend/nonce semantics.
- Executor modules, fallback modules, recursive self-calls, post-bootstrap module mutation, and upgrades must default-deny in the first profile.
- The initial kernel must be installed atomically and pinned independently of the mutable hook slot.
- Pre-check may enforce only typed projections; post-check may verify only enumerable postconditions. Generic value conservation is invalid until each asset profile defines a closed accounting universe.
- Existing `IntegrityGovernance` cannot directly call the account's EntryPoint-or-self-only module mutation functions; recovery/removal needs a dedicated, reviewed state machine rather than superficial timelock reuse.
- `AgentPrimitivesFactory` and `IntegrityIdentityReadV1` currently assume the `SovereignAgent` AccessControl/`agentDID()` interface. A future account needs a versioned identity/controller interface and one controller truth, not dummy compatibility state.
- AIS adapters must not use current post-boost `effectiveScore()` as the proposed pre-boost input. A versioned, clamped, fresh, profile-bound accessor and constrained verifier/anchor/reporting-period administration are prerequisites.
- Hook frames must authenticate the account and correlate account, execution depth, action digest, pre-state digest, configuration epoch, nonce, and one-shot consumption; shared “latest snapshot” state is unsafe.
- Canonical intent must bind account, kernel/profile, chain, exact action/mode/calldata, configuration epoch, verifier semantics, nonce namespace, deadline, and authorization context. The current process-local nonce is not an on-chain replay barrier.
- Adapter arrays, returndata, revert data, callbacks, storage growth, and gas reserved for post-check require explicit bounds. Reverted rejection events are not durable diagnostics.
- The first account and kernel should be non-upgradeable.

Recommended eventual tracer slice, only if separately authorized: a non-deployable, non-upgradeable experimental account using an exactly pinned hooked-account/EntryPoint profile, atomic immutable kernel binding, single default `CALL` only, authenticated one-shot hook frames, no prefund, and one conservative native-value per-operation/cumulative budget. All other modes and adapters remain disabled. Implement with strict RED→GREEN test-driven development and do not call that slice Phase I complete.

## 10. Required next steps for Claude if the user later authorizes Phase I

1. Read repository guidance: `CLAUDE.md`, `.agents/AGENTS.md`, current `HANDOFF.md`, this file, and the external active plan.
2. Preserve the dirty worktree and inspect diffs before editing.
3. Read and reconcile the completed Devil's Advocate review. Record required mitigations and revise the Phase I plan/interface contract before code.
4. Complete dependency inventory:
   - exact installed OpenZeppelin versions from lockfiles;
   - exact ERC-7579 draft interfaces and account hook call flow;
   - supported execution modes, fallback, batches, module installation/removal, and hook lifecycle;
   - factory/registry registration assumptions.
5. Define one vertical tracer-bullet slice using strict test-driven development:
   - write one failing Foundry test first;
   - run it and confirm expected failure;
   - implement the smallest behavior that passes;
   - run focused and full suites;
   - do not write a horizontal pile of tests or production stubs.
6. Update `docs/INTERFACE_CONTRACT.md`, `PRODUCTION_GAPS.md`, canonical wiki, and handoff alongside any accepted local interface change.
7. Do not deploy, broadcast, publish, commit, push, accept v0.5, or mutate external systems without separate explicit approval.

## 11. Current task state

- Phase 0 and its added documentation criterion: complete locally.
- Phase I boundary-document correction: complete.
- Phase I Devil's Advocate review: complete and preserved above.
- OpenZeppelin and existing-interface inventory: partial; execution task cancelled when the active goal returned to Phase 0.
- Smallest safe Phase I slice: review recommendation preserved, not selected or authorized for implementation.
- Phase I implementation: not started; task cancelled.

## 12. Changed tracked paths in integrity-core

- `.agents/AGENTS.md`
- `.github/workflows/ci.yml`
- `CLAUDE.md`
- `HANDOFF.md`
- `IMPLEMENTATION_PLAN.md`
- `Makefile`
- `PRODUCTION_GAPS.md`
- `README.md`
- `SPECIFICATION.md`
- `contracts/README.md`
- `contracts/script/Deploy.s.sol`
- `contracts/script/DeployEHRGate.s.sol`
- `contracts/script/DeployMarkets.s.sol`
- `contracts/script/DeployXnsGovernance.s.sol`
- `contracts/script/FixComplianceGateFactory.s.sol`
- `contracts/script/RotateOperatorKeyGrant.s.sol`
- `docs/CONTRIBUTOR_VALIDATION.md`
- `docs/INTERFACE_CONTRACT.md`
- `docs/MAINNET_READINESS.md`
- `docs/TESTING.md`
- `docs/guides/smart-contract-development.md`
- `docs/plans/2026-08-17-whitepaper-spec-reconciliation.md`
- `docs/wiki/WIKI_INDEX.md`
- `docs/wiki/WIKI_LOG.md`
- `docs/wiki/architecture/ecosystem-dependencies.md`
- `docs/wiki/architecture/repository-implementation-plans.md`
- `docs/wiki/concepts/ais.md`
- `docs/wiki/concepts/integrity-specification.md`
- `docs/wiki/concepts/testing-strategy.md`
- `docs/wiki/concepts/zkp.md`
- `docs/wiki/entities/contracts.md`
- `docs/wiki/index.md`
- `integrity-dashboard/PRODUCTION_GAPS.md`
- `integrity-oracle/README.md`
- `scripts/wiki_linter.py`
- `spec/Integrity_Protocol_Whitepaper_v3.2.pdf`
- `spec/README.md`
- `spec/integrity-protocol-v0.4.md`
- `spec/integrity-protocol-v0.5-proposed.md`
- `spec/integrity-protocol-v3.2.md`

## 13. Untracked paths to preserve

- `contracts/src/kernel/IntegrityIdentityReadV1.sol`
- `contracts/test/IntegrityIdentityReadV1.t.sol`
- `docs/plans/2026-08-17-ecosystem-adoption-strategy.md` — pre-existing user plan; preserve.
- `scripts/build_whitepaper_v32.py`
- `CLAUDE_HANDOFF_2026-08-17.md` — this handoff.

## 14. External modified file

The active plan outside the repository was modified and must also be preserved:

`/home/xibalba/.claude/plans/where-are-we-with-dapper-gem.md`

## 15. Safety and claim boundaries

- No Base Sepolia mutation occurred.
- No external transaction was broadcast.
- No specification proposal was accepted.
- No commit or push was performed.
- No credential value belongs in this handoff; any credential seen in prior command context remains `[REDACTED]`.
- A hash, signature, Merkle proof, or generated PDF checksum proves only the bounded property verified; it does not prove truth, authorization, deployment, or completeness.
