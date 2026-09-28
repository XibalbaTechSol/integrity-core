# Execution Plan: The Xibalba Ecosystem, Balanced and Monetizable

**Status:** Final draft, pending owner approval. Once approved, Phase A5 makes this the single
execution-plan authority in `docs/DOCUMENT_STATUS.yaml` and archives the plans it supersedes.
**Scope:** integrity-core (renamed integrity-kernel in C5), xibalba-shield, xibalba-cortex, and two
new repositories: integrity-console and integrity-lab.
**Grounded against:** `main` @ `d22128b` (2026-09-28), plus the repository review recorded in
[Appendix A](#appendix-a-pre-execution-review-2026-09-28).

## 1. Objective and governing principle

Leave the ecosystem with a simpler architecture, one coherent documentation system, and two
independently deployable, monetizable SaaS products, Shield and Cortex. Both depend on a small,
stable Integrity trust substrate.

Judge every component by the job it does, not by who calls it today. There are six jobs:

| Function | Implemented by |
|---|---|
| Identity | DID file, agent account, registry, XNS handle |
| Rules | Signed packs and deterministic adapters |
| Enforcement | Shield/BCC off-chain; kernel on-chain |
| Evidence | Signed receipts, evidence-anchor roots, offline verify |
| Feedback | AIS |
| Access | SDK, CLI, hooks |

Anything new must name the function it serves and the gate it satisfies. Work that serves no function
is deferred. Integrity is essential to trust-bearing artifacts, but it must never become a runtime or
availability bottleneck for Shield or Cortex.

## 2. Desired outcomes

1. **Simplified architecture.** One authority each for identity, packs, receipts, verification,
   anchoring and AIS. No duplicate kernel, adapter, policy, memory or canonicalization authorities.
2. **Consolidated documentation.** This plan plus a small set of authoritative domain documents.
   Superseded material goes to integrity-lab.
3. **Monetizable Shield.** Tenant-isolated policy enforcement, device control, compliance evidence
   and exports.
4. **Monetizable Cortex.** Tenant-isolated governed memory, provenance, retention, retrieval and
   evidence.
5. **No runtime lock-in.** Shield and Cortex produce Integrity-compatible artifacts and keep working
   when anchoring, the oracle or vendor services are down.
6. **Safe extensibility.** Third parties build deterministic off-chain adapters and packs against
   documented SDK contracts, without authority over the kernel, receipts or anchors.
7. **Honest readiness boundary.** Local pilot, external integration, real-funds and real-PHI evidence
   are reported as separate classes.

## 3. Products and boundaries

```text
CUSTOMER BOUNDARY                                      INTEGRITY TRUST LAYER
harness root: agent.did.json (public)                  packs + adapters
key store: outside the harness root                     │
        ├── Shield: on-device gate ── signed receipts ─┤
        │                                               ├── evidence anchor (roots, checkpoints)
        └── Cortex: memory/content ── provenance ──────┤
                                                        ├── AIS feedback
                                                        └── console / exports
```

| Repository | Role |
|---|---|
| xibalba-shield | On-device enforcement product (SaaS) |
| xibalba-cortex | Memory, content and provenance product (SaaS) |
| integrity-core → integrity-kernel | Trust substrate: SDK, contracts, oracle, BCC, CLI |
| integrity-console (new) | Operator UI and user API: dashboard, userapi, demo |
| integrity-lab (new) | Frozen mirror of removed, historical and deferred code |

**What each promises:**
- **Shield:** enforce AI-agent policies at the customer boundary, with independently verifiable
  evidence.
- **Cortex:** governed agent memory and content provenance, with Integrity-backed identity, receipts,
  retention and retrieval evidence.
- **Integrity:** portable, verifiable evidence that no single party can quietly rewrite.

**Runtime rules:**
- Shield keeps enforcing locally if the chain, the oracle or hosted Integrity services are down.
- Cortex keeps storing and retrieving locally if anchoring is down.
- Receipts queue for later anchoring. Anchoring and vendor integrations enhance evidence; they are
  never availability dependencies.
- Customer content stays inside the declared Shield/Cortex boundary.

## 4. Fixed owner decisions

**Repositories**
- Split the dashboard, userapi and demo into integrity-console in A1.
- Rename integrity-core to integrity-kernel in C5.
- Cut removed code into integrity-lab.
- Until C5, new code uses repository-neutral names. GitHub's rename redirect is the interim alias.

**Keep**
- Health, XNS, integrity-cli, BCC, OPA, and AIS as the feedback loop.
- Kernel-only agent accounts as the target model, with the bridge code in the SDK.
- Persistent memory and an agent-owned contract as registration requirements.

**Identity layout (decided and implemented, `ad56d97`)**
- The harness root holds only a public `agent.did.json`.
- Private keys live outside every harness root: `$INTEGRITY_DID_HOME` or `~/.integrity/did`, under
  `profiles/<root hash>/`, with mode 0600 inside 0700 directories.
- The harness root is never chosen by env-var precedence. `INTEGRITY_PROFILE_ROOT` disambiguates.
- Legacy in-root keys are relocated on first use: copy, verify, then delete.

**Registration until C2**
- `registerCore` (SovereignAgent + StateAnchor, no ITK bond) with an Oracle-local XNS handle is the
  interim default. No further registration paths are added before C2.
- The Base Sepolia factory predates `registerCore`, so new testnet registrations use
  `full_registration=True` until the C5 genesis.

**Cut**
- ZK tooling, markets, licence, CCIP, governance, and the on-chain adapter registry, all subject to
  the ordering constraints in §8.

**Defer**
- Session keys, staking, paymasters, tokens, the signing daemon, formal SMT analysis, extra harness
  hooks, and billing code.

**No custom factory in v1**
- Accounts deploy through the standard deterministic CREATE2 deployer. The account address is
  therefore known before its kernel is deployed, with no nonce prediction.
- Canonicality is verified by the registrar (C2). If that proves brittle, a minimal factory is the
  fallback.

## 5. Shared SDK contracts

| ID | Contract |
|---|---|
| C1 Canonical bytes | JCS (RFC 8785) is the only canonicalization for anything hashed or signed. |
| C2 Identity | The public DID file is separate from the agent signing key and the device key. The signing key never lives in a harness root. |
| C3 Pack | A signed bundle covering every file, including Rego. `permit` means permitted. Each event class declares its no-match default (`deny`, `log_only` or `permit`). A missing, malformed, unknown or incompatible *decision* always denies. `INTEGRITY_*` reason codes are reserved for the gate itself. |
| C4 Receipt | A signed, chained decision record: `receipt_version`, `agent_did`, `device_id_hmac`, `action_hmac`, `pack_hash`, `decision`, `reason_code`, `seq`, `prev_hash`, `timestamp`, `checkpoint_reference`. The gate or device key signs it. HMAC protects identifiers; it is not the authenticity mechanism. |
| C5 Hook | The runner calls the local Shield gate if present, otherwise BCC. |
| C6 Memory provider | Genesis, append-only provenance metadata, and nonce spot-checks returning `H(nonce‖content)` with a proof. Encrypted content is required in the regulated profile. |
| C7 Data boundary | Customer content stays in the customer environment unless it is classified as permitted metadata. |

**Versioning:**
- The contracts follow semver.
- Receipts carry `receipt_version`, packs carry `kernel_range`, and adapters declare the contract
  version.
- Breaking changes ship with a transition window in which verifiers accept the prior version.

**Adapters:**
- Adapters run only at compile time (CLI or CI), never inside a gate. Their output is a pack the
  operator reviews and signs.
- The conformance kit enforces determinism, with no network or filesystem access under test.
- Adapters cannot override deny, sign receipts, anchor evidence, change kernel parameters outside the
  pack contract, or cross tenant boundaries.
- There is no on-chain adapter registry and no runtime sandbox in v1.

## 6. Trust, receipt and memory models

- **The organization** holds the guardian, HMAC and encryption keys, and funds gas.
- **The registrar/oracle** can censor or move AIS, but cannot impersonate an agent.
- **Anchors** store roots and signed checkpoints only: never raw records, never PHI.
- **The kernel** mediates value inside the account; value leaving the account counts as spent.
- **Agent keys** (0600, outside the harness root) are still readable by a same-user process. Shield
  protects key paths on managed devices; a signing daemon is deferred.
- **Offline verify** proves signature validity, chain position, inclusion and anchoring. It cannot
  recover HMAC-protected identifiers without the organization's key.
- **Cortex memory:**
  - an immutable provenance log (event IDs, timestamps, pack hashes, receipt references, content
    commitments), kept separate from purgeable content (content, FTS indexes, blobs, embeddings,
    keys);
  - purge destroys content and decryption material within the declared retention boundary;
  - historical roots stay, but must not allow PHI reconstruction.

## 7. Not done in v1

- A kernel rewrite, an on-chain policy compiler, or an on-chain adapter registry.
- A custom factory.
- A memory checkpoint chain beyond provenance/root evidence.
- Session keys, staking, paymasters, tokens, the signing daemon, or billing code.
- Formal SMT analysis, or LLM-judged rules in a gate.
- Codex, Agy or Hermes hooks (Claude Code comes first).
- A runtime adapter sandbox.
- Any public-chain or vendor dependency for local demos, tests, acceptance, or normal runtime
  enforcement.

## 8. Execution model

**Gates:** architecture and documentation (A) → sellable pilot (B-local) → optional integrations
(B-integrations) → production trust (C). A failed required gate stops the run with a report.

**History:** commit series grouped by phase and repository on `claude/quirky-wright-g7yl7g`, plus one
branch per sibling repository. Draft PRs open as each repository's Phase A goes green.

**Phase A order:** **A0 → A4 → A2 → A1 → A3 → A5 → A6.** The order is forced by dependencies found in
review:

| Constraint | Consequence |
|---|---|
| `IntegrityKernel` imports `AdapterRegistry`/`IAdapter` | A4 removes that branch before A1 cuts `registry/` |
| `Slasher` (a kept clone template) imports `IntegrityToken` | $ITK stays until Phase C |
| `ReputationRegistry`/`VerifierRegistry` import `IZkVerifier` | A1 cuts only `integrity-zkp`, `UltraPlonkVerifier` and the SDK prover; ZK interfaces stay until C |
| `health.py` (kept) imports `markets._execute_via_agent` | The helper moves before `markets.py` is cut |
| SDK `__init__` eagerly imports `auto_hook` and `integrity.py` | A2's lazy init lands before A1's SDK cuts |
| `test_agent_runtime.py` and `__main__.py` use `mcp_server` | Identity helpers already moved to `did.py` (`ad56d97`); the rest move in A2 |
| The demo imports `markets.allocate_capital` | The demo's market scenario is dropped in the console split |
| `DeployXnsGovernance.s.sol` couples XNS with governance | The script is split before governance is cut |

**Owner checkpoints:**
1. Create integrity-lab and integrity-console. Push access to Shield and Cortex already exists.
2. Approve any testnet broadcast (evidence anchor, genesis). Each is preceded by an Anvil dry run of
   the identical script.
3. Approve the repository rename in C5.

# Phase A: architectural and documentation simplicity

## A0. Preconditions (S)

- **Toolchain:** install the pinned versions from `INTERFACE_CONTRACT.md` (forge/anvil 1.7.1, opa
  1.18.2, cargo 1.96, node 22, uv). In cloud sessions `binaries.soliditylang.org` is blocked, so solc
  0.8.28 comes from the GitHub release. Gate A cannot pass without forge, Halmos and OPA.
- **Jules:** pause `close-conflicting-jules-prs.yml` for Phase A; auto-merge is already disabled.
- **Hygiene:** all three repositories are public. Mirrors and splits are made from a clean clone,
  never from a workstation that holds `contracts/.env` or the prover `secret_key`. A secret scan runs
  before every push.
- **Sibling repositories:** Shield and Cortex work branches from their latest `main`; no concurrent
  sessions run on them.

## A4. Minimal kernel patch (S)

- Remove the adapter-registry branch (constructor parameters, `registryHook`/`registryAdapter`
  immutables, the gas-bounded call).
- Add a `requireAssuranceTier` flag, so a disabled tier no longer reverts `AssuranceTierNotMet`.
- Set `evm_version = "cancun"`.
- Update the kernel deploy scripts and tests.
- Record the Base Sepolia `experimentalPhase1Reference` kernel as legacy; it is not redeployed.
- No kernel rewrite and no on-chain policy compiler.

## A2. SDK core: C1–C7 (M)

- **Core, tagged `integrity-sdk-v0.x` and dependency-light:**
  - JCS;
  - DID and DID-file support (the layout from `ad56d97`);
  - RFC 9162-style Merkle inclusion proofs;
  - receipts (create, sign, chain, checkpoint, verify locally);
  - pack schema, compile, sign and verify, with the decision contract;
  - hook normalization, the memory-provider interface, the OPA client, agent identity over HTTP.
- **Loading:**
  - lazy (PEP 562) package initialization;
  - import-hygiene tests: importing the core must not load `requests`, `web3`, `eth_account`,
    OpenTelemetry or MLflow.
- **`[connector]` extra:** chain, registration, account, telemetry, hook runner, clients.
- **Before A1:**
  - move `_execute_via_agent` out of `markets.py`;
  - move the MCP helpers still used elsewhere out of `mcp_server.py`.

## A1. Clear the ground (M)

- Snapshot the source and write a cut-path manifest. Mirror both to integrity-lab.
- **Split integrity-console** (about 21.8k lines: dashboard 18.1k, demo 1.6k, userapi 2.1k):
  - `git filter-repo` the dashboard, userapi and demo;
  - carry over or explicitly drop the unmerged `feat/cortex-operations-dashboard` branch;
  - remove pages for cut features.
- **Move to integrity-lab:**
  - `integrity-zkp`, `UltraPlonkVerifier`, the SDK prover;
  - SDK `markets.py`, `mcp_server.py`, root `integrity.py`, the duplicate root `opa_client.py`,
    `auto_hook`;
  - contracts `markets/`, `licence/`, `registry/`, `CCIPReputationBridge`, `IntegrityGovernance`, and
    their scripts and tests;
  - oracle routes `/v1/markets*`, `/v1/governance/proposals`, `/v1/agent/{id}/stake`.
- **Keep until Phase C:** `SovereignAgent`, the PrimitiveSet templates, `registerCore`,
  `IntegrityToken`, `IZkVerifier`, `VerifierRegistry` and `submitZkAttestation`. Live agents depend
  on them.
- **Checks:** pre-cut test run, secret scan, post-cut manifest comparison.

## A3. Independent Shield and Cortex (M each)

Both depend on SDK core only and use lazy connector imports. Neither has hard-coded `/home/xibalba`
paths or sibling Docker copies. Both pass independence CI against the SDK tag.

**Shield:**
- Policy bundles become signed packs covering the Rego; the enforced pack hash equals the signed
  pack hash.
- `permit` means permitted. No-match takes the pack's per-class default: `hipaa` agent tool calls
  deny; device sensor events are `log_only`.
- A missing, malformed, unknown or evaluator-error decision denies in enforce mode.
- Replace the mocked test (`tests/test_policy_engine.py:60-77`) with real OPA output.
- Exports carry labels and HMAC-protected paths, never raw `cmdline` or content-bearing arguments.
- Separate device-auth and agent keys.
- Replace the seven canonical-JSON copies with SDK JCS, re-sign bundles, and bump the schema.
- Keep `mlflow` optional.
- Read the agent identity from the DID file, not `.integrity/identity.json`.

**Cortex:**
- Authenticate the OTLP receiver.
- Register the `provider_telemetry_export` Merkle domain.
- Use SDK JCS.
- Bind create events to `content_hash`.
- Resolve agents from the DID file; `XIBALBA_AGENT_ID` becomes an explicit override only.

## A5. Consolidate plans and documentation (M)

- **Authorities:**
  - make this plan the execution authority in `DOCUMENT_STATUS.yaml`;
  - merge root `AGENTS.md` with `.agents/AGENTS.md` into one file (`CLAUDE.md` = `@AGENTS.md`);
  - create `STATUS.md` (≤150 lines), `ECOSYSTEM.md`, `DATA.md` and ADR-0001 (the six-function test).
- **Archive or merge the competing authorities:**
  - `docs/IMPLEMENTATION_PLAN.md`, `PRODUCTION_READINESS_PLAN.md`, `ARCHIVE_PLAN.md`,
    `SPEC-v2.0.0-proposed.md`, `MAINNET_READINESS.md`;
  - the dated handoffs, reconciliations and audits;
  - `docs/packs/trading/`;
  - the `park/policy-packs-2026-09-26` branch. It stores packs in userapi Postgres, a second pack
    authority; only its UI is reused, as the B0 promotion view.
- **Inventory:** classify every Markdown file (188 files, about 45k lines) as authoritative,
  merge-required, historical or removable. `PRODUCTION_GAPS.md` entries that are still open move to
  `STATUS.md` or an ADR.
- **CI:**
  - link, path, duplicate-claim and authority checks, plus the `STATUS.md` cap;
  - `sync-wiki.yml` follows the consolidated set;
  - fix the two pages failing `wiki_toc.py --check` on `main` (`local-metrology.md`,
    `integrity-oracle.md`).
- No new hand-maintained registers.

## A6. Stable SaaS seams (M)

SDK/API contracts plus local reference implementations (no billing code) for:
- tenant and organization identity;
- agent and device registration;
- signed pack distribution and version pinning;
- receipt submission and local queueing;
- offline verification;
- Cortex provider and store identity;
- entitlements and capability checks;
- redacted usage and audit metrics.

A customer can run locally and later move to hosted or anchored services with no change in policy
semantics or receipt meaning.

## Gate A

- **Builds:** relevant suites, import hygiene, Shield/Cortex independence CI and the console build
  are green. The cut-path manifest is in integrity-lab. One SDK JCS implementation is used across
  active repositories.
- **Shield:**
  - the signed pack hash equals the enforced hash;
  - tampered, malformed, stale or incompatible packs refuse to load;
  - no-match follows the per-class default;
  - malformed, unknown or evaluator-error decisions deny;
  - exports contain no raw command content;
  - the device key differs from the agent key.
- **Cortex:** unauthenticated OTLP is rejected; provenance export works; create events bind
  `content_hash`.
- **Kernel:** it no longer imports `registry/`; the tier-off test and Halmos pass.
- **Receipts:** a receipt can be created, signed and verified locally, unanchored.
- **Identity:** no private key exists under any harness root in any test or pilot fixture.
- **Docs:** every active normative document has an identified authority; superseded material is in
  integrity-lab; no active repository holds a competing plan or architecture register.

# Phase B: sellable Shield and Cortex SaaS

**Outcome:** independently deployable, tenant-isolated, pilot-ready products. The first package is
**Integrity Health**: Shield enforcement paired with Cortex provenance, on synthetic regulated data
until Gate C.

## B0. SaaS productization (L)

**Scope guard:** single region and a single node per product, with per-tenant database files. Region
policy is configuration only. HA and Postgres are deferred.

**Shared requirements:**
- tenant-scoped agents, devices, packs, receipts, memory stores, exports and audit logs;
- organization-admin and operator roles;
- device enrollment and revocation;
- entitlements (no billing);
- configurable retention;
- local-first pilot mode with hosted-compatible APIs;
- usage and audit summaries;
- backup, restore, tenant deletion and export.

**Shield slice:**
- signed pack promotion and rollback (the console view reuses the parked policy-packs UI);
- device health and key status;
- on-device enforcement with local BCC fallback, and fail-closed regulated mode when both are down;
- receipt queue and verification status;
- shadow/enforce modes and signed break-glass.

**Cortex slice:**
- tenant-scoped providers and stores;
- agent-scoped content and provenance views;
- retention, purge, export and provider health;
- authenticated ingestion and retrieval;
- spot-check API and proof status.

**Monetization:** pilots are sellable without billing code.
- **Shield:** enforcement, devices, evidence retention and exports.
- **Cortex:** capacity, retention, providers, retrieval and provenance exports.
- **Integrity:** verification is included; public-chain anchoring is a higher tier.

## B1. Packs, adapters and the conformance kit (M)

- `packs/base` and `packs/hipaa` each contain `pack.yaml` (with per-class defaults), `policy.rego`
  and `controls.yaml`, seeded from `CONTROLS_MATRIX.md`:
  - HIPAA §164.312(a)(1)/(b) and §164.502(b);
  - SOC 2 CC6.1/CC7.2;
  - ISO 42001.
- The compiler rejects policy relaxation.
- `baa.py` is deterministic.
- The adapter contract and conformance kit ship with a sample third-party adapter.
- BAA conditions are operational controls; the evidence does not certify legal compliance.

## B2. Gates emit receipts (M)

- BCC and Shield evaluate the same compiled pack and pass shared conformance vectors in CI.
- Both support atomic loads, fail-closed reason codes, shadow/enforce modes, and signed chained
  receipts with checkpoints.
- Shield's local gate daemon exposes a Unix socket for PreToolUse.

## B3. Claude Code hooks (S)

`integrity hooks install --harness claude-code --gate shield|bcc --memory cortex` does three things:
- writes the DID file into the harness root and the key outside it;
- writes marker-tagged hooks;
- is idempotent, and uninstall is exact.

## B4. Verifiable evidence (M)

- A dedicated protocol evidence instance of `StateAnchor` (same code, separate from each agent's
  memory `StateAnchor`).
- `anchor_batch_per_agent` stops writing receipt roots into agent anchors, whose `latestRoot` is the
  memory root that registration checks.
- Local Anvil in Phase B. Queued receipts anchor after recovery.
- `integrity verify` checks signature, chain position, inclusion and anchor.
- Testnet deployment needs owner approval.

## B5. Telemetry policy (S)

- `regulated` is the default with `hipaa`: no content leaves the boundary; signals are derived at the
  edge and marked self-reported.
- The receiver strips `user.email` and other prohibited identity fields.
- Negative tests cover:
  - prompts, tool arguments, file contents;
  - environment variables, stdout/stderr;
  - URLs and query strings, filenames, repository names;
  - exception messages and stack traces.

## B6. Pilot packaging (M)

A reproducible pilot with:
- one organization admin, and at least two tenant-scoped agents and devices;
- policy promotion and rollback;
- Cortex store creation, retention, purge and export;
- a local receipt queue with verification;
- operator-visible health;
- synthetic-data reset and tenant teardown.

The pilot demonstrates that Shield and Cortex stay useful when the anchor, the oracle and vendors are
down.

## B7. Revenue-facing exports (M)

- A Vanta private integration linking per-control tests to receipts.
- OCSF 6003 and JSONL exports.
- Local acceptance uses Vanta fixtures.

## Gate B-local

**Setup:** Compose, local Integrity services, a local Anvil evidence anchor, Shield, Cortex, BCC,
synthetic regulated data and Claude Code hooks.

**Required:**
- **Enforcement:**
  - a PreToolUse without an active BAA is denied on-device by `hipaa`, and the receipt cites the
    control and pack hash;
  - shadow mode records without enforcing.
- **Evidence:**
  - receipts anchor locally, and offline verify passes;
  - tampered, wrong-key, wrong-proof and truncated-tail receipts fail;
  - queued receipts anchor after recovery.
- **Data boundary:** a traffic audit shows no content leaving the boundary.
- **Packs:**
  - golden hashes pass, and every rule cites a control;
  - the sample adapter passes the conformance kit.
- **Exports:** Vanta fixture tests pass.
- **Tenancy and devices:**
  - two tenants cannot read or alter each other's data;
  - revoked devices get no new packs and their receipts are rejected, while they still fail closed
    locally.
- **Resilience:** Shield and Cortex stay operational when the anchor and oracle are down.
- **Retention:** purge removes content and keeps only permitted non-content evidence.
- **Entitlements:** enforced without billing.

## Gate B-integrations (optional)

Base Sepolia evidence anchor, a Vanta sandbox run, and external oracle/BCC connectivity. Each result
is classified as verified, unverified or blocked. None of these invalidates Gate B-local.

# Phase C: production-grade Integrity trust

Phase C follows the first pilots and does not block synthetic-data sales.

## C1. Kernel mediation (L)

- Disable ERC-1271. If analysis keeps it, it must not validate Permit/Permit2 typed data, and any
  signed approval counts as outflow.
- EntryPoint is deposit-only; `withdrawTo` is blocked.
- Approvals count as outflow.
- The rescue sweep stays only as a documented, bounded exception.
- Proofs: kernel M1 test, sequence invariant, ERC-7579 conformance, `mediation_audit.py`.

## C2. Accounts and registration (M)

Accounts deploy via standard CREATE2 from the canonical `IntegrityAccount`.

**Registrar verification, off-chain:**
- runtime bytecode is compared with the artifact, with immutables masked via
  `immutableReferences`;
- immutable values are checked through getters;
- the kernel binding and `packHash` are checked the same way;
- re-verification runs on every `KernelSwapped` event;
- BCC and Shield trust a `packHash` only after verification.

**Registration:**
1. The account calls the registrar.
2. The registrar verifies an Ed25519 attestation over the account, chain ID, DID, guardian, pack hash,
   memory provider and XNS handle.
3. The registrar verifies canonical bytecode and the kernel binding.
4. A conforming memory provider completes genesis.
5. The registry records the account, DID, provider and handle.

Registration rejects forged or replayed attestations, non-canonical accounts, mismatched guardians,
and roots with no provider behind them.

**Also:**
- a shared `ReputationRegistry`;
- `integrity contracts claim` for ERC-173 recognition;
- an authoritative, verified `packHash` pushed to Shield.

## C3. Verified memory (M)

**Cortex:**
- store-wide append-only provenance;
- encryption at rest;
- `spot_check(root, index, nonce)`;
- an anchorable provable root;
- hard purge of content, FTS, blobs, embeddings, replicas and keys;
- a PHI-redaction hook and pack-driven retention.

**The oracle:**
- spot-checks without receiving PHI;
- turns failures into `MemoryUnavailable` receipts.

## C4. Human oversight (S)

- Approval receipts are bound to the action HMAC, and both gates re-check them.
- Break-glass approvals are signed and expire.
- `pack simulate --since 90d` runs before enforcement changes.
- Replayed, expired, wrong-action, wrong-pack and wrong-agent approvals are rejected.

## C5. Cutover (M)

- Run an Anvil regenesis dry run, then broadcast a fresh Base Sepolia genesis with owner approval.
- Migrate the 15 registered agents, from both the `registerPrimitives` and `registerCore` paths,
  preserving DIDs, XNS handles and valid history. Agents without provider-backed memory are reported
  as blocked.
- Move the legacy account model, `SovereignAgent`, the PrimitiveSet templates, `IntegrityToken` and
  the ZK interfaces to integrity-lab.
- Rename to integrity-kernel and remove old pins.
- Rebuild the CLI on the SDK and remove duplicate implementations.

## Gate C

- **Kernel:** mediation proofs and conformance pass; an over-budget UserOp reverts.
- **Registration:**
  - forged or replayed registrations are rejected;
  - canonical verification is enforced, including after a kernel swap;
  - no self-scoring.
- **Memory:** a provider-backed spot-check passes, a digest-only fake fails, and purged content is
  unrecoverable.
- **Oversight:** replayed approvals are rejected.
- **Cutover:** the dry run preserves DIDs, handles and history; no stale load-bearing references to
  integrity-core remain.

## 9. Expected outcomes by gate

| After | You have | You may claim | You may not claim |
|---|---|---|---|
| Gate A | One trust layer (JCS, packs, receipts, identity with keys outside harness roots); about 22k lines moved to the console; cut code in the lab; a handful of authoritative docs with drift CI; Shield and Cortex standalone | "Simpler, consistent architecture; products run independently" | Any compliance or security guarantee |
| Gate B-local | The Integrity Health demo on synthetic data: on-device HIPAA deny → signed receipt citing the control → offline verify → green Vanta test. Two pilot-ready, tenant-isolated products that survive outages | "Enforces configured policy with independently verifiable evidence" (pilot, synthetic data) | HIPAA certification, real-PHI readiness, real-funds safety |
| Gate C | Proven kernel mediation, forgery-resistant registration, spot-checked memory, real purge, non-replayable approvals, a fresh testnet with the 15 agents' DIDs and handles preserved, the repo renamed | Readiness for real-PHI and real-funds pilots, subject to audit | Mainnet or audited status; HIPAA certification (still needs SOC 2 Type II and a BAA) |

**Not produced by this plan:**
- automated revenue collection;
- an independent audit;
- non-Linux Shield;
- harnesses other than Claude Code;
- a validated AIS.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Scope creep (largest risk: B0, A5, A6) | Six-function test, §7 not-done list, capped `STATUS.md`, B0 scope guard |
| Restructure collides with concurrent work (Jules, Codex, active Shield/Cortex pushes) | A0 pauses Jules; branch from latest `main`; one session per repository |
| Secret leakage from public repositories | Clean-clone mirrors, pre-push secret scan, keys never in harness roots |
| Kernel hardening stalls | Phase B ships local evidence without real-funds claims |
| Integrity becomes a runtime bottleneck | Local enforcement, queued receipts |
| Products impressive but not sellable | B0 tenancy, workflows, entitlements, packaging, exports, teardown |
| Gate commoditization (Microsoft AGT, Drata) | Compete on anchored, verifiable evidence and regulation packs |
| Regulated buyers distrust anchoring | Roots and checkpoints only, documented in `DATA.md` |
| Pack evaluator drift | One compiler, pack hash, and shared conformance vectors in BCC and Shield CI |
| No factory → non-canonical kernel after a swap | Registrar re-verification on `KernelSwapped`; fallback to a minimal factory |
| Identity relocation strands a sibling caller | Shield and Cortex move to the DID file in A3; legacy keys relocate automatically and conflicts fail closed |
| Solo review load | Commits grouped by phase and repository; gates as review points |

## 11. Open questions (none block Phase A)

1. Whether stake is introduced later (v1 has none).
2. MIT or open-core licensing for Shield and Cortex.
3. When Shield's SQLite backend must become Postgres/HA.
4. SOC 2 Type II timing, and the BAA template for health buyers.

## 12. Deferred work

| Area | Items |
|---|---|
| Regulation packs | EU AI Act pack before December 2027 |
| Integrations | Drata/Secureframe, gRPC ext_authz PEP, ERC-7579 registry listing, ERC-8004 write-back |
| Platform | Shield macOS/Windows, LSM pre-blocking, DNS controls; Cortex team profiles; HA/Postgres |
| Hooks | Codex, Agy, Hermes |
| Analysis | Formal SMT pack analysis; runtime adapter sandbox |
| Accounts | Session keys, staking, paymaster, signing daemon |
| Research | AIS predictive validation; ZK |
| Documentation | Generated-facts lint |
| Revenue | Billing, payments, invoicing |

## Appendix A: pre-execution review (2026-09-28)

Findings from reviewing `main` before execution, and how this draft resolves each:

| # | Finding | Resolution |
|---|---|---|
| 1 | The working branch was 39 commits behind `main` | Fast-forwarded; the plan is grounded on `d22128b` |
| 2 | Already on `main`: mlflow optional, BCC shadow default, handoffs archived, harness-profile identity | Credited; not redone |
| 3 | `registerCore` + XNS handle is the new default; the Base Sepolia factory lacks it | §4 interim path; C2 carries the handle; C5 migrates both paths |
| 4 | Keys stored inside the harness root; root chosen by env-var precedence | **Fixed in `ad56d97`**; §4, C2 |
| 5 | Contract cut dependencies (kernel → registry, Slasher → ITK, registries → IZkVerifier) | §8 ordering table; A4 before A1 |
| 6 | SDK cut dependencies (health → markets, eager `__init__`, mcp helpers) | §8; A2 before A1 |
| 7 | Competing authorities (parked policy-packs branch, unmerged dashboard branch, five plan documents, two `AGENTS.md` files, trading pack, Jules workflow) | A0, A1, A5 |
| 8 | Deployed experimental kernel uses the adapter-registry constructor | A4 records it as legacy |
| 9 | Sizes: about 105k code lines and 45k Markdown lines in this repo; console split about 21.8k lines | §9 and A1 updated |
| 10 | Shield and Cortex push access exists; all repos public; siblings actively pushed | Checkpoint 1 reduced; A0 hygiene |
| 11 | Toolchain missing in cloud sessions; solc host blocked | A0 |
