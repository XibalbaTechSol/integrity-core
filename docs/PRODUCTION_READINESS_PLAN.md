# Integrity Core Protocol Production-Readiness Plan

**Status:** Active planning baseline; backbone protocol under heavy iteration, no
deployment/audit of promoted contracts, SDK unpublished
**Updated:** 2026-09-04
**Target:** A stable, versioned protocol backbone that `xibalba-shield` and
`xibalba-cortex` can build SaaS products on top of

## 1. Executive decision

`integrity-core` is **not itself a SaaS product** — it is the backbone protocol
(identity, on-chain reputation, BCC intent commitments, ZK proving, Oracle scoring, the
Python SDK/CLI, and the dashboard) that `xibalba-shield` and `xibalba-cortex` consume as
external, one-way dependents. Its production-readiness bar is therefore different from
theirs: this repo needs a **stable, versioned, independently trustworthy backbone**, not
a billable product surface. See §5, "Backbone contract," for what Core specifically owes
those two consumers.

This document restructures the existing append-style gap register
(`PRODUCTION_GAPS.md`, ~3855 lines, dated entries never silently rewritten) into a
gate-format readiness plan, matching `xibalba-shield`'s
`docs/PRODUCTION_READINESS_PLAN.md`. It summarizes that register's per-subsystem
Closed/Partial/Open state as of its final entries (through §65, `bb8b121`) rather than
re-deriving findings from scratch. `PRODUCTION_GAPS.md` remains the detailed,
line-item-cited source of record; this document is the gate-level index over it.

Two honest facts anchor this plan: (1) the promoted production kernel
(`IntegrityKernel.sol`/`IntegrityAccount.sol`, renamed from `...V1Experimental` on
2026-08-24) has **never been deployed anywhere, audited, or run past 6 machine-checked
Halmos properties on a subset of its configuration space**; (2) `integrity-sdk` is
version `0.1.0`, `Development Status :: 3 - Alpha`, and has never been published — every
current consumer, including `xibalba-cortex`, depends on it via a local filesystem path
to a sibling checkout.

Production readiness is an evidence threshold. A feature is not complete because code
exists, a Foundry test passes, or a testnet transaction was submitted once.

## 2. Readiness levels

### L0 — Research / active iteration (current baseline)

- Real, live-tested Oracle (SSE streaming, OTLP ingestion, server-side signal
  re-derivation, on-chain score push, Verification Ladder rungs 1-3), a real ZK circuit
  wired end-to-end, a real BCC middleware with active quarantine enforcement, real
  userapi auth, and a dashboard with disclosed (not silent) mock surfaces where no
  backend exists.
- A promoted-but-undeployed production kernel/account pair with 6 proven Halmos
  properties on the registry-*disabled* configuration only.
- An ERC-4337 licence-account reference stack deployed and exercised once on Base
  Sepolia — explicitly "experimental, unaudited testnet deployment... illustrative
  parameters."
- `integrity-sdk` at 0.1.0/alpha, local-path-only consumption; `integrity-cli` as an
  independent, non-shared-library reimplementation of the same functionality.

### L1 — Backbone pilot (consumable by one real downstream SaaS pilot)

Exit requires all of the following:

- `integrity-sdk` published as a real, version-pinned installable package (closes the
  hard blocker in both `xibalba-cortex`'s and any future `xibalba-shield` SDK-facing
  production plan).
- A documented semver/deprecation policy for the SDK and CLI, covering the fact that
  they are independent reimplementations kept in sync only by cross-package round-trip
  tests today — no changelog discipline or version-pin enforcement exists currently
  (confirmed: no PyPI reference anywhere in `integrity-sdk/pyproject.toml` or README).
- Oracle production key-separation actually enforced (today `ANCHOR_SIGNER_PRIVATE_KEY`
  equals both the `oracleSigner` and `disputer` on-chain roles; a separate
  `REPUTATION_SIGNER_PRIVATE_KEY` seam exists but nothing forces its use).
- The registry-enabled kernel `preCheck` gas gap closed or explicitly re-scoped (see
  Workstream B) and Halmos coverage extended to the registry-*enabled* configuration —
  currently zero symbolic coverage exists for it.
- At least one of the two AIS scoring floor decisions (§ Workstream A) made
  non-blocking: the repo's own 2026-08-17 decision to wait for a second registered
  agent before picking component floors cannot hold indefinitely once a downstream
  pilot depends on the score being meaningful.

### L2 — Hardened backbone production

L2 adds: an independent security audit of the promoted kernel/account contracts before
any real-value deployment; a real deployed-and-verified `IntegrityKernel` on at least
one production chain; resolved dispute-detection beyond the current flagged-ratio
heuristic; a durable local export/spool queue in `bcc_middleware` so an oracle outage
cannot silently drop an audit report; horizontal scale-out for the Oracle and
`bcc_middleware`'s currently in-memory nonce/circuit-breaker state; and a unified
cross-runtime telemetry contract (today Claude Code, Hermes, and agy each run
incompatible partial instrumentation loops with no common per-runtime grouping in the
Oracle).

### L3 — Ecosystem and licence-economy expansion

Live bundler/EntryPoint transactions and funded paymaster sponsorship for the
ERC-4337 licence-account path, a real DEX price oracle and slashing policy for
`LicenceEconomy`, production multi-party governance for the fee router, and general
multi-asset value-conservation coverage beyond the one currently-declared ERC-20 token
are L3 deliverables — explicitly out of scope for L1/L2.

## 3. Protocol invariants

These are the non-negotiable design rules the gap register already enforces
implicitly; stated explicitly here the way Shield's plan states its own:

1. **AIS is computed in exactly one place** — Oracle's `scoring-core`. No consuming
   repo (including this one's own dashboard) may compute or approximate a score
   locally.
2. **Tier 1 deterministic policy/scoring inputs are re-derived server-side, never
   trusted verbatim from a signed client claim** — a signature proves *who* sent data,
   never *whether it's honest*. This is why the Oracle independently recomputes
   entropy/grounding/sacrifice from raw signed `otel_spans` rather than storing a
   client's self-reported `derived_signals`.
3. **Chain is the source of truth.** A cached or cross-chain primitive must never be
   served as an authoritative 200 when the chain itself doesn't have the record — this
   invariant is currently *violated* by the Oracle in one disclosed, unfixed case (see
   Workstream A) and is listed here as the acceptance bar for closing it, not a claim
   it already holds.
4. **BCC commitment shape is frozen** — only `integrity_sdk.bcc.build_bcc_commitment`
   constructs one; no downstream repo (Shield included, per its own CLAUDE.md) may
   invent its own commitment fields.
5. **No silent mocks.** A disclosed-mock or intentionally-unbuilt surface must say so in
   its own docstring/README/UI badge, not imply completeness — the dashboard's
   `SeededDataBadge` pattern is the reference implementation of this rule.
6. **"Tamper-evident" is not "root-resistant."** Any evidence or logging claim in this
   protocol must state which threat model it actually defends against, matching the
   same distinction Shield's plan already draws for its own local logs.
7. **A promoted contract name does not imply an audited or deployed contract.** The
   2026-08-24 `...V1Experimental` → `IntegrityKernel`/`IntegrityAccount` rename was
   naming-only; nothing about production-readiness moved with it.
8. **The accepted normative baseline is a specific, versioned document, not "whatever
   the whitepaper currently says."** `docs/archive/2026-08/integrity-protocol-v0.4.md`
   is the accepted baseline; `docs/WHITEPAPER.md` (v3.2) is current explanatory
   documentation; `docs/archive/2026-08/integrity-protocol-v0.5-proposed.md` is **not
   accepted**. A further, narrower cutover to `docs/SPEC.md` (via
   `docs/DOCUMENT_STATUS.yaml`) is already cited as the current normative source for at
   least Phase III adapter-registry work — this document's own top-of-file pointer has
   not been updated to say so, a real doc-drift item worth closing (see Workstream G).

## 4. Workstreams

### A. Oracle scoring and trust boundary

**Closed:** SSE streaming proven bit-identical to direct AIS reads; OTLP gRPC ingestion
with rate limiting; server-side re-derivation of entropy/grounding/compliance from raw
signed span content, replacing trust in client-reported values; on-chain score push and
dispute-raising (21 real tests against anvil); durable audit-log storage; Verification
Ladder rungs 1-3 (DNS TXT, GitHub identity, AWS Nitro TEE) live-tested; tier-ceiling
clamp pinned by 8 Foundry ladder tests; deployed-vs-source drift detection.

**Still open:**
- AIS scoring §3.1.4 gaps remain: compliance is still self-reported for non-healthcare
  agents with no independent evidence requirement; sacrifice is still self-reported
  token counts, not validator/TEE-attested; no per-component floor/conjunctive gate
  exists (a 90%-violation agent can still score ~0.631, not zero); reported `ais` is
  post-boost/unclamped rather than the pre-boost `[0,1]`-clamped value the spec wants
  as the real constraint input. Floor-value selection is explicitly deferred pending a
  second real registered agent (decision recorded 2026-08-17) — this cannot remain
  deferred once a downstream SaaS pilot depends on the score.
- `lexical_stability_score` is mis-specified (measures repetitiveness, not stability) —
  identified, deliberately not fixed pending a dual Python+Rust bit-identical change and
  a live-score-movement validation pass.
- **Closed 2026-09-05** (PR #85, `fix/oracle-chain-scoped-cache`, verified against live
  code this session, not just the merge log): the chain-is-source-of-truth violation
  (§3 item 3) is fixed. `get_agent`, `resolve_primitives_row`, and the leaderboard cache
  path (`handlers.rs`, tagged `E11` at each site) now only trust a cached primitives row
  if it was resolved against the oracle's *currently configured* chain id; a row from a
  different chain, or `NULL` (predates the chain-id column), is treated exactly like a
  cache miss and never served as-is — falling back to a live chain re-resolution rather
  than a stale-chain answer. Real e2e coverage exists
  (`integrity-oracle/backend/tests/e2e.rs`, `wrong_chain`/`legacy_null_chain` cases) but
  needs `ORACLE_E2E=1` and a live test database to execute, not run in this pass.
- `covered_entity_address` spoofing: the Oracle trusts a client-supplied compliance
  address with no on-chain ownership check.
- Single signer for oracle/disputer roles in the current deployment; a
  `REPUTATION_SIGNER_PRIVATE_KEY` separation seam exists but is not enforced.
- Dispute signal remains a flagged-ratio heuristic, not a real BCC-commitment-vs-
  on-chain-action comparator, which doesn't exist yet.
- ZK-boost binding is period-wide (`BOOL_OR` over the whole reporting window), not
  per-event — needs a circuit/on-chain change.
- Nonce race under load-balanced RPC (`nonce too low` recurring even after chain-id fix
  and process-wide lock) — leading hypothesis is stale RPC reads, unconfirmed.
- In-memory `nonce_store`/circuit-breaker state blocks horizontal Oracle scale-out
  (not urgent at current single-instance scale, but real).

### B. Kernel and account contracts (Phase I: `IntegrityKernel`/`IntegrityAccount`)

**Closed:** value-conservation budget, module-governance timelocked kernel-swap,
guardian M-of-N execution quorum and unanimous emergency propose/cancel, guardian-set
rotation, kernel-swap reentrancy guard for the fallback path, reputation-floor and
assurance-tier adapters with epoch-snapshotting, 6 machine-checked Halmos properties
proven unbounded for the base (registry-disabled) kernel configuration. **Closed
2026-09-05:** Halmos coverage for the registry-ENABLED configuration
(`test/halmos/KernelPropertiesRegistryEnabled.t.sol`, via
`HalmosKernelFixture._deployRealKernelWithRegistry`) — 3/3 properties passed: budget
containment and the reentrancy guard both hold unchanged with a real, registered,
passing `ReputationFloorAdapter` installed, and a new property proves the registry
adapter's floor and the kernel's own cached floor are each independently, conjunctively
enforced across the full symbolic score range (neither ever substitutes for the other).
This closes the "zero Halmos coverage for registry-enabled" gap listed below, but does
NOT close the separate registry-enabled gas-ceiling gap (still open, see below) — a
Halmos property proves logical soundness, not gas cost.

**Still open:**
- **No deployment anywhere**, no independent/external audit, and no machine-checked
  invariance argument beyond the 6 proven properties — the 2026-08-24 rename to
  production names changed nothing about this.
- Multi-asset value conservation (declared ERC-20 budget) measures ~41k gas, over the
  whitepaper's Table 4 `<=40k` `preCheck` ceiling — disclosed, unmitigated; general
  value-conservation scope beyond one declared token is an open design question.
- **Registry-enabled `preCheck` gas gap** (tracked separately in project memory,
  independently re-verified from `PRODUCTION_GAPS.md` §54-55): mitigated from ~59.2k
  gas to 49,290 gas (a real ~16.7% reduction, commit `d1e59eb`) — still **~9.3k gas
  over** the `<=40k` ceiling. Closing the rest needs either a cheaper adapter body or a
  rework of `AdapterRegistry`'s installability semantics.
- ~~**Halmos has zero coverage for the registry-enabled configuration**~~ — **closed
  2026-09-05**, see above.
- A second, broader reentrancy exception remains: `approveKernelSwap`/guardian-action
  entry points are deliberately never routed through the reentrancy hook (would be
  circular otherwise) — a disclosed, accepted design exception, not a bug, but real
  attack surface.
- The "broken-kernel-brick" scenario (a malicious/buggy kernel that passes the
  interface probe but reverts unconditionally in `preCheck`) is architecturally
  un-rescuable for account repair — investigated and confirmed impossible without
  forking the underlying account-abstraction base contract. Mitigated only by a
  guardian emergency funds-sweep, which drains value rather than repairing the account.
- `epochLengthSeconds` (reputation-cache freshness) vs. `moduleActionTimelockSeconds`
  (governance timelock) is an unenforced cross-contract deployment invariant — a
  misconfigured deployment can produce a stale-on-arrival kernel after a swap.
- Guardian mechanisms all carry the standing caveat that collusion/compromise at
  threshold is unverifiable on-chain by construction.

### C. SDK, CLI, and cross-language contracts

**Closed:** registration ordering and full idempotency in both SDK and CLI
(progress-file + bytecode verification before trusting a recorded address); Nitro
attestation test coverage (found and fixed a truncated root-CA fingerprint that made
verification completely non-functional in production, silently, until tests first ran);
wallet keystore atomic-write race; SDK-generated float-canonicalization ambiguity
(quantized to 6dp, SDK-generated floats only).

**Still open:**
- `redact_phi` defaults to **False** on OpenAI/LangChain telemetry integrations — an
  explicit, accepted behavior change requiring healthcare-vertical agents to opt in,
  with **no runtime enforcement** preventing a misconfigured healthcare deployment from
  shipping unredacted data. A `health.py`-level guard is logged as a follow-up, not
  built.
- General float-canonicalization (RFC 8785/JCS) remains a wire-contract change across 4
  packages, out of scope for the narrower SDK-only fix — a caller-supplied arbitrary
  float can still hit the ambiguity.
- Non-ASCII canonical-JSON divergence between Rust (`serde_json`) and Python
  (`ensure_ascii=True`) is documented and unfixed.
- `register_agent()`'s `resolve_did` short-circuit can skip genesis memory anchoring
  entirely for an already-deployed agent, leaving it permanently oracle-unregistrable
  until manually anchored — reproduced live for one real agent, worked around manually,
  not fixed in the SDK itself (`registration.py` lines ~214-243 need the same
  anchor-if-zero check the main path already has).
- Duplicate `#evm-1` verification-method entries in at least one agent's `did_document`
  — cosmetic, uninvestigated.
- **SDK and CLI are independent reimplementations, not a shared library** — kept in
  sync only by cross-package round-trip tests, doubling the surface a versioning policy
  must cover.
- **`integrity-sdk` is unpublished (0.1.0, alpha, no PyPI reference anywhere).** Every
  downstream consumer resolves it via a local filesystem path to a sibling checkout.
  This is the single largest blocker to either downstream SaaS repo's own standalone
  installability. See §5.

### D. BCC middleware

**Closed:** hot-path event-loop blocking removed; HMAC-keyed verification tokens;
cross-thread signer nonce race; `POST /v1/bcc/anchor/flush` root-mismatch bug fixed;
redundant score-push elimination; active quarantine enforcement (deliberately
**fails open** on an unverifiable dispute check — a considered tradeoff, disclosed, not
an oversight); `chain_id`/`verifying_contract` deployment-binding check for both the
non-ZK BCC commitment (closed earlier) and the ZK circuit's `intent_commitment` Pedersen
hash (closed later, same binding now covers both paths). **Closed 2026-09-05:** durable
local audit-report spool (`app/spool.py`) — a failed `report_decision`/
`report_anchor_events` POST is now written to a local SQLite file and retried by a
periodic background loop (`SPOOL_RETRY_INTERVAL_SECONDS`, capped exponential backoff per
row, `SPOOL_MAX_BACKOFF_SECONDS`) instead of being silently and permanently lost.
Verified against a real local HTTP server (not mocked): a decision reported while the
"oracle" returns 503 is spooled, stays pending across a retry attempted while still
down, and delivers with the original payload intact once the server recovers.
`GET /v1/audit/spool/status` / `POST /v1/audit/spool/retry` are the new ops hooks.

**Still open:**
- Merkle anchoring remains batch-size-triggered only; no periodic anchoring loop.
- In-memory nonce/circuit-breaker state blocks horizontal scale-out (same class of gap
  as the Oracle's).
- The audit spool is single SQLite file, single-process/single-replica (disclosed,
  same scope-limitation class as the in-memory state above) — a multi-replica
  deployment needs a shared durable queue instead. Rows are retried indefinitely with
  capped backoff, never dead-lettered — a prolonged outage grows the file unboundedly;
  no operator alert exists yet beyond polling `GET /v1/audit/spool/status`.

### E. ZK circuit (`integrity-zkp`)

**Closed:** `chain_id`/`verifying_contract` binding added to the Pedersen
`intent_commitment` hash, closing the ZK half of the cross-deployment replay gap;
`prover.py` now genuinely wired to the real circuit (previously pointed at a placeholder
with zero call sites); the UltraPlonkVerifier is a real generated verifier with
direct-fixture-proof coverage.

**Still open:** registry forwarding, fresh-environment proof regeneration, and deployed
on-chain verification remain separate, not-yet-closed items beyond direct-fixture
coverage.

### F. ERC-4337 licence-account path (Phase II) and adapter registry (Phase III)

**Closed:** ERC-4337/ERC-6551 dual-surface `LicenceAccount` with session-key
restriction; allowlisted paymaster with per-op cost cap; six typed licence terms behind
a fail-closed typed-consume route; licence-economy fee router with governance delay; the
full reference stack deployed and verified on Base Sepolia with one real live `consume`
transaction reconciled end-to-end. `AdapterRegistry` R3 (bounded cost) is real; R1
(determinism) has a genuine off-chain differential-replay admission-suite tool; R5
(Identity — published source + machine-readable semantics + version hash) closed via
`publishIdentity()`, with the standard disclosed limitation that the registry cannot
verify `metadataURI`'s content matches `specHash`.

**Still open:**
- No live bundler/EntryPoint transaction and no funded paymaster sponsorship (deposit
  is zero).
- No DEX price oracle, slashing policy, or production multi-party governance for the
  licence economy router.
- External-adoption evidence gate requires live receipts plus human-reviewed
  counterparty evidence — neither exists yet.
- No independent audit of this contract family; explicitly described in its own repo as
  "experimental, unaudited testnet deployment... illustrative parameters."
- The general adapter-encoding-strategy question referenced in
  `docs/design/phase3-adapter-encoding-strategy-2026-08-25.md` remains open in that
  design doc, not resolved here.

### G. Governance, dashboard, and documentation integrity

**Closed:** on-chain governance deployed and live on Base Sepolia, wired into the
dashboard for voting; extensive dashboard remediation — essentially every previously
undisclosed-mock or dead-button surface across the app was either wired to real data or
given an honest `SeededDataBadge`/disabled state.

**Still open:**
- Governance `propose`/`queue`/`execute` is deliberately never wired to any UI or
  CLI/SDK path — a disclosed security-review scope decision, not a time gap.
- Deliberately disclosed-not-real dashboard surfaces remain by design (Documents/RAG
  tab, Contracts Build/Deploy IDE, agent-hiring marketplace, several finance/health
  aggregate widgets, TEE "Regenerate Attestation") — these are correctly labeled, not a
  gap to close, but must stay correctly labeled as the dashboard evolves.
- A GET-route naming trap remains undeferred: `GET /v1/agent/{id}/traces` returns
  judge-evaluation records, not spans — a wire-contract rename deferred, not fixed.
- **Documentation pointer drift:** this repo's own top-of-file normative pointer
  (`PRODUCTION_GAPS.md`) still names `docs/archive/2026-08/integrity-protocol-v0.4.md`
  as the accepted baseline, while a later, narrower cutover already cites `docs/SPEC.md`
  (via `docs/DOCUMENT_STATUS.yaml`) as the current normative source for at least Phase
  III adapter-registry work. The top-level pointer was never updated to reflect this.
  This document's own §3 invariant 8 states both facts; closing the drift means
  updating `PRODUCTION_GAPS.md`'s own header, not just noting it here.

### H. Cross-runtime telemetry and dogfooding

**Closed (representative):** per-agent OTel `TracerProvider`s fixed (previously a
global-singleton trap); span flush-on-exit; funder-balance preflight; SSE
connection-pool exhaustion fixed via shared/ref-counted `EventSource`; the Claude Code
harness dogfooding loop's BCC gate fixed after being structurally blind (0 denials out
of 792 logged decisions) by adding a real risk-class label.

**Still open:**
- Three runtimes — Claude Code, Hermes, agy — run three incompatible partial
  instrumentation loops; no runtime has pre-exec gate + per-action telemetry + memory
  anchoring all three simultaneously, and the Oracle doesn't group scoring by runtime
  yet.
- Hermes' `post_llm_call` hook still doesn't pass token usage upstream, so `sacrifice`
  stays absent for Hermes-attributed work — deliberately not estimated or faked.
- The Claude Code PreToolUse hook is ratified fail-open by design (developer shell),
  an intentional asymmetry against `bcc_middleware`'s fail-closed production posture —
  disclosed, not accidental.
- Nothing detects deployed-vs-source drift automatically beyond the manual
  `make check-deploy` step.

### I. `integrity-userapi` and MCP signing-tool boundary

**Closed:** API-key auth, JWT revocation (`jti` + self-pruning `revoked_tokens` table),
login rate-limiting, `demo_runs` completion lifecycle; `integrity_sdk/mcp_server.py`'s
signing/on-chain-write tools (register, flush-telemetry, invoke-intent, commit-memory)
disabled by default at both discovery and dispatch, gated behind explicit opt-in, with a
new fail-closed parameter specific to this tool class (existing Bash/Write/Edit coverage
remains deliberately fail-open, untouched).

**Still open:** none named specifically for this workstream beyond what's already
covered under C (SDK) and A (Oracle) — this workstream is comparatively closed relative
to the rest of the register.

## 5. Backbone contract — what Core owes Shield and Cortex

This section exists because Core is infrastructure for two downstream SaaS products,
not a SaaS product itself. Neither `xibalba-shield` nor `xibalba-cortex` can finalize
their own production timelines without these commitments from Core:

1. **A published, version-pinned `integrity-sdk` release.** Today it is 0.1.0/alpha,
   consumed only via local path. Both `xibalba-cortex`'s own production plan (Gate 2,
   "Standalone deployability") and any future Shield SDK dependency are blocked on
   this. This is the single highest-leverage item in this entire document for
   unblocking the other two repos.
2. **A stated semver and deprecation policy**, covering the fact that `integrity-sdk`
   and `integrity-cli` are independent reimplementations kept in sync only by
   cross-package round-trip tests — a downstream consumer pinning an SDK version has no
   guarantee today about what changes underneath it between versions.
3. **Change-visibility for downstream consumers.** A real precedent already exists for
   this failing silently: a stale, non-editable `integrity-sdk` install in
   `xibalba-cortex`'s own venv would have broken on the `chain_id`/`verifying_contract`
   signature change had it not been caught opportunistically. A publish/changelog
   process must close this class of gap, not rely on opportunistic discovery.
4. **Oracle multi-tenant auth and a stated uptime commitment**, once either downstream
   product depends on Oracle scoring for real customer-facing behavior — today the
   Oracle has no multi-tenant concept of its own and only a single production agent is
   registered.
5. **An explicit support boundary.** Per each downstream repo's own CLAUDE.md, Shield
   and Cortex consume Core as external, unprivileged callers — no special-cased access,
   no privileged API. This document does not change that; it only makes explicit that
   Core's own readiness gates (especially §4.A's Oracle scoring gaps and §4.C's SDK
   publication gap) sit on the critical path for both downstream repos' own L1 gates.

## 6. Release gates

### Gate 1 — Normative baseline consistency

Pass when `PRODUCTION_GAPS.md`'s own top-of-file pointer is reconciled with the
`docs/SPEC.md`/`docs/DOCUMENT_STATUS.yaml` cutover already in effect for Phase III work
(Workstream G), so there is one unambiguous current normative source, not two competing
pointers.

### Gate 2 — SDK publication and versioning

Pass when `integrity-sdk` is published as a version-pinned installable package with a
stated semver/deprecation policy covering both the SDK and CLI (§5 items 1-2).

### Gate 3 — Oracle scoring integrity

Chain-is-source-of-truth is fixed (closed 2026-09-05, see Workstream A). Remaining to
pass: signer role separation enforced in production configuration, and at least an
interim component-floor decision made for AIS scoring rather than indefinitely deferred.

### Gate 4 — Kernel deployment readiness

Pass when the registry-enabled `preCheck` gas gap is closed or explicitly re-scoped,
Halmos coverage exists for the registry-enabled configuration (closed 2026-09-05, see
Workstream B), and an independent security audit of `IntegrityKernel`/`IntegrityAccount`
is scheduled or complete — promotion-in-name-only is not sufficient (§3 invariant 7).
Remaining to pass: the gas gap and the audit.

### Gate 5 — Evidence continuity

`bcc_middleware`'s durable local export/spool queue (closing the audit-report-loss-on-
outage gap) closed 2026-09-05 — see Workstream D. Remaining to pass: Merkle anchoring
moves from batch-triggered-only to a real periodic loop.

### Gate 6 — Cross-runtime telemetry contract

Pass when at least one runtime (Claude Code, Hermes, or agy) has pre-exec gate +
per-action telemetry + memory anchoring unified in one loop, and the Oracle groups
scoring by runtime.

### Gate 7 — Downstream unblocking

Pass when both `xibalba-shield` and `xibalba-cortex` confirm their own SDK-dependent
production gates (Cortex's own Gate 2, "Standalone deployability") are unblocked by
Gates 2-3 above.

## 7. Immediate implementation sequence

1. Publish `integrity-sdk` as a real, version-pinned package — this single item
   unblocks the most downstream work across all three repos (§5 item 1). Proven
   publishable on TestPyPI (2026-09-04); real publish still needs the account holder's
   own PyPI credentials.
2. ~~Reconcile the normative-baseline pointer drift~~ — **closed 2026-09-05**: fixed in
   `PRODUCTION_GAPS.md` and every other living reference doc that had drifted from
   `docs/DOCUMENT_STATUS.yaml` (Gate 1).
3. ~~Fix the chain-is-source-of-truth violation in the Oracle~~ — **closed 2026-09-05**
   (verified against live code, landed via PR #85 slightly earlier): see Workstream A.
4. Extend Halmos coverage to the registry-enabled kernel configuration and re-attempt
   the registry `preCheck` gas mitigation (Workstream B) — needed before any kernel
   deployment can be responsibly scheduled.
5. Add a durable local export/spool queue to `bcc_middleware` (Workstream D) — closes a
   real evidence-loss window that a production pilot on either downstream repo would
   inherit.
6. Schedule an independent security audit of the promoted kernel/account contracts
   before considering any real-value deployment (Gate 4).
7. Make an interim AIS component-floor decision rather than waiting indefinitely for a
   second registered agent (Workstream A) — once a downstream SaaS pilot depends on
   the score, "wait for more data" stops being a safe default.

## 8. External gates that cannot be completed locally

- An independent, funded security audit of `IntegrityKernel`/`IntegrityAccount` and the
  ERC-4337 licence-account contract family.
- A real second (and further) registered agent, needed to make AIS component-floor
  values meaningful rather than deferred indefinitely.
- Production PyPI publishing infrastructure and package-signing/provenance for
  `integrity-sdk`.
- Funded paymaster sponsorship and a real bundler/EntryPoint transaction for the
  licence-account path (L3, not on the L1/L2 critical path).
- A live pilot from at least one downstream repo (Shield or Cortex) actually depending
  on Oracle scoring, needed to validate Gate 3 and Gate 7 against real usage rather than
  synthetic/single-agent data.

## 9. Definition of done for backbone pilot-readiness

`integrity-core` may be called **backbone pilot-ready** only when Gates 1-6 pass and
Gate 7 confirms both downstream repos' own SDK-dependent gates are actually unblocked in
practice, not just in principle. Any future revision of this document must re-verify
its Closed/Partial/Open claims against `PRODUCTION_GAPS.md`'s current final entry and
live `git log`/`git status`, the same discipline used to write it — this is a snapshot,
not a frozen contract.
