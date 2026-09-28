# Execution Plan: The Xibalba Ecosystem, Balanced and Monetizable

**Status:** Approved by the owner on 2026-09-28; execution in progress. Phase A5 records this plan as
the single execution-plan authority in `docs/DOCUMENT_STATUS.yaml` and archives the plans it
supersedes.
**Scope:** integrity-core, xibalba-shield, xibalba-cortex, and two
new repositories: integrity-console and integrity-lab.
**Tracking:** work items are GitHub task-list checkboxes. Tick an item (`- [x]`) in the same commit
that completes it (`git blame` on the line finds that commit); name earlier commits explicitly. A gate item is ticked only when its check has actually run
and passed. `python3 scripts/plan_progress.py` counts progress per section from the checkboxes, so
there is no hand-maintained total to drift.
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
| integrity-core | Trust substrate: SDK, contracts (including the on-chain `IntegrityKernel`), oracle, BCC, CLI |
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
- Keep the name integrity-core. It names the whole trust substrate; `IntegrityKernel` stays the name
  of one contract inside it. No repository rename.
- Cut removed code into integrity-lab.

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
1. [x] Create integrity-lab and integrity-console. Push access to Shield and Cortex already exists.
   Both repos exist; integrity-lab#1 (cut-path import) and integrity-console#1/#4 (dashboard/userapi/
   demo import, then cut-feature page removal) are merged.
2. [ ] Approve any testnet broadcast (evidence anchor, genesis). Each is preceded by an Anvil dry run of
   the identical script.

## Pre-execution

- [x] Review `main` before execution; findings in [Appendix A](#appendix-a-pre-execution-review-2026-09-28).
- [x] Keep agent private keys outside the harness root (`ad56d97`).
- [x] Write this final draft (`8cf35bd`).
- [x] Keep the name integrity-core; drop the rename (`5361cf7`).
- [x] Owner approves this plan (2026-09-28).

# Phase A: architectural and documentation simplicity

## A0. Preconditions (S)

- [x] **Toolchain:** install the pinned versions from `INTERFACE_CONTRACT.md` (forge/anvil 1.7.1, opa
  1.18.2, cargo 1.96, node 22, uv). In cloud sessions `binaries.soliditylang.org` is blocked, so solc
  0.8.28 comes from the GitHub release. Gate A cannot pass without forge, Halmos and OPA.
  `scripts/install_toolchain.sh` installs forge/anvil/solc/opa from GitHub releases (build with
  `FOUNDRY_OFFLINE=true`); Halmos comes from `make verify-kernel`. Baseline: `forge test` 527 passed,
  1 skipped.
- [x] **Jules:** pause `close-conflicting-jules-prs.yml` for Phase A; auto-merge is already disabled.
  Schedule commented out (manual dispatch kept); restore after Gate A. The local Jules controller on
  the owner's workstation is outside this repository and must be paused there.
- [x] **Hygiene:** all three repositories are public. Mirrors and splits are made from a clean clone,
  never from a workstation that holds `contracts/.env` or the prover `secret_key`. A secret scan runs
  before every push: `scripts/secret_scan.sh [base]` (pinned gitleaks over `base..HEAD`, redacted;
  verified to fail on a committed private key).
- [ ] **Sibling repositories:** Shield and Cortex work branches from their latest `main`; no concurrent
  sessions run on them.

## A4. Minimal kernel patch (S)

- [x] Remove the adapter-registry branch (constructor parameters, `registryHook`/`registryAdapter`
  immutables, the gas-bounded call). The kernel no longer imports `registry/`.
- [x] Add a `requireAssuranceTier` flag, so a disabled tier no longer reverts `AssuranceTierNotMet`.
  7 tests in `test/kernel/IntegrityKernelAssuranceTier.t.sol`: tier off removes only that gate.
- [x] Set `evm_version = "cancun"`.
- [x] Update the kernel deploy scripts and tests. Registry-only tests removed with the feature
  (`IntegrityKernelRegistryHook.t.sol`, `KernelPropertiesRegistryEnabled.t.sol`); `forge test` 527
  passed, 1 skipped (46 suites).
- [x] Record the Base Sepolia `experimentalPhase1Reference` kernel as legacy; it is not redeployed.
- Constraint: no kernel rewrite and no on-chain policy compiler.

## A2. SDK core: C1–C7 (M)

- [x] Tag `integrity-sdk-v0.1.0` on `main` (`pyproject.toml` already reads `0.1.0`; tagged after #105
  merged, so the tag includes the A3 canonicalization bumps — `telemetry.envelope` schema v2 and
  `memory_dag` schema v2. Consumers pinning this tag get those hash changes.).
- **Core, tagged `integrity-sdk-v0.x` and dependency-light:**
  - [x] JCS (`core/jcs.py`; `bcc.canonical_json_bytes` delegates to it);
  - [x] DID and DID-file support (the layout from `ad56d97`);
  - [x] Merkle inclusion proofs in the protocol's one convention (OpenZeppelin semantics, what
    `StateAnchor.verifyLeaf` checks), passing `spec/vault-merkle` vectors; `vault.py` now reuses it;
  - [x] receipts (create, sign, chain, checkpoint, verify locally) (`core/receipts.py`);
  - [x] pack schema, compile, sign and verify, with the decision contract (`core/packs.py`,
    `core/decision.py`; sample Rego checked against real OPA 1.18.2);
  - [x] hook normalization (`normalize_hook`, core-safe);
  - [x] the memory-provider interface (C6) (`core/memory.py`: interface only; how a verifier checks
    retrievability without receiving PHI is C3);
  - [x] the OPA client (one, replacing `opa_client.py` and `policy/opa_client.py`) (`core/opa.py`:
    installs the verified Rego, reads it back, fails closed; tested against a real OPA server; the
    two old clients leave in A1);
  - [x] agent identity over HTTP (signed requests with the agent key) (`core/signed_body.py`,
    byte-compatible with the oracle's current wire; `client.py` signs through it);
  - Moved to A3: the remaining ad-hoc canonicalizations, because each hash is read by another
    package and must change on both sides at once.
- **Loading:**
  - [x] lazy (PEP 562) package initialization;
  - [x] import-hygiene tests: importing the core must not load `requests`, `web3`, `eth_account`,
    OpenTelemetry or MLflow. `tests/unit/test_import_hygiene.py` (fresh interpreter per import; 7 of 8
    fail against the old eager `__init__`).
- [x] **`[connector]` extra:** chain, registration, account, telemetry, hook runner, clients.
  Defined; the same packages stay in the base dependencies until A3 moves Shield and Cortex onto
  `[connector]`, then leave the base list.
- [ ] Drop the connector packages from the base dependencies (after A3).
- **Before A1:**
  - [x] move `_execute_via_agent` out of `markets.py` (now `chain.execute_via_agent`);
  - [x] move the MCP helpers still used elsewhere out of `mcp_server.py` (`did.find_existing_identity`;
    only `mcp_server`'s own tests still import it).

## A1. Clear the ground (M)

- [x] Snapshot the source and write a cut-path manifest. Mirror both to integrity-lab. Snapshot:
  `main` @ `761e019`; 91 files with history + manifest in integrity-lab#1 (open for merge).
- [x] **Split integrity-console** (about 21.8k lines: dashboard 18.1k, demo 1.6k, userapi 2.1k):
  import merged in integrity-console#1; integrity-console#4 merged 2026-09-28T03:19Z.
  - [x] `git filter-repo` the dashboard, userapi and demo (191 commits, history kept);
  - [x] carry over or explicitly drop the unmerged `feat/cortex-operations-dashboard` branch (carried
    over, with `park/policy-packs-2026-09-26`);
  - [x] remove pages for cut features (integrity-console#4: Staking/Credit/Actuarial/Licence/Factory
    pages, oracle DTOs for the cut routes, the demo's capital-allocation flow; Health's quarantine
    scan now reads `Slasher.lockedStakeOf` on-chain).
- **Move to integrity-lab:**
  - [x] `integrity-zkp`, `UltraPlonkVerifier`, the SDK prover (and the oracle's bb verifier);
  - [x] SDK `markets.py`, `mcp_server.py`, root `integrity.py`, the duplicate root `opa_client.py`,
    `auto_hook`. The `integrity.auto()` facade (`integrity_sdk/integrity.py`) is kept: it is the README
    quickstart (Appendix A row 14);
  - [x] contracts `markets/`, `licence/`, `registry/`, `CCIPReputationBridge`, `IntegrityGovernance`, and
    their scripts and tests (XNS kept: `DeployXns.s.sol` replaces `DeployXnsGovernance.s.sol`);
  - [x] oracle routes `/v1/markets*`, `/v1/governance/proposals`, `/v1/agent/{id}/stake` (also `credit`,
    `contracts`, `/v1/stats`, which served only cut contracts; recorded in `spec/ais-api/CHANGELOG.md`
    as an exception to v1's additive-only policy).
- **Keep until Phase C (constraint):** `SovereignAgent`, the PrimitiveSet templates, `registerCore`,
  `IntegrityToken`, `IZkVerifier`, `VerifierRegistry` and `submitZkAttestation`. Live agents depend
  on them.
- [x] **Checks:** pre-cut test run, secret scan, post-cut manifest comparison. Each stage re-ran its
  suites (forge 335, SDK 437 on Anvil, CLI 70, oracle 146+22); gitleaks on every push and on the
  full lab/console histories; the lab manifest is derived from `git diff --diff-filter=D`.

## A3. Independent Shield and Cortex (M each)

Both depend on SDK core only and use lazy connector imports. Neither has hard-coded `/home/xibalba`
paths or sibling Docker copies. Both pass independence CI against the SDK tag.

**Shield:** (xibalba-shield#36 fixed a breakage this phase surfaced)
- [x] Policy bundles become signed packs covering the Rego; the enforced pack hash equals the signed
  pack hash. **Prerequisite found and fixed first (xibalba-shield#36):** `policy_engine/engine.py`
  imported the now-deleted `integrity_sdk.policy.opa_client` (A1 removed it; it was BCC
  middleware's own vendored client, never used by the SDK) — Shield's policy engine could not be
  imported at all against current `main`. Restored with a Shield-owned copy of the same module,
  a behavior-preserving port, so this item can build on a working engine. Implemented and merged
  in xibalba-shield#38 (`00eadda`): `PolicyEngine` now installs and queries the verified
  `LoadedPack` through `integrity_sdk.core.opa.OpaClient`; the enforced hash is sourced from that
  pack, explicit `--pack-dir` and trusted signer flags are supported, built-in profiles resolve
  signed packs, and the zero-config path retains the existing permissive SMB fallback through a
  verified ephemeral pack. Test seams were migrated to real pack-aware OPA behavior.

  **Owner decision (2026-09-28): pack-signing key custody, resolved.** A dedicated Ed25519
  keypair, generated and held the same way as the existing release-signing key
  (`shield/release/signing.py`'s lazy-generate/PEM/0600 convention) — a separate key file from
  release signing, agent/device DID keys, and any other signing domain, per this repo's own
  stated rule that different blast radii never share a key. Held by the operator, consistent
  with the plan's existing "single-operator testnet setup" for every other key in the system
  (guardian, HMAC, funder, oracle signer). Real HSM/multi-party custody stays deferred to a
  later production-infra gate, same as the release-signing key and the no-signing-daemon-in-v1
  decision already in this plan. `packaging/systemd/shield.env.example`'s
  `XIBALBA_ORACLE_POLICY_PUBLIC_KEY=file:...` convention is the distribution mechanism for the
  public half. HSM/multi-party custody remains deferred to the production-infra gate.
- [x] `permit` means permitted. No-match takes the pack's per-class default: `hipaa` agent tool calls
  deny; device sensor events are `log_only`. Done independently of the full signed-packs migration
  above: `shield/policies/rego/*.rego` each add `decision`/`reason_code` vars (the C3
  `{"decision","reason_code","controls"}` shape) alongside the existing legacy vars, deliberately
  with no `default` for either — undefined on no-match, which is what lets
  `integrity_sdk.core.decision.resolve()` apply a per-`event.klass` default instead of one
  hardcoded in Rego. `policy_engine/engine.py` now calls `resolve()` and translates its 3-way
  permit/deny/log_only result back onto Shield's own frozen 5-way `Decision.action` vocabulary
  (allow/deny/contain/log_only/escalate — spec §5.5) via the reason code's `_CONTAIN_`/`_ESCALATE_`
  marker, so `router.py` and every existing consumer see the exact same action strings as before.
  `REGULATED_EVENT_DEFAULTS` (agent_event → deny) is the literal "hipaa agent tool calls deny" case;
  every other class stays `log_only`, unchanged. Exercised for real against `shield local-run`'s
  three profiles. **Now wired into the live `shield run` path** (xibalba-shield `c7d4617`):
  `DeviceConfig.policy_profile` names the compliance vertical, `event_defaults_for_profile()`
  maps it to `EVENT_DEFAULTS_BY_PROFILE`, and `cli.py`'s `_run` passes that into `PolicyEngine`'s
  construction. Unset/unrecognized values fall back to today's log_only-everywhere default, so an
  operator who never sets the new field sees no behavior change.
- [x] A missing, malformed, unknown or evaluator-error decision denies in enforce mode.
  `resolve()` provides this directly — evaluator error (OPA unreachable) and an out-of-contract
  `decision`/`reason_code` pair both already tested; an event class not in `event_defaults` now
  denies rather than silently falling through (new test:
  `test_unknown_event_class_denies_in_enforce_mode`).
- [x] Replace the mocked test (`tests/test_policy_engine.py:60-77`, now
  `test_opa_allow_translates_to_policy_decision`) with real OPA output. Deleted outright: its
  premise (`action: "allow"` for a no-match result) is something no real Rego rule in this repo
  can ever produce — `default action := "log_only"`, and no rule ever sets `action := "allow"` —
  so the mock was testing a shape real OPA cannot return, the exact "mocked test hid a bug" case
  `core.decision`'s own module docstring names. Real coverage already existed for this scenario
  (`test_real_opa_unmatched_process_is_log_only`, all three profiles, unchanged). Two other mocked
  unit tests in the same file needed their mock data updated (not replaced) to include
  `decision`/`reason_code` so they still exercise the intended scenario post-fix, and 6 more
  mocked tests across `test_cli.py`/`test_guardrail_hooks.py`/`test_hot_reload.py` needed the same
  fix or a corrected assertion (they asserted the same impossible `"allow"`/no-op-`"deny"`
  outcomes) — full list in xibalba-shield's PR. `.venv/bin/python -m pytest`: 454 passed, 12
  skipped (was 451; net +3 after the one deletion).
- [ ] Exports carry labels and HMAC-protected paths, never raw `cmdline` or content-bearing arguments.
- [ ] Separate device-auth and agent keys.
- [ ] Replace the seven canonical-JSON copies with SDK JCS, re-sign bundles, and bump the schema.
- [x] Keep `mlflow` optional. Already true: `mlflow` is not a Shield dependency at all (checked
  `pyproject.toml`), so there is nothing non-optional to fix.
- [x] Read the agent identity from the DID file, not `.integrity/identity.json`. Already true:
  `integrity_exporter/exporter.py` and `preflight.py` both call `integrity_sdk.did.load_or_create_did`
  (the current DID-file-based function, `ad56d97`); no `.integrity/identity.json` reference exists
  anywhere in this repo. Likely landed independently as Shield's own development kept pace with
  the SDK, before this plan item was written.

**SDK canonicalizations, with their consumers (moved from A2):**
- [x] `telemetry/envelope.canonical_bytes` → core JCS (`SCHEMA_VERSION` 1 → 2). Checked the oracle
  side first: it never reads this envelope's `content_hash`/`payload_hash` at all — its own
  identically-named fields in `handlers.rs`'s telemetry-ingest path are computed independently
  over the signed request, via `crypto::canonical_json_bytes`, not from this SDK-local dataclass.
  So there is no oracle-side change here, and no non-ASCII disagreement to close on this specific
  hash (that gap was about `bcc.py`'s wire format, already closed in A2) — corrected from the
  plan's original wording, which conflated the two.
- [x] `memory_dag.canonical` → core JCS, with a node-id version bump (`SCHEMA` v1 → v2; v1 stays
  documented as historical, not deleted). No other package computes a `memory_dag` node id today
  (Cortex's own future JCS migration is a separate A3 item, in that repo).
- [x] `harness_hooks._hash` → core JCS (`json.dumps(default=str)` round-trip kept, to still tolerate
  non-JSON-native tool args/results, before JCS canonicalizes the result); `tool_input_hash`/
  `result_hash` ride inside `telemetry.envelope`'s payload, so they change value under the same
  `SCHEMA_VERSION` bump above rather than a separate one.

**Cortex:** (xibalba-cortex#30)
- [x] Authenticate the OTLP receiver. It had none at all — any local process (or, with a
  non-default `--host`, any network caller) could inject provenance evidence with no
  attribution. Now requires the same mandatory bearer token `local_api.py` already enforces
  (`memory:write` scope), via the standard `OTEL_EXPORTER_OTLP_HEADERS` exporter header.
- [x] Register the `provider_telemetry_export` Merkle domain. Found genuinely broken, not just
  missing: `store.export_provider_telemetry()` has always called `domain_merkle_root(...,
  domain="provider_telemetry_export")`, but that domain was never in `events.MERKLE_DOMAINS` —
  every call raised `ValueError: unknown Merkle domain`, with zero test coverage.
- [ ] Use SDK JCS. **Owner decision (2026-09-28): migration allowed, resolved.** `SPECIFICATION.md`
  §0's freeze covers the MCP tool contract and table shapes ("existing tools keep their current
  signatures... existing table shapes don't change field meaning") — it does not freeze the
  internal canonicalization behind a hash. Checked whether any real external verifier depends on
  today's exact bytes: anchoring is opt-in and off by default
  (`auto_anchor_on_session_end`/`XIBALBA_ANCHOR_URL`), and no evidence exists on this machine of a
  Cortex Merkle root ever actually being anchored on-chain, so no third party currently holds a
  proof computed under today's canonicalization. Migration proceeds with the same domain/schema
  version bump + dual-hash verification window already used for `telemetry.envelope` and
  `memory_dag` above (v1 stays historical, not deleted; new writes use SDK JCS under a new tag).
  `SPECIFICATION.md` §0 gets its wording clarified to state the freeze scope explicitly, so this
  doesn't get re-litigated. **Still not implemented** — `_canonical_json` has dozens of call
  sites; this is real, multi-file work for its own session, not a quick fix.
- [x] Bind create events to `content_hash`. Already true for the primary create path:
  `store_memory` computes `content_digest` and binds it into `source_payload["content_hash"]`
  before the row is written. Not re-verified against every ingestion path (OTLP, transcript,
  Drive, Codex backfill) in this pass.
- [ ] Resolve agents from the DID file; `XIBALBA_AGENT_ID` becomes an explicit override only.
  **Not done here, scoped as separate follow-up:** `XIBALBA_AGENT_ID` is read as a required
  identifier in roughly 10 call sites (`server.py`, `store.py`, `provider_bridge.py`, the hook
  bridges); `server.py`'s own docstring calls it "required: without it this server cannot scope
  memory access." Making DID-file resolution primary is a real multi-file behavior change, not a
  drop-in fix, and deserved its own pass rather than riding alongside the two bug fixes above.

## A5. Consolidate plans and documentation (M)

- **Authorities:**
  - [x] make this plan the execution authority in `DOCUMENT_STATUS.yaml`. Completed 2026-09-28:
    `docs/DOCUMENT_STATUS.yaml` now points at this plan with `authority: execution`; the older
    `docs/IMPLEMENTATION_PLAN.md` is retained as historical context pending the remaining A5
    archive/merge work.
  - [ ] merge root `AGENTS.md` with `.agents/AGENTS.md` into one file (`CLAUDE.md` = `@AGENTS.md`);
  - [ ] create `STATUS.md` (≤150 lines), `ECOSYSTEM.md`, `DATA.md` and ADR-0001 (the six-function test).
- **Archive or merge the competing authorities:**
  - [ ] `docs/IMPLEMENTATION_PLAN.md`, `PRODUCTION_READINESS_PLAN.md`, `ARCHIVE_PLAN.md`,
    `SPEC-v2.0.0-proposed.md`, `MAINNET_READINESS.md`;
  - [ ] the dated handoffs, reconciliations and audits;
  - [ ] `docs/packs/trading/`;
  - [ ] the `park/policy-packs-2026-09-26` branch. It stores packs in userapi Postgres, a second pack
    authority; only its UI is reused, as the B0 promotion view.
- [ ] **Inventory:** classify every Markdown file (188 files, about 45k lines) as authoritative,
  merge-required, historical or removable. `PRODUCTION_GAPS.md` entries that are still open move to
  `STATUS.md` or an ADR.
- **CI:**
  - [ ] link, path, duplicate-claim and authority checks, plus the `STATUS.md` cap;
  - [ ] `sync-wiki.yml` follows the consolidated set;
  - [ ] fix the two pages failing `wiki_toc.py --check` on `main` (`local-metrology.md`,
    `integrity-oracle.md`).
- Constraint: no new hand-maintained registers.

## A6. Stable SaaS seams (M)

SDK/API contracts plus local reference implementations (no billing code) for:
- [ ] tenant and organization identity;
- [ ] agent and device registration;
- [ ] signed pack distribution and version pinning;
- [ ] receipt submission and local queueing;
- [ ] offline verification;
- [ ] Cortex provider and store identity;
- [ ] entitlements and capability checks;
- [ ] redacted usage and audit metrics.

A customer can run locally and later move to hosted or anchored services with no change in policy
semantics or receipt meaning.

## Gate A

- [ ] **Builds:** relevant suites, import hygiene, Shield/Cortex independence CI and the console build
  are green. The cut-path manifest is in integrity-lab. One SDK JCS implementation is used across
  active repositories.
- **Shield:**
  - [ ] the signed pack hash equals the enforced hash;
  - [ ] tampered, malformed, stale or incompatible packs refuse to load;
  - [ ] no-match follows the per-class default;
  - [ ] malformed, unknown or evaluator-error decisions deny;
  - [ ] exports contain no raw command content;
  - [ ] the device key differs from the agent key.
- [ ] **Cortex:** unauthenticated OTLP is rejected; provenance export works; create events bind
  `content_hash`.
- [x] **Kernel:** it no longer imports `registry/`; the tier-off test and Halmos pass. `make verify-kernel`: KernelSwapHarnessTest 2/2,
  KernelPropertiesTest 6/6 (2026-09-28, after A4); tier-off covered by `IntegrityKernelAssuranceTier.t.sol`.
- [x] **Receipts:** a receipt can be created, signed and verified locally, unanchored. `tests/unit/test_core_receipts.py`
  (17 tests: sign/verify, chain, checkpoint, inclusion, tamper/truncation/foreign-key refusals).
- [ ] **Identity:** no private key exists under any harness root in any test or pilot fixture.
- [ ] **Docs:** every active normative document has an identified authority; superseded material is in
  integrity-lab; no active repository holds a competing plan or architecture register.

# Phase B: sellable Shield and Cortex SaaS

**Outcome:** independently deployable, tenant-isolated, pilot-ready products. The first package is
**Integrity Health**: Shield enforcement paired with Cortex provenance, on synthetic regulated data
until Gate C.

## B0. SaaS productization (L)

**Scope guard:** single region and a single node per product, with per-tenant database files. Region
policy is configuration only. HA and Postgres are deferred.

**Shared requirements:**
- [ ] tenant-scoped agents, devices, packs, receipts, memory stores, exports and audit logs;
- [ ] organization-admin and operator roles;
- [ ] device enrollment and revocation;
- [ ] entitlements (no billing);
- [ ] configurable retention;
- [ ] local-first pilot mode with hosted-compatible APIs;
- [ ] usage and audit summaries;
- [ ] backup, restore, tenant deletion and export.

**Shield slice:**
- [ ] signed pack promotion and rollback (the console view reuses the parked policy-packs UI);
- [ ] device health and key status;
- [ ] on-device enforcement with local BCC fallback, and fail-closed regulated mode when both are down;
- [ ] receipt queue and verification status;
- [ ] shadow/enforce modes and signed break-glass.

**Cortex slice:**
- [ ] tenant-scoped providers and stores;
- [ ] agent-scoped content and provenance views;
- [ ] retention, purge, export and provider health;
- [ ] authenticated ingestion and retrieval;
- [ ] spot-check API and proof status.

**Monetization:** pilots are sellable without billing code.
- **Shield:** enforcement, devices, evidence retention and exports.
- **Cortex:** capacity, retention, providers, retrieval and provenance exports.
- **Integrity:** verification is included; public-chain anchoring is a higher tier.

## B1. Packs, adapters and the conformance kit (M)

- [ ] `packs/base` and `packs/hipaa` each contain `pack.yaml` (with per-class defaults), `policy.rego`
  and `controls.yaml`, seeded from `CONTROLS_MATRIX.md`:
  - [ ] HIPAA §164.312(a)(1)/(b) and §164.502(b);
  - [ ] SOC 2 CC6.1/CC7.2;
  - [ ] ISO 42001.
- [ ] The compiler rejects policy relaxation.
- [ ] `baa.py` is deterministic.
- [ ] The adapter contract and conformance kit ship with a sample third-party adapter.
- [ ] BAA conditions are operational controls; the evidence does not certify legal compliance.

## B2. Gates emit receipts (M)

- [ ] BCC and Shield evaluate the same compiled pack and pass shared conformance vectors in CI.
- [ ] Both support atomic loads, fail-closed reason codes, shadow/enforce modes, and signed chained
  receipts with checkpoints.
- [ ] Shield's local gate daemon exposes a Unix socket for PreToolUse.

## B3. Claude Code hooks (S)

`integrity hooks install --harness claude-code --gate shield|bcc --memory cortex` does three things:
- [ ] writes the DID file into the harness root and the key outside it;
- [ ] writes marker-tagged hooks;
- [ ] is idempotent, and uninstall is exact.

## B4. Verifiable evidence (M)

- [ ] A dedicated protocol evidence instance of `StateAnchor` (same code, separate from each agent's
  memory `StateAnchor`).
- [ ] `anchor_batch_per_agent` stops writing receipt roots into agent anchors, whose `latestRoot` is the
  memory root that registration checks.
- [ ] Local Anvil in Phase B. Queued receipts anchor after recovery.
- [ ] `integrity verify` checks signature, chain position, inclusion and anchor.
- [ ] Testnet deployment needs owner approval.

## B5. Telemetry policy (S)

- [ ] `regulated` is the default with `hipaa`: no content leaves the boundary; signals are derived at the
  edge and marked self-reported.
- [ ] The receiver strips `user.email` and other prohibited identity fields.
- [ ] Negative tests cover:
  - [ ] prompts, tool arguments, file contents;
  - [ ] environment variables, stdout/stderr;
  - [ ] URLs and query strings, filenames, repository names;
  - [ ] exception messages and stack traces.

## B6. Pilot packaging (M)

A reproducible pilot with:
- [ ] one organization admin, and at least two tenant-scoped agents and devices;
- [ ] policy promotion and rollback;
- [ ] Cortex store creation, retention, purge and export;
- [ ] a local receipt queue with verification;
- [ ] operator-visible health;
- [ ] synthetic-data reset and tenant teardown.

The pilot demonstrates that Shield and Cortex stay useful when the anchor, the oracle and vendors are
down.

## B7. Revenue-facing exports (M)

- [ ] A Vanta private integration linking per-control tests to receipts.
- [ ] OCSF 6003 and JSONL exports.
- [ ] Local acceptance uses Vanta fixtures.

## Gate B-local

**Setup:** Compose, local Integrity services, a local Anvil evidence anchor, Shield, Cortex, BCC,
synthetic regulated data and Claude Code hooks.

**Required:**
- **Enforcement:**
  - [ ] a PreToolUse without an active BAA is denied on-device by `hipaa`, and the receipt cites the
    control and pack hash;
  - [ ] shadow mode records without enforcing.
- **Evidence:**
  - [ ] receipts anchor locally, and offline verify passes;
  - [ ] tampered, wrong-key, wrong-proof and truncated-tail receipts fail;
  - [ ] queued receipts anchor after recovery.
- [ ] **Data boundary:** a traffic audit shows no content leaving the boundary.
- **Packs:**
  - [ ] golden hashes pass, and every rule cites a control;
  - [ ] the sample adapter passes the conformance kit.
- [ ] **Exports:** Vanta fixture tests pass.
- **Tenancy and devices:**
  - [ ] two tenants cannot read or alter each other's data;
  - [ ] revoked devices get no new packs and their receipts are rejected, while they still fail closed
    locally.
- [ ] **Resilience:** Shield and Cortex stay operational when the anchor and oracle are down.
- [ ] **Retention:** purge removes content and keeps only permitted non-content evidence.
- [ ] **Entitlements:** enforced without billing.

## Gate B-integrations (optional)

Each result is recorded as verified, unverified or blocked; tick an item once it has a recorded
result. None of these invalidates Gate B-local.

- [ ] Base Sepolia evidence anchor (owner-approved broadcast).
- [ ] Vanta sandbox run.
- [ ] External oracle/BCC connectivity.

# Phase C: production-grade Integrity trust

Phase C follows the first pilots and does not block synthetic-data sales.

## C1. Kernel mediation (L)

- [ ] Disable ERC-1271. If analysis keeps it, it must not validate Permit/Permit2 typed data, and any
  signed approval counts as outflow.
- [ ] EntryPoint is deposit-only; `withdrawTo` is blocked.
- [ ] Approvals count as outflow.
- [ ] The rescue sweep stays only as a documented, bounded exception.
- [ ] Proofs: kernel M1 test, sequence invariant, ERC-7579 conformance, `mediation_audit.py`.

## C2. Accounts and registration (M)

Accounts deploy via standard CREATE2 from the canonical `IntegrityAccount`.

**Registrar verification, off-chain:**
- [ ] runtime bytecode is compared with the artifact, with immutables masked via
  `immutableReferences`;
- [ ] immutable values are checked through getters;
- [ ] the kernel binding and `packHash` are checked the same way;
- [ ] re-verification runs on every `KernelSwapped` event;
- [ ] BCC and Shield trust a `packHash` only after verification.

**Registration:**
1. [ ] The account calls the registrar.
2. [ ] The registrar verifies an Ed25519 attestation over the account, chain ID, DID, guardian, pack hash,
   memory provider and XNS handle.
3. [ ] The registrar verifies canonical bytecode and the kernel binding.
4. [ ] A conforming memory provider completes genesis.
5. [ ] The registry records the account, DID, provider and handle.

Registration rejects forged or replayed attestations, non-canonical accounts, mismatched guardians,
and roots with no provider behind them.

**Also:**
- [ ] a shared `ReputationRegistry`;
- [ ] `integrity contracts claim` for ERC-173 recognition;
- [ ] an authoritative, verified `packHash` pushed to Shield.

## C3. Verified memory (M)

**Cortex:**
- [ ] store-wide append-only provenance;
- [ ] encryption at rest;
- [ ] `spot_check(root, index, nonce)`;
- [ ] an anchorable provable root;
- [ ] hard purge of content, FTS, blobs, embeddings, replicas and keys;
- [ ] a PHI-redaction hook and pack-driven retention.

**The oracle:**
- [ ] spot-checks without receiving PHI;
- [ ] turns failures into `MemoryUnavailable` receipts.

## C4. Human oversight (S)

- [ ] Approval receipts are bound to the action HMAC, and both gates re-check them.
- [ ] Break-glass approvals are signed and expire.
- [ ] `pack simulate --since 90d` runs before enforcement changes.
- [ ] Replayed, expired, wrong-action, wrong-pack and wrong-agent approvals are rejected.

## C5. Cutover (M)

- [ ] Run an Anvil regenesis dry run, then broadcast a fresh Base Sepolia genesis with owner approval.
- [ ] Migrate the 15 registered agents, from both the `registerPrimitives` and `registerCore` paths,
  preserving DIDs, XNS handles and valid history. Agents without provider-backed memory are reported
  as blocked.
- [ ] Move the legacy account model, `SovereignAgent`, the PrimitiveSet templates, `IntegrityToken` and
  the ZK interfaces to integrity-lab.
- [ ] Rebuild the CLI on the SDK and remove duplicate implementations.

## Gate C

- [ ] **Kernel:** mediation proofs and conformance pass; an over-budget UserOp reverts.
- **Registration:**
  - [ ] forged or replayed registrations are rejected;
  - [ ] canonical verification is enforced, including after a kernel swap;
  - [ ] no self-scoring.
- [ ] **Memory:** a provider-backed spot-check passes, a digest-only fake fails, and purged content is
  unrecoverable.
- [ ] **Oversight:** replayed approvals are rejected.
- [ ] **Cutover:** the dry run preserves DIDs, handles and history; no load-bearing references to the
  legacy account model or cut code remain in active repositories.

## 9. Expected outcomes by gate

| After | You have | You may claim | You may not claim |
|---|---|---|---|
| Gate A | One trust layer (JCS, packs, receipts, identity with keys outside harness roots); about 22k lines moved to the console; cut code in the lab; a handful of authoritative docs with drift CI; Shield and Cortex standalone | "Simpler, consistent architecture; products run independently" | Any compliance or security guarantee |
| Gate B-local | The Integrity Health demo on synthetic data: on-device HIPAA deny → signed receipt citing the control → offline verify → green Vanta test. Two pilot-ready, tenant-isolated products that survive outages | "Enforces configured policy with independently verifiable evidence" (pilot, synthetic data) | HIPAA certification, real-PHI readiness, real-funds safety |
| Gate C | Proven kernel mediation, forgery-resistant registration, spot-checked memory, real purge, non-replayable approvals, a fresh testnet with the 15 agents' DIDs and handles preserved | Readiness for real-PHI and real-funds pilots, subject to audit | Mainnet or audited status; HIPAA certification (still needs SOC 2 Type II and a BAA) |

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
| 12 | The planned rename to integrity-kernel had no technical driver and would collide with the `IntegrityKernel` contract name | Owner decision 2026-09-28: keep integrity-core; rename, its checkpoint and interim naming rule removed |
| 13 | The plan said RFC 9162 Merkle proofs, but the repo already standardizes on OpenZeppelin semantics (`merkle-standardization.md`, `spec/vault-merkle`, `StateAnchor.verifyLeaf`) | A2 uses the existing convention; a second scheme would be a duplicate authority |
| 14 | "Root `integrity.py`" was ambiguous; `integrity_sdk/integrity.py` is the SDK's documented quickstart (`integrity.auto()`) | Kept as the Access entry point; the other listed SDK modules were cut |
| 15 | The oracle carried its own bb-backed ZK verifier and extra market-only routes (`credit`, `contracts`, `/v1/stats`) | Cut with ZK and markets; telemetry `zk_proof` is accepted but never verified |
