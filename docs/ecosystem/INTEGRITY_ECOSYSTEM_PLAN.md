# Plan: The Xibalba Ecosystem, Balanced and Monetizable

**Scope:** integrity-kernel · Shield · Cortex
**Execution:** one continuous, gated run
**Objective:** leave the ecosystem with a simpler architecture, one coherent planning and documentation system, and two independently deployable and monetizable SaaS products—Shield and Cortex—that depend on a small, stable Integrity trust substrate. Optional Jev annotations may enrich observable decision provenance, but they are not part of the enforcement authority or minimum SaaS product.

## Context and governing principle

The ecosystem spans four active repositories, roughly 60k lines of code, roughly 48k lines of documentation, and several partially implemented architectures. The active repositories are integrity-core, xibalba-cortex, xibalba-shield, and integrity-console. This plan preserves the owner's fixed decisions, removes contradictory commitments, and orders work by customer value first, SaaS readiness second, and protocol hardening third.

Judge every component by the job it does, not by who calls it today. The six jobs are identity, rules, enforcement, evidence, feedback, and access. Integrity is essential to trust-bearing artifacts, but it must not become a runtime or availability bottleneck for Shield or Cortex.

## Desired outcomes

The plan is successful only if these outcomes are true:

1. **Simplified architecture:** one clear authority for identity, packs, receipts, verification, anchoring, and AIS; no duplicate kernel, adapter, policy, memory, or canonicalization authorities.
2. **Consolidated documentation:** one authoritative execution plan plus a small set of authoritative domain documents; superseded plans, audits, and exploratory material are archived in integrity-lab.
3. **Monetizable Shield:** a tenant-isolated SaaS product for policy enforcement, device control, compliance evidence, and exports.
4. **Monetizable Cortex:** a tenant-isolated SaaS product for governed memory/content, provenance, retention, retrieval, and evidence.
5. **Integrity dependency without runtime lock-in:** Shield and Cortex produce Integrity-compatible artifacts and continue operating locally when anchoring, Oracle, or vendor services are unavailable.
6. **Safe extensibility:** third parties can build deterministic off-chain adapters and packs against documented SDK contracts without gaining authority over the kernel, receipts, or anchors.
7. **Honest readiness boundary:** local pilots, external integrations, real-funds readiness, and real-PHI readiness are reported as separate evidence classes.
8. **Optional annotation provenance:** if the Jev extension is enabled, Hermes, Shield, and Cortex can correlate observable events and advisory annotations without claiming hidden chain-of-thought access, calibrated probability, or causal proof. This extension cannot block the core SaaS outcome.

Every phase and gate below exists to prove one or more of these outcomes. Work that does not advance an outcome is deferred.

## Product boundary

~~~text
CUSTOMER BOUNDARY                         DECISION / TRUST LAYER

harness + agent.did.json                    Jev decision gateway
        │                                   observable annotations only
        ├── Shield: on-device gate ──┐                │
        │                            ├── DecisionTrace ── signed receipts
        └── Cortex: memory/content ──┘                ├── Merkle roots/proofs
                                                     ├── StateAnchor roots
                                                     ├── AIS feedback
                                                     └── console / exports
~~~

- Shield is the on-device enforcement product.
- Cortex is the memory, content, and provenance product.
- integrity-kernel is the trust substrate and on-chain value-enforcement product.
- integrity-console is the operator UI and user-facing API.
- integrity-lab is the frozen mirror for removed, historical, and deferred code.
- the optional Jev decision plane classifies, scores, and annotates observable state; it never replaces product policy, identity, OPA/BCC authorization, or Integrity verification.

Shield, Cortex, and the console remain independent products with separate routes, ownership, and workflows.

## Commercial architecture

Integrity is a dependency, not a merged product console:

```text
Integrity SDK/contracts
  identity · packs · receipts · decision traces · verification · anchoring · AIS

        stable contracts, not a runtime choke point

Shield SaaS                              Cortex SaaS
policy enforcement                       memory and content
device control                           provenance and retention
compliance evidence                      retrieval proofs
cost/risk analysis                       decision graph and telemetry
exports                                  compliance review
```

Shield and Cortex may be sold, deployed, and operated independently, but every trust-bearing artifact they produce must be Integrity-compatible.

- Shield's promise: enforce AI-agent policies at the customer boundary and produce independently verifiable evidence through Integrity.
- Cortex's promise: provide governed agent memory and content provenance with Integrity-backed identity, receipts, retention, and retrieval evidence.
- Integrity's promise: make Shield and Cortex evidence portable, verifiable, and resistant to unilateral rewriting.

Runtime rules:

- Shield continues enforcing locally if public-chain, Oracle, or hosted Integrity services are unavailable.
- Cortex continues storing and retrieving locally if anchoring is unavailable.
- Receipts may queue for later anchoring.
- Public-chain anchoring and vendor integrations are evidence enhancements, not SaaS availability dependencies.
- Tenant data and customer content remain within the declared Shield/Cortex boundary.

## Fixed owner decisions

### Repositories

- Rename integrity-core to integrity-kernel during Phase C5.
- Rename dashboard plus user API to integrity-console during Phase C5.
- Cut removed and historical code into integrity-lab, a frozen mirror.
- Until C5, new code must use repository-neutral package names and must not add new load-bearing references to integrity-core.

### Keep

- Health, XNS, integrity-cli, BCC, OPA, and AIS as the feedback loop.
- The Hermes observer seam remains available for a later optional DecisionTrace extension.
- Kernel-only agent accounts.
- Bridge code in the SDK.
- DID files for agent identity.
- Persistent memory and agent-owned contracts as registration requirements.
- Shield and Cortex as independently monetizable products.

### Cut or defer

- ZK tooling, markets, licence, CCIP, governance, and the on-chain adapter registry.
- Session keys, staking, paymasters, tokens, signing daemon, formal SMT analysis, and unbounded new harness hooks.
- Billing code.
- A deploy factory in v1. Accounts are deployed directly from the canonical IntegrityAccount implementation.

## Six-function test

| Function | Implemented by |
|---|---|
| Identity | DID file, IntegrityAccount, registry, XNS |
| Rules | Signed packs and deterministic adapters |
| Enforcement | Shield/BCC off-chain; kernel on-chain |
| Evidence | Signed receipts, optional trace roots, StateAnchor roots, offline verify |
| Feedback | AIS |
| Access | SDK, CLI, hooks |

Anything new must name the function it advances and the gate it satisfies.

## Shared SDK contracts

The SDK defines these contracts once:

- **C1 Canonical bytes:** JCS is the sole canonicalization method.
- **C2 Identity:** the agent DID file is separate from the device key and agent signing key.
- **C3 Pack:** a signed bundle covers every file, including Rego, and contains one decision contract. permit means permitted. Missing, malformed, unknown, or incompatible decisions deny.
- **C4 Receipt:** a signed, chained decision record with HMAC-protected identifiers and anchor references.
- **C5 Hook:** runner to local Shield gate if present, otherwise BCC.
- **C6 Memory provider:** genesis, append-only provenance metadata, encrypted content, and nonce-based spot-checks.
- **C7 Data boundary:** customer content remains inside the customer environment unless explicitly classified as permitted metadata.
The following are optional annotation extensions, versioned separately from the core contracts:

- **C8 DecisionEnvelope:** a typed Jev annotation records provider/model, rubric, result, probability/confidence, usage, latency, redaction status, and the observable event it annotates. It is a signal, never an authorization. A probability is reported as provider output, not as a calibrated truth claim.
- **C9 DecisionTrace:** an append-only, parent-linked sequence of observable events covering LLM/API calls, Jev decisions, proposed actions, policy results, executions, approvals, outcomes, and memory effects. Edges are typed as observed or declared dependencies; none is represented as proven causality.
- **C10 Trace Merkle domain:** DecisionTrace leaves use a versioned, domain-separated Integrity Merkle convention and reuse SDK JCS, hash, proof, receipt, offline-verification, and queued-anchoring primitives. Trace roots are separate from provider-telemetry and memory roots.
- **C11 Provider boundary:** `JevDecisionGateway` may call hosted Jev, a Jev-compatible local model, or deterministic fixtures. Provider identity and execution mode are recorded. Thresholds and final actions remain in Shield, Cortex, or Hermes policy code. No provider is required by Gate A or Gate B-local.

If the optional annotation extension is enabled, the Shield provider boundary is tenant-configurable in the dedicated Settings surface:
`disabled`, deterministic `jev`, `local_classifier`, Lila-compatible JSON, and
OpenAI-compatible `llm`. Endpoint, model, prompt-profile, timeout, token, temperature, event-class,
failure-mode, and non-secret secret-reference settings are validated server-side. Remote keys stay
host-managed; non-loopback HTTP endpoints require HTTPS. All providers remain advisory and run only
after deterministic Shield policy evaluation.

## Third-party adapter readiness

Adapters remain deterministic, off-chain, and outside the kernel. The SDK exposes a versioned adapter contract and conformance kit so third parties can add regulation and control packs without creating a second authority.

The plan distinguishes two extension types:

- **Pack adapters:** pure deterministic transformations from declared inputs to regulation/control rules. They have no arbitrary network, filesystem, credential, or execution authority.
- **Connectors:** authenticated integrations with external systems. Connectors are not pack adapters; they use a separate API, declared egress policy, bounded credentials, and redacted input/output records.

An adapter must provide:

- signed metadata and a content hash;
- supported SDK, pack, and schema versions;
- deterministic input/output behavior;
- control citations and decision vectors;
- declared capabilities and data requirements;
- provenance included in compiled packs and receipts;
- sandbox-compatible execution with no arbitrary network or filesystem authority.

Neither pack adapters nor connectors can override deny, sign receipts, anchor evidence, change kernel parameters outside the pack contract, or bypass tenant boundaries. There is no on-chain adapter registry in v1.

## Authority map

| Claim | Authority |
|---|---|
| Whether an action is allowed | Shield/BCC policy receipt |
| Whether a receipt is signed and chained | SDK receipt verifier |
| Whether an optional trace event was observed | Signed DecisionTrace event, if enabled |
| Whether content was stored | Cortex content/provenance store |
| Whether memory was available at spot-check time | Cortex retrieval proof |
| Whether a root was anchored | StateAnchor |
| Authoritative AIS | Oracle/scoring-core; local AIS is self-reported feedback |
| What Jev recommended | Jev annotation only; never policy authority |

## Trust, receipt, and memory models

The organization holds guardian, HMAC, and encryption keys and funds gas. The registrar/oracle can censor or move AIS but cannot impersonate an agent account. Anchors store roots and signed checkpoints, not raw records or PHI. The kernel mediates value inside the account; value leaving it counts as spent. Agent keys at mode 0600 are readable by a same-user process. Shield protects key paths on managed devices; a signing daemon is deferred.

The gate or device key signs each receipt. HMAC keys protect identifiers and sensitive correlation fields; HMAC is not the sole authenticity mechanism. Each receipt signs at least:

~~~text
receipt_version
agent_did_hash
device_id_hmac
action_hmac
pack_hash
decision
reason_code
seq
prev_hash
timestamp
checkpoint_reference
~~~

Offline verify proves signature validity, chain position, inclusion, and anchoring. It does not recover HMAC-protected identifiers without the organization's key. Device signing keys are scoped, rotatable, and revocable independently of agent identity keys.

Cortex separates immutable provenance metadata from encrypted content:

- The provenance log is append-only and may retain event IDs, timestamps, pack hashes, receipt references, and content commitments.
- Content, FTS indexes, blobs, derived embeddings, and encryption keys are purgeable.
- A spot-check proves that the provider can currently retrieve requested content and return H(nonce||content) with a valid proof.
- Purging destroys content and required decryption material and removes searchable and replicated copies within the declared retention boundary.
- Historical roots may remain as non-content evidence but must not permit PHI reconstruction.

### Jev decision and trace model

Jev is the decision plane for bounded, observable judgments. It is not the trust plane, policy engine, action executor, identity resolver, or causal explainer.

The first implementation is a local `JevDecisionGateway` called by Hermes observer and action-boundary code. It receives the minimum redacted state required for a narrow Choice, Score, or Noul question and returns a `DecisionEnvelope`. The gateway records provider, model, rubric version, input/output hashes, probabilities, confidence where supported, usage, latency, timeout/retry status, and fallback mode. API credentials remain server-side.

The observable trace is:

~~~text
Hermes event
  -> LLM/API invocation
  -> Jev annotation
  -> proposed tool/action
  -> OPA/BCC/Shield policy result
  -> execution or review
  -> outcome
  -> Cortex memory/provenance effect
~~~

Each trace event is JCS-canonicalized, signed when it is trust-bearing, linked to its declared parent, and committed to a domain-separated Merkle leaf. A session or tenant root may be queued for later anchoring. Leaf proofs establish integrity and inclusion; parent links establish declared sequence; neither proves hidden reasoning, truth, or causality.

Trace event classes are `llm_call`, `jev_assessment`, `action_proposal`, `policy_decision`, `approval`, `tool_execution`, `outcome`, `memory_effect`, and `anchor_checkpoint`. The minimum correlation fields are `trace_id`, `session_id`, `turn_id`, `invocation_id`, `tool_call_id`, `event_id`, `parent_event_hash`, `agent_did_hash`, tenant/store/device references, policy/pack hash, and content/decision hashes.

Shield consumes the trace for live risk, cost, policy, and execution views. Cortex consumes it for session exploration, memory provenance, retrieval evidence, and historical graph queries. Both products retain their own authorization and tenant boundaries.

## Deliberately not done in v1

- No kernel rewrite or on-chain policy compiler.
- No on-chain adapter registry.
- No deploy factory.
- No memory checkpoint chain beyond required provenance/root evidence.
- No session keys, staking, paymaster, tokens, signing daemon, or billing code.
- No formal SMT analysis or Jev/LLM-judged rules as the authoritative enforcement gate.
- No Codex or Agy DecisionTrace hooks in the first slice; Hermes observer capture is first because its session, invocation, approval, and tool seams already exist. Existing Claude Code hooks remain independently gated.
- No raw chain-of-thought capture, token-by-token causal graph, or UI claim that a Jev probability proves correctness or causality.
- No requirement that hosted Jev, a local compatible model, Oracle, or public-chain anchoring be available for local Shield/Cortex operation.
- No public-chain or vendor dependency for local demos, tests, cleanup, acceptance, or normal Shield/Cortex runtime enforcement.

All deferred items are listed in STATUS.md with their reason and intended timing.

## Execution model

The run proceeds through outcome gates: architecture and documentation consolidation → SaaS pilot outcome → optional integration outcome → production trust outcome. A failed required gate stops the run with a report. Optional integration gates do not invalidate local acceptance or pilot operation.

Each active repository receives a dedicated feature worktree created with `xb-wt start <repo> <type>/<topic>` from that repository's declared base branch. Base checkouts remain clean and untouched. Worktree paths and branches are recorded in the phase tracker. Pushes use `xb-wt push`; merges occur only after green CI. Never use a bare `git push`, assume `main`, or use `git stash`.

Before Phase A, run `xb-wt doctor` and `xb-wt list`. Preserve dirty worktrees, classify unreadable worktrees, and do not begin feature work until the worktree map and ownership of each existing change are recorded.

### Canonical documentation home

The authoritative plan and domain documents must be tracked in one active repository, not only as an untracked file at the Projects root. Until the rename, use:

~~~text
integrity-core/docs/ecosystem/
  INTEGRITY_ECOSYSTEM_PLAN.md
  ECOSYSTEM.md
  DATA.md
  STATUS.md
  ADR-0001-six-function-test.md
~~~

The C5 rename migrates this documentation namespace to integrity-kernel or to an explicitly approved successor. The current Projects-root copy is a working copy until that migration is committed.

Owner checkpoints:

All three owner checkpoints were **granted by the owner on 2026-11-03**. An approval authorizes the
action; it is not evidence the action happened. Each still executes as its own gated step, in its own
worktree, with its own recorded evidence.

| # | Checkpoint | Owner decision | Execution state |
|---|---|---|---|
| 1 | Create integrity-lab and integrity-console; grant push access to Shield and Cortex | Approved 2026-11-03 | **Both repositories already exist** — `XibalbaTechSol/integrity-console` and `XibalbaTechSol/integrity-lab` both resolve. The approval ratifies what is in place; A1's lab mirror is not blocked on repository creation. |
| 2 | Testnet broadcasts, including Base Sepolia StateAnchor deployment and genesis | Approved 2026-11-03 | **Not executed, and still blocked — see B4 below.** Approval is necessary but not sufficient: a credential rotation must precede any broadcast. Core PR #184, merged 2026-11-03 as `87fd2390`, records this same approval and the same precondition. |
| 3 | Repository rename during C5 | Approved 2026-11-03 | Not executed; C5 has not started. The approval does **not** authorize renaming integrity-core during the current documentation consolidation, which is explicitly excluded by the 2026-11-03 handoff. |

Recording these approvals closes the owner-decision dependency only. No repository was created, no
chain transaction was broadcast, and no repository was renamed as part of recording them.

## Inherited state: handoff integration, 2026-11-03

This section discharges the Execution-model precondition above — *"do not begin feature work until the
worktree map and ownership of each existing change are recorded"* — and folds every handoff found
across the four active repositories into this plan.

It was produced by auditing `origin/main` and every remote and local ref in all four repositories, not
by reading the base checkouts. The `xibalba-cortex` base is pinned to `local`, has never been pushed,
and sits behind `origin/main`, so its working tree is not current truth.

**Evidence rule applied throughout.** Every inherited claim carries one of three states: **verified**
(a commit, PR, or CI run was checked), **stale** (the claim was true when written and the audit shows it
has since been superseded), or **unverified** (no runnable evidence was found). Prose that asserts PASS
is not evidence, and an unticked checkbox is not evidence that work did not happen — both failure modes
occurred in the inherited documents and are corrected below.

### Handoff register

Every handoff in the four repositories, with what the audit found.

| Handoff | Where it lives | State |
|---|---|---|
| `integrity-core/docs/ecosystem/HANDOFF_CLAUDE_2026-11-03.md` | `origin/main` — **PR #183 merged 2026-11-03 as `ad5f0f52`** | **Current.** Establishes this `docs/ecosystem/` namespace as authority, now on `main`. Two of its five next actions are closed — see "Corrections" below. |
| `xibalba-shield/docs/handoffs/2026-11-03-claude-phase3-gate1-handoff.md` | `origin/test/phase3-gate1-sdk-runtime` | **Current.** Records Phase 3 Gate 1 PASS and defines the Gate 2 objective. Pushed 2026-11-03 at owner request; no longer single-copy. |
| `xibalba-shield/docs/handoffs/2026-11-03-phase3-gate1-result.md` | `origin/test/phase3-gate1-sdk-runtime` | **Current.** The Gate 1 evidence: Cortex 11 focused tests, Shield 16, identity canary signature verified, key material untouched. Pushed 2026-11-03; no longer single-copy. |
| `xibalba-shield/docs/handoffs/2026-11-03-shield-ui-visual-audit.md` | `origin/fix/ui-visual-redo-20261103` (no PR open) | **Current.** Console routes audited at 1600/1280/390px; 30 Playwright tests pass against mocked control-plane responses. Explicitly *not* live-backend verification. |
| `xibalba-cortex/viewer/HANDOFF.md` | `origin/main` | **Current.** Console theme, information architecture, honesty rules, and the §9/§10 open items. Byte-identical across all 15 branch copies — no newer version is hiding on a branch. |
| `xibalba-cortex/docs/operations/codex-handoff-runtime-plugins.md` | `origin/main` | **Stale in its continuation instruction.** It says to continue on `feat/cortex-runtime-and-plugins`; that branch **does not exist on origin**. Its content landed: the canaries document, the plugin builder, `perplexity_runtime.py` and both test modules are on `main`. Its *outstanding* items remain open — see below. |
| `xibalba-cortex/docs/PROJECT_STATE.md` | `origin/main` | **Current as a ledger, stale in one pointer.** Carries the G1–G7 gate ledger. Names `docs/EXECUTION_PLAN.md` as cross-product authority, which this namespace supersedes. |
| `xibalba-cortex/docs/superpowers/plans/2026-11-02-cortex-production-readiness.md` | `origin/main` | **Current plan, stale Resume Brief.** See "Corrections". Its cited evidence is not in git — see "Durable-evidence gap". |
| `xibalba-shield/docs/handoffs/2026-09-23-shield-hermes-ui.md` | many branches | Historical. |
| `xibalba-cortex/docs/archive/2026-08/2026-08-13-hybrid-extraction-handoff.md` | `origin/main` archive | Historical. Its phases A–C were complete and live-verified at the time. |
| `integrity-core/docs/HANDOFF_GATE_A_2026-09-28.md` and the 13 handoffs under `docs/archive/2026-09/` | `origin/main` | Historical. Gate A has since closed 12/12; superseded by `STATUS.md`. |

Under the migration manifest's classification rules these historical handoffs stay in their dated
archives and remain non-normative. Only the items extracted below are carried into this plan.

**One handoff channel could not be read, and the reason is correct scoping, not a defect.** Cortex's
ledger contract in `PROJECT_STATE.md` requires every session to store its checkpoint as a `summary`
memory in Cortex, which makes those memories part of the handoff set. This session cannot read them.

The first reading of this was wrong and is recorded here so it is not repeated. Against the `default`
store (`memory_status`: schema 16, WAL, FTS5 on, `integrity_check: ok`, **3,202 memories**),
`memory_hybrid_retrieve` and `memory_recall` return **zero results for every query tried** — including
the bare term `cortex`, and including a term present in 3,117 rows with that status explicitly
requested — while reporting `lexical: available`, `vector: available`, `temporal: available`,
`degraded: []`. That looks like a retrieval defect and was initially written up as one.

A read-only inspection of the store disproves it. The `memories` table carries no agent column;
scoping is on `sources.agent_id`, and retrieval is agent-scoped and fail-closed by design. The store's
sources carry seven distinct agent identities. This session binds `XIBALBA_AGENT_ID=claude`, resolving
to the on-disk identity at `~/.hermes/xibalba-cortex/agent.did.json`, and **that identity owns none of
them**. A principal with no memories of its own correctly sees nothing. `memory_fts` is fully populated
(3,202 rows, 52 matching `cortex`), so the index is healthy and the empty result is the scope boundary
working, exactly as `viewer/HANDOFF.md` §6 describes.

What this does establish:

- **The checkpoint-memory channel is a blocked input, not an absent one.** No checkpoint content is
  integrated into this section. Any such memories live under other agent identities. This is the
  standing rule that an empty Cortex read is never evidence of absence.
- **The ledger contract is not being honoured under this agent's identity.** No agent visible in the
  store corresponds to this harness, so the required per-session `summary` memory is either not being
  written or is written under an identity that the writing session cannot itself read back. A contract
  that mandates a durable checkpoint is not satisfied by one no one can retrieve.
- **The store is 97% one agent's telemetry.** 3,117 of 3,202 memories are `candidate`-status policy-decision
  records from a single agent; only 26 memories are `confirmed`. Any claim about recall quality or
  retrieval evidence measured against this store is measuring machine telemetry, not curated memory.

### Corrections to inherited claims

Each of these was asserted in a handoff and contradicted by the audit.

1. **The core handoff's uncommitted documentation-contract patch is now committed.** It recorded
   `scripts/check_docs.py` as "patched locally but not yet committed or pushed". On the PR branch that
   script now reads `docs/ecosystem/INTEGRITY_ECOSYSTEM_PLAN.md` as the execution authority, and the
   change is committed. Its next-action 2 is closed.
2. **Core PR #183 is merged.** The handoff recorded CI as rerunning with the documentation contract
   failing. All ten required checks passed and the PR merged on 2026-11-03 as `ad5f0f52`. Its
   next-action 3 is closed.
3. **Cortex PR #89 has regressed to `DIRTY` with no checks reported.** The handoff expected a named
   workflow run to confirm it. It now needs conflict resolution before it can merge. Its next-action 4
   is **not** closed, and the state is worse than recorded.
4. **The Cortex Resume Brief's repository-state section is stale.** It states, verified 2026-11-02, that
   `origin/main` "does not carry the code work" and that `hostedApi.ts` is absent. As of today
   `src/xibalba_cortex/managed/ingest.py`, `tests/test_managed_ingest.py` and `viewer/src/hostedApi.ts`
   **are on `origin/main`**: Phase 5 Task 1 landed. `viewer/src/edition.ts` is still absent.
5. **Unticked checkboxes in the Cortex plan understate progress.** Every step box in its Phases 1–2 is
   unticked, yet PR #86 (a zero-agent account opens on connect-an-agent) and PR #87 (the signed,
   single-use enrollment code) merged on 2026-11-03 — Phase 2 Tasks 1 and 2. Reconcile the boxes against
   merged PRs before treating any of them as open work.
6. **The runtime-plugins continuation branch is gone, not pending.** See the register.
7. **PR #183 archived a stale copy of the superseded plan, silently reverting PR #182's
   reconciliation.** When #183 moved `docs/EXECUTION_PLAN.md` to
   `docs/archive/2026-11/EXECUTION_PLAN-superseded.md`, the archived file was an older revision than
   the one on `main`, so the merge undid #182's reconciliation and the quoted progress count stopped
   being reproducible from any file in the repository. **Repaired 2026-11-03** on the #184 branch by
   overwriting the archive with the full `main`-derived version; the archive now regenerates
   146/232 (62%), matching `STATUS.md`. An archive move is a content change: diff the archived copy
   against the live file before merging one.

### Worktree and branch ownership map

`xb-wt doctor` reports all four bases clean and on their declared branch, with one expected WARN: the
`xibalba-cortex` pinned `local` branch has never been pushed to origin.

Three worktrees sit at the worktrees root rather than under `<repo>/<topic>`: `cortex-baseline`,
`cortex-main-verify` and `cortex-toolcount`. WORKFLOW.md grandfathers these; they are retired by
`xb-wt finish`, never renamed. `cortex-baseline` is dirty.

Dirty worktrees, preserved and not touched by this audit:

| Worktree | Dirt |
|---|---|
| `integrity-core/ecosystem-authority-20261103` | `integrity-sdk/tests/unit/test_core_decision_trace.py` — the core handoff's next-action 1, still open. It is an artifact of constructing merge commit `1d5e70bf` with index plumbing; inspect the diff before staging it. |
| `xibalba-cortex/bind-selects-agent` | 3 paths |
| `cortex-baseline` (grandfathered) | 1 path |

**Ownership of every local branch not on origin.** Twenty-eight such branches carry commits. They were
classified with `git merge-tree --write-tree` against `origin/main`, which is the only reliable test: a
blob-level comparison falsely flags any branch whose files `main` edited later, and a squash merge
leaves a branch a non-ancestor of `main` even when its content has fully landed.

*Adds nothing to `main` — content already landed. Safe to sweep with `xb-wt prune` after the per-branch
PR check Rule 8 requires (9 branches):* `integrity-core` `docs/jev-decisiontrace-status`;
`xibalba-cortex` `a3/cortex-jcs`, `docs/readme-capability-citations`,
`feat/decision-trace-advisory-retries`, `feat/enrollment-code`, `fix/hosted-landing-grammar-test`;
`xibalba-shield` `cron/pr24-ci-repair`, `docs/ecosystem-authority-20261103`,
`fix/inference-endpoint-url-validation`.

*Real unlanded content — must be pushed or deliberately abandoned (3 branches):*

| Repo | Branch | Carries |
|---|---|---|
| `xibalba-shield` | `test/phase3-gate1-sdk-runtime` | Both Phase 3 Gate 1 handoffs. **Resolved: pushed 2026-11-03** to `origin/test/phase3-gate1-sdk-runtime` at `d41c4e76`, verified by `ls-remote`, and open as draft PR #68. Docs-only, +289 lines. |
| `xibalba-cortex` | `feat/bind-selects-agent` | Phase 2 Task 3: a redeemed code binds an agent the console can open. |
| `xibalba-cortex` | `feat/inbound-ingest-throttling` | Binds an OTLP ingest credential to its profile on the HTTP transport. |

*Conflicts with `main` — each needs an explicit keep-or-abandon decision (16 branches), most based in
August and September:* `integrity-core` `a5/mainnet-readiness-adr`, `docs/gate-a-status-update`,
`docs/reconcile-v1-authority`, `feat/adapter-registry-r1-r5`, `feat/periodic-merkle-anchor`,
`fix/ci-dependency-resolution-20260818`, `fix/default-ci-contract-compile`,
`test/policy-hooks-revert-and-access-control`; `xibalba-cortex` `cron/pr6-rebuild-20260829` (26
commits), `docs/account-registration-design`, `feat/decision-trace-viewer`,
`fix/report-every-e2e-failure`; `xibalba-shield` `fix/exporter-url-plumbing-and-registration-docs`,
`fix/honest-live-bcc-gate`, `fix/local-run-profile-validation`,
`test/policy-engine-combined-conditions`.

WORKFLOW.md Rule 3 already names `cron/pr6-rebuild-20260829`, `a3/cortex-jcs` and
`docs/reconcile-v1-authority` as the original orphaned-work problem, caused by feature branches
tracking `origin/main`. They are known orphans, not new findings.

**Remote branches not merged into `origin/main`**, classified the same way. These are pushed, so they
are not at risk of loss, but each is unlanded work someone must land or retire. Excluding the five open
PR heads and this integration branch:

| Repo | Adds nothing (prune) | Real content | Conflicts |
|---|---|---|---|
| `integrity-core` | — | `audit/harness-loop-2026-07-30` (+10) | `a5/docs-authority-gates`, `docs/rescope-registry-precheck-gas` (+60), `feat/cortex-operations-dashboard` (+6), `fix/sdk-nitro-trust-root-wheel`, `park/policy-packs-2026-09-26` |
| `xibalba-cortex` | `feat/cortex-brain-logo`, `fix/console-timeline-routes` (+3) | — | `feat/cortex-decision-trace`, `feat/runtime-telemetry-adapters` |
| `xibalba-shield` | — | `fix/ui-visual-redo-20261103` (the audited UI work, no PR open) | `feat/evidence-chain-ui`, `feat/jev-decision-trace`, `fix/ui-console-chassis-parity` (+10, has a worktree), `park/policy-packs-2026-09-26` |
| `integrity-console` | `docs/ecosystem-authority-20261103` | — | — |

`docs/rescope-registry-precheck-gas` at +60 commits is the largest single body of unlanded remote work
in the ecosystem and has no open PR. `park/policy-packs-2026-09-26` exists in both core and Shield and
is named "park", so confirm it is still a deliberate parking place rather than forgotten work.

Three Antigravity harness worktrees also exist under
`~/.gemini/antigravity-cli/brain/.../worktrees/` against `integrity-core`. WORKFLOW.md tolerates them
and `xb-wt prune` sweeps their branches like any other.

### Durable-evidence gap

The Cortex production-readiness plan cites `.superpowers/sdd/.../phase0-task5-report.md` and
`phase5-task1-report.md` — a 198/198 Playwright baseline and **nine recorded mutation proofs** — as the
evidence base for its Phases 0 and 5.

Those reports are **untracked and unignored**. They exist only inside the
`xibalba-cortex/account-registration-design` worktree on `/mnt/storage`. Nothing is in git: `main`
carries zero `.superpowers` paths. An `xb-wt finish` on that worktree, which Rule 7 permits once its
branch lands, destroys the entire cited evidence base.

This is the failure class already recorded in project memory, where an audit document carried PASS for
values no test ever asserted. Closing it is a precondition for trusting any Cortex phase status.

### Numbering crosswalk

Four numbering schemes are in play. This plan's A/B/C phases and gates are the authority; the others are
repository-local and must not be restated here as parallel roadmaps. Cortex's own ledger contract
forbids creating a new roadmap for work G1–G7 already covers, so these rows link rather than duplicate.

| Scheme | Where defined | Relation to this plan |
|---|---|---|
| A/B/C phases, Gate A, Gate B-local, Gate C | this document | Authority. |
| Cortex G1–G7 | `xibalba-cortex/docs/PRODUCTION_READINESS_PLAN.md` §6, ledgered in `PROJECT_STATE.md` | Cortex's share of B0 and Gate B-local. G2 is the SDK-layout item below. G5 and G7 are external-pilot gates matching this plan's pilot work. |
| Cortex Phases 0–5 and readiness levels L0–L3 | `docs/superpowers/plans/2026-11-02-cortex-production-readiness.md` | The implementation sequence for the Cortex SaaS slice of B0. |
| Shield "Phase 2 approved / Phase 3 Gate 1–2" | **only** the Gate 1 handoff, on `origin/test/phase3-gate1-sdk-runtime` via draft PR #68; not yet on `main` | **Undefined in any repository.** Even once #68 lands, `main` will carry the Gate 1 *result* but still no definition of Shield Phases 1–3. Treat the result as evidence; do not treat the numbering as authoritative until it is defined here or retired in favour of these A/B/C gates. #68 names this as blocked follow-up. |

### Items carried into the plan

- **A2/A3 — one reproducible SDK layout.** Shield and Cortex both declare the editable dependency
  `../integrity-core/integrity-sdk`. It resolves in the sibling checkout layout but **not** from a fresh
  `xb-wt` worktree, where `xb-wt setup` fails with a missing-distribution error. This is one defect
  reported twice: it is Cortex **G2, "BLOCKED EXTERNALLY"**, and Shield **Phase 3 Gate 2**. It is also
  the recorded reason Cortex end-to-end tests need a sibling `integrity-core`. Acceptance, from the
  Gate 1 handoff: a clean prescribed worktree resolves the frozen SDK through the declared dependency
  mechanism; both consumers resolve the same frozen revision; CI reproduces the layout with no
  developer-only absolute path; `uv lock --check` and the focused SDK tests pass for both consumers; and
  no installed service, base checkout, identity store, credential, database, queue or outbox changes.
  No absolute `/home/xibalba/...` path in committed metadata, and no permanent external symlink. This
  gates A3's "consume the SDK without sibling copies".
- **A5/A6 — one authority pointer is still stale on `main`; the other is fixed in an open PR.**
  `integrity-core/STATUS.md` line 4 still records execution authority as `docs/EXECUTION_PLAN.md`, now a
  compatibility redirect. PR #184 edited that same file without repointing it, and **re-verified on
  `main` after #184 merged, line 4 is unchanged** — the merge did not fix it. Repoint it. The Cortex
  side needs no new work: **open PR #89 already** adds an
  "Ecosystem authority" section to the Cortex README and repoints its cross-product plan links to
  `docs/ecosystem/INTEGRITY_ECOSYSTEM_PLAN.md`. Land #89 rather than duplicating it.
  `scripts/check_docs.py` already enforces this namespace.
- **A5/A6 — the plan progress metric is already broken, verified.** `STATUS.md` reports
  "**146/232 checkboxes (62%)**, generated by `python3 scripts/plan_progress.py`; it is not
  hand-maintained" — raised from 134/232 by PR #184, now merged — having previously drifted to a stale
  hand-edited 88/201. That command still **fails**:
  the script defaults to `docs/EXECUTION_PLAN.md`, which is a redirect with no task lists, and exits
  `ValueError: max() iterable argument is empty`. Pointing it at this plan fails identically, because
  this plan expresses work as prose bullets and contains **zero** checkboxes. The 146/232 figure is
  reproducible *only* from `docs/archive/2026-11/EXECUTION_PLAN-superseded.md`, a document this
  namespace marks historical — and reproducible from it at all only because the stale-archive
  regression in correction 7 was repaired. So the one progress number the project quotes now measures
  a superseded plan and cannot be regenerated against the authority. Decide one of: make this plan carry
  checkable items, repoint the script and define what it counts here, or retire the metric and delete
  the claim from `STATUS.md`. Do not leave `STATUS.md` asserting a generated number that no command
  reproduces.
- **B2a — already closed by an open PR; land it, do not redo it.** `STATUS.md` on `main` lists B2a at
  6/8 with the Cortex viewer trace panel and the advisory retry queue open. Cortex PR #83 (render the
  DecisionTrace evidence panel) and PR #84 (retry unavailable DecisionTrace advisories) merged on
  2026-11-03 with exactly those titles, and **core PR #184 marks B2a Complete (8/8)**, citing #84's
  durable hash-bound retry queue and Shield PR #65's endpoint validation. #184 merged 2026-11-03 as
  `87fd2390`, so **B2a Complete (8/8) is now on `main`** — verified. Do not tick it separately.
- **B4 — approved but still blocked on signer hygiene. Do not treat the approval as a green light.**
  Testnet deployment was held for owner approval, granted 2026-11-03. Core PR #184, merged
  2026-11-03, records that approval *and* the blocker: the local deployment credential requires review and rotation because a
  prior troubleshooting session may have exposed it, and shared operator memory independently records
  exposed Base Sepolia credentials in local env files with "rotate before deployment". The replacement
  must be testnet-only, stored with owner-only permissions, and funded. **Do not broadcast using the
  current local credential.** Sequence after rotation: repeat the exact Anvil dry run, take a live gas
  estimate, broadcast the approved anchor script, verify deployed bytecode and roles on Base Sepolia,
  then add the address and transaction evidence to the manifest and deployment record. The script has
  already passed an Anvil dry run; no live transaction has been sent.
- **B0 — unchanged as the largest unstarted block** (0/19). The Cortex Phases 0–5 plan is its Cortex-side
  sequence, and that plan's Phase 5 Task 1 has landed on `main`. Its operator-amended running order is
  **Phase 0 → Phase 5 Tasks 1–2 → Phase 1 → Phase 2 → Phase 3 → Phase 5 Tasks 3–6**, chosen to reach a
  deployable test build sooner. Phase 0 and Phase 5 Tasks 1–2 are done, and Phase 2 Tasks 1–2 landed
  early as PRs #86 and #87, so the next item is Phase 1 Task 1.
- **B0, Cortex — two self-hosted MCP exposures the REST route closed but the MCP path keeps.** Both are
  recorded in the Phase 5 Task 1 report as live gaps rather than notes, and neither is fixed:
  1. **Metadata shadowing.** `ingest_turn` strips reserved `metadata` keys, but `ingest_agent_turn`
     still merges caller metadata *after* its own, so a caller-supplied `metadata.session_id`
     overwrites the source's real `session_id`. The REST route is protected; the self-hosted MCP path
     retains the exposure. Provenance that a caller can overwrite is not provenance, so this is a
     trust-substrate defect, not a cosmetic one.
  2. **Unrepeated account checks.** Account-state checks (active, verified, approved) and cookie CSRF
     live in `api.authenticate`, not in `ingest_turn`. The MCP transport must perform equivalent checks
     before calling it or it will serve unverified accounts.
  Also from that report: one ingested turn meters as a single `writes` unit while storing two memories
  plus OTel rows, and the handler is **not transactional** — a quota failure on the second memory
  leaves the first stored. Decide whether that partial write is acceptable before pilot metering is
  sold against it.
- **Cortex runtime-plugin items still open**, from the stale-continuation handoff: live model-host
  callbacks; native host installation, trust, callback and menu checks on a pilot machine; Perplexity
  billing and API canaries; and consumer OAuth/HTTPS dispatch. The hosted resource server implements no
  authorization server, and hosted ChatGPT cannot execute the local stdio package. Official directory
  submission is a separate action: repository publication makes a package discoverable, not listed.
  Provider telemetry deletion and export still cover only the GraphStore, not the recorder's local
  journal.
- **Cortex console items**, from `viewer/HANDOFF.md` §9–§10: server-side scoping for the older
  store-wide read routes, with a test per route proving an agent-bound credential cannot reach another
  agent's data; a worker heartbeat if "is it running?" must be answerable, which needs a schema
  migration and a spec amendment; a mockup recapture after the typography and ground-colour change; and
  the password-reset `503`/`200` disclosure, which is a deployment decision, not a UI one.
- **Shield UI**: the audited visual work on `origin/fix/ui-visual-redo-20261103` has no open PR.
- **Cortex G3, G5 and G7 remain external**: storage is a local pilot pass, not high-availability or
  point-in-time-recovery proof; real-data evaluation and burn-in need a real pilot tenant.

### Merge queue, in order

The owner authorized merging on 2026-11-03, and the four non-deploying pull requests were merged in
the order below, each with `--match-head-commit` at the SHA CI actually ran on, per Rule 6. Core PRs
#183 and #184 both touched the `docs/EXECUTION_PLAN.md` area, so order mattered: #183 turned that path
into a redirect, which put #184 into conflict as predicted.

| Order | PR | State | Outcome |
|---|---|---|---|
| 1 | `integrity-core` #183 | was `CLEAN`, 10/10 green | **Merged** 2026-11-03 as `ad5f0f52`. Landed this namespace on `main`. Also archived a stale plan copy — see correction 7. |
| 2 | `integrity-core` #184 | went `DIRTY` after #183, then re-greened | **Merged** 2026-11-03 as `87fd2390`. Resolved by merging `origin/main` into `docs/testnet-jev-rollout` (`640df6f8`), taking `main`'s redirect for `docs/EXECUTION_PLAN.md` and restoring the archive to the `main`-derived version, which also repaired #183's regression. All 10 checks green on `640df6f8`, the SHA passed to `--match-head-commit`. |
| 3 | `xibalba-shield` #67 | `CLEAN`, green | **Merged** 2026-11-03 as `6093ea92`. |
| 4 | `xibalba-shield` #68 | was draft, `root-free-tests` green on `d41c4e76` | **Merged** 2026-11-03 as `6e2eea13`. The Phase 3 Gate 1 evidence is now on `main`, no longer single-copy on a branch. |

Two Cortex pull requests remain, and both are deliberately **not** merged:

| PR | State | Why it is held |
|---|---|---|
| `xibalba-cortex` #90 | `CLEAN`, 2/2 green | Mergeable, but merging Cortex `main` auto-deploys the managed pilot. That makes it a deploy, which needs its own owner approval separate from the merge approval above. |
| `xibalba-cortex` #89 | **`DIRTY`, no checks reported** | Needs conflict resolution first, and carries the same deploy consequence. It also holds the Cortex authority-pointer fix, so A5/A6 waits on it. |

Shield PR #66 and Console PR #6 were already merged before this audit.

### Next actions

1. ~~Push `xibalba-shield` `test/phase3-gate1-sdk-runtime`, open a PR, and merge it.~~ **Done
   2026-11-03**: pushed with `xb-wt push` to `d41c4e76`, verified by `ls-remote`, opened as PR #68
   (2 files, +289/−0, docs-only) and merged as `6e2eea13` on green CI at `d41c4e76`. The Gate 1
   evidence is on `main` and no longer single-copy.
2. Get the `.superpowers/sdd` evidence into git, or into a durable location this plan names, before any
   `xb-wt finish` touches the `account-registration-design` worktree. **This is now the only remaining
   single-copy evidence problem**, and the highest-value open item in this section.
3. ~~Land the merge queue in order, each at its own green head.~~ **Done 2026-11-03** for the four
   non-deploying pull requests: core #183 and #184, Shield #67 and #68. The two Cortex pull requests
   are held — merging Cortex `main` is a deploy and needs its own approval. Decide #90, and resolve
   #89's conflicts.
4. Resolve the SDK layout item: it blocks A3 and two repository-local gates at once.
5. Repoint the two stale authority pointers, and reconcile the Cortex checkboxes against merged PRs.
6. Decide keep-or-abandon on the 16 conflicting local branches and the 11 conflicting remote ones, and
   sweep the 9 local plus 3 remote branches that add nothing. Open a PR for Shield's audited UI work on
   `fix/ui-visual-redo-20261103`, and decide the fate of `docs/rescope-registry-precheck-gas` (+60).
7. Reconcile the Cortex checkpoint-memory contract with agent identity: decide which identity owns
   session checkpoints, make the writing session able to read its own back, and stop quoting recall
   quality against a store that is 97% one agent's policy telemetry.

# Phase A: achieve architectural and documentation simplicity

**Outcome:** a small, coherent Integrity dependency exists; duplicate and obsolete authorities are removed or archived; Shield and Cortex can consume the SDK without sibling copies; and the active documentation set has one clear authority.

## A1. Clear the ground — kernel repository, M

- Create an immutable source snapshot and cut-path manifest.
- Mirror removed and historical material into integrity-lab.
- Filter the console to remove pages for cut features.
- Move to the lab: integrity-zkp; SDK prover, markets, MCP server, root integrity.py, root OPA client, and auto_hook; markets, licence, CCIP, governance, adapter registry, and removed adapters; dead oracle routes.
- Keep SovereignAgent and PrimitiveSet until Phase C because live agents still use them.
- Run pre-cut tests, secret scanning, and post-cut manifest comparison.

## A2. SDK core and C1–C7 — M

Create and tag integrity-sdk-v0.x with JCS, DID/DID-file support, Merkle primitives, receipts, DecisionEnvelope/DecisionTrace schemas, domain-separated trace leaves and proofs, pack schema/compilation/signing/verification, hook normalization, the memory interface, the OPA client, and agent identity/HTTP support.

Use lazy package initialization and import-hygiene tests. Put chain, registration, account, telemetry, hook-runner, and client integrations behind a connector extra.

## A3. Independent Shield and Cortex — M each

Both products depend on SDK core only, use lazy connector imports, contain no hard-coded /home/xibalba paths or sibling Docker copies, and pass independence CI against the SDK tag.

### Shield

- Policy bundles are signed packs covering the Rego itself.
- Enforced policy hash equals signed pack hash.
- permit means permitted; no-match, malformed, unknown, or evaluator-error denies in enforce mode.
- Export labels and HMAC-protected paths, never raw cmdline or content-bearing arguments.
- Separate device-auth and agent keys.
- Replace seven canonical-JSON copies with SDK JCS, re-sign bundles, and bump the schema.
- Keep mlflow optional.
- Reserve an optional JevDecisionGateway connector boundary; if enabled, hosted Jev, compatible-local inference, and deterministic fixtures are interchangeable providers, while OPA/BCC remains authoritative for enforcement.
- Bind regulated execution to an authenticated, canonical signed DID file with ownership/mode checks, device binding, rotation/recovery rules, and change detection.
- Enforce the universal hook fallback: Shield available means Shield enforcement; Shield unavailable means local BCC enforcement; both unavailable means regulated action denial.

### Cortex

- Authenticate the OTLP receiver.
- Register the provider_telemetry_export Merkle domain.
- Use SDK JCS.
- Bind create events to content_hash.
- Resolve agents from the DID file; retain XIBALBA_AGENT_ID only as an explicit override.
- Reuse session/exchange correlation and Merkle-chained exchange evidence for DecisionTrace projections without making trace metadata a replacement for Cortex content provenance.

## A4. Minimal kernel patch — S

- Add the requireAssuranceTier flag.
- Remove the obsolete adapter branch.
- Set evm_version to cancun.
- Do not rewrite the kernel or introduce an on-chain policy compiler.

## A5. Non-drifting documentation — S

Create AGENTS.md, CLAUDE.md as @AGENTS.md, STATUS.md capped at 150 lines, ECOSYSTEM.md, DATA.md, and ADR-0001 defining the six-function test. Add CI link/path checks and the STATUS.md cap. Move wiki, handoffs, audits, and historical design material to the lab.

## A6. Consolidate plans and documentation — M

Inventory every Markdown, design document, plan, register, audit, handoff, and README in the active repositories. Classify each as authoritative, merge-required, historical, or removable.

- Merge current normative decisions into this plan, STATUS.md, ECOSYSTEM.md, DATA.md, or an ADR.
- Move superseded plans and exploratory material to integrity-lab.
- Remove duplicate normative claims from active repositories.
- Add link, path, duplicate-claim, and authoritative-document checks to CI.
- Make generated facts a later documented workstream rather than allowing new hand-maintained registers.

The result is not one enormous document. It is one authoritative execution plan with a deliberately small set of authoritative domain documents.

## A7. Stable SaaS seams — M

Define the interfaces that let Shield and Cortex depend on Integrity without becoming one product:

- tenant and organization identity;
- agent and device registration;
- signed pack distribution and version pinning;
- receipt submission, local queueing, and later anchoring;
- offline verification;
- provider and store identity for Cortex;
- product entitlements and capability checks;
- redacted usage and audit metrics.

These are SDK/API contracts and local reference implementations, not billing code. They must support a customer running Shield or Cortex with local Integrity services and later upgrading to hosted or anchored Integrity services without changing policy semantics or receipt meaning.

## A8. Optional DecisionTrace and Jev foundation — M

Define the optional cross-product annotation contract only after the core SDK and SaaS seams are stable. A8 is not a prerequisite for Gate A or Gate B-local.

- publish `decision_trace.v1`, `decision_envelope.v1`, and `trace_merkle.v1` schemas;
- define the event classes, required correlation IDs, parent-link semantics, provider/fallback fields, redaction policy, and causal-status vocabulary;
- reuse SDK JCS, `leaf_hash`, `merkle_root`, `merkle_proof`, `verify_leaf`, signed-body, receipt-log, and offline-verification primitives;
- use domain-separated leaf preimages so DecisionTrace roots cannot be confused with memory, provider telemetry, or Shield receipt roots;
- define the `JevDecisionGateway` interface with timeouts, retries, cache keys, provider identity, model/rubric pinning, usage/cost capture, and deterministic fixture mode;
- add a strict rule that Jev annotations can recommend, classify, or score but cannot authorize, sign as the enforcement actor, resolve identity, choose a tenant/store, or execute a tool;
- add schema vectors for hosted Jev responses, compatible-local responses, timeout, malformed response, unavailable provider, redacted input, and threshold boundary cases;
- define a compliance export that distinguishes observed events, model annotations, policy authority, execution evidence, and unproven causality.

The first proof is local and synthetic: one Hermes session produces a linked trace, a Jev fixture annotates a proposed action, Shield/OPA/BCC records the policy result, Cortex records the memory effect, and Integrity verifies the receipt chain plus Merkle inclusion proof. No external Jev, Oracle, or public chain is required.

## Gate A: architecture and documentation outcome

Required:

- Relevant suites, import hygiene, Shield/Cortex independence CI, and console build are green.
- The exact cut-path manifest exists in integrity-lab.
- One SDK JCS implementation is used across active repositories.
- Signed pack hash equals enforced pack hash.
- Tampered, malformed, stale, or incompatible packs refuse to load.
- No-match denies.
- No raw command content appears in exports.
- Device key differs from agent key.
- Unauthenticated Cortex OTLP is rejected.
- Cortex provenance export works and create events bind content_hash.
- Kernel tier-off test and Halmos pass.
- Shield and Cortex can create isolated pilot tenants using only local Integrity-compatible services.
- A queued receipt can be verified locally before and after later anchoring.
- Every active normative document has an identified authority.
- Superseded plans and historical material are present in integrity-lab.
- No active repository contains a competing architecture register or duplicate product plan.
- A third party can build and validate a sample adapter using the SDK contract and conformance kit.

## Optional Gate J: annotation extension

If A8 is implemented, require a local deterministic-fixture proof that one Hermes-to-Shield-to-Cortex trace produces valid annotation, trace, receipt-chain, and Merkle-inclusion evidence with provider mode explicitly recorded. A Jev timeout, malformed result, or unavailable provider must never authorize an action. Trace proofs must fail closed on mutation, reordering, wrong domain, wrong index, wrong parent, or wrong tenant/store scope.

# Phase B: achieve the monetizable Shield and Cortex SaaS outcome

**Outcome:** Shield and Cortex are independently deployable, tenant-isolated, pilot-ready SaaS products that depend on Integrity contracts without depending on public-chain availability. They have clear paid capability boundaries, operational workflows, and evidence exports.

The first commercial package is Integrity Health: a Shield policy-enforcement deployment paired with Cortex provenance and memory, using synthetic regulated data until Gate C is complete.

## B0. SaaS productization — L

### Shared SaaS requirements

- Explicit tenant and organization boundaries.
- Tenant-scoped agents, devices, packs, receipts, memory stores, exports, and audit logs.
- Organization administrator and operator roles.
- Device enrollment and revocation.
- Product entitlements and capability checks without implementing billing.
- Configurable retention and region policy.
- The first commercial deployment is single-tenant and customer-local or managed single-tenant. Hosted multi-tenant operation is a later scale gate, not an implied Phase B claim.
- Hosted-service-compatible APIs for later SaaS operation, with the same tenant, receipt, pack, and verification contracts.
- Usage and audit summaries suitable for future pricing, without charging or payment processing in v1.
- Backup, restore, tenant deletion, and export procedures.
- Explicit control-plane/data-plane boundary, tenant authentication, organization roles, session/credential lifecycle, rate limits, quotas, and operator access audit.

### Shield SaaS slice

- Organization policy management with signed pack promotion and rollback.
- Device enrollment, health, key status, and revocation.
- On-device enforcement with a local BCC fallback when Shield is unavailable.
- Fail-closed regulated mode when both Shield and BCC are unavailable.
- Receipt queue, verification status, and compliance export.
- Operator workflow for shadow mode, enforcement mode, and controlled break-glass.
- Optional annotation timeline for observable event → Jev assessment → policy result → execution/outcome; this is excluded from the minimum sellable Shield slice.

### Cortex SaaS slice

- Tenant-scoped memory providers and stores.
- Agent-scoped content and provenance views.
- Retention, purge, export, and provider health controls.
- Authenticated ingestion and retrieval APIs.
- Retrieval spot-check API and proof status.
- Clear separation between customer content, metadata, and Integrity evidence.
- Session and decision-graph explorer joining Hermes invocations, Jev annotations, tool outcomes, and Cortex memory effects.
- Evidence inspector distinguishing observed content, derived/model annotations, policy decisions, and unproven causal links.
- Retention and purge behavior that removes content while preserving only permitted non-content trace commitments.

### Monetization boundary

The pilot is monetizable without billing code. Define paid capabilities and deployment packaging now; implement invoicing, payment processing, and automated billing later. The first sellable boundary is:

- Shield: per-organization policy enforcement, enrolled devices, evidence retention, and compliance exports.
- Cortex: per-organization memory capacity, retention policy, providers, retrieval, and provenance exports.
- Integrity: included trust compatibility and verification; public-chain anchoring and advanced attestations are higher-tier or separately provisioned capabilities.

## B1. Packs and deterministic adapters — M

Create packs/base and packs/hipaa containing pack.yaml, policy.rego, controls.yaml, HIPAA §164.312(a)(1)/(b) and §164.502(b) mappings, SOC 2 CC6.1/CC7.2 and ISO 42001 mappings, and content seeded from CONTROLS_MATRIX.md.

The compiler rejects policy relaxation. baa.py is deterministic. BAA conditions are operational off-chain controls enforced by BCC, Shield, or EHRGate; the evidence does not itself certify legal compliance.

## B2. Gates emit receipts — M

BCC and Shield evaluate the same compiled pack artifact and shared conformance vectors. Both support atomic pack loads, fail-closed reason codes, shadow/enforce modes, signed receipts with HMAC-protected identifiers, sequence numbers, previous-hash links, and checkpoints.

Shield's local gate daemon exposes a Unix socket for PreToolUse and contains or denies through ActionBroker.

## B2a. Optional Jev-assisted DecisionTrace — M

If the optional annotation extension is approved after the core SaaS gate, implement the provider gateway and first product workflows:

- instrument Hermes `post_llm_call`, `pre_tool_call`, `post_tool_call`, `post_approval_response`, session lifecycle, and subagent boundaries using the existing `hermes.observer.v1` correlation IDs;
- emit `llm_call`, `jev_assessment`, `action_proposal`, `policy_decision`, `approval`, `tool_execution`, `outcome`, and `memory_effect` trace events with bounded hashes by default;
- run Jev in shadow mode for action risk, human-review need, route, expected cost, and context-retention questions;
- batch independent Choice/Score/Noul questions over one redacted state where possible, recording usage and latency;
- store trace events in the local outbox and Cortex session/exchange projection without blocking low-risk local operation;
- bind high-risk traces to Shield invocation/action receipts and preserve OPA/BCC as the final authority;
- add operator-visible provider status: hosted, compatible-local, fixture, unavailable, timeout, or malformed;
- add a deterministic fallback policy for provider failure: continue analysis-only work, but hold or deny high-impact actions;
- implement idempotency on `(tenant_id, agent_id, session_id, event_id)` and preserve profile/store isolation;
- expose a read-only trace API for Shield and Cortex, with separate product-scoped authorization.

Jev is not called for every token or hidden reasoning step. It is called at observable decision boundaries only. The product must label every probability as a model annotation and every transition as observed or declared, never as proven causal reasoning.

## B3. Claude Code hooks — S

Implement:

~~~text
integrity hooks install --harness claude-code --gate shield|bcc --memory cortex
~~~

The command writes the DID file and marker-tagged hooks, is idempotent, and has exact uninstall behavior.

## B4. Verifiable evidence — M

Use one protocol, StateAnchor, for local and testnet anchoring.

- Phase B uses Anvil locally.
- The anchor receives epoch roots and signed checkpoints from BCC and Shield receipts.
- integrity verify checks signature, chain position, inclusion, and anchor.
- Agent-scoped StateAnchor writes replace anchor_batch_per_agent writes.
- Testnet deployment is optional and requires owner approval.
- DecisionTrace roots use the `trace_merkle.v1` domain and are separately identifiable from Shield action-receipt roots, Cortex memory roots, and provider-telemetry roots.
- Offline verification proves signed event integrity, parent linkage, Merkle inclusion, and anchor status; it does not prove model correctness or causality.

## B5. Telemetry policy — S

The regulated profile is the default with hipaa:

- no customer content leaves the boundary;
- signals are derived at the edge;
- AIS marks edge signals as self-reported;
- the receiver strips user.email and other prohibited identity fields.

Negative tests cover prompts, tool arguments, file contents, environment variables, stdout/stderr, URLs and query strings, filenames, repository names, exception messages, and stack traces.

DecisionTrace redaction is mandatory before Jev or telemetry delivery. Store full customer content only inside the declared Cortex content boundary; use content hashes, bounded excerpts, HMAC-protected identifiers, and policy-approved metadata in trace envelopes.

## B6. Pilot packaging and operator workflow — M

Create a reproducible pilot deployment for Shield and Cortex with:

- one organization administrator;
- at least two tenant-scoped agents and devices;
- policy promotion and rollback;
- Cortex store creation, retention, purge, and export;
- local receipt queue and verification;
- operator-visible health and evidence status;
- synthetic-data reset and tenant teardown.

The pilot must demonstrate that Shield and Cortex remain useful products when StateAnchor, Oracle, or vendor integrations are unavailable.

## B7. Revenue-facing exports — M

Build a Vanta private integration linking per-control tests to receipts and produce OCSF 6003 and JSONL exports for SIEMs. Test the Vanta adapter with local fixtures during local acceptance.

## Gate B-local: sellable SaaS outcome

Use Compose, local Integrity-compatible services, local Anvil StateAnchor, Shield, Cortex, BCC, synthetic regulated data, and Claude Code hooks. The pilot must remain operational with anchoring disabled and must queue evidence for later anchoring.

Required:

- A PreToolUse without an active configured BAA is denied on-device by the hipaa pack.
- The receipt cites the mapped control and pack hash.
- Shadow mode records without enforcing.
- Receipts anchor locally and offline verify passes.
- Tampered, wrong-key, wrong-proof, and truncated-tail receipts fail verification.
- A traffic audit proves no content leaves the boundary.
- Pack golden hashes pass and every rule cites a control.
- Vanta fixture tests pass.
- Two tenants cannot read or alter one another's agents, devices, packs, memory, receipts, or exports.
- Revoked devices cannot enforce or submit accepted receipts.
- Shield and Cortex remain operational when StateAnchor and external Oracle services are unavailable.
- Queued receipts verify locally and become anchored after service recovery.
- Tenant purge removes customer content while preserving only permitted non-content evidence.
- Product entitlements are enforced without requiring billing or payment services.
- The core Shield timeline shows policy decisions, execution outcomes, and receipt status. If the optional annotation extension is enabled, its output is visibly labeled as model-generated and non-authoritative.
- Cortex can navigate from a session/exchange to its contributing memories and back, with profile/store authorization enforced. Optional DecisionTrace projections do not replace Cortex content provenance.
- A compliance export separates observed evidence, policy authority, execution evidence, and Merkle/anchor proof status. Optional model annotations are a separately labeled section.

This demonstrates enforcement of configured policy. It does not by itself certify HIPAA compliance.

## Gate B-integrations: optional external evidence

May include Base Sepolia StateAnchor deployment, Vanta sandbox execution, and external Oracle/BCC connectivity. Each result is classified as verified, unverified, or blocked. Failure or unavailability here does not invalidate Gate B-local.

# Phase C: achieve production-grade Integrity trust

**Outcome:** Integrity is safe to use as the authority for high-consequence claims involving real funds or real PHI. Phase C follows the first Shield/Cortex pilots and does not block local pilots, synthetic-data sales conversations, or controlled SaaS operation.

## C1. Make kernel mediation true — L

- Choose and document one supported account-authorization model before implementation; Gate C must test that explicit model and must not retain a conditional ERC-1271 decision.
- Make EntryPoint interaction deposit-only and block withdrawTo.
- Count approvals as outflow.
- Keep rescue sweep only as a separately authorized recovery path with guardian quorum, bounded recipients/assets, replay protection, explicit event/receipt, and spending-accounting updates. Ordinary account execution must not invoke it.
- Produce the kernel M1 test, sequence invariant, ERC-7579 conformance tests, and mediation_audit.py.

## C2. Accounts and registration — M

Deploy accounts directly from the canonical IntegrityAccount implementation. Do not introduce a factory.

Registration requires:

1. The account calls the registrar.
2. The registrar verifies an Ed25519 attestation over account address, chain ID, DID hash, guardian, pack hash, and memory provider.
3. The registrar verifies the fixed implementation/version identifier, canonical account code or approved immutable-argument encoding, and kernel binding. Proxy and unapproved upgradeable variants are rejected.
4. Cortex completes memory genesis.
5. The registry records the account/DID/provider relationship.

Registration rejects forged or replayed attestations, non-canonical accounts, mismatched guardians, roots without a provider, and unsigned or changed DID files.

Add a shared ReputationRegistry, integrity contracts claim for ERC-173 recognition, and an authoritative pinned packHash used by BCC and pushed to Shield.

## C3. Verified memory requirement — M

Cortex provides store-wide append-only provenance metadata, encrypted content at rest, spot_check(root, index, nonce) returning H(nonce||content) plus proof, a provable root suitable for anchoring, hard purge of content/FTS/blobs/embeddings/replicas/keys within the declared retention boundary, a PHI-redaction hook, and pack-driven retention.

The oracle performs spot-checks without receiving PHI. Failures become MemoryUnavailable receipts. Historical roots may remain but contain no reconstructable PHI.

## C4. Human oversight — S

Escalation produces an approval receipt bound to the action HMAC. Both gates re-check it. Break-glass approvals are signed and expiring. pack simulate --since 90d runs before enforcement changes. Replayed, expired, wrong-action, wrong-pack, and wrong-agent approvals are rejected. Jev may recommend escalation and annotate the approval path; it cannot create or substitute for the approval receipt.

## C5. Cut over — M

- Run an Anvil regenesis dry-run.
- With owner approval, broadcast fresh Base Sepolia genesis.
- Preserve DIDs and valid history for 15 agents.
- Report agents without provider-backed memory as blocked.
- Move the legacy account and oracle path to integrity-lab.
- Rename integrity-core to integrity-kernel across active repositories.
- Rename dashboard plus user API to integrity-console.
- Build the CLI on the SDK and remove duplicate implementations.
- Remove the temporary repository-name compatibility alias.

## Gate C: real-funds and real-PHI readiness

Required:

- mediation proofs and conformance tests;
- forged-registration rejection;
- canonical account and kernel validation;
- provider-backed memory spot-check;
- digest-only fake fails;
- purged content is unrecoverable within the declared boundary;
- replayed approvals are rejected;
- over-budget UserOp reverts;
- regenesis dry-run preserves DIDs and valid history;
- no self-scoring;
- no stale load-bearing references to integrity-core.

## Final definition of done

The plan is complete only when:

- the active architecture has one authority per trust-bearing function;
- Shield and Cortex operate as separate tenant-isolated products;
- both products depend on Integrity-compatible contracts without requiring live public-chain availability;
- a third party can extend packs/adapters without gaining protocol authority;
- the active documentation set is consolidated and cross-linked;
- local pilot evidence, external integration evidence, and production-readiness evidence are clearly separated;
- the remaining deferred work is recorded in STATUS.md rather than scattered across competing plans.

# Risks and mitigations

| Risk | Mitigation |
|---|---|
| Scope creep | Six-function test, do-not-do list, and capped STATUS.md. |
| Kernel hardening stalls | Phase B ships local evidence without claiming real-funds readiness. |
| Integrity becomes a runtime bottleneck | Shield and Cortex enforce locally, queue receipts, and continue operating without public-chain or Oracle availability. |
| Products are technically impressive but not sellable | Phase B requires tenant isolation, operator workflows, entitlements, deployment packaging, exports, and pilot teardown. |
| Gate commoditization | Compete on anchored, independently verifiable evidence and regulation packs. |
| Regulated buyers distrust anchoring | Anchor roots and checkpoints only; document this in DATA.md. |
| Signature-format changes | Re-sign and bump schema; verifier accepts v1 during a defined transition window. |
| Pack evaluator drift | Shared compiler, pack hash, decision vectors, and deny-on-disagreement. |
| Memory purge ambiguity | Separate immutable provenance from purgeable encrypted content and keys. |
| Jev/provider drift | Pin model and rubric versions, record provider mode, maintain labeled decision vectors, recalibrate thresholds, and never transfer thresholds between hosted and compatible-local providers without validation. |
| False causal interpretation | Use typed observed/declared edges, explicit `causality_not_proven` status, and compliance exports that separate model annotations from policy and execution evidence. |
| DecisionTrace becomes a data-exfiltration path | Redact before gateway/telemetry, hash content by default, enforce tenant/store scope, and keep raw content inside Shield/Cortex boundaries. |
| Jev outage blocks enforcement | Jev is advisory; Shield/OPA/BCC continue deterministic operation, while high-impact actions fail closed or enter review according to policy. |
| External service unavailability | Keep local acceptance independent and classify external evidence separately. |
| Solo-developer review load | Group commits by phase and repository; use gates as review points. |

# Open questions not blocking Phase A

1. Whether stake is introduced later; v1 has none.
2. MIT versus open-core licensing for Shield and Cortex.
3. When Shield's SQLite pilot backend must become Postgres/HA.
4. SOC 2 Type II timing and the BAA template required for health buyers.
5. Whether the first hosted Jev budget is funded directly or routed through an approved provider gateway with separate quota accounting.
6. Which compatible-local fallback, if any, is acceptable for commercial data and which labeled corpus will calibrate it.

# Deferred work

| Area | Items |
|---|---|
| Regulation packs | EU AI Act pack before December 2027. |
| Exports and integrations | Drata/Secureframe, gRPC ext_authz PEP, ERC-7579 registry listing, ERC-8004 write-back. |
| Product platform | Shield macOS/Windows, LSM pre-blocking, DNS controls, Cortex team profiles. |
| Hooks | Codex and Agy DecisionTrace integrations; Hermes is the first supported observer. |
| Local inference | A Jev-compatible local provider, model operations, and production calibration are optional after the hosted/fixture path is proven. |
| Policy analysis | Formal SMT pack analysis. |
| Account and economics | Session keys, staking, paymaster, signing daemon. |
| Research | AIS predictive validation and ZK. |
| Documentation | Generated-facts documentation lint. |
| Revenue | Billing, payment processing, and automated invoicing. |
