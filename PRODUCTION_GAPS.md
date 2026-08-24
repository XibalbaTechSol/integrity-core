# Production Architecture Gap Analysis & Codebase Audit

> **Current pointer — 2026-08-17:** Phase 0 identity closure and the Whitepaper v3.2/specification reconciliation are recorded in the newest section of [`HANDOFF.md`](HANDOFF.md). The accepted normative baseline remains [`spec/integrity-protocol-v0.4.md`](spec/integrity-protocol-v0.4.md); [`spec/integrity-protocol-v0.5-proposed.md`](spec/integrity-protocol-v0.5-proposed.md) is not accepted, and Whitepaper v3.2 is explanatory. This document remains the detailed append-style gap register; dated entries below are not silently rewritten.

Following a deep audit of the `integrity-core` codebase, the following outlines the specific, technical gaps required to connect the `integrity-dashboard` UI to the backend production systems.

## 1. Oracle (`integrity-oracle/backend`)
*Current State:* Streaming, real OTLP ingestion, and time-bucketed historical queries
are now real (see `stream.rs`, `otlp.rs`, migration `0004_timescale_and_otel_spans.sql`)
— verified end-to-end against a live server with the real, unmodified SDK exporter and
a real EIP-191-signed ingest, not just unit-tested. What's below is what's still
genuinely open, not a restatement of the original three gaps.
* **Closed - Streaming Telemetry (SSE):** `GET /v1/stream` and
  `GET /v1/agent/{id}/stream` push `TelemetryEvent`/`OtelSpan`/`AisUpdate` frames over
  Server-Sent Events (not WebSocket — every consumer here only receives, never sends).
  `AisUpdate` always comes from `handlers::compute_ais_for_agent`, the same function
  `GET /v1/agent/{id}/ais` calls, so a pushed score can never drift from a direct read —
  proven by `oracle_e2e_sse_matches_direct_ais` (real HTTP, real signature, asserts
  numeric equality). Fan-out is an in-process `tokio::sync::broadcast` channel, correct
  at today's single-oracle-instance scale (`docker-compose.yml`); Redis pub/sub is the
  noted scale-out path if the oracle is ever run as more than one replica, not built.
* **Closed - OTLP Ingestion:** `otlp.rs` runs a real `tonic` gRPC server on
  `OTLP_GRPC_ADDR` (default `0.0.0.0:4317`) implementing `TraceService`/`MetricsService`
  from `opentelemetry-proto`. This lights up `integrity-sdk`'s already-working
  `OTLPSpanExporter` (which previously exported into a void) — verified with the real
  exporter, not a hand-rolled client, in `oracle_e2e_otlp_ingestion`. Spans are
  PHI-scanned (same backstop as `POST /v1/telemetry/ingest`) and persisted to a new
  `otel_spans` table, deliberately **separate from `telemetry_events` and never an AIS
  input** — real OTLP spans carry no signature envelope, so treating them as
  equally-trusted input would let an unauthenticated source move an agent's score. This
  stays true — and `/v1/agent/{id}/otel/volume`'s data should be treated as
  unauthenticated, not tamper-evident — until real SDK-side span signing exists (see
  item 2 below, still open). Metrics export is accepted (the SDK's `OTLPMetricExporter`
  gets a real response) but not parsed/persisted — no metrics table exists yet; a real,
  named gap, not a silent one.
* **Partially closed - Time-Series Storage:** `otel_spans` is a genuine TimescaleDB
  hypertable (`CREATE EXTENSION timescaledb` + `create_hypertable`, see
  `docker-compose.yml`'s `postgres` service, now `timescale/timescaledb:latest-pg16`).
  `telemetry_events` is deliberately **not** converted to a hypertable — it's referenced
  by an inbound foreign key from `judge_evaluations.telemetry_event_id`, and TimescaleDB
  does not support foreign keys that reference a hypertable; converting would break that
  constraint for no clear payoff at current data volumes. `time_bucket()` (via
  `GET /v1/agent/{id}/ais/history`, `.../telemetry/volume`, `.../otel/volume`) works
  against `telemetry_events` regardless, since the function only needs the extension
  installed, not the target table to be a hypertable. **Still open:** the GraphQL layer
  (`async-graphql`) named in the original ask was deliberately deferred — only 2-3 fixed
  query shapes exist today, served by the three REST endpoints above; GraphQL is the
  first thing to add if/when the query surface actually grows past that. Continuous
  aggregates/compression policies (Timescale features that matter once volume is large)
  are also not configured yet — not needed at current/Dashboard volume.

### 1a. AIS input-signal trust (server-side re-derivation)
*Current State:* `POST /v1/telemetry/ingest` used to store the client's self-reported
`derived_signals` (entropy/grounding/sacrifice/compliance) verbatim as the actual AIS
inputs — a signature proved *who* sent them, never *whether they were honest*. The
oracle now independently recomputes entropy/grounding/sacrifice server-side from the
raw `otel_spans` content already inside the same signed request (`backend/src/derive.rs`,
mirroring `integrity_sdk/telemetry/derive.py`'s algorithms and `crate::phi`'s
defense-in-depth posture), and does the on-chain "compliance gate wins" check itself
rather than trusting an SDK-side opt-in. Verified end-to-end
(`oracle_e2e_recomputed_grounding_overrides_inflated_client_claim`): a client claiming
an inflated grounding score while its own signed `otel_spans` contain hallucination
markers gets the oracle's low, real recomputation stored and scored, not its claim.
Two pre-existing scoring-formula bugs, found while making this change, were fixed in
the same pass: `performance_variance`'s polarity was inverted relative to what
`calculate_entropy_score` expects (stable claims scored *worse*), and `gpu_hours_verified`
was double-log-compressed (SDK pre-normalized to `[0,1]`, then `scoring-core` log-compressed
again) — both fixed at the `derive.rs` call site, no `scoring-core` changes needed.

**Still open, deliberately out of scope for this pass:**
* **ZK-boost binding is looser than the name implies.** `db::aggregate_for_ais` computes
  `zk_verified_this_period` as `BOOL_OR(zk_verified)` over the whole reporting window — a
  single ZK-proof-bearing submission flips the boost boolean for the *entire period's
  average*, not just the specific event the proof was submitted with.
  `ingest_telemetry` never decodes/cross-checks the proof's `public_inputs` against the
  specific submission's `nonce`/`derived_signals` either. Tightening this to a genuine
  per-event binding needs a circuit/on-chain change (the real ZK circuit,
  `integrity-zkp/src/main.nr`, proves identity+intent-commitment binding only — it has no
  numeric/behavioral inputs today, so it doesn't attest to entropy/grounding/sacrifice
  claims at all).
* **TEE/Tier-3 attestation is unwired.** `integrity_sdk/security/attestation.py`'s Nitro
  attestation *verifier* is real, tested against a real captured AWS fixture, and
  correctly pins the root CA — but nothing in the codebase calls it. No oracle endpoint
  resolves an agent to Tier 3 ("Institutional," AIS ceiling 1000 per the README's
  verification ladder) via a real attestation check.
  `NitroAttestationGenerator.get_attestation_document` is an honest
  `NotImplementedError` (no enclave hardware available), not a mock.
* **`covered_entity_address` spoofing.** The oracle's on-chain compliance check trusts
  whatever `covered_entity_address` a client supplies in `otel_spans[].metadata` — an
  agent could name a genuinely-compliant third party's address to earn the on-chain-wins
  ceiling without being that entity's agent. Identical, pre-existing behavior to the
  SDK's own caller-supplied `covered_entity_address` kwarg (`derive.py`) — not a new gap
  introduced here.
* **Oracle-to-chain score push — CLOSED.** `bcc_middleware/app/reputation.py` +
  `app/scoring_loop.py` now periodically (`SCORE_SYNC_INTERVAL_SECONDS`, default 300s)
  list every agent the oracle knows about, accept each one's geometric, tier-capped
  `ais` from `GET /v1/agent/{id}/ais` as authoritative, remove only the response's
  reported ZK multiplier, and sign+submit a real
  `ReputationRegistry.updateScore(agent, baseScore)` transaction per agent. Also raises
  a real `Slasher.raiseDispute` when an agent's oracle-computed flagged-telemetry ratio
  (`GET /v1/agent/{id}/telemetry/volume`) crosses `DISPUTE_FLAGGED_RATIO_THRESHOLD`
  (default 50%) over a minimum sample size (`DISPUTE_MIN_EVENTS`), locking
  `DISPUTE_STAKE_BPS` (default 10%) of the agent's currently-available stake, subject to
  a per-agent cooldown (`DISPUTE_COOLDOWN_SECONDS`) so one ongoing misbehavior pattern
  doesn't spam duplicate disputes. `POST /v1/reputation/sync` triggers one cycle
  on-demand for ops/tests. 21 real tests (12 against a real anvil chain via
  `MockReputationRegistry`/`MockSlasher` fixtures, 9 orchestration tests with the oracle
  HTTP boundary mocked) in `bcc_middleware/tests/test_reputation.py` and
  `test_scoring_loop.py`.

  Deliberately reuses `bcc_middleware`'s existing `ANCHOR_SIGNER_PRIVATE_KEY` /
  `ANCHOR_ROLE` signer (via a `REPUTATION_SIGNER_PRIVATE_KEY` override that falls back to
  it) rather than standing up a new dedicated oracle-signer service — an explicit,
  user-made tradeoff: less new infrastructure and no new key to custody, at the cost of
  coupling `bcc_middleware`'s pre-execution policy-gate trust domain to score-settlement
  and dispute-raising. `integrity-oracle` itself remains deliberately read-only
  (`chain.rs`'s own invariant is untouched).

  Residual gaps, explicitly out of scope for this pass:
  - **Single signer, still.** On today's single-operator testnet deployment
    (`deployments.baseSepolia.json`), `ANCHOR_SIGNER_PRIVATE_KEY` and the on-chain
    `oracleSigner`/`disputer` roles are the same address, so this "just works" without
    any new role grant. Production key-separation (a distinct `ORACLE_ROLE` /
    `DISPUTER_ROLE` key from the anchor signer) is not built — `REPUTATION_SIGNER_PRIVATE_KEY`
    exists as the seam for that, but nothing forces its use.
  - **Dispute signal is a flagged-ratio heuristic, not a BCC-commitment-vs-on-chain-action
    comparator.** `raiseDispute` fires off the oracle's already-real per-event `flagged`
    boolean (see the entropy/grounding/sacrifice/compliance re-derivation above), not a
    dedicated "does this agent's signed BCC commitment match what it actually did
    on-chain" check — that comparator still doesn't exist anywhere in the monorepo.
  - **No idempotency/backoff tuning beyond the fixed interval + cooldown.** A crashed
    or slow score-push cycle simply retries on the next `SCORE_SYNC_INTERVAL_SECONDS`
    tick; there's no exponential backoff or per-agent staggering, so a large agent
    population could see one slow cycle delay everyone's next update.
  - **Merkle anchoring is still batch-size-triggered only** (see `bcc_middleware/app/anchor.py`),
    not on the same periodic loop this section adds — a low-traffic agent's anchoring can
    still lag independently of its now-working score sync.

## 2. Oracle (`integrity-oracle/backend`) — findings from a full-package audit, ALL CLOSED

*Current State:* the audit below covers `routes.rs`/`handlers.rs`/`derive.rs`/`chain.rs`/`otlp.rs`/`db.rs` end-to-end. Every finding from this pass has been fixed and verified against real infra (9 e2e tests, up from 6, all passing against real Postgres/Redis/anvil/SDK; 72 backend + 8 scoring-core unit tests; `cargo clippy` clean).

* **CLOSED — compliance/`flagged` polarity was inverted, live, for every agent.**
  `handlers.rs`'s `ingest_telemetry` computed `flagged = compliance > 0.5` against a
  high-is-good `compliance` value (from `oracle_compliance()`, matching
  `derive::self_reported_compliance`'s `1.0 - flagged_ratio` and the on-chain branch's
  `Ok(false) => 0.0`) — inverted for every agent: a clean batch scored `flagged = true`
  (penalized), an all-violation batch scored `flagged = false` (not penalized). Fixed to
  `compliance < 0.5`. Regression test `oracle_e2e_compliance_flagged_polarity_is_correct`
  submits both a clean and an all-violation batch over real HTTP and asserts polarity via
  both the ingest response and the `GET /v1/agent/{id}/telemetry` read-back — verified to
  actually catch the bug (fails on the pre-fix comparator, passes on the fix).
* **CLOSED — `GET /v1/leaderboard` had no cache.** Now backed by `leaderboard_cache`/
  `leaderboard_sync` (migration `0005_leaderboard_cache.sql`), mirroring
  `markets_cache`/`markets_index_sync`'s exact staleness-cache pattern
  (`MARKETS_CACHE_STALENESS_SECS`, reused). `refresh_leaderboard_if_stale` re-enumerates
  `agents` and refreshes every row only when the last full sync is >30s old; reads are
  served from cache and sorted numerically via `U256` comparison (not lexicographic
  string sort, which would have put "9" above "10").
* **CLOSED — OTLP gRPC receiver had no rate limiting.** `otlp.rs` now runs the same
  fixed-window Redis limiter shape as `POST /v1/telemetry/ingest`
  (`check_otlp_rate_limit`, distinct `ratelimit:otlp:*` key namespace, same configured
  `telemetry_rate_limit_per_minute`), checked once per resource-spans group before any
  PHI scan or Postgres write. Verified end-to-end
  (`oracle_e2e_otlp_rate_limit_rejects_excess_spans`): the real SDK exporter's third
  export within a tiny-overridden window gets a real `RESOURCE_EXHAUSTED` gRPC status,
  and only the within-limit spans land in `otel_spans`.
* **Documented, not removed — Merkle-anchoring dead code.** `db::fetch_pending_leaves`/
  `create_merkle_root_and_assign` (`db.rs`) are confirmed to have zero callers anywhere;
  real anchoring happens entirely through `bcc_middleware/app/anchor.py`'s independent
  per-agent batching, an incompatible single-global-root vs. per-agent-sub-root design.
  Left in place (real, tested in isolation) rather than deleted, since deleting would
  also mean dropping the `merkle_root_id`/`leaf_index` fields `GET /v1/agent/{id}/telemetry`
  already exposes (now doc-commented as "always null today" at both the DB and DTO
  layers) — kept as the oracle-side alternative if a future design ever needs the oracle
  itself, not bcc_middleware, to anchor a cross-agent root.
* **CLOSED — nonce-replay (409) and rate-limit (429) test coverage.** Three new e2e
  tests: `oracle_e2e_telemetry_nonce_replay_returns_409` (same nonce twice → second
  submission 409s, event count stays at 1), `oracle_e2e_telemetry_rate_limit_returns_429`
  (tiny rate-limit override, third submission in-window 429s), and the OTLP rate-limit
  test above. `GET /v1/agents`/`GET /v1/agent/{id}`/history endpoints/single-market
  detail remain untested by e2e — smaller, lower-risk gap, not addressed this pass.

## 3. Python SDK & CLI (`integrity-sdk`, `integrity-cli`) — findings from a full-package audit, ALL CLOSED

*Current State:* `integrity-cli` does not import `integrity-sdk` — independent
reimplementations kept in sync by cross-package tests, not shared code. Every finding below
was fixed AND verified by actually running the resulting test suite against real
infrastructure (real anvil for chain-touching tests, real HTTP mocks for client-only logic) —
no fix was accepted on code-review alone. SDK: 122 passed, 1 skipped. CLI: 68 passed, 1
skipped.

* **CLOSED — CLI minted testnet ITK to the agent's wallet, not its SovereignAgent contract.**
  Reordered `integrity-cli/integrity_cli/main.py`'s registration steps (funding → deploy
  SovereignAgent → deploy StateAnchor → mint ITK to the SovereignAgent *contract*, not the
  wallet → grant anchor role → register primitives), matching `integrity-sdk`'s already-fixed
  sequence. `integrity-cli/tests/test_chain.py::test_cli_chain_full_registration` now asserts
  the on-chain ITK balance lands on the contract, not the EOA.
* **CLOSED — registration had no idempotency, in both SDK and CLI.** `integrity_sdk/chain.py`
  gained `resolve_did()`, which calls the real `XibalbaAgentRegistry.resolveDID` and — a real
  bug caught while building this — had to be written to catch the contract's
  `UnknownDID()` custom-error *revert*, not treat the ABI's `view` mutability as proof it
  never reverts. `registration.py`'s `register_agent()` now short-circuits to the existing
  on-chain primitives when the DID already resolves, instead of deploying a second orphaned
  pair. Verified end-to-end: `test_register_agent_is_idempotent_for_an_already_registered_did`
  calls `register_agent()` twice for the same identity and asserts both calls return
  identical primitive addresses.
* **CLOSED — `EHRGate` ABI + Integrity Health wrapper functions.** `scripts/sync_abis.py` now syncs
  `EHRGate`; new `integrity_sdk/health.py` wraps `CoveredEntityRegistry`/`SmartBAAFactory`/
  `SmartBAA`/`ComplianceGate`/`EHRGate`, reusing `markets._execute_via_agent` for every
  agent-routed call. Verified against real anvil-deployed contracts in
  `tests/test_health.py`: a full happy path (register covered entity → create BAA → agent
  signs it → self-declared compliance → patient grants EHR access → AIS pushed above
  threshold → access check passes → `verifyAndLogAccess` succeeds) plus a negative case
  proving the on-chain AIS-threshold gate is real, not decorative (access stays denied when
  the agent's score is left at the registry's zero default despite consent + an active BAA).
* **CLOSED — telemetry client nonce handling stalled permanently after a process restart.**
  `client.py`'s `flush_telemetry` now calls a new `_sync_nonce_from_oracle()` (reads
  `GET /v1/agent/{id}`'s `last_nonce`) before the first flush of a fresh client instance, and
  a 409 response re-syncs from the oracle instead of blindly rolling back (the old behavior,
  which just replayed the same already-consumed nonce forever). Verified with 4 new mocked-
  HTTP unit tests in `tests/unit/test_client.py` covering: first-flush sync, no redundant
  sync on later flushes, 409 → re-sync (not rollback), and non-409 failure → rollback (still
  correct for that case, since the oracle never saw that nonce at all).
* **CLOSED — `security/attestation.py` claimed test coverage that didn't exist.** Wrote
  `tests/test_attestation.py` against the real captured fixture
  (`tests/fixtures/aws_nitro_document.cbor`) — signature/chain/root-pin verification,
  payload field exposure, validity-period enforcement, five independent tamper-detection
  cases, and malformed-input handling. Running it for the first time surfaced two real,
  pre-existing bugs in the code under test, both fixed here:
  1. **The pinned root-CA fingerprint constant was truncated by one hex character** (63
     chars — an impossible length for a SHA-256 hexdigest, always 64) — every single call to
     `verify_nitro_attestation` unconditionally raised `AttestationError`, meaning Nitro
     attestation verification was completely non-functional in production, silently, until
     this test suite ran it for the first time. The bundled PEM itself is genuine (the real
     fixture's cert chain validates against it end-to-end once the constant is corrected).
  2. **A corrupted/tampered certificate could crash the verifier with an unhandled
     `ValueError`** rather than reporting `chain_valid = False`: `cryptography`'s ASN.1
     parsing is lazy, so a cert can load successfully yet still raise when a field like
     `.subject` is read later (exactly what an error-message-formatting f-string did). Added
     a `_safe_subject_name` helper and wrapped certificate loading in a typed
     `AttestationError`, so malformed attacker-supplied input degrades to a reported failure
     instead of an uncaught exception — this is security-critical code processing untrusted
     input, so a crash there is a real hardening gap, not just a test nuisance.
* **CLOSED — wallet keystore write path was an unguarded, non-atomic, check-then-act race,
  duplicated in both packages.** Both `integrity_sdk/wallet.py` and
  `integrity_cli/wallet.py` now write to a per-call temp file (`O_CREAT | O_EXCL`) and claim
  the final path via `os.link` (atomic, fails with `FileExistsError` instead of silently
  overwriting like `os.rename` would) — a losing concurrent caller discards its own generated
  keypair and loads the winner's instead of orphaning it. Added typed `CorruptedKeystoreError`
  / `WalletDecryptionError` in place of raw `JSONDecodeError`/`ValueError`. Verified with a
  race-simulation test in both packages (`test_concurrent_bootstrap_converges_on_one_keypair`,
  using a monkeypatched `os.open` to inject a second "concurrent" caller mid-write) proving
  both callers converge on one keypair with no leftover temp files.
* **NEW CAPABILITY — SDK telemetry integrations widened (operational metadata), plus a real
  breaking behavior change to redaction defaults.** Following a request to widen what the SDK
  captures per-call, `integrations/openai_integrity.py` and `integrations/langchain_callback.py`
  both gained real, previously-uncaptured fields the underlying provider already returns:
  `model_requested`/`model_actual`, `system_fingerprint`, `service_tier`, `tool_calls` (names
  only — `function.arguments`/tool `args` are deliberately never captured, since they can carry
  caller-supplied content that hasn't been through redaction), `conversation_length`, and a
  previously-nonexistent error path for the OpenAI wrapper (it had zero telemetry on a failed
  call before this; LangChain's `on_llm_error` already existed) that logs
  `type(exception).__name__` as a real, provider-native error taxonomy rather than a
  hand-maintained code mapping. Neither integration had any test coverage before this — both
  now do (`tests/unit/test_openai_integrity.py`, `tests/unit/test_langchain_callback.py`, 13
  new tests total, using realistic `SimpleNamespace`/real-`langchain_core`-class fixtures since
  hitting the real OpenAI/Anthropic APIs isn't feasible in a test run).
  **Real behavior change, explicitly requested and confirmed:** both integrations' `redact_phi`
  parameter now defaults to **`False`** (previously, `redact_text()` ran unconditionally on
  every prompt/completion/reasoning-trace/tool-call string in both files). Per explicit
  decision: PHI/PII redaction is now opt-in, scoped to Integrity Health / healthcare-vertical
  agents, who **must** pass `redact_phi=True` when constructing `IntegrityOpenAI` /
  `IntegrityLangChainCallback` — neither wrapper has any way to know an agent's
  `compliance_vertical` on its own (that's registered separately), so nothing here can safely
  auto-detect "this needs redaction." Both wrappers log a `logger.warning` naming the agent at
  construction time whenever `redact_phi` is left at its default `False`, so a misconfigured
  healthcare deployment is at least loud about it rather than silent — but there is **no
  runtime enforcement** preventing a healthcare-vertical agent from being built without
  `redact_phi=True`. This is a real, accepted residual risk from the chosen default, not an
  oversight: flagged here so it isn't lost track of, and worth a `health.py`-level guard (e.g.
  refusing to proceed, or checking `compliance_vertical` against a resolvable registry) as a
  real follow-up rather than relying on every integrator remembering the flag.

## 4. Smart Contracts (`contracts/src`) — findings from a full-package audit, ALL CLOSED

*Current State:* 209 Foundry tests passing as of 2026-08-17. Web3 wallet
connectivity and real on-chain writes from the frontend already exist (see §7) — the
prior version of this section's "zero Web3 connectivity" claim was stale and has been
removed. Every finding below is fixed and covered by a new regression test.

* **CLOSED — `SmartBAAFactory.createBAA` permanently blocked re-forming a BAA after
  termination.** `baaOf[coveredEntity][businessAssociate]` was set once and never
  cleared — neither `SmartBAA.revoke()` nor a slashing `arbitrate(true)` cleared it, so
  `createBAA` reverted `BAAAlreadyExists` forever after the first termination, with no
  renewal path (BAAs are routinely renewed in practice). Fixed: `createBAA` now allows
  re-formation once the existing BAA's `status()` reaches `Terminated`, while still
  blocking a duplicate while `Proposed`/`Active`/`Disputed`. Three new tests
  (`test_canReformBAAAfterRevoke`, `test_canReformBAAAfterSlash`,
  `test_cannotReformBAAWhileDisputed`) in `test/health/SmartBAA.t.sol`.
* **CLOSED — `IntegrityMarket.resolve()` to a zero-stake outcome permanently locked the
  whole pool.** No check that `outcomeStaked[_winningOutcome] > 0`; an honest resolver
  reporting a genuinely zero-stake true outcome made every position hit `LosingPosition`
  with `totalStaked` unclaimable by anyone, forever. Fixed: `claimPayout` now handles the
  "push" case — when `winningPool == 0`, every position holder is refunded exactly their
  own original stake instead of a pari-mutuel share, draining the pool completely with no
  shortfall. New test `test_resolveToZeroStakeOutcome_refundsEveryoneTheirOwnStake` in
  `test/markets/IntegrityMarket.t.sol`.
* **CLOSED — `A2ACapitalPool.flagBreach` had no status guard, contradicting its own
  NatSpec.** NatSpec said it's for a *Released* allocation, but the code never checked
  `a.status` — calling it on a still-`Escrowed` or already-`ClawedBack` allocation
  (wrong id, stale data) set `Breached` with funds still inside and no path back to
  `Escrowed`. Fixed: requires `status == Released`, reverting `NotReleased()` otherwise.
  Two new tests (`test_flagBreach_revertsOnStillEscrowedAllocation`,
  `test_flagBreach_revertsOnClawedBackAllocation`) in `test/markets/A2ACapitalPool.t.sol`.
* **CLOSED — `EHRGate` (the actual PHI-access enforcement contract) was never deployed
  anywhere.** Not in `Deploy.s.sol`, `DeployMarkets.s.sol`, or
  `deployments.baseSepolia.json`, despite being real, fully tested in isolation, and
  explicitly relied on by `ComplianceGate`'s own NatSpec. Fixed: `Deploy.s.sol` now
  deploys `EHRGate` as part of genesis (verified end-to-end against local anvil — logs,
  deploys, and writes the address into `deployments.local.json` correctly). A new
  incremental script, `script/DeployEHRGate.s.sol` (mirrors `DeployMarkets.s.sol`'s
  established "add one singleton to an already-live deployment without re-running
  genesis" pattern), adds it to Base Sepolia's existing deployment without touching any
  other singleton — verified end-to-end against local anvil simulating the live file's
  exact current shape (including the missing-`XibalbaNameService` case below, handled via
  a `keyExistsJson` guard rather than reverting). **Not yet run against live Base
  Sepolia** — that's a real, gas-costing, operator-triggered action
  (`forge script script/DeployEHRGate.s.sol --rpc-url base_sepolia --broadcast --verify`
  with `FUNDER_PRIVATE_KEY` set) deliberately left for the account holder to run.
* **CLOSED (deployed 2026-07-26) — XNS is live on Base Sepolia.** `XibalbaNameService` is
  deployed at `0x71f42aC04781c41e007e7f03244235341ce15cc8` (chainId 84532) and written into
  `deployments.baseSepolia.json`, via the new incremental `script/DeployXnsGovernance.s.sol`
  ("funder signs, agent owns": funder `0x67bA…D556` paid gas, the Xibalba agent
  `0xabfeEaCbA00F38810E697b2970399fE03080FBeB` holds `DEFAULT_ADMIN_ROLE`/`REGISTRAR_ROLE`).
  Verified live: `GET /v1/xns/resolve` now returns 200 (was 400 MissingSingleton). The
  register-handle *write* flow is now wired into the dashboard as of 2026-08-02 (see the
  correction at the end of this entry) — the "deliberate deferral, CLI/SDK for now" framing
  below is the original, now-superseded record.
  Historical note (pre-deploy): `deployments.baseSepolia.json` previously had no
  `XibalbaNameService` key. What's now real: the `XibalbaNameService.sol`
  contract (14 forge tests passing), the oracle's read path — `ChainClient::{resolve_handle,
  primary_handle}` over a `sol!` `IXibalbaNameService` interface, exposed as
  `GET /v1/xns/resolve?handle=…` and `GET /v1/agent/{id}/handle` — and the dashboard wiring
  (`oracle.resolveXns` / `oracle.getAgentHandle`, consumed by `XNSSearchService` handle
  lookups and `DIDExplorer`'s `XNS_RESOLVE` field). The oracle reads the singleton live where
  it exists (`deployments.local.json` has it at the deterministic anvil address, deployed by
  genesis `Deploy.s.sol`) and returns **400 MissingSingleton** — an honest "not deployed on
  this network yet", never a fabricated handle — where it doesn't (Base Sepolia). The single
  remaining step is the operator-run, gas-costing deploy of `XibalbaNameService` to Base
  Sepolia + writing its address into `deployments.baseSepolia.json`; `DeployEHRGate.s.sol`
  already tolerates the missing key via a `keyExistsJson` guard so no other singleton is
  disturbed until then. Originally recorded here as **read-only in the UI by design** (handle
  lookup wired, register-handle deferred to CLI/SDK). **Correction (2026-08-02): the write is
  now wired too.** New `chain/xns.ts` + `components/ui/XNSRegisterForm.tsx` (mounted in
  `IdentityPanel`) call `XibalbaNameService.register(handle)` routed through the agent's own
  `SovereignAgent.execute` — the same `executeAsAgent` convention every other on-chain write
  in this dashboard already uses (`chain/markets.ts`), required because `register` checks
  `agentRegistry.isRegisteredAgent(msg.sender)`, so a direct wallet-EOA call would always
  revert. Also fixed in the same pass: `src/deployments.baseSepolia.json` (the dashboard's
  own mirror of the root deployments file) was missing the `XibalbaNameService` **and**
  `IntegrityGovernance` singleton entries entirely, despite both being live on Base Sepolia —
  the write flow could not have been wired without that fix regardless of UI code.
* **CLOSED (deployed 2026-07-26) — on-chain governance is live on Base Sepolia.**
  `IntegrityGovernance` is deployed at `0x62ef8A3B42b07FDee7498199696dae31AC2A9255` (chainId
  84532), guardian/owner = the Xibalba agent `0xabfeEaCbA00F38810E697b2970399fE03080FBeB`
  ("funder signs, agent owns"), genesis params (3-day vote / 2-day timelock / 1,000 ITK
  threshold / 10,000 ITK quorum — verified via `quorumVotes()` on-chain). Deployed via the
  incremental `script/DeployXnsGovernance.s.sol` + written into `deployments.baseSepolia.json`.
  Verified live: `GET /v1/governance/proposals` now returns 200 `[]` (was 400 MissingSingleton);
  `GovernancePanel`/`GuardianPilot` now render the live (currently empty) proposal set. Voting
  is now wired into the dashboard as of 2026-08-02 (see the correction below); propose/queue/
  execute remain a deliberate CLI/SDK-only deferral, for a narrower reason than voting was.
  Historical note (pre-deploy): originally a full gap (no Governance contract existed, and the
  panels honestly showed a roadmap + "not live" notice). Now real: `IntegrityGovernance.sol`
  — lock-to-vote (ITK locked to propose/vote; flash-loan/sybil resistant precisely because
  IntegrityToken has no fee-on-transfer, so `transferFrom` credits exactly `amount`), a
  hand-rolled but hard-constrained timelocked execute (action fixed at propose time and run
  verbatim, `nonReentrant`, ETA + bounded grace window), with an index-based read surface
  (`proposalCount` / `getProposal` / `state`) — plus 26 forge tests covering the full lifecycle
  and adversarial paths. The oracle reads it via `ChainClient::read_proposals` over a `sol!`
  `IIntegrityGovernance` interface, exposed as `GET /v1/governance/proposals`; the dashboard's
  `oracle.getGovernanceProposals` feeds both `GovernancePanel` (live proposal cards) and
  `GuardianPilot`. It is wired into genesis `Deploy.s.sol` (deploys + serializes the singleton),
  so a fresh deploy includes it. The endpoint returns **400 MissingSingleton** — and both panels
  stay in their honest "Not Yet Live" state, never a live-but-empty list — anywhere the singleton
  is absent (Base Sepolia today; also the current `deployments.local.json`, deliberately NOT
  regenerated because a fresh local deploy would remint every address and invalidate the seeded
  audit DB's agent DIDs). Remaining: the operator-run, gas-costing Base Sepolia deploy +
  `deployments.baseSepolia.json` entry. Originally recorded here as **read-only in the UI by
  design**, with the write half deferred "done via CLI/SDK for now" — that CLI/SDK claim was
  never actually true: `integrity-cli/integrity_cli/main.py`'s own module docstring records
  that a `governance` sub-app existed in the old prototype and was deliberately NOT rebuilt in
  this rewrite ("Re-add it once/if a real backend contract for it exists" — one now does, but
  the CLI was never updated). Nothing anywhere could vote until this pass.
  **Correction (2026-08-02): `castVote` is now wired into the dashboard, `propose`/`queue`/
  `execute` remain deferred, deliberately and for a different reason than before.** New
  `chain/governance.ts` + `GovernancePanel`'s vote form call `IntegrityGovernance.castVote(id,
  support, amount)`, routed through `executeAsAgent` exactly like the XNS write above, with the
  same approve-then-act ITK flow `ActuarialHub`'s market-entry code already established
  (top up the SovereignAgent's ITK balance if short, approve the Governance contract for the
  vote amount, then cast). `propose`/`queue`/`execute` are excluded on purpose, not from time
  pressure: `propose` accepts an arbitrary `(target, value, callData)` and `execute` runs it
  verbatim after the timelock — exposing that through a generic UI without a security review
  of what actions a proposal could carry is real governance/financial risk, not a UI gap. They
  stay CLI/SDK-only until a real CLI/SDK governance path is built (see the correction above:
  none exists yet either).
* **CLOSED — `CCIPReputationBridge.bridgeReputation` had no refund for overpaid native
  fee.** `msg.value - fee` was permanently trapped (no `receive()`/`withdraw()`/sweep
  anywhere). Fixed: the excess is now refunded to `msg.sender` via a low-level call
  immediately after `ccipSend`, with the function now `nonReentrant` (added
  `ReentrancyGuard`) since that refund is a call to an attacker-controlled address, unlike
  the trusted, fixed-address router call preceding it. New test
  `test_bridgeReputation_refundsExcessNativeFee` in `test/CCIPReputationBridge.t.sol`.

## 5. BCC Middleware (`bcc_middleware`) — findings from a full-package audit, ALL CLOSED

*Current State:* 91 pytest (75 baseline + 16 new) + 28 OPA tests passing, with `uv run
pytest -q` (no env overrides) now matching that count exactly. `app/reputation.py`/
`scoring_loop.py` (the new score-push/dispute signer, see §1a) are real and tested. Every
finding below was fixed and verified against real infrastructure — real anvil for chain-writing
tests, real threading for the nonce-race and batcher-concurrency regressions, real HTTP
round-trips through the actual FastAPI app for the token fix.

*A second-pass review of these fixes (not the original audit) surfaced three follow-on
items, all closed in the same pass:*
* **`MerkleBatcher` wasn't thread-safe.** The hot-path fix below (wrapping
  `_flush_and_anchor` in `asyncio.to_thread`) made concurrent `add()`/`flush()` access
  possible for the first time — previously `run_intercept` was single-threaded end-to-end,
  so this was never reachable. `add`/`flush`/`is_full`/`reset`/`pending_count` are now
  guarded by a `threading.Lock` held for the full check-then-act sequence. A stress test
  (many concurrent adders + flushers) is included as regression coverage; note this
  specific race did NOT reproduce empirically even under aggressive
  `sys.setswitchinterval` stress testing (unlike the nonce race below, which reproduced
  reliably) — the fix is based on a direct code-level trace of the unguarded multi-op
  `batch, self._pending = self._pending, []` swap racing a concurrent `append`/second
  `flush()`, not on a captured failure. Documented here rather than silently claimed as
  "proven", per this repo's own rule.
* **`_issued_tokens` (new in the token fix below) grew unbounded** — one entry per
  authorized intercept, forever, unlike the agent-count-bounded `nonce_store`/
  `circuit_breaker`. Capped at 50,000 entries with oldest-first eviction.
* **Tests silently depended on `CHAIN_ID` being unset.** `_settings()`-style test helpers
  never passed `chain_id=` explicitly, relying on `Settings`' env-var default — which
  silently picks up the repo-root `.env`'s `CHAIN_ID=84532` (Base Sepolia) instead of the
  local anvil fixture's real `31337`, breaking 11 tests for anyone whose shell inherits
  that file. Fixed at the source: the session-scoped `anvil_chain` fixture now sets
  `os.environ["CHAIN_ID"]` to the real anvil's chain ID before any test constructs a
  `Settings()`, rather than requiring ~15 individual call sites across 5 test files to each
  remember to override it.

* **CLOSED — the intercept hot path blocked the single asyncio event loop on synchronous
  chain/oracle I/O.** `run_intercept`'s three offending calls (`resolve_verification_tier`,
  `check_baa_status`, `_flush_and_anchor`) are now wrapped in `asyncio.to_thread`, matching
  `_score_sync_loop`'s existing pattern — no I/O runs directly on the event loop anymore.
* **CLOSED — `verification_token` proved nothing and was checked by nobody.** New
  `app/verification_token.py`: the token is now HMAC-SHA256-keyed with a process-local
  secret (`Settings.bcc_verification_secret`) rather than a bare `sha256` of public fields —
  unforgeable without the secret — and persisted (in-memory, same accepted scope as
  `nonce_store.py`) so a relying party can ask `POST /v1/bcc/verify_token` whether a given
  token was genuinely issued for exactly those commitment fields. Verified: a token cannot
  be reproduced by recomputing `sha256` of the public fields (the old scheme could be, by
  construction); two independently-started `Settings()` instances get different secrets and
  reject each other's tokens; a full HTTP round trip through real `/v1/bcc/intercept` →
  `/v1/bcc/verify_token` confirms `valid: true` for a genuine token and `false` for a forged
  one.
* **CLOSED — cross-thread signer nonce race between anchoring and reputation sync.** New
  `app/nonce_lock.py`: a process-wide, per-signer-address `threading.Lock` held for the FULL
  read-nonce → sign → broadcast → mine sequence in `anchor.py::anchor_root`,
  `reputation.py::push_score`, and `reputation.py::raise_dispute`. Verified two ways: (1) with
  the lock removed, 8 concurrent `push_score` calls sharing one signer key against a real
  anvil produced 6/8 real `"nonce too low"` RPC errors, confirming this was a genuine,
  reproducible race, not a theoretical one; (2) with the lock restored, the same 8-thread test
  passes cleanly every time, on-chain state confirmed for all 8 agents.
* **CLOSED — `POST /v1/bcc/anchor/flush`'s returned `root` didn't match what was actually
  anchored.** `AnchorResult` gained a `root` field set to the real per-agent sub-root
  `anchor_batch_per_agent` computes and submits; the endpoint now returns each agent's own
  root under `agents[agent_id].root` instead of the discarded full-batch root. Verified
  against real anvil: the returned root for each agent independently recomputes to
  `merkle_root` over only that agent's own leaves, and two agents in the same flushed batch
  get two distinct, individually-correct roots.
* **CLOSED — score pushes were unconditional every cycle, even when unchanged.**
  `scoring_loop.py` caches the last-successfully-pushed `base_score` per agent
  (`_last_pushed_score`, same in-memory posture as the existing dispute cooldown) and skips
  the real transaction when unchanged, only updating the cache on a confirmed submission (so
  a failed push is retried, never permanently skipped). Verified against real anvil: a second
  sync cycle with an identical score submits no transaction; a cycle with a genuinely
  different score does, confirmed by reading the new value back on-chain.
* **CLOSED — Active Quarantine Enforcement.** New `app/quarantine.py` + a new step 4b in
  `run_intercept` (`app/main.py`): every commitment now reads `Slasher.lockedStakeOf(agent)`
  on the agent's own Slasher clone before OPA evaluation, and denies (`AGENT_QUARANTINED`) if
  it's nonzero — i.e. the agent has stake locked under an unresolved dispute
  `scoring_loop.py::raise_dispute` raised. No separate un-quarantine step was needed:
  `Slasher.resolveDispute` always decrements `lockedStakeOf` back to zero regardless of
  outcome, so the gate clears itself the moment governance resolves the dispute.
  **Deliberately fails OPEN, not closed, on an unverifiable check** — this is the one place
  this service's stated fail-closed posture is inverted, and on purpose: unlike the BAA check
  (scoped to a narrow healthcare intent class), this gate runs on *every* request, so failing
  closed would mean one oracle/RPC hiccup denies all traffic from every agent. Only a
  positively confirmed locked dispute denies; a check that can't be completed logs a warning
  and lets the request continue to OPA. First implementation failed closed here too and broke
  15 of the suite's pre-existing tests that don't stand up an oracle/anvil fixture — caught
  by running the full suite, not by review, and corrected before landing.
* **Merkle anchoring is still batch-size-triggered only (confirmed, see §1a)** — no
  periodic equivalent to the score-sync loop exists for it yet.
* **In-memory `nonce_store`/`circuit_breaker` are safe today but block horizontal
  scale-out.** Verified `docker-compose.yml`: single instance, no `deploy.replicas` — so
  this is a real gap only the moment this service is ever scaled to >1 replica (an
  attacker could replay a commitment or reset a lockout by hitting a different replica).
  Needs Redis-backed state before that happens, not urgent today.

## 6. `integrity-userapi` (user accounts, strictly non-chain) — ALL CLOSED

*Current State:* all four findings below are fixed and verified against a real Postgres
(`userapi-postgres`, port 5435) — 49 tests passing (up from 35), plus 6 new real-HTTP tests
in `integrity-dashboard/demo` for the new userapi bridge. No mocked internals anywhere in the new
coverage: auth flows run through the real FastAPI app + `asgi-lifespan`, and the demo-bridge
tests hit a real local `ThreadingHTTPServer`, matching this package's existing
`_FakeOracleServer` pattern.

* **CLOSED — developer API keys now actually authenticate requests.** `get_current_user_id`
  (`app/deps.py`) accepts either a JWT bearer token *or* an `X-API-Key` header carrying a raw
  `uak_...` key; the latter is sha256-hashed and looked up against `api_keys.key_hash WHERE
  revoked_at IS NULL`, resolving to the key's owning `user_id`. Every existing route that
  depended on `get_current_user_id` gained this for free (no per-route changes needed) —
  `GET /me`, `GET /api-keys`, `/me/agents`, `/demo/*` are all now reachable with either
  credential. Deliberate exception: minting (`POST /api-keys`) and revoking (`DELETE
  /api-keys/{id}`) a key are JWT-only (`get_current_token`, not `get_current_user_id`) — an
  API key that could mint further keys would let one leaked long-lived credential perpetuate
  itself past its own revocation, so credential-management stays gated behind the shorter-lived,
  individually-revocable JWT. Revoking a key now has a real, immediate effect: `revoked_at IS
  NULL` in the lookup means a revoked key 401s on its very next use. Regression tests in
  `tests/test_api_keys.py` (`test_api_key_authenticates_a_request`,
  `test_revoked_api_key_no_longer_authenticates`, `test_unknown_api_key_401s`,
  `test_api_key_resolves_to_its_own_owner_not_another_users`,
  `test_api_key_cannot_mint_further_api_keys`, `test_api_key_cannot_revoke_api_keys`) replace
  the old docstring that explicitly said this code path didn't exist.
* **CLOSED — JWTs are now revocable.** `create_access_token` (`app/security.py`) stamps a
  per-token `jti` (uuid4) into every issued token; `decode_access_token` now returns a
  `DecodedToken(user_id, jti, expires_at)` instead of a bare string. New
  `migrations/0002_jwt_revocation.sql` adds a `revoked_tokens(jti PK, user_id, revoked_at,
  expires_at)` table. `get_current_token` (`app/deps.py`, the dependency `get_current_user_id`
  now delegates to for the bearer-token path) checks `revoked_tokens` on every request. New
  `POST /auth/logout` inserts the presented token's `jti` there — and, since it now has the
  transaction open, opportunistically `DELETE`s any `revoked_tokens` rows past their own
  `expires_at` first, so the table self-prunes without needing a separate cron/worker (a
  revoked token whose `exp` has already passed could never be replayed anyway — `jwt.decode`
  rejects it on expiry before `revoked_tokens` is ever consulted). Tests:
  `test_logout_revokes_the_token_immediately`,
  `test_logout_only_revokes_the_presented_token_not_others` (two independent logins for the
  same user get distinct `jti`s; revoking one doesn't touch the other),
  `test_logout_requires_a_valid_token`.
* **CLOSED — login now rate-limits repeated failures.** New `app/login_limiter.py`
  (`LoginRateLimiter`) mirrors `bcc_middleware/app/circuit_breaker.py`'s in-memory
  per-key-counter-plus-timed-lockout shape, keyed on the lowercased login email rather than an
  agent DID, with deliberately looser defaults (`login_failure_threshold=5`,
  `login_lockout_duration_seconds=300`, vs. bcc's `violation_threshold=3`/`900s`) since a login
  form has a much higher legitimate-typo rate than a signed agent commitment. `POST
  /auth/login` checks `is_locked_out` first (429 + `Retry-After` header if tripped), records a
  failure on a bad password, and clears the counter on success. Same accepted single-process
  state tradeoff as the circuit breaker it mirrors (would need Redis for multi-replica). Tests:
  `test_login_locks_out_after_repeated_failures` (even the *correct* password 429s once
  locked out), `test_login_lockout_is_scoped_to_one_email`,
  `test_login_success_resets_the_failure_count`.
* **CLOSED (real bridge added; UI trigger explicitly out of scope, documented) — `demo_runs`
  now has a real completion path.** New `PATCH /demo/runs/{id}` (`app/main.py`,
  `DemoRunUpdateRequest` in `app/schemas.py`) lets an authenticated owner transition their run
  through `running` → `completed`/`failed`, stamping `finished_at` only on a terminal status
  and storing a real `result_summary` JSONB payload (asyncpg now round-trips `jsonb` as plain
  dicts everywhere via a codec registered in `app/db.py::create_pool` — previously
  unregistered, since nothing had ever written non-null JSONB before this). New
  `integrity-dashboard/demo/src/integrity_demo/userapi_bridge.py` calls this endpoint from the
  scenario engine itself: `main()` now reports `running` at start and `completed`/`failed` (with
  a real summary — agents registered, their sovereign-agent addresses, or the exception string)
  at the end, entirely opt-in via three env vars (`USERAPI_URL`/`USERAPI_TOKEN`/
  `USERAPI_RUN_ID`) an operator sets when they want a specific `make demo` invocation tied back
  to a `demo_runs` row created beforehand — unset, it's a no-op, so the engine still runs
  standalone exactly as before. Callback failures are logged and swallowed, never raised,
  matching this repo's fail-open posture for non-authorization side channels (same posture as
  `bcc_middleware`'s best-effort Merkle anchoring). Tests: `tests/test_demo_runs.py` (PATCH
  transitions, 404 on unknown/other-user's run, 422 on an invalid status) and
  `integrity-dashboard/demo/tests/test_userapi_bridge.py` (6 tests against a real local HTTP server:
  no-op when unset, bearer-vs-`X-API-Key` header selection, and that HTTP/connection errors are
  swallowed, not raised). Honest coverage note: `main()`/`_run_scenario()`'s own refactor (the
  split that lets `main()` wrap the real scenario in a try/except and report `completed` vs.
  `failed`) is inspection-verified, not runtime-tested — running it needs a live Base Sepolia
  RPC + funded wallet, which is outside what this fix's test run could exercise. The
  `userapi_bridge` module itself (what actually talks to userapi) has full real-HTTP coverage;
  the call sites around it in `main()` do not. Genuinely still out of scope, not fixed here:
  nothing in `integrity-dashboard`'s dashboard UI currently creates a `demo_runs` row or launches this
  CLI process (`userapi.ts` has no demo-run calls, no "Start Demo" button exists) — `make demo`
  remains an operator-run script against live Base Sepolia using a funder private key, not
  something the frontend can trigger; wiring that would need a job-queue/worker service, a
  materially bigger and separate piece of scope than closing the recording/reporting gap this
  finding was actually about.

## 7. Frontend (`integrity-dashboard`) — findings from a full-package audit, ALL CLOSED

*Current State:* real backend wiring landed this session for `ChainOfThoughtPage`,
`SdkTelemetryPage`, `IntelligencePage`, `CompareTracesPage`, `HealthPage`'s Stability
Certification tab, and the dashboard's `throughput`/`events`/`radar` widgets.
`AgentContext.tsx` is confirmed real (calls `oracle.listAgents()`) — this doc previously,
incorrectly, listed it as mock; that was stale. Two real on-chain write paths already
exist via wagmi (`HealthPage.tsx`'s BAA sign/revoke, `ExchangePage.tsx`'s market entry) —
the prior "zero Web3 connectivity" claim in this doc was also stale and has been removed.
`npm run build` (`tsc -b && vite build`) now succeeds cleanly — verified end-to-end,
including the 3 unrelated pre-existing unused-import errors that were silently failing
the production build before anyone had run it locally.

* **CLOSED — `npm run test` currently fails.** `vitest.config.ts`'s exclude list doesn't cover
  `demo/`, so Vitest picks up a `node:test`-based file inside `integrity-dashboard/demo/` and
  fails to bundle it — red CI/local runs even though the app's own tests pass. **Fix:**
  add `'demo/**'` to the exclude array. One line.
* **CLOSED — undefined CSS custom properties beyond the `--primary`/`--gold` pair fixed
  earlier this session.** `--bg-surface` (12 files), `--border`/`--border-main` (5+3
  files), `--space-2` through `--space-12` (a full spacing scale, 9+ files), the broken
  `hsla(var(--accent-primary) / 0.5)` in `.glass-panel-hover:hover` (was a hex string,
  not an HSL triplet — the whole declaration silently dropped), `--accent-primary-hsl`
  (added per-theme, since it can't be derived from the hex color at runtime), plus ~25
  more (`--bg-card`, `--shadow`/`--shadow-lg`, `--glass-*`, `--r-xs/sm/md`, status/brand
  aliases) found by a full `var(...)`-reference sweep, not just the originally-named
  ones. All added to `:root` as aliases of existing theme tokens. Verified visually
  across Dashboard/Contracts/Exchange/CompareTraces/Health/Documents/Finance/Identity.
* **CLOSED — `AuditPage.tsx` made a specific, false security claim with no mock-data
  disclosure.** Its copy asserted actions are "cryptographically hashed and anchored to
  Base L2" and "cannot be tampered with by the agent, host, or hypervisor," backed by 3
  hardcoded `LoggerContext.tsx` entries (including a fabricated tx hash) — nothing was
  hashed, nothing was anchored. Rewritten to honestly state what's real (BCC Middleware
  DOES batch-anchor approved intents, best-effort, not yet per-event) versus what this
  specific page shows (a simulated local event feed, now `SeededDataBadge`-marked, no
  real audit-trail query endpoint exists yet).
* **CLOSED — `HealthPage.tsx`'s consent/slash actions were theater, not disclosed
  stubs.** `handleSlashViolation` showed a native `alert()` claiming "Locked ITK Stake
  Slashed" with no contract call at all. Neither action can honestly be wired to a real
  transaction from this dashboard (EHRGate.grantAccess/revokeAccess are PATIENT-signed;
  a real slash needs Slasher's arbiter role after a dispute window) — both now use
  `addToast('info', ...)` with an explicit "Simulated only... No transaction was sent"
  message, matching the real wagmi handlers' toast pattern instead of a native `alert()`
  that read as more legitimate than it was. Fixing this surfaced a second, separate real
  bug: `.toast`/`.toast-container` had NO CSS anywhere in the app, so every toast in the
  app (including the real wagmi success/error toasts) rendered invisibly — fixed
  alongside, verified visually (toast now renders bottom-right, styled, on click).
* **CLOSED — `CompareTracesPage.tsx` was 100% hardcoded to 3 fixed fake trace IDs
  despite `oracle.getTraceTree()` already working in `ChainOfThoughtPage`.** Now
  discovers recent trace_ids from the real SSE stream (same "no list-traces endpoint,
  only get-by-id" pattern `ChainOfThoughtPage` already proved out) and fetches each via
  the real endpoint; Gantt offsets/widths/durations, the JSON payload tab, and the
  Deviations panel are now all computed from the real fetched span trees instead of a
  curated fake pair. Honest empty/error states when no real trace has streamed in yet.
* **CLOSED — radar widgets in `WidgetRegistry.tsx`/`IntelligencePage.tsx` plotted fixed,
  fabricated dimensions ignoring real `AisComponents` already fetched elsewhere.** Both
  now plot the real entropy/grounding/sacrifice/compliance breakdown
  (`oracle.getAis()`) — the dashboard widget for the selected agent, the Intelligence
  page for the top 2 real leaderboard agents — with an honest "select an agent" /
  "needs 2+ leaderboard agents" fallback instead of ever showing a fabricated number.
* **CLOSED — `HealthPage.tsx`'s "Stability Certification" tab was hardcoded despite
  sibling tabs on the same page already proving the live oracle+on-chain-read pattern.**
  The tier badge is now derived from the real AIS score; the BAA Compliance Ratio from
  the real per-agent BAA data this same page already fetches via `getLogs`/
  `readContract`. "Prediction Accuracy (Markets)" and "Collateral Health Factor" have no
  real backend source anywhere in the monorepo (no market-prediction-scoring endpoint;
  `Slasher.sol`'s real `stakeOf`/`lockedStakeOf` aren't wired to this frontend) — shown
  as an explicit "Not available" state instead of a fabricated percentage.
* **VERIFIED, NOT A REAL GAP — `ActuarialHub.tsx`'s original finding ("could use real
  `oracle.listMarkets()`") doesn't hold up under inspection.** `oracle.listMarkets()`
  returns `MarketSummaryDto` — real `IntegrityMarket` prediction-market data (`question`,
  `outcome_count`, `resolve_deadline`, per-outcome staking), already correctly used by
  `ExchangePage`. `ActuarialHub`'s agent-hiring-task marketplace concept (`title`,
  `reward_itk`, bidding, escrow) is a structurally different domain with no
  corresponding oracle endpoint at all — substituting `listMarkets()` in would produce a
  broken, nonsensical page, not a fix. The component already carries precise, accurate
  disclosure at both of its real mock points (`"A2ACapitalPool has no oracle read
  endpoint yet"`, `"No benchmark-ingestion endpoint yet"`) — no code change needed here;
  this bullet is corrected rather than closed by a wire-up.
* **CLOSED — several buttons had no handler at all, undisclosed.** `IdentityPage.tsx`'s
  "Rotate Keys"/"Request Credential"/"Launch XNS Explorer" turned out to already be wired
  in a later redesign this session missed on first read; "Regenerate Attestation
  Document" and "Stake ITK"/"Withdraw" are now `disabled` with an honest `title` tooltip
  (`NitroAttestationGenerator` really does raise `NotImplementedError` rather than fake a
  document; `Slasher.sol` has real `stake()`/`unstake()` entrypoints but this frontend
  doesn't sync the Slasher ABI or resolve the agent's Slasher clone address yet — a real
  follow-up, not silently abandoned). `FinancePage.tsx`'s Receive/Send/Swap/Buy are
  disabled with per-action tooltips (no transfer/DEX/fiat-onramp integration exists
  anywhere in this stack); "New Allowance Rule" is disabled (OPA policies are static
  Rego files, not dynamically editable via a UI); "View Explorer" is now wired for real
  — opens the connected wallet's address on the actual configured chain's block explorer
  via wagmi's chain config, not a placeholder.
* **CLOSED — `DocumentsPage.tsx`** was fully fabricated with no backing capability
  anywhere (`oracle.ts`/`userapi.ts` have no document/RAG-indexing endpoint) and no
  disclosure badge. Added an explicit "Not yet implemented" banner + `SeededDataBadge`,
  and disabled the "Upload Document" button with a tooltip explaining there's nowhere
  for an uploaded file to go — matching the honestly-badged posture of every other
  Tier-4 mock in the app instead of being the one silent exception.
* **CLOSED — `TriMetricWidget.tsx` (dashboard's "Tri-Metric Risk Analysis" panel) badged
  itself "LIVE MODEL" while every number on it was fake.** Found during a follow-up audit
  focused specifically on this widget. `avgAis` was picked from 3 hardcoded magic
  constants (920/850/950) gated on a crude threshold; `blockedRate` ("0.42") and
  `riskExposure` ("12,500") were literal strings with no computation at all; all three
  sparklines were fabricated trend arrays. Unlike every sibling in
  `WidgetRegistry.tsx` (which either fetches real data or renders a `SeededDataBadge`),
  this one did neither — the single most severe fake-data surface left in the dashboard.
  Fixed two of the three metrics with real data reusing existing infrastructure: `AIS
  Deficit` and `BCC Intent Violation Rate` now fan out `oracle.getAis()` across every
  agent in the already-global `AgentContext` (same real-data pattern `DashboardPage.tsx`'s
  `gauge` widget already used), averaging real `ais` and `components.compliance` — the
  latter is exactly `(1 - flagged_ratio) * 1000` per scoring-core's own polarity, so
  inverting it back out recovers the real BCC-violation ratio the formula names, not a
  proxy. The third metric ("Smart BAA Value at Risk") is now honestly marked unavailable
  via `SeededDataBadge` instead of showing a number: no probability-of-leak model exists
  anywhere in this protocol (same conclusion independently reached for ActuarialHub
  earlier this session), and no network-wide index of staked BAA collateral exists either
  — `SmartBAA.requiredCollateral()` is only readable per-BAA-address today (confirmed via
  `HealthPage.tsx`), there's no "list every active BAA" capability to sum across. Building
  that real aggregate would need a new oracle-side indexing endpoint — logged as a genuine
  follow-up, not fabricated here. Fabricated sparklines were removed rather than kept
  under the now-real numbers (a fake trend line under a real value would itself be
  misleading — implies historical data that isn't being fetched). `npx tsc -b --noEmit`,
  `npm run lint`, and `npm run build` all pass clean.
  **Two real runtime bugs were only caught by actually loading the dashboard in a browser
  against the live local stack** (real Postgres/oracle/anvil, one real registered agent,
  `VITE_MOCK_MODE` temporarily overridden to `false` for the test run since the default
  `.env` filters `listAgents()` down to `mock-agent-*` IDs and the one real local agent
  doesn't match that prefix):
  1. The 3 KaTeX formula sub-components (`AisFormula`/`BccFormula`/`ExposureFormula`) were
     defined as local consts *inside* the widget's function body — a pre-existing pattern
     copied forward from the original file, harmless while the widget was static props-only.
     Adding real `useEffect`/`useState` here meant the widget now re-renders on its own
     fetch-driven state changes too, and each re-render redefined those consts as new
     component *types*, forcing React to fully unmount+remount (re-parse) all 3 KaTeX
     formulas every render — observed as `mathVsTextAccents` console warnings flooding
     multiple times per second and freezing the tab (`Page.captureScreenshot` timing out).
     Fixed by hoisting all 3 to module scope; also added a reference-equality guard on the
     `agents.length === 0` branch's `setSamples([])` call to avoid an unnecessary render
     from a fresh-but-equivalent empty-array literal.
  2. Even after the freeze was fixed, the two now-real value numbers ("50.0%"/"0.00%") were
     visually clipped by the grid cell boundary — `DashboardPage.tsx`'s hardcoded
     `DEFAULT_LAYOUTS` gives this widget `h: 2` (300px at `rowHeight=150`), sized for the
     *old* layout where the sparklines were absolutely-positioned background decoration
     that consumed no real flex height. The new layout's formula+value+label content
     needs more room. Bumped to `h: 3`/`minH: 3` in both `lg`/`md` breakpoints
     (`DEFAULT_LAYOUTS`) and `WidgetRegistry.tsx`'s `defaultSize` for consistency;
     react-grid-layout's default vertical compaction reflows every widget below it
     automatically, no other entry's coordinates needed hand-adjusting. Re-verified via
     screenshot: all three metrics (including the honest "Not available" disclosure text)
     now render fully visible with no clipping and no repeated console warnings.
* **Correction (2026-07-16) — the six pages named above (`AuditPage`, `ChainOfThoughtPage`,
  `CompareTracesPage`, `ExchangePage`, `IntelligencePage`, `SdkTelemetryPage`) no longer
  exist under those names.** A later pass in this same session consolidated them into two
  pages: `TraceAnalyticsPage.tsx` (`/traces` — merges `ChainOfThoughtPage`'s Historical
  Traces DAG view and `CompareTracesPage`'s Gantt/compare view into one tabbed page, plus
  new "Metrics"/"Time-Travel Debugger" tabs that are honestly `SeededDataBadge`-marked, no
  backend exists for those two yet) and `SystemDiagnosticsPage.tsx` (`/diagnostics` —
  merges `SdkTelemetryPage`'s real oracle telemetry/OTLP-volume view and `AuditPage`'s
  disclosed-simulated audit-log feed into one tabbed page). `IntelligencePage`'s real
  radar-widget work described above now lives on the Dashboard (`/`) directly.
  `ExchangePage`'s real wagmi market-entry flow was folded into `FinancePage`'s "A2A
  Markets & Escrow" tab (`src/components/finance/MarketsEscrowPanel.tsx`). Verified for
  real (not just by reading code): brought up a full local anvil + `docker-compose`
  stack, generated a genuine 3-span nested OTel trace via the SDK's `traceable()` API
  against the live oracle, and confirmed `TraceAnalyticsPage`'s Live Stream and
  Historical Traces tabs render it as a real DAG with real span attributes, and
  `SystemDiagnosticsPage`'s telemetry volume chart reflects the same real data — the
  full demo→oracle→frontend pipeline this doc's §10 describes is intact after the
  page consolidation, not silently broken by the rename.
* **CLOSED (2026-07-16) — two dangling nav references left over from the page
  consolidation above.** `CommandPalette.tsx`'s "Go to Telemetry" and "View Audit Logs"
  commands still `navigate()`d to `/telemetry` and `/audit`, neither a route in the
  current `App.tsx` — fixed to point at `/diagnostics` (where both capabilities now
  live), and a missing "Go to Trace Analytics" (`/traces`) command was added since that
  page had no command-palette entry at all. `e2e/smoke.spec.ts`'s `ROUTES` array was
  similarly still listing `/cognition`, `/telemetry`, `/exchange`, `/chain-of-thought`,
  `/compare-traces`, `/intelligence`, `/audit` — none real — rewritten to the current
  11-route list; separately, `waitUntil: 'networkidle'` in that same spec never resolves
  on `/` or `/traces`, both of which hold an open SSE (`EventSource`) connection to the
  oracle's live stream by design — switched to `waitUntil: 'load'` plus a 1s settle
  window, which still catches real render/console errors without waiting on a
  connection that's supposed to stay open.
* **CLOSED (2026-07-16) — `FinancePage.tsx`'s live ITK balance was off by 10^18, a real
  bug only caught by loading the page in a browser against a real registered agent.**
  `GET /v1/agent/{id}/wallet`'s `itk_balance` is deliberately the raw on-chain `U256`
  wei-scale decimal string (`integrity-oracle/backend/src/handlers.rs`, ITK is an
  18-decimal ERC-20 like ETH) — `FinancePage.tsx` was passing it straight into
  `Number(itkBalance).toLocaleString()` with no scaling, rendering "9,999,000,...,000
  ITK" and a "$12,498,750,...,000.00" total portfolio value instead of "9.999 ITK" /
  "$35,456.84". Fixed with `formatUnits(BigInt(itkBalance), 18)` (`viem`, already a
  dependency) before formatting. Re-verified live: portfolio value and per-asset balance
  now render sane numbers with no console errors.
* **CLOSED (2026-07-16) — `IdentityPage.tsx` fabricated an AIS score and a false
  hardware-attestation claim for every agent, undisclosed.** `ais = selectedAgent ? 9.5
  : null` was a hardcoded constant (never a real fetch, despite `oracle.getAis()`
  already being the proven pattern on `HealthPage`'s Stability Certification tab);
  `tier` was derived from the coarse `ACTIVE`/`IDLE` status boolean and always showed
  `'AAA'` regardless of real score; worse, `teeVerified = true` was hardcoded
  unconditionally, rendering "TEE Status: Verified (Nitro)" for every agent with no
  real attestation ever performed — `NitroAttestationGenerator` raises
  `NotImplementedError` everywhere else in this codebase (this same page's own disabled
  "Regenerate Attestation Document" button already discloses that honestly). Fixed:
  real `oracle.getAis()` fetch + the same `stabilityTier()` score-banding function
  `HealthPage` already uses, `teeVerified` set to `false` (renders the page's own
  pre-existing honest "Not Attested" branch), and the "TEE Measurements" panel's
  hardcoded PCR0/PCR1 hashes now carry a `SeededDataBadge`. Re-verified live: AIS Score
  "500.0 / 1000", Verification Tier "B" (both matching this agent's real score
  everywhere else in the app), TEE Status "Not Attested".
* **CLOSED (2026-07-16) — Dashboard's `CognitionWidget` ("LLM Routing Layer", "Intent
  Commitments", "Memory & Context") was 100% hardcoded with zero disclosure**, unlike
  its sibling `ThroughputWidget` in the same file which either fetches real data or
  discloses via `SeededDataBadge`. Confirmed no real backend capability exists for any
  of the three: no LLM-routing-config tracking, no latency field anywhere in
  `telemetry_events`/`TelemetryEventDetailDto`, and no RAG/tool-execution-success
  metric anywhere in this monorepo (matches `DocumentsPage`'s already-documented "no
  backend exists" finding). Rather than fabricate a partial wire-up (e.g. a real event
  count next to a still-fake latency number — this doc's own §7 `TriMetricWidget`
  writeup already warns a fake number next to a real one is more misleading, not
  less), added `SeededDataBadge` to all three card headers.
* **CLOSED (2026-07-16) — a full page-by-page sweep of every remaining route for
  undisclosed mocks found and fixed six more, dispatched via 3 parallel investigation
  passes covering every page not yet swept this session.**
  - `ContractsPage.tsx`'s entire Build/Deploy/function-call IDE flow had zero
    disclosure: `handleDeploy` generates a `Math.random()`-derived fake contract
    address and logs `[success] X deployed at 0x...` as if it were a genuine Base
    Sepolia deployment, and per-function "call" buttons log fake `[system]
    Transaction: X() on Y` lines — no compile/deploy route exists anywhere in this
    monorepo (`routes.rs` has none). Added a persistent `SeededDataBadge` to the IDE
    toolbar header rather than build a real compiler/deployer, which is out of scope
    for this stack.
  - `TopBar.tsx`'s notification bell was a fixed 3-item array ("Oracle Connected"/
    "Policy Enforced"/"Attestation Verified" with fabricated timestamps) driving a
    real-looking unread-count badge — no notifications endpoint exists in
    `oracle.ts` or `userapi.ts`. Disclosed via `SeededDataBadge` in the dropdown
    header.
  - `Sidebar.tsx`'s profile footer hardcoded "Admin User" / "Manager" as if a real
    logged-in identity — no global auth/session context threads a real
    `userapi.users.me()` result up to this shell (`SettingsPage`'s login flow is
    self-contained), and there is no `role` field in `UserResponse` anywhere to back
    "Manager" even if it were wired. Disclosed via `SeededDataBadge` rather than
    building new global-auth-state plumbing out of scope for this pass.
  - `IdentityPage.tsx` — see the entry above this one; found via the same sweep.
  - Dashboard's `WidgetRegistry.tsx` `gauge` widget ("Network Security Score")
    silently fell back to hardcoded `94%` / `AIS_DISTRIBUTION_FALLBACK` counts
    (1420/230/12) with zero disclosure whenever `aisDistribution`/`highIntegrityPct`
    hadn't loaded yet — unlike its siblings (`latency`, `nodes`, `costAnalytics`,
    `throughput`, `radar`) which all disclose their fallback state. The real data
    was already being computed and passed in by `DashboardPage.tsx`; the fix was
    purely adding the same conditional `SeededDataBadge` pattern its siblings
    already use, not new plumbing.
  - `FinancePage.tsx`'s "Wallet & Portfolio" hero section remained largely
    fabricated even after the ITK-balance-scaling fix above: `ASSETS`' ETH/USDC
    balances and all three `usdPrice` fields are hardcoded (`WalletResponse` has no
    ETH/USDC balance field or price-feed method anywhere in `oracle.ts`), the "+
    $1,240.50 (4.2%) Today" daily-change line and the 7-day `PORTFOLIO_HISTORY`
    trend chart are both static, and the hero's wallet-address chip showed a
    hardcoded `0x7F...3B92` instead of the real connected `address` (from
    `useAccount()`) already imported and used elsewhere in the same file. Fixed the
    address chip for real; disclosed everything else via `SeededDataBadge`
    (per-asset badge on ETH/USDC rows only, not ITK; a badge on "TOTAL PORTFOLIO
    VALUE" since it sums fake+real; a reference-equality-gated badge on "Recent
    Activity" that only shows when `transactions` is still the unreplaced
    `TRANSACTIONS` fallback array, same technique the `TriMetricWidget` fix already
    used for `AgentContext`-driven fallback detection).
  - Confirmed clean by the same sweep, no changes needed: `SettingsPage.tsx`
    (real `userapi.*` calls or already-disclosed toggles), `HealthPage.tsx`'s Smart
    BAAs/PHI Access Gates/Audit & Compliance/Quarantine Zone tabs (real chain reads
    or already `SeededDataBadge`-marked), `FinancePage.tsx`'s "A2A Markets &
    Escrow" tab (`MarketsEscrowPanel.tsx` — real oracle reads, already-disclosed
    seed sections), and `AgentsPage.tsx`'s stat cards/table (all real
    `oracle.listAgents()`/`getAis()` data — `AgentsPage`'s "Deploy"/"Verify & Claim"
    buttons having no `onClick` handler and no disabled/tooltip disclosure was
    flagged as a separate, lower-severity dead-button issue, not a fabricated-data
    one; not fixed in this pass).
  - `npm run build`/`tsc -b --noEmit`/`npm run lint` clean, 13/13 Playwright e2e
    green, all re-verified live against the real local stack.
* **(2026-07-16) `DocumentsPage.tsx` merged into `HealthPage.tsx` as a new "Documents"
  tab, then removed as a standalone route.** Per explicit request: the page's own
  content was always HIPAA/clinical-document-flavored (`HIPAA_Compliance_Guidelines_
  2026.pdf`, `Patient_Onboarding_Protocol.docx`, `Clinical_Trial_Results_Q3.pdf`), so
  it belongs on the compliance page its filenames are about rather than a separate
  top-level nav item. Moved verbatim (banner, 3 stat cards, trend chart, document
  table) into a new `Documents` entry in `HealthPage.tsx`'s `SUB_TABS`, keeping the
  exact same honest disclosure (`SeededDataBadge`, "Not yet implemented" banner, no
  document/RAG-indexing backend exists anywhere in this monorepo — nothing was
  silently upgraded to "real" in the move). Removed `DocumentsPage.tsx`, the
  `/documents` route (`App.tsx`), and the Sidebar nav entry; `e2e/smoke.spec.ts`'s
  `ROUTES` updated to 10 entries (was 11). `npm run build`/`tsc -b --noEmit`/
  `npm run lint` clean, 12/12 Playwright e2e green, re-verified live: the merged
  "Documents" tab renders correctly under Integrity Health, `/documents` no longer resolves to
  anything.

## 8. CI / Autonomous Fix-Forward (`.github/workflows/ci.yml`)
*Current State:* A real CI workflow now runs every package's test suite (mirroring the root `Makefile`'s `test` target) as separate per-package jobs on push/PR to `main`. The `notify-jules-on-failure` job makes a real call to the Jules API (`POST https://jules.googleapis.com/v1alpha/sessions`, `X-Goog-Api-Key` auth, `AUTOMATION_MODE_AUTO_CREATE_PR`) — verified against `@google/jules-sdk`'s actual published source, not guessed.
* **Gap - One-time repo-owner authorization still required:** the workflow will fail loudly (not silently no-op) until (1) Jules is authorized for `XibalbaTechSol/integrity-core` at jules.google.com (grants its GitHub App repo access), and (2) a `JULES_API_KEY` secret (from jules.google.com/settings/api) is added under repo Settings → Secrets and variables → Actions. Both are account-holder actions no automation can complete on the owner's behalf.
* **CLOSED (2026-07-16) — `auto-merge-jules.yml`'s own actor filter never actually matched anything.** Confirmed via the API: every PR in this repo, including ones on `jules-<id>-<hash>` branches, is attributed to user `XibalbaTechSol` (type `User`), not a distinct `jules-google[bot]` identity `github.actor == 'jules-google[bot]'` checks for. The workflow has likely never fired. Also confirmed `allow_auto_merge` was `false` at the repo level — a documented prerequisite in that workflow's own setup comments that was never actually done; fixed via `gh api` PATCH. `auto-merge-jules.yml` itself was not rewritten (not this pass's file to unilaterally edit) — flagged here so the mismatch isn't lost.
* **CLOSED (2026-07-16) — 21 stale branches, 5 of 8 open PRs in real CONFLICTING state.** Root cause: `auto-merge-jules.yml` only re-evaluates a PR on `opened`/`synchronize`/`reopened`, never when `main` itself advances past it — several Jules branches cut from a similar base drifted into genuine git conflicts as earlier ones merged serially, then sat forever (GitHub won't auto-merge a conflicting PR regardless of how long auto-merge stays "enabled" on it). Verified directly: `gh pr view --json mergeable` showed `CONFLICTING` for #12/14/18/19/24/26. Separately, 18 of 26 total PRs were already merged but their branches were never deleted (no "automatically delete head branches" repo setting). **GitHub Merge Queue is unavailable for this repo** — a `merge_queue` ruleset rule is rejected by the API while an otherwise-identical `required_status_checks` rule succeeds; likely a personal-account plan restriction (org-owned repos get merge queue, and this repo's owner returns `404` on `/orgs/{owner}`). Fix applied instead: a `required_status_checks` ruleset naming the 8 real CI job names from `ci.yml` (verified against the workflow source, not guessed), plus a new hourly workflow (`.github/workflows/close-conflicting-jules-prs.yml`) that finds Jules-branch PRs (matched by branch-name pattern, not the broken actor check) sitting in `CONFLICTING` state and closes them with an explanatory comment — if the underlying CI failure is still real, the next failure on `main` has Jules open a fresh PR against current `main`. **Note:** an earlier attempt also added `required_status_checks` alone (without `merge_queue`) directly to `main`'s branch protection and discovered empirically that it blocks *direct* pushes to `main`, not just PR merges — removed again since that conflicts with this repo's established direct-push workflow; only the auto-close-conflicting-PRs workflow was kept.

## 9. `integrity-dashboard/demo` (scenario engine) — real bugs found by actually running it end-to-end

*Current State:* Previously undocumented — this section is new. Found and fixed by running the real 4-persona scenario engine against a real local anvil chain + real deployed contracts + a real running oracle (not by code inspection), per this repo's "no silent mocks" rule applied to testing itself: a bug that only shows up when you actually run the thing doesn't count as covered just because the code reads plausibly.
* **CLOSED — every span this engine ever exported was silently rejected by the oracle.** `main.py` built one shared, module-level OTel `Resource` with no `integrity.agent.id` attribute at all — the oracle's real OTLP receiver requires it and was rejecting every single span (`resource missing required 'integrity.agent.id' attribute`), 100% of the time, for as long as this file has existed. Worse than a one-line omission: the engine manages 4 *different* agent identities in one process, and OTel's global tracer-provider model (`opentelemetry.trace.set_tracer_provider`, and this SDK's own `telemetry/core.py::init_telemetry` which wraps it) is a one-shot singleton — the first call wins, every later call silently no-ops — so even a naive fix would have misattributed every agent's spans to whichever agent registered first. Fixed with a real per-agent `TracerProvider`/`Tracer` (`_tracer_for(agent_id)`, cached, used directly via `.get_tracer()` and never installed as the process-global provider — the standard OTel pattern for multiple independent resources in one process). Verified for real, not just re-run without error: queried the oracle's `otel_spans` table directly after a run and confirmed real, correctly-attributed `register_agent`/`agent_conversation` rows for all 4 distinct agent IDs.
* **CLOSED — one LLM call failure crashed the entire process.** The capital-allocation tool-calling section had no error handling at all, unlike the registration loop just above it (which already degrades one agent at a time and continues). Reproduced with a real invalid API key present in the environment: a raw Python traceback, non-zero exit, no clean failure report. Wrapped in try/except matching the registration loop's own pattern — the failure is now logged, recorded in the run summary (which `userapi_bridge.report_status("failed", ...)` already had a real path for, previously unable to fire cleanly for this failure mode), and the process exits 0 with whatever did succeed intact.
* **CLOSED — no preflight funder-balance check.** The live Base Sepolia funder wallet sits at ~0.001 ETH — under the SDK's own default per-agent funding amount (0.01 ETH) by 10x, a pre-existing state `FAUCET_INFO.md` already documented but nothing in the demo engine checked before spending gas. A real run against the live network would have failed registration 1 of 4 with a deep RPC error instead of a clear one. `_check_funder_balance` now reads the real on-chain balance via the same `FUNDER_PRIVATE_KEY`/`RPC_URL` `register_agent()` itself uses, and compares against `register_agent`'s own default `fund_amount_wei` (read via `inspect.signature`, not a second hardcoded constant that could drift from the real one) times the agent count, raising a clear, actionable error before any registration is attempted.
* **CLOSED — `make demo` didn't exist.** Referenced in `README.md`/`CLAUDE.md`/`docs/TESTING.md` for the whole life of this rewrite, with no actual Makefile target backing it — the only way to run the demo was to know to `cd integrity-dashboard/demo && uv run integrity-demo` and hand-export four env vars. Added the target (defaults to live Base Sepolia per the existing docs' own description; a local-anvil override is documented in the target's own comment for exactly the funding-shortfall situation above).
* **CLOSED (2026-07-16) — two more real bugs found by actually re-running this engine end-to-end against a real local stack, both of which mean the bullet directly above ("confirmed real, correctly-attributed rows for all 4 distinct agent IDs") was true but incomplete — it verified the spans existed and had the right `service.name`/no-`integrity.agent.id`-missing fix, not that every subsequent run of this same engine would actually reach the oracle.**
  1. **Every span was silently dropped on process exit, 100% of the time, for as long as this fix has existed.** `main.py` never called `force_flush()`/`shutdown()` on any of its per-agent `TracerProvider`s before the process exited. `BatchSpanProcessor` buffers spans and only exports on a timer/batch-size threshold — a short-lived CLI script that exits immediately after its work is exactly the shape of process this silently loses spans for. Confirmed for real: ran the engine, then queried `otel_spans` directly and found zero rows for any of the 4 just-registered agents, despite the spans genuinely being created in-process (confirmed via a minimal isolated repro of the same `TracerProvider`/`BatchSpanProcessor`/`force_flush` pattern, which worked once the flush call was added). Fixed by tracking every created `TracerProvider` (not just the `Tracer` handles `_tracer_for` previously kept) and flushing+shutting down all of them in a `finally` block around `main()`'s scenario run, so telemetry is exported whether the run succeeds or fails partway.
  2. **Every span was tagged with the internal persona short-name (`"capital_allocation_agent"`) instead of the agent's real DID, making it permanently invisible to any per-agent frontend view.** The oracle's telemetry/trace endpoints and every frontend consumer (`AgentContext`, `TraceAnalyticsPage`, `SystemDiagnosticsPage`) key exclusively by DID (`GET /v1/agent/{did}/...`) — a span resource attribute of `"capital_allocation_agent"` instead of `"did:integrity:..."` meant `GET /v1/agent/{did}/otel/volume` would return `[]` forever for that agent, even though the spans were sitting right there in the table under the wrong key. Fixed by resolving the real DID via `load_or_create_did(a["id"])` (a pure local keypair load/create, no chain call, and `register_agent()` calls the same function internally with an identical result) *before* opening each agent's registration span, and threading that real DID through to the capital-allocator's tool-call and conversation spans too (previously hardcoded to the short-name in both the `_tracer_for()` key and the `agent.id` span attribute). Verified for real: `GET /v1/agent/{did}/otel/volume` and `GET /v1/traces/{trace_id}` both now return the correct span data keyed by the real DID, confirmed against a fresh local run with 4 newly-registered agents (fresh `~/.integrity/wallet`/`~/.integrity/did` identities — the prior session's persona keystores were reset for this verification pass, see `docs/wiki/WIKI_LOG.md` for why).
  Also confirmed, not a bug: a freshly-registered agent with zero telemetry history legitimately fails `A2ACapitalPool`'s `AisTooLow(50, 0)` gate when another agent tries to allocate it capital — `bcc_middleware`'s `scoring_loop.py` continuously re-syncs each agent's real oracle-computed score on-chain (`Settings.score_sync_interval_seconds`), so a manual `updateScore` seed gets overwritten by the next real sync cycle within seconds. This is the reputation-sync safety mechanism working exactly as designed, not a demo bug — earning a real score requires real telemetry/compliant activity over time, same as any other agent.
* **Partially closed (2026-08-14) — sequential agent-signed transactions in `integrity_sdk/chain.py` raced `get_transaction_count` against a load-balanced public RPC.** Found running `xibalba-shield/scripts/register_with_oracle.py` against real Base Sepolia via `base-sepolia-rpc.publicnode.com`: `deploy_sovereign_agent` → `deploy_state_anchor` → `grant_anchor_role` → `anchor_genesis_root` are four separate transactions signed by the same freshly-created agent wallet, each fetching its own nonce via `w3.eth.get_transaction_count(agent.address)`. Even with `_wait()` genuinely blocking on `wait_for_transaction_receipt` (confirmed by reading it directly, not assumed) before the next call, the very next `get_transaction_count` could still be answered by a different backend node in the RPC's pool that hadn't yet converged on the just-mined tx, returning a stale nonce and getting the resend rejected outright with `nonce too low` — reproduced three times in a row, at three different points in the sequence (`next nonce 1, tx nonce 0` → `next nonce 2, tx nonce 1` → `next nonce 3, tx nonce 2`), confirming this is systemic to the sequence rather than one flaky call. Each failed attempt orphaned a real `SovereignAgent`/`StateAnchor` pair on Base Sepolia (see `register_with_oracle.py`'s corrected docstring — re-running before full completion is not idempotent). Ruled out before fixing, not assumed: `_wait` (read directly, blocks correctly, no swallowed timeout) and client-side caching (`get_w3` only `lru_cache`s the `Web3`/`HTTPProvider` instance itself, no request-level caching middleware is attached). Fixed two ways: (1) all 9 nonce-fetch call sites in `chain.py` now query the `"pending"` block tag instead of the default `"latest"`, which includes the node's own mempool view; (2) all 9 now go through a new shared `_send_signed` helper that retries once or twice with a short backoff and a fresh nonce fetch specifically on a `"nonce too low"` rejection (never on any other error) — a real, standard mitigation for this exact multi-node-RPC race, not a broader nonce-tracking refactor (that would need to change signatures shared with `markets.py`/tests, and wasn't justified without first confirming — via the two ruled-out causes above — that the race is genuinely RPC-side). **Marked partially closed, not closed:** a live re-run after this fix got substantially further (all the way to the final `registerPrimitives` step, no nonce errors at all) but then hit a different failure — see the next entry — so this fix is confirmed to have resolved the specific nonce race but registration as a whole is still not verified end-to-end. Covered by the full `integrity-sdk` test suite (259 passed, 3 skipped, no regressions).
* **Root-caused and CLOSED (2026-08-14) — `deployments.baseSepolia.json`'s `AgentPrimitivesFactory` address has had NO deployed bytecode since 2026-08-13, and `REGISTRAR_ROLE` on `XibalbaAgentRegistry` has been granted only to that empty address since the same date — registration has been completely broken for every agent, not an SDK bug.** The earlier entry in this file (now corrected) speculated about an SDK-side event-filtering bug; that was wrong. The real chain, confirmed via two independent RPC providers (`sepolia.base.org` and Blockscout's indexed log API, cross-checked against raw `eth_getTransactionByHash`/`eth_getCode`/`eth_call` reads, not trusted from any JSON file or broadcast label):
  1. `contracts/broadcast/RotateOperatorKeyGrant.s.sol/84532/run-latest.json` records a `CREATE` of a new `AgentPrimitivesFactory` at `0x219109961c1c9bB8e9f27a37757a5d426e1f91Ec` with `hash: null` — this transaction, and 12 others after it in the same run, were never actually broadcast (only the first 3 of 22 transactions have real tx hashes; `receipts: []` is empty). `deployments.baseSepolia.json` was updated with this address anyway, as if the rotation had completed. `eth_getCode` confirms zero bytecode at that address today.
  2. Despite the deploy never happening, `REGISTRAR_ROLE` was later granted to this same empty address at block 44942495, and revoked from the real, working factory (`0xC19fc9cB2cB87297EfDF11DA7e211e44A6C1181D`, real bytecode confirmed, 6/6 transactions in `broadcast/FixComplianceGateFactory.s.sol/84532/run-latest.json` genuinely broadcast and verified via on-chain logs) at block 44942506 — both via a `cast send` or similar not captured in any `broadcast/` JSON, presumably trusting the same wrong `deployments.baseSepolia.json` record. Full `RoleGranted`/`RoleRevoked` history for `REGISTRAR_ROLE`, confirmed via Blockscout's log API (`base-sepolia.blockscout.com/api?module=logs&action=getLogs`): genesis factory `0x215f39C8a2Cea2F8c6976fA10bbf48479825aD6e` (block 43837743) → `0xC19fc9cB2cB87297EfDF11DA7e211e44A6C1181D` (granted block 43927267, revoked block 44942506) → the empty phantom address (granted block 44942495, still current).
  3. A call to an address with no bytecode always trivially "succeeds" with empty return data (`0x`) regardless of calldata — this is why every `registerPrimitives` call this session returned `status: 1` with `gasUsed` far too low for the real function (29,270 gas for something that should cost several hundred thousand) and zero logs: it never reached any real contract logic. Confirmed by replaying the exact failing call via `eth_call` against the pre-transaction block, which also returned bare `0x`.
  **Fix**: grant `REGISTRAR_ROLE` back to the real, working factory `0xC19fc9cB2cB87297EfDF11DA7e211e44A6C1181D` (`0x7530bd7Cb142C50d5cC742EdF02263f368e89E2f`, controlled by `.env`'s `ORACLE_SIGNER_PRIVATE_KEY`, confirmed to hold `DEFAULT_ADMIN_ROLE` on the registry today and can do this). This is a stopgap using the existing factory (still has the old shared-key `governance`/`oracleSigner`/`disputer`) — properly redeploying a new factory with the new Safe/EOA roles (see `docs/signer-role-rotation-2026-08.md`) will supersede it once that work completes; this time verify `eth_getCode` on any newly-deployed factory address before writing it to `deployments.baseSepolia.json` or granting any role to it, precisely to avoid repeating this exact class of bug. The SDK-side defensive fixes from the (incorrect) earlier diagnosis — checksummed address comparison, tx-hash/log diagnostics in the error message — are harmless and were kept; they just weren't the actual fix. **Orphaned on-chain from failed attempts against the broken factory, real testnet gas spent, no cleanup path:** at least four `SovereignAgent`/`StateAnchor` pairs, including `0x95e2390D4b826DBCb7A7C3d56F7838bBE5F1087C`/`0xFa4EdF80B9B14D484B9905924D683461803c6292`, `0x9366595315BF23c7e6eEb28B43286D2D43e367cd`/`0x9290e91ea80bBa5E99c2C46eF496670B17Cf020d`, `0x3B3a46507A0029EF205A26cfA81435594350A911`/`0xFC78af016870E0373Fcca675699f02E98e71624D`, `0x4459d17Cc6FFC1BCCFd327584309A4231755667b`/`0x9cBc8A8930E2e86a01921B8d94C19B84949CB584`.
  4. **After granting `REGISTRAR_ROLE` back (verified via `sepolia.base.org`), a registration attempt against the running stack still reverted** with `AccessControlUnauthorizedAccount(0xC19fc9cB..., REGISTRAR_ROLE)` — a real, correctly-decoded custom-error revert this time (`0xe2517d3f`, not a phantom-address silent success), meaning the stack's own view of chain state was stale relative to the grant. Root cause: `.env`'s `DOCKER_RPC_URL` (what `oracle-backend`/`shield` actually use) was still `base-sepolia-rpc.publicnode.com`, the same load-balanced third-party endpoint responsible for the nonce race earlier in this file — evidently also inconsistent for role-state reads, not just nonces. Switched `DOCKER_RPC_URL` to `https://sepolia.base.org` (Base's own official endpoint, already used for all the verification reads in this entry) and restarted `oracle-backend`/`shield` to pick it up.
  5. **Even after switching to the official RPC, two more read-after-write lag instances hit**, confirming this class of issue isn't specific to any one provider — it's inherent to reading state moments after writing it: (a) `fund_agent_wallet`'s transfer confirmed (`_wait` returned a real mined receipt) but `deploy_sovereign_agent`'s very next balance-implied check reported `insufficient funds ... have 0` — verified transient by directly reading the agent wallet's on-chain balance afterward (`0.01 ETH`, exactly the expected amount, nonce still 0) — the funds were there, just not yet visible to whatever backend/view answered the failing check. (b) `grant_anchor_role`'s `StateAnchor.ANCHOR_ROLE().call()`, reading a contract `deploy_state_anchor` had just deployed and `_wait`-confirmed moments earlier, failed with `BadFunctionCallOutput` ("is contract deployed correctly and chain synced?") — verified transient the same way (a manual `cast call` for the same function on the same address, seconds later, returned real data). Fixed generally this time instead of case-by-case: `chain.py` gained `_call_with_retry`, a backoff-retry wrapper specifically for `BadFunctionCallOutput` on read-only `.call()`s, mirroring `_send_signed`'s existing retry-on-stale-nonce pattern for writes — applied to `grant_anchor_role`'s `ANCHOR_ROLE()` read (the confirmed failure site). Covered by the full test suite (259 passed, 3 skipped, no regressions).
  6. **The same lag hit a third form**: a later live attempt failed at `deploy_sovereign_agent` itself with `insufficient funds for gas * price + value: have 0` straight from `send_raw_transaction` — again verified transient (the agent wallet genuinely held 0.02 ETH and nonce 2 immediately after, proving the funds were real and prior sends had gone through). `_send_signed`'s retry condition, previously only "nonce too low", now also catches "insufficient funds" — same reasoning: a rejection at submission never enters any mempool, so retrying costs nothing, and a genuinely-out-of-funds condition still correctly fails after `max_attempts` since it won't resolve on retry. Covered by the full test suite (259 passed, 3 skipped, no regressions). Not yet re-verified with a fresh live registration attempt end-to-end.
  7. **RESOLVED (2026-08-17) — item 4's diagnosis was incomplete, and there was a SECOND missing role grant, not RPC staleness.** Re-ran `xibalba-shield/scripts/register_with_oracle.py` for real against the live stack. It got all the way through step 8b (genesis root anchored, confirmed via `StateAnchor.latestRoot()` returning non-zero) and deployed a real `SovereignAgent`
    (`0x0C24806C751A04B785F1aF3A9E915FE4d4313A77`) and `StateAnchor`
    (`0x4131ccebaA186A95B51f7017f99fF8E55c87B358`) — then failed at step 9 with the exact same `AccessControlUnauthorizedAccount(0xC19fc9cB..., REGISTRAR_ROLE)` revert item 4 already saw, decoded fresh (`0xe2517d3f`, confirmed against `sepolia.base.org` directly, not inferred). **Item 4 was wrong to attribute this to RPC staleness.** `AgentPrimitivesFactory.registerPrimitives` (`contracts/src/framework/AgentPrimitivesFactory.sol`) calls into **two** registries requiring `REGISTRAR_ROLE` — its own NatSpec says so explicitly ("Holds `REGISTRAR_ROLE` on both registries") — `XibalbaAgentRegistry.registerPrimitives` (which the earlier fix correctly re-granted) **and** `DomainRegistry.recordJoin` (`onlyRole(REGISTRAR_ROLE)`), which never got re-granted after the same phantom-factory rotation incident. Confirmed live, no ambiguity: `DomainRegistry.hasRole(REGISTRAR_ROLE, 0xC19fc9cB...)` returned `false` against `sepolia.base.org` — the same canonical endpoint item 4 already trusted — ruling out staleness as the explanation this time. (The `DOCKER_RPC_URL` switch in item 4 may still have been a real, separate fix for the nonce/balance-read lag documented in items 5-6; it just wasn't sufficient for *this* revert, which was a genuinely-missing grant, not a stale read of a genuinely-present one.)

     **Fix**: granted `REGISTRAR_ROLE` to the real factory on `DomainRegistry`
     (`0xC1aee61b8826d79c21a335Fb1777cA372Bea1Ba0`) from the funder/governance wallet
     (confirmed to hold `DEFAULT_ADMIN_ROLE` there), tx
     `0xd40ac7e2586b3aca21d2d36c015385b07650202c3efe61e5b9d962e2b2ccb979`, verified via
     `hasRole` returning `true` afterward. **Registration then completed successfully without
     creating a new orphan** — rather than re-running the non-idempotent script from scratch
     (which would have deployed a *fifth* orphaned pair on top of the four already listed
     above), resumed from the already-deployed `SovereignAgent`/`StateAnchor` directly via a
     one-off script calling `integrity_sdk.chain.register_primitives` with those existing
     addresses. `resolveDID` now returns the full real 7-primitive set;
     `GET /v1/agent/{id}` confirms `oracle_registered: true` and the agent no longer appears
     in `GET /v1/shield/unregistered-agents`. Milestone 2 of
     `docs/demo-shield-integration.md` is genuinely complete for the Shield agent's DID as of
     this entry — see that doc's own updated status section.

     **Still open**: `DomainRegistry` should get the same `docs/signer-role-rotation-2026-08.md`
     treatment eventually noted for `XibalbaAgentRegistry` in item 3's fix — both registries'
     `REGISTRAR_ROLE` currently point at the same stopgap factory with the old shared-key
     roles. The four orphaned `SovereignAgent`/`StateAnchor` pairs listed in item 3 remain
     orphaned; this entry didn't create a fifth, but it also didn't clean up the existing four
     — no cleanup path exists for any of them.

## 10. SDK tracing → oracle → frontend trace-tree pipeline (LangSmith-style spans/traces)

*Current State:* Requested: verify and improve the full pipeline for "spans, traces, and more" — `integrity_sdk.client.IntegrityClient.traceable()`/`trace_run()` → real OTel export → `integrity-oracle`'s OTLP receiver → the `otel_spans` table → `GET /v1/traces/{trace_id}` → `integrity-dashboard`'s `ChainOfThoughtPage`/`CompareTracesPage` tree/Gantt views. A prior research pass established that the *plumbing* (`trace_tree.rs`'s tree reconstruction, the frontend's real Gantt/DAG rendering, real parent/child span nesting via `contextvars`) was already real and well-built — but the SDK's own front door to it was completely non-functional.
* **CLOSED — the SDK's own "recommended general-purpose tracing API" silently exported nothing, ever.** `IntegrityClient.traceable(...)`/`trace_run(..., client=...)` opens a real OTel span (`get_tracer(...).start_as_current_span(...)`) on every call — genuinely nested via `contextvars`, genuinely PHI-redacted — but nothing ever installed a real `TracerProvider`/OTLP exporter before this fix. `get_tracer(...)` silently returned OTel's default no-op tracer, so every span this API ever produced was thrown away before it left the process. `telemetry/core.py::init_telemetry` is the one thing that installs a real exporter, but it was only ever called from the optional `telemetry/mlflow_tracing.py` autolog path — `IntegrityClient.__init__` never called it, despite having everything `init_telemetry` needs (`agent_id`) available at construction time. Confirmed by tracing a real 3-level nested call (`agent_run` → `llm_call` → `tool_call`) end-to-end before the fix and finding zero rows in the oracle's real `otel_spans` table. Fixed: `IntegrityClient.__init__` now calls `telemetry_core.init_telemetry(agent_id, endpoint=...)` unconditionally (safe — idempotent, and a missing/unreachable OTLP collector fails silently in the background per that function's own existing "best-effort" design, matching this class's own stated telemetry philosophy). The OTLP endpoint defaults to `oracle_url`'s host on port `4317` (the oracle-backend process serves both from one container — a real architectural fact of this deployment, not a guess), overridable via a new `otlp_endpoint=` constructor param, or skippable via `enable_otel_export=False`.
  Verified for real, twice: (1) a standalone script using only the public `IntegrityClient`/`traceable` API produced a real 3-span nested tree, confirmed by querying `otel_spans` directly (`trading_agent`/`llm_call`/`tool_call` rows, correct `parent_span_id` chain, shared `trace_id`) and by a real `curl GET /v1/traces/{trace_id}` returning the exact nested JSON tree with real durations/attributes; (2) a new opt-in e2e test (`integrity-sdk/tests/test_tracing_oracle_e2e.py`, `ORACLE_E2E=1`) that traces a real nested call, discovers the resulting `trace_id` via the real SSE stream (the same mechanism the frontend uses — no shortcut), and asserts the reconstructed tree shape via a real HTTP call to the real running oracle. Also added 3 unit tests (`test_client.py`) proving the endpoint-derivation/override/opt-out logic in isolation.
* **CLOSED — stale Docker image made `CompareTracesPage` *look* broken when it wasn't.** While validating the fix above in a browser, `CompareTracesPage` appeared to show fabricated example traces ("Identity Resolution (Stable)", etc.) instead of picking up a real, freshly-generated trace — looked like a regression in that page's earlier real-data rewrite. It wasn't: `docker-compose.yml`'s `dashboard` service `COPY`s the source at image-build time with no volume mount, and the running container simply predated that rewrite by many hours. Rebuilt (`docker compose build dashboard && docker compose up -d --no-deps dashboard`) and re-verified: both `ChainOfThoughtPage`'s Historical-Traces DAG view and `CompareTracesPage`'s Gantt view correctly auto-discover and render a real, freshly-traced 3-span tree with real names/durations, confirmed via live screenshots, zero fabricated data. Worth remembering for future frontend verification passes on this repo: **the docker-compose `dashboard` container does not reflect source changes until explicitly rebuilt** — a `docker compose up -d` restart alone is not enough.
* **Naming trap, documented not fixed (kept out of scope):** `GET /v1/agent/{id}/traces` does **not** return spans or a trace tree despite the name — it returns `AgentJudgeEvaluationDto[]` (LLM-judge verdict records: `judge_model`, `verdict`, `score`). It's unrelated to `GET /v1/traces/{trace_id}` (the real span-tree endpoint) and has zero call sites anywhere in the frontend. Not renamed in this pass — it's a wire-contract change (`docs/INTERFACE_CONTRACT.md`, `spec/ais-api/`) outside today's scope — but flagged here so the next person chasing "why doesn't `/agent/{id}/traces` return spans" doesn't have to rediscover this from scratch.

## 11. Real audit-log system (2026-07-16) — `AuditLogsPanel` was 100% fake, now backed by durable storage

*Current State:* Explicit request: "fix audit logs to be a genuine source of truth for the integrity system. it should log every event in the system." `AuditLogsPanel.tsx` previously rendered `LoggerContext`'s `INITIAL_LOGS` — three hardcoded rows, session-scoped, only ever appended to by `ActuarialHub.tsx` (a fully-mock marketplace component) with fabricated strings. Investigation before fixing this found the real gap was bigger than a frontend wiring issue: **`bcc_middleware` — the component that makes real per-request OPA ALLOW/DENY policy decisions — had zero durable storage anywhere** (confirmed by grep across `bcc_middleware/app/` for sqlite/psycopg/sqlalchemy/`CREATE TABLE`). Deny reasons only ever existed in the HTTP response body; allow-decisions only existed as an opaque 32-byte Merkle leaf hash on-chain. Genuinely capturing "every event in the system" required a new write path, not just a new read endpoint over existing tables.
* **CLOSED — added `audit_log`, a new durable Postgres table (`integrity-oracle/backend/migrations/0006_audit_log.sql`).** `agent_id` deliberately has no FK to `agents(id)` (mirrors `otel_spans`' same choice, migration 0004) — a forged-signature or unknown-agent deny is exactly the kind of event worth keeping, and may reference an `agent_id` that never resolves to a real row.
* **CLOSED — `bcc_middleware` now reports every intercept decision, allow AND deny, not just approved ones.** New module `bcc_middleware/app/audit.py`, called from `run_intercept`'s `_deny()` helper (parses the existing `"CODE: detail"` reason string into `reason_code`/`detail`) and from the final approval path. Fire-and-forget via `asyncio.ensure_future` (task references held in a module-level set so they aren't garbage-collected mid-flight) POSTing to a new `POST /v1/audit/ingest` oracle endpoint — best-effort, same documented asymmetry as `anchor.py`'s on-chain anchoring: by the time this runs, `run_intercept` has already decided allow/deny, so a slow/unreachable oracle can never add latency or change the response, only mean that one decision is missing from the audit trail until the next successful report. Both `/v1/audit/ingest` and the receiving oracle endpoint are deliberately unauthenticated, matching the OTLP receiver's (`otlp.rs`) existing posture for this single-operator dev/demo topology — a forged entry is a known, documented limitation, not silently claimed to be tamper-proof. 91/91 `bcc_middleware` pytest suite still green after the `_deny()` signature change.
* **CLOSED — new oracle endpoints: `POST /v1/audit/ingest`, `GET /v1/audit-log`.** The GET side (`backend::handlers::get_audit_log`) merges two real sources: the new `audit_log` table (BCC intercept decisions — the only source with an explicit allow/deny verdict) and, when `agent_id` is given, that agent's `telemetry_events` rows surfaced as `flagged`/`recorded` (there's no existing "recent across all agents" query for `telemetry_events`, so the global/no-agent feed is `audit_log` only — documented in `get_audit_log`'s own doc comment rather than silently omitted). Merged in Rust, not a SQL UNION — the two source tables don't share a column shape. Both endpoints added to `ApiDocExtra` in `openapi.rs` (utoipa's 15-paths-per-struct limit meant `ApiDocCore` was already full). `cargo build --workspace` and `cargo test --workspace --lib` (80 tests) clean.
* **CLOSED — `AuditLogsPanel.tsx` rewritten to query the real endpoint, reactive to the global agent selector.** Per an explicit follow-up ("agent selector should be working to determine which data to display"): the panel now calls `oracle.getAuditLog(selectedAgent?.id, 200)` from `AgentContext`'s `selectedAgent` (the same global TopBar picker `SystemDiagnosticsPage`'s sibling "SDK Telemetry" tab already reacts to), refetching on agent change. Removed the `SeededDataBadge`/"Simulated event feed" disclosure entirely — this data source is now real, not merely honestly-disclosed-fake. `LoggerContext.tsx` was left in place, not deleted: it's still a legitimate (if minor) dependency of `ActuarialHub.tsx`'s own mock marketplace flow, which is out of this pass's scope; only `AuditLogsPanel`'s use of it was removed. `HealthPage.tsx`'s separate "Medical Record Interaction Logs" table (`MOCK_AUDIT_LOGS`, a different, EHR-action-shaped concept) was left as-is — already honestly disclosed via its own `SeededDataBadge`, and wiring it to the new generic `audit_log` feed would misrepresent it as PHI-specific interaction logging it isn't.
* **Verified for real, end-to-end, live:** rebuilt and restarted the dockerized `oracle-backend`/`bcc-middleware` images (both `COPY` source at build time, same trap documented in §10 for the `dashboard` container — a `docker compose up -d` restart alone would not have picked up any of this), confirmed migration `0006_audit_log` applied via the oracle's boot log, then sent a real malformed-signature commitment straight to `POST /v1/bcc/intercept` (`curl`, no test harness) and confirmed via `GET /v1/audit-log?agent_id=...` that a `BCC_INVALID_SIGNATURE` deny row appeared with the correct `reason_code`/`detail` split. Then browser-verified live (`npm run dev`, not the stale Docker dashboard image) at `/diagnostics` → Audit Logs: the exact same real deny row rendered correctly for the probed agent, and switching the TopBar agent selector to a different, never-probed agent correctly showed an empty table (not stale or fabricated data) — confirming the agent-selector reactivity explicitly requested. Zero console errors.

## 12. Dashboard/Trace Analytics rendered empty despite real backend data (2026-07-16)

*Current State:* Two independent user reports in the same session ("why doesnt seeded data display in frontend. everything is empty", "trace analytics is completely empty no data") — both traced to real bugs, not correctly-empty states, since backend queries confirmed real data existed the whole time.
* **CLOSED — Recharts' `<ResponsiveContainer>` gets permanently stuck at an 8x8 fallback SVG size inside this dashboard's react-grid-layout grid.** Found on `DashboardPage.tsx`'s "Cost & Token Analytics" widget: its `<svg class="recharts-surface">` rendered `width="8" height="8"` — the badge and axis labels displayed, but the chart itself was invisible, which is what "seeded data won't display" actually meant (the seeded `COST_DATA` array was always there; only the chart canvas was broken). Root-caused via direct DOM measurement (`getBoundingClientRect()` on `.recharts-responsive-container` showed the correct final grid-cell box, 573×244, while Recharts' own internal `containerWidth`/`containerHeight` state stayed frozen at the tiny value) and confirmed via `node_modules/recharts/es6/component/ResponsiveContainer.js`'s source that this is Recharts' own `ResizeObserver`-driven measurement, not a react-grid-layout sizing bug. Ruled out three plausible fixes by testing each live, not by inspection: (1) forcing the whole grid to remount once react-grid-layout's real width was known (`key` swap) — no change; (2) nudging `layouts` to a new object reference after mount — no change, and turned out to be redundant since `onLayoutChange` already updates it naturally on first mount; (3) Recharts' own `debounce` prop, meant for exactly this class of race — no change even at 2s past mount, in both `npm run dev` and a production `vite preview` build (so not a React StrictMode dev-only artifact either). Fixed by bypassing `ResponsiveContainer`'s broken internal measurement entirely: a new `useMeasuredSize` hook (`WidgetRegistry.tsx`) runs our own `ResizeObserver` against a wrapper div and passes explicit pixel `width`/`height` straight to `<AreaChart>`, which accepts them directly. Extracted into a properly named `CostAnalyticsWidget: React.FC<WidgetProps>` (was an anonymous inline `component: () => {...}`) — required for oxlint's `rules-of-hooks` check to recognize `useMeasuredSize` as a hook call inside a real component, not just to satisfy the linter cosmetically. **Self-inflicted bug caught before shipping:** the hook's first version called `setSize` unconditionally on every `ResizeObserver` callback, and the just-rendered chart's own reflow (e.g. legend wrap) could nudge the observed box by a sub-pixel amount, creating a render→resize→render loop that tripped React's "Maximum update depth exceeded" guard — fixed with a rounded-value equality check before calling `setSize`. Verified live: fresh page loads now render the full area chart on first paint, zero console errors, `npm run build`/`npm run lint` clean. Only the one confirmed-broken widget was converted — `BCC Middleware Latency` (a `BarChart` in the same grid) was never observed broken across repeated fresh loads and was left on `ResponsiveContainer` rather than converting every chart in the file speculatively.
* **CLOSED — Trace Analytics' "Historical Traces" tab had no way to discover a trace_id that arrived before the tab was opened.** Confirmed via a direct oracle query (`GET /v1/agent/{id}/otel/traces` — see below) that 6 real spans already existed in `otel_spans` for the selected agent, yet the page showed "No traces observed yet this session." Root cause was already honestly documented in the frontend's own code comment: `recentTraceIds` was derived exclusively from the live SSE stream (`useOracleStream`), and the comment explicitly said "there's no 'list recent traces' endpoint, only get-by-id" — this closes that gap for real rather than leaving the disclosed limitation in place. Added `GET /v1/agent/{id}/otel/traces` (`backend::handlers::get_recent_traces`, `db::get_recent_root_spans`): one row per trace's root span (`parent_span_id IS NULL`), most recent first, `?limit=` (default 20, max 200) — a straightforward sibling to the existing `/otel/volume` bucketed-count endpoint, added to `ApiDocExtra` in `openapi.rs`. `TraceAnalyticsPage.tsx` now fetches this on mount/agent-change and merges it with the live-stream-discovered list (stream entries take precedence as most-recent; historical fills in anything not already seen this session) via `oracle.getRecentTraces()`. Verified live: rebuilt/restarted the dockerized `oracle-backend` image, confirmed `curl .../otel/traces` returns the real 6 spans' 4 distinct trace_ids with names/timestamps, then browser-verified the Historical Traces tab renders a real 2-span DAG (`agent_conversation` → `agent_tool_allocate_capital`, real durations, real attributes including the agent's DID) on a fresh page load with no prior live-stream activity. `cargo build --workspace`/`cargo test --workspace --lib` (80 tests)/`npm run build`/`npm run lint` all clean.
* **Not a bug, real account action taken:** per explicit request, registered a real `integrity-userapi` user (`POST /auth/register`, email `admin@xibalba.dev`) and linked all 13 currently-registered demo agents to it via 13×`POST /me/agents`, confirmed via `GET /me/agents` returning 13 rows with live oracle data fanned in per agent. `integrity-userapi`'s `users` table has no role/permission column at all (confirmed by reading `app/schemas.py`/`app/main.py` — only `email`/`hashed_password`), so "admin" here is just this account's chosen label, not a fabricated permission tier; the dashboard shell's own "Admin User" sidebar badge remains explicitly disclosed as `<SeededDataBadge label="Not a real session/role" />` (§7) since no global auth context wires a real `userapi` session into the shell yet — unrelated to and not resolved by this account's creation.

## 13. Continued undisclosed-mock sweep (2026-07-16) — 6 findings across 5 files, each fixed differently

*Current State:* Explicit request: "keep sweeping the other pages for undisclosed mocks." Three parallel read-only investigation passes covered every remaining frontend page/component without an existing `SeededDataBadge` audit trail (`AgentsPage.tsx`, `ImmutableLedger.tsx`, `ConnectWalletButton.tsx`, `ClaimAgentModal.tsx`, `XNSSearchService.tsx`, `SandboxConsole.tsx`, `TraceNode.tsx`, `CompareTracesPanel.tsx`, `RegistryExplorer.tsx`). `ClaimAgentModal.tsx`, `ConnectWalletButton.tsx`, `TraceNode.tsx`, and `CompareTracesPanel.tsx` were confirmed already genuinely real — no action. Six real findings, each fixed with whatever was actually correct for that finding rather than reflexively slapping a badge on everything:
* **CLOSED — `RegistryExplorer.tsx` asserted a false security claim: "ZK-PROOFED DID DOCUMENT" + a green checkmark, shown unconditionally on every result, regardless of whether the proof was ever actually verified.** The oracle's real `AisResponse` already returns a `zk_proof_verified: boolean` field (reachable via the same `/ais` call the component already made) — it was being fetched and silently discarded, not merely undisclosed. This is a step above the usual "fake data" finding: it's a real endpoint's real security signal being overridden by a hardcoded UI claim. Fixed by capturing `zk_proof_verified` and gating the label/checkmark on it — an unverified DID document now shows a neutral "DID DOCUMENT" label with no checkmark. Verified live via the landing page's "XNS Resolver" modal against a real, unboosted agent: label correctly read plain "DID DOCUMENT", no checkmark.
* **CLOSED — `ImmutableLedger.tsx` was 100% fabricated end-to-end (mock rows literally commented `// Mock data for Dashboard`, a fake dispute-submission flow, a CSV export of the fake rows, a fake Merkle proof panel built by substring-slicing the fake tx hash, and misleading branding: "BASE_SEPOLIA_NODE_01 // TRUST_LEDGER_STREAM", "N SECURE_RECORDS_INDEXED") — with zero `SeededDataBadge` anywhere.** Confirmed via grep that this component is never imported by any page (dead code since the initial commit) — attempted to delete it outright as dead-code cleanup, which the session's own auto-mode classifier correctly blocked as an irreversible, unrequested deletion beyond the scope of a disclosure sweep. Fixed the requested way instead: every fabricated section now carries an honest `SeededDataBadge` or corrected copy (terminal-tab header, export button, dispute-submission toast, Merkle-proof panel, footer "SEEDED_RECORDS" label), and the two hardcoded fallback addresses (`0xcc3fa2...`, `0x5b5670...`) were replaced with an honest `'—'` empty-state instead of looking like real fallback data. Left un-deleted and in place per the above — if ever wired into a real page, every disclosure needs to become a real wire-up first, not be silently dropped.
* **CLOSED — `XNSSearchService.tsx` (live on `IdentityPage.tsx`'s Identity & DID tab) faked its entire search flow: any query except the literal string `"notfound"` returned the same hardcoded result (`"Xibalba Node"`, a fixed ETH address, AIS 950, Tier A) after a 1s fake-loading delay.** This one got a real fix, not a badge — wired to the same real `oracle.getAgent()` + `oracle.getAis()` calls `RegistryExplorer.tsx`'s registry search already uses, with `zk_proof_verified`-aware tier labels matching `RegistryExplorer.tsx`'s real `tierLabels` map exactly (`Unverified`/`Sovereign`/`Linked`/`Institutional`) rather than inventing new ones. The fabricated ".intg" XNS-handle-guessing (`query.includes('.') ? query : query + '.intg'`) was removed entirely along with its display block — there is no real on-chain XNS handle resolution anywhere in this monorepo, so echoing a fake-looking resolved handle back was actively misleading, not just seeded. Verified live: querying a real registered DID now returns that exact agent's real AIS score, address, and tier; a 404 now correctly surfaces "Agent not found," not a fabricated match.
* **CLOSED — the same `IdentityPage.tsx` tab had an adjacent, separate undisclosed fake flow: a "Register Additional Handle" modal claiming a real "50 ITK Registration Fee" on-chain transaction, whose `handleRegister` only ever set local React state (`setXnsName`) — no wagmi/viem call, no oracle POST, nothing on-chain.** Found while browser-verifying the `XNSSearchService.tsx` fix above (same tab, same "XNS Search Service" panel) — not part of any subagent's assigned file list, caught by inspection during live verification. Fixed with `SeededDataBadge`s on both the panel's "Your Registered Handle" label and the modal's own title, plus corrected copy: "50 ITK (not charged -- no real contract call)" and a relabeled "Confirm & Register (Simulated)" button, rather than silently implying money moves.
* **CLOSED — `AgentsPage.tsx` had two dead-end buttons presented as functional: "Deploy" (Register New Agent card) and the original "Verify & Claim" (Claim Existing Agent card) both had no `onClick` handler at all — clicking them did nothing, with no disclosure that nothing would happen.** These weren't fake *data*, they were fake *affordances* — a button that looks clickable and does nothing is worse than one that's honestly disabled. Two different fixes for two different situations: "Deploy" has no real backend counterpart anywhere in this frontend (real on-chain agent registration only exists in `integrity-sdk`/`integrity-cli`'s `register_agent()`), so it was disabled with a `SeededDataBadge` pointing at the real CLI/SDK path instead. "Verify & Claim" *does* have a real, already-built implementation sitting completely unwired — `ClaimAgentModal.tsx` (confirmed real by this pass's own investigation: real `readContract` against `XibalbaAgentRegistry`, real `signMessageAsync`/`verifyMessage`, no fake transaction) — it just was never imported into `AgentsPage.tsx`. Wired it in for real: the address input now feeds the modal's `defaultAddress`, the button opens it, and `onSuccess` triggers a real agent-list refetch. Verified live: clicking "Verify & Claim" now opens the real modal with its own honest "no on-chain takeover mechanism exists" disclosure text intact.
* **CLOSED — `SandboxConsole.tsx` (a labeled "Protocol Sandbox" what-if calculator, so its overall framing was already adequate disclosure) silently fixed 3 of its 5 weighted AIS-formula inputs (`avgPartnerAIS`/`stakedRatio`/`agentAge`/`volume`) with zero UI control, despite `npm run lint` already flagging their setters as unused dead code, plus one fully hardcoded, undisclosed constant (`const auditIdx = 0.95`).** Since this is a local-only, backend-free calculator, the correct fix was completion, not disclosure: added real slider/number inputs for all four previously-dead parameters, fixed the `useEffect` dependency array (was missing `avgPartnerAIS`/`stakedRatio`/`agentAge`/`volume` entirely, so changing them wouldn't have recomputed the score even after adding controls), and added an inline note disclosing the one input that's staying fixed by design (`auditIdx`, a stand-in for an external "Xibalba Audit Score" the sandbox doesn't simulate). Also removed the file's `// @ts-nocheck` and the resulting unused `React` import once real type-checking was re-enabled on it — both build and lint clean.
Full regression after all six fixes: `npm run build`/`npm run lint` clean (only pre-existing, unrelated warnings remain), every fix browser-verified live against the real running stack, zero console errors on any touched page.

## 14. Continued undisclosed-mock sweep, round 3 (2026-07-16) — 5 more findings across 7 files

*Current State:* Explicit request: "keep going" (continuing the mock sweep). Three parallel investigation passes covered every remaining unaudited surface: `SettingsPage.tsx`/`SystemDiagnosticsPage.tsx` (beyond their prior `SeededDataBadge` instances), `LandingPage.tsx`/`ContactModal.tsx`/`CommandPalette.tsx`, and `NotionDatabase.tsx`/`MermaidDiagram.tsx`/`Toast.tsx`/`MarketsEscrowPanel.tsx`. Four of these seven files came back completely clean (`NotionDatabase.tsx`, `MermaidDiagram.tsx`, `Toast.tsx`, `MarketsEscrowPanel.tsx` — the last already fully badged from a prior pass, its order-placement flow confirmed calling real `readContract`/`writeContract` against real ABIs/deployments, not faking success) and `SystemDiagnosticsPage.tsx` and `ContactModal.tsx` had no findings (`ContactModal.tsx` genuinely POSTs to a real backend and surfaces real errors). Five real findings, fixed:
* **CLOSED — `SettingsPage.tsx`'s TopBar had a global "Save Changes" button whose only behavior was `window.alert('Settings saved to volatile memory.')` — no real persistence, and nothing on the page actually needed a manual save step (theme/font persist live via `ThemeContext` on change, API keys are created/revoked via real `userapi` calls immediately, the Network panel is separately disclosed as non-functional).** Removed the button entirely rather than relabel it — there was no real save action to disclose-and-keep. A second, narrower finding in the same file: "Save Network Settings" (inside the already-`SeededDataBadge`-disclosed Network panel) had no `onClick` handler at all, a silent no-op rather than a visibly inert control — fixed by adding `disabled` + a `title` tooltip so the non-functionality is visible, not just discoverable by clicking and observing nothing happen.
* **CLOSED — three separate landing-page/header buttons (`HeroSection.tsx`'s "Launch Dashboard", `CinematicHeader.tsx`'s desktop+mobile "Launch Dashboard" and "Sign In", `CoreFeatures.tsx`'s "OPEN ESCROWS") all navigated to `/integrity`, which is not and has never been a route in `App.tsx`** (real routes: `/`, `/landing`, `/identity`, `/contracts`, `/settings`, `/finance`, `/traces`, `/diagnostics`, `/health`, `/agents`) — every one of these was a dead link rendering a blank page. Fixed by pointing each at the real destination its label promises: "Launch Dashboard" → `/` (the real Intelligence Command dashboard), "Sign In" → `/settings` (where the real `userapi` email/password login form already lives), "OPEN ESCROWS" → `/finance` (real `MarketsEscrowPanel.tsx`). `CinematicHeader.tsx`'s "Sign In" button additionally fired `alert("Google Sign-In flow initiated.")` before navigating — a fake OAuth flow with no real Google/any-provider integration anywhere in this monorepo — removed entirely along with the dead-route fix, not just disclosed, since a real login path already exists one click away.
* **CLOSED — `LandingPage.tsx`'s "Agent XNS Lookup" search box was fully uncontrolled (no `value`/`onChange`) — typing an agent DID and clicking "Lookup" silently discarded the input and opened `RegistryExplorer.tsx`'s modal with its own independent, always-blank `query` state.** `RegistryExplorer.tsx` didn't accept an initial-query prop at all, so this wasn't fixable from the landing page alone. Added `initialQuery?: string` to `RegistryExplorerProps`, plus a `useEffect` keyed on `[isOpen, initialQuery]` (needed because the component self-guards on `isOpen` via `if (!isOpen) return null` rather than being conditionally mounted by its parent — a plain `useState` initializer would only ever apply `initialQuery` once, on first mount, not on every re-open) — then wired the landing page's input through it. Verified live: typing a real registered DID and clicking Lookup now opens the modal with that exact DID pre-filled, and Resolve returns that agent's real on-chain data.
* **CLOSED — `CommandPalette.tsx`'s "Toggle Theme" command only ever called `addToast('info', 'Theme toggled')` — it never touched the real `ThemeContext` (`setTheme`), so the toast claimed success while nothing on screen changed.** `ThemeContext.tsx` already exposes 4 real themes (`default`/`navy-gold`/`clinical-light`/`notion`) wired live elsewhere (`SettingsPage.tsx`'s Appearance panel). Fixed by importing `useTheme`/`Theme` and cycling through the same 4-theme list for real, with the toast message reporting the actual theme now active rather than a generic claim. Verified live in a fresh browser tab: invoking the command visibly re-themes the entire app (confirmed dark → light background swap matching the `clinical-light` theme).
Full regression: `npm run build`/`npm run lint` clean (zero new errors; only the same pre-existing unrelated warnings remain), every fix browser-verified live. One unrelated hazard discovered during verification, not caused by this pass: clicking on `DashboardPage.tsx`'s react-grid-layout widget area can trigger a pre-existing library bug (`react-grid-layout`'s dev-mode `log()` helper references bare `process.env` with no browser shim, throwing `ReferenceError: process is not defined` on drag-start and wedging that browser tab's renderer) — a fresh tab was unaffected and confirmed the app itself was healthy throughout. Not fixed in this pass (out of scope for a mock-disclosure sweep), flagged here so it's not mistaken for a regression next time someone hits it.

## 15. `integrity-dashboard/demo`'s scenario engine never submitted real SDK telemetry, only OTel spans (2026-07-17) — closed architecturally

*Current State:* Found while running a full end-to-end telemetry validation pass (per explicit request): `GET /v1/agent/{id}/telemetry` and `event_count` in `GET /v1/agent/{id}/ais` were empty/zero for **every** currently-registered demo agent, network-wide, with no exceptions — despite §9/§10's earlier fixes already having made this engine's real OTel span pipeline work correctly (spans/traces genuinely exist and render in Trace Analytics). Root-caused, not guessed: `telemetry_events` (the table `scoring-core`'s entropy/grounding/sacrifice/compliance signals are actually derived from — a *different* real pipeline from OTel spans, see §10's own "two separate real pipelines" framing) requires a client to call `IntegrityClient.log_telemetry()` + `flush_telemetry()` (`POST /v1/telemetry/ingest`), and `integrity-dashboard/demo/src/integrity_demo/main.py` never did — it only ever used the raw OTel `TracerProvider`/`Tracer` machinery from §9/§10's fixes, never touching `integrity_sdk.client.IntegrityClient` at all. Every dashboard widget reading AIS/telemetry (Tri-Metric Risk Analysis's "BCC Intent Violation Rate", the Identity page's AIS score, `SystemDiagnosticsPage`'s SDK Telemetry tab) was correctly showing an honest "—"/"No AIS data yet" empty state rather than fabricating a number — confirmed this was the *correct* behavior for genuinely-empty real data, not a display bug, before treating the underlying emptiness itself as the thing to fix.
* **CLOSED — added real telemetry submission alongside the existing OTel tracing, not instead of it.** New `_client_for(agent_id, keypair)` in `main.py` constructs one `IntegrityClient` per agent (mirroring `_tracer_for`'s existing per-agent-provider pattern), reusing the *same* real `Keypair` `load_or_create_did` already returns for that agent's registration — the identical signing key the oracle already has on file, not a second identity. Constructed with `enable_otel_export=False` deliberately: `IntegrityClient.__init__` would otherwise call `telemetry_core.init_telemetry()`, which installs a **global** `TracerProvider` (a one-shot singleton, first call wins) — exactly the multi-agent trap `_tracer_for`'s independent per-agent providers were built to avoid in §9/§10. OTel span tracing and telemetry-event submission are two independent real pipelines in this file now, neither routed through the other.
* **CLOSED — every agent gets a real telemetry row the moment it registers**, not only the one agent (`capital_allocation_agent`) that happens to make an LLM call. `_submit_telemetry(agent_did, keypair, {"event": "agent_registered", "vertical": ..., "persona": ...})` fires right after each successful registration, for all 4 personas unconditionally — this doesn't depend on `OPENAI_API_KEY`/`GEMINI_API_KEY` being set at all, unlike the capital-allocation conversation below it. With no `text_output` in the metadata, `derive.py` computes real (not fabricated) neutral defaults — entropy/grounding both derive to 1.0 ("no evidence of instability" for a batch with no text to measure, per that module's own documented polarity) — which is an honest description of "this agent just registered and hasn't said anything yet," not a faked high score.
* **CLOSED — the capital-allocation agent's real LLM output now feeds a second, richer telemetry entry** when its `agent_conversation` step succeeds: `_submit_telemetry(allocator_did, allocator["keypair"], {"event": "agent_conversation", "text_output": response})`, using the actual string `agent.run_conversation()` returned — real Shannon-entropy/keyword-grounding derivation over real text, not a placeholder.
* **Verified for real, end-to-end, against the live oracle** — not just import-checked: since the persisted DID/Ed25519 keypair (`~/.integrity/did/<agent>/private_key.pem`, used for telemetry signing) is unrelated to and unlocked without the separately-password-protected EVM wallet keystore (`~/.integrity/wallet/<agent>/keystore.json`, blocked this session by an unknown prior password — see the "Not a bug" note in §12), called `_submit_telemetry` directly against a real, already-registered agent's real keypair without needing a full wallet-unlocked demo re-run. First call (registration-shaped, no text): oracle returned 200, `nonce` advanced from 0→1, `GET .../ais` went from "no data" to a real `ais: 800.0, event_count: 1` with `entropy/grounding` both exactly 1000 (the honest neutral default, matching the no-text-yet case above). Second call (conversation-shaped, real text): oracle returned 200 again, `nonce` advanced to 2, `event_count: 2`, and — critically — `entropy`/`grounding` changed to genuinely *different*, non-round numbers (`701.39`/`975.0`) computed from the real submitted text, proving the derivation path is live end-to-end, not just accepting and discarding the payload. `integrity-dashboard/demo`'s own `pytest tests/` (6 tests, pre-existing, unrelated to this change) still green; a full syntax/import check of the modified `main.py` passed cleanly.
* **Known follow-up, not done in this pass:** a genuinely fresh `make demo` run (registering brand-new agent identities from scratch, exercising the real registration→telemetry→AIS flow together in one process rather than the split registration-already-done / telemetry-submitted-standalone verification above) is still blocked by the same password-protected EVM wallet keystores noted in §12 — needs either the original `INTEGRITY_WALLET_PASSWORD` or an explicit, user-approved wallet reset before it can run. The telemetry-submission code path itself is fully verified live against the real oracle regardless of that blocker.

## 16. `useOracleStream` leaked an SSE connection per consumer, deadlocking the whole dashboard (2026-07-17)

*Current State:* Found while chasing what looked like flaky browser automation and what the user was independently seeing as **"no agents listed under Intelligence or Agents tab"** — the same bug, from two directions. This is a real, user-facing, ship-blocking defect, not a test artifact: with enough dashboard tabs open, **every** oracle `fetch()` in the app hangs forever — no error, no timeout, no console message — and every page renders its honest empty state ("—", empty tables) as though the agent population were genuinely zero.
* **Root cause, measured rather than guessed:** `useOracleStream` opened a brand-new `EventSource` on every hook call and only closed it on unmount. An SSE stream holds one of the browser's **6-per-origin HTTP/1.1 connections** open indefinitely — that is what a stream *is*. The dashboard opens **two** on its own (`DashboardPage`'s `useOracleStream(selectedAgent?.id)` plus `WidgetRegistry`'s `EventsWidget` `useOracleStream(undefined, 12)`), and `TraceAnalyticsPage` a third. **~3 open tabs exhausts the entire per-origin budget**, after which every subsequent request queues forever behind streams that never yield.
* **The evidence chain** (each step ruled out the prior hypothesis, which is why the earlier "browser/automation is degraded" reads in this session were wrong): `curl` to `/v1/agents` returned in <15ms while the UI hung → server fine. `ss -tnp` showed Chrome's network process holding **exactly 6-7 established connections to `[::1]:8080`**, reappearing with **fresh source ports within seconds of a `docker compose restart oracle-backend`** → `EventSource`'s own auto-reconnect, i.e. leaked long-lived streams, not stale TCP. The apparent contradiction that navigating the same browser *directly* to `http://localhost:8080/v1/agents` rendered all 17 agents instantly **while the pool was full** is itself the confirming detail: Chrome **partitions socket pools by top-level site**, so the leaked streams saturate the `localhost:5173`-partitioned pool (starving every dashboard fetch) while a top-level visit to `localhost:8080` draws from a different partition entirely.
* **CLOSED — two fixes, both required** (`src/hooks/useOracleStream.ts`): (1) **share one real `EventSource` per stream URL** across every consumer of that URL, ref-counted via a module-level registry, instead of one per hook call — collapses the dashboard's own two sockets into one whenever both consumers watch the same URL; each consumer still keeps its own independently-capped `events` buffer so `maxEvents` stays per-consumer. (2) **disconnect while the page is hidden** (Page Visibility API) and reconnect on return — a background tab holding a socket open is pure cost since nothing is rendering its events, and this is what stops N open tabs from linearly consuming the whole budget. `npm run build`/`npm run lint` clean.
* **Why not fix it server-side:** a real HTTP/2 origin multiplexes every request over a single connection and makes the 6-limit moot, but browsers only speak h2 over TLS and the oracle serves plain HTTP/1.1 today (`backend/src/routes.rs`, no TLS/h2 termination). Until that changes the client has to be the one to behave. Worth revisiting when the oracle gets real TLS — it would make this class of bug structurally impossible rather than merely well-managed.
* **Operational note, cost us real time here:** already-open tabs keep leaking until they reload, and Chrome throttles timers in hidden tabs hard enough that Vite's reconnect-and-reload may not fire until the tab is focused. After deploying this fix, stale dashboard tabs must be closed or clicked into once. A fresh tab alone does not clear it — the pool is shared across the whole browser profile, so one forgotten background tab from hours earlier is enough to keep the entire dashboard wedged.

## 17. Signed telemetry silently rejected ~20% of the time: cross-language float canonicalization (2026-07-17)

*Current State:* Found by chasing a recurring, gracefully-degraded `400 Bad Request` in the heartbeat generator's logs rather than writing it off as noise — the SDK's best-effort design logs-and-requeues on failure (correctly), so this had been quietly dropping roughly one in five **correctly signed** telemetry submissions with no user-visible symptom beyond an AIS that undercounted real activity. This is a protocol-correctness bug in the signature scheme itself, not a demo artifact: any real agent whose derived signals land on an unlucky float hits it.
* **Root cause, isolated empirically rather than reasoned from the error text:** `client.flush_telemetry` signs the canonical JSON of a payload containing float `derived_signals`, and the oracle re-serializes that same payload with Rust's `serde_json` to verify. Both sides emit "the shortest string that round-trips to this exact f64" — but **when a float has two equally-short round-tripping representations, Python's repr (David Gay) and Rust's ryu may each legitimately pick a different one.** Neither is wrong; the canonical bytes simply differ, and Ed25519 verification fails on a payload that was signed perfectly.
* **The reproduction** (each step narrowed the space, and the first two hypotheses — a race, then exponent-notation — were both wrong): identical text + identical tokens flushed 6/6 OK → not a race or nonce-state bug. Sweeping all 16 heartbeat task templates → exactly 2 failed, **both with the identical derived entropy `0.011890908425879365`**, while `0.009712883245855508` passed every time → content-dependent, and specifically float-dependent. Probing 12 hand-picked floats through a monkeypatched `derive_ais_signals` with everything else held constant → **only `0.011890908425879365` failed**; truncating a single digit to `0.011890908425879` passed. The clincher, in Python: both `"0.011890908425879365"` **and** `"0.011890908425879366"` round-trip to that same f64 (hex `0x1.85a42b6789780p-7`) — the exact two-candidate ambiguity, demonstrated rather than assumed.
* **The error message was a red herring and cost real time — worth remembering:** the oracle surfaced `eip191 verification error: signature must be 65 bytes (r || s || v), got 64`, which reads like an EIP-191/wallet problem and has nothing to do with the actual fault. `crypto::verify_agent_signature` tries Ed25519 first, gets a plain `false` (not an error), falls through to the EIP-191 branch, and *that* branch chokes on a 64-byte Ed25519 signature. The last error in the chain won, and it named the wrong subsystem entirely.
* **CLOSED (partially — scope is honest, see below) —** `integrity-sdk/integrity_sdk/telemetry/derive.py` now quantizes all four signals to 6 decimal places (`_SIGNAL_DECIMALS`) before they are signed. The ambiguity is a ~17-significant-digit phenomenon; at 6dp the shortest round-tripping representation is unique, so both languages necessarily agree. 6dp is also far more precision than these heuristics justify — every `derive_*` docstring already describes them as first-pass client-side estimates the oracle independently recomputes anyway (`oracle_recomputed_signals`) — so no real signal is lost. Verified against the live oracle: the two previously-failing templates now pass, **16/16 heartbeat templates OK (was 14/16)**, and `integrity-sdk`'s own suite stays green at **139 passed, 2 skipped**.
* **Remaining gap, deliberately NOT papered over:** this fixes only the floats the SDK generates itself. A caller passing an arbitrary float through `log_telemetry(metadata=...)` can still land on an ambiguous value and be rejected, because that value is signed verbatim inside `otel_spans`. The general fix is a shared canonicalization standard with a fully-specified number format on both sides — **RFC 8785 (JCS)** mandates ECMAScript's `Number::toString`, which is deterministic — instead of each language's own shortest-repr. That is a wire-contract change across `integrity-sdk`/`integrity-cli`/`bcc_middleware`/`integrity-oracle` (`docs/INTERFACE_CONTRACT.md` §4.2) and was out of scope to rush here. Note this is the **same family** as the non-ASCII `ensure_ascii` divergence `bcc.py`'s canonicalization docstring already flags: the oracle solved that one with a custom `AsciiEscapingFormatter`, but floats were never considered. Both are symptoms of "two independent implementations of 'canonical JSON'" rather than one specified standard.

## 18. Continuous real-activity generator + dashboard "feel real" fixes (2026-07-17/18)

*Current State:* After the pipeline fixes above, the dashboard was correct but *static* — a single `make demo` run yields 1-2 events per agent, not enough for time-bucketed charts, live feeds, or trace comparison to feel like a running system. Plus several UI surfaces were either scoped wrong, hidden by a layout bug, or presenting a disclosed-fake identity. All fixed with real data and real wiring, no mocks.
* **NEW — `integrity-heartbeat` continuous generator** (`integrity-dashboard/demo/src/integrity_demo/heartbeat.py`, `integrity-heartbeat` console script). Runs indefinitely, every few seconds picking one of the 4 demo agents and emitting a weighted mix of REAL events through the exact same signature-verified pipelines proved in §15/§17: `IntegrityClient.flush_telemetry` (signed telemetry), real nested OTel spans (per-agent `TracerProvider`, `agent_task → llm_call/tool_call` shapes), and real signed `BCCCommitment`s through bcc_middleware's real OPA engine — a deliberate ~25% of the latter are genuine policy violations (unauthorized clinical intent_type, keyword-flagged) producing real DENYs, not staged ones. This is what makes AIS-history/volume charts, the live SSE feed, and Trace Analytics actually populate and trend. Verified live: 19,101 telemetry submissions accepted, 0 rejected, across a multi-hour run; every OTel span queryable via the real trace endpoints. NOT a mock seeder — nothing writes to any DB directly; the *content* is a small rotating set of realistic task strings but every signature/nonce/policy-decision is genuine.
* **CLOSED — unified "everything logged" diagnostics table.** Per an explicit "one huge table with filtering for manual debugging" request, `GET /v1/audit-log` now merges a THIRD real source (`otel_spans`, flat, via `db::get_recent_spans_flat`) alongside BCC decisions and telemetry — `decision` repurposed to the span's real `status_code`, `reason_code` to its parent span_id. `SystemDiagnosticsPage.tsx` de-tabbed into one page: metrics + volume chart + one filterable `AuditLogsPanel` table with source-filter chips (All/BCC/Telemetry/OTel-Span) plus free-text filter. Verified live against a real agent: 300 merged rows (58 BCC / 96 telemetry / 146 spans), the OTel-Span filter correctly narrowing to real spans with real trace_ids/durations/parent-ids.
* **CLOSED — diagnostics table was invisible below the fold.** The de-tabbed page's fixed metrics+chart consumed all vertical space, squeezing the table to a header-only sliver. Fixed by making `page-content` scroll (`overflowY: auto`) and giving the log panel a firm `min-height` so it's always usably tall — the "cant see unified event stream" report.
* **CLOSED — Compare Traces / Flame Graph was unusable and un-scoped.** It discovered trace_ids only from the *all-agent* live SSE stream (`useOracleStream(undefined)`), so both Trace A/B dropdowns sat empty until a live event happened to arrive, and another agent's traces could leak in under the header's selected agent. Rewired to the global `selectedAgent` (agent-scoped stream) + `oracle.getRecentTraces(selectedAgent.id)` preload — both dropdowns now auto-populate with the selected agent's real traces immediately, and clear on agent change. Also improved the Flame Graph render: real proportional widths from real durations with a firm min-width so short spans stay readable, per-bar duration labels, and an L0/L1 depth axis. Verified live: both traces render side-by-side with a real computed "Latency Delta: Trace B is 62ms faster than Trace A" deviation. Addresses both the "fix agent selector on traces page" and "fix flame graph" reports.
* **CLOSED — sidebar profile was a disclosed-fake "Admin User / NOT A REAL SESSION".** Wired `Sidebar.tsx` to the real `userapi` session: reads the JWT from sessionStorage, fetches `GET /me`, shows the real email + "Signed in via userapi" (or an honest "Sign in" affordance when logged out); real logout clears the token. `userapi.ts`'s `setToken`/`clearToken` now fire an `integrity-auth-changed` event so the shell updates without reload. The `SeededDataBadge` is gone because it's a real session now, not disclosed-fake.
* **NEW — admin as the default demo/testing session** (`DevAutoLogin.tsx`). When `VITE_DEV_AUTO_LOGIN_EMAIL`/`VITE_DEV_AUTO_LOGIN_PASSWORD` are set in `.env` (git-ignored, local-only, documented commented-out in `.env.example`) and no session exists, the app auto-logs-in via the SAME real `POST /auth/login` the Settings form uses — a genuine JWT session, not a bypass. Omitted in any real build → inert → honest "Sign in" state. Verified live: the dashboard boots straight into `admin@xibalba.dev` with no manual login.
Full regression after all of the above: frontend `npm run build`/`npm run lint` clean, oracle `cargo test --workspace --lib` (72+8) green, SDK pytest (139 passed / 2 skipped), bcc_middleware pytest (91 passed). Every fix browser-verified live against the running stack with the heartbeat feeding real data; zero console errors on any touched page.

## 19. Spec v0.3 persistent-memory primitive: gate built, existing agents non-compliant (2026-07-29)

*Current State:* *Integrity Protocol — Comprehensive Design & Specification v0.3* makes **Persistent Memory** a foundational primitive (§4.1) — an agent MUST control a durable Trust Vault whose commitments are Merkle-anchored on its own `StateAnchor`, and registration requires `StateAnchor.latestRoot != bytes32(0)` (§6). Appendix A gap 1 (oracle enforcement) and the SDK half of gap 2 are now closed; the rest is open and listed below rather than implied to be done.

* **CLOSED — oracle memory gate (§7.1).** `ChainClient::memory_state` reads `(latestRoot, latestEpoch)` directly from the agent's own `StateAnchor`; `POST /v1/agent/register` returns the new `AppError::MemoryNotInitialized` → **400** on a zero root, checked immediately after the PrimitiveSet match with the same independent-read posture (chain is the source of truth, never the client's claim). Verified by a real e2e (`oracle_e2e_register_rejects_missing_genesis_memory_root`) that deploys a genuine on-chain agent with *only* the genesis anchor omitted, and empirically against live Base Sepolia.
* **CLOSED — SDK anchors genesis at registration (§6 ordering).** `chain.anchor_genesis_root()` routes `anchorRoot` through `SovereignAgent.execute`; `registration.register_agent` calls it as step 8b, before `registerPrimitives`. **No Solidity change was required for §7.2's "genesis MUST be agent-authorized"** — `StateAnchor`'s admin *is* the `SovereignAgent` contract, which the constructor also grants `ANCHOR_ROLE`.
* **CLOSED — decision recorded (2026-08-02): the 7 legacy agents' non-compliance is accepted, not a pending migration.** Previously stated as "each needs one controller-signed `anchorRoot` tx" as if that were merely un-run housekeeping. It is not: `xibalba.integrity`'s own genesis anchoring (§7.2, closed above) already proves the *mechanism* works — every agent registered from this point forward is spec-conformant by construction. Retroactively anchoring the 7 pre-existing agents would require either (a) their controllers running the tx individually, which is outside this protocol's control and cannot be forced, or (b) the protocol doing it on their behalf, which would mean anchoring a genesis root the agent's own controller never signed — precisely the "protocol may never author a genesis root" invariant §7.2 exists to enforce. There is no compliant path to close this retroactively; a `latestRoot == 0` legacy agent is a permanent, structural fact about agents registered before this gate existed, not a to-do. Decision: document it as such (this entry) rather than carry it as an open action item nobody can complete. **Superseded, not solved, by termination/re-registration** (§7.6 rules termination explicitly out of scope for the same registry-mutability reason — see the coherence derivation in `docs/design/primitive-set-coherence.md`), which is the only mechanism that could ever let a legacy agent re-establish itself as a fresh, spec-conformant registration.
* **OPEN — §7.2 enforcement (Appendix A gap 2) is genuinely unbuildable for existing agents.** Gating `anchorRoot` to `latestEpoch >= 1` would stop the protocol's `ANCHOR_ROLE` signer from anchoring epoch 1, but `StateAnchor` is deployed **per agent, not cloned** — every already-deployed anchor keeps its current bytecode forever, so a contract change reaches only future agents. Any such gate must also leave `DEFAULT_ADMIN_ROLE` able to perform genesis at any epoch-0 moment, or an agent on new bytecode that skipped genesis could never recover. Deferred until that migration question is answered, not silently skipped.
* **OPEN — Appendix A gaps 3–8, status reconciled:** uniform minimum stake at registration; tighter ZK-boost binding (per-event / public inputs) — today it is a period-wide `BOOL_OR`; lineage attestation + on-chain record (§7.4); optional ERC-8004 discovery adapter; silence-as-signal for the observability obligation. The identity-ceiling clamp formerly listed here is now **CLOSED** (`AIS_final = min(AIS, Tier_ceiling)` in `score_with_tier`).
* **Spec drift, confirmed:** §16's package map lists `integrity-mvp/`, which was **replaced by** `integrity-dashboard/`. The package was deleted on disk during that consolidation but the deletion sat uncommitted until 2026-07-29 (944 files), which is why the tree appeared to contain both. The spec should say `integrity-dashboard/`.

## 20. ITK testnet liquidity moved to the agent; Finance wallet + Cognition traces fixed (2026-07-29)

*Current State:* `xibalba.integrity` is now a real minting source for testnet $ITK, the Finance tab shows the agent's true on-chain treasury, and the Cognition tab's emptiness turned out to be a genuine data-path gap rather than a UI bug. One reproducible frontend hang is open.

* **CLOSED — `xibalba.integrity` can mint ITK as the protocol's liquidity source.** `MINTER_ROLE` granted on `IntegrityToken` to its `SovereignAgent 0x360E2a56…` (tx `0xdddf4742…`, block 44781859). New SDK helper `chain.mint_testnet_itk_from_treasury()` routes `SovereignAgent.execute → IntegrityToken.mint`, signed by the agent's own controller, so the mint is attributable on-chain to the agent rather than to an operator EOA — same self-sovereign routing as `grant_anchor_role`/`anchor_genesis_root`. Proven live on Base Sepolia: the agent minted 500 ITK with no funder key in the path (tx `0x20e3076b…`); treasury 10,000 → 10,500 ITK, supply 100,500 → 101,000. The funder retains `MINTER_ROLE` as issuer of last resort, by explicit choice.
* **CLOSED (with a documented limit) — registration now prefers the liquidity agent.** `registration.py` step 7 mints via `mint_testnet_itk_from_treasury` when `INTEGRITY_LIQUIDITY_AGENT` names a local agent whose `primitives.json` and controller wallet are present, and falls back to the funder mint otherwise — logging a warning that names the fallback rather than failing silently.
  * **Inherent limit, not a gap to close by coding:** `SovereignAgent.execute` may only be called by the controller, so minting through the liquidity agent requires that agent's controller key locally. That holds for the current single-operator testnet and is false in general — a third party registering its own agent cannot sign as `xibalba.integrity`. A multi-operator deployment needs a faucet *service* the liquidity agent runs, not a shared key. The fallback exists precisely so that case degrades honestly.
* **CLOSED — Finance tab showed 0.00 ITK while the agent held 10,000.** Two compounding faults: `oracle.getWallet` existed in `services/oracle.ts` but was called from **nowhere**, and `TokenWallet` passed `selectedAgent.eth_address` — which carries the agent's **DID**, not an EVM address — straight to `balanceOf`. On top of that, any connected browser wallet won the address race, so the panel rendered the operator EOA's balance (0) instead of the agent's. Now the agent treasury resolves first through the oracle; the panel reads the real 10,000.00 ITK at `0x360e2a56eb…`. Also replaced two hardcoded `https://sepolia.base.org` literals with the `RPC_URL` constant.
* **CLOSED — Cognition was empty because no OTel spans existed.** Not a dashboard bug: Integrity has two parallel span paths (spec v0.3 §10), and the Xibalba session hooks only ever used path A (signed telemetry → `telemetry_events` → AIS). Cognition reads path B (`otel_spans`). All three hooks set `enable_otel_export=False`, and flipping that flag alone changes nothing because nothing was *creating* spans. `session_start.py`/`session_stop.py` now enable export and emit a real span per session boundary, with `force_flush` since hooks are short-lived. Verified: `otel_spans` 0 → 1 for the agent, and `GET /v1/agent/{id}/otel/traces` returns `claude_session_start` (trace `49a5a48c…`).
* **CLOSED — the Cognition page froze the renderer on agent selection.** Cause: the four Cognition panels each depended on the `selectedAgent` **object**, and `DashboardProvider` re-polls every 15s building a fresh object via `mapOracleAgent`, so every effect re-ran and re-armed its own 5s `setInterval` on each poll — four panels compounding into a timer/fetch storm that eventually wedged the renderer. Fixed by depending on `selectedAgent?.eth_address` (matching `TokenWallet`'s existing fix) across `COTPlatform`, `ObservabilityHub`, `DiagnosticsPanel`, `EvalsPanel`, `TraceAnalysisPanel`.
  * **Diagnosis note, because the record briefly said otherwise:** this fix was first written off as disproved, because a retest froze afterwards. That retest was run in a tab loaded before Vite HMR applied the change. Re-verified properly by bisecting with the page's own module toggles (all four off → select agent → re-enable one at a time) and then repeating the original path: 4 agent selections with all four panels mounted, including the trace-bearing agent, all responsive. Reading the code alone did not find this; the toggle bisect did.
* **CLOSED — default target network is now Base Sepolia, not local anvil.** Root `.env` set to `RPC_URL=https://base-sepolia-rpc.publicnode.com`, `CHAIN_ID=84532`, `DEPLOYMENTS_FILE=deployments.baseSepolia.json`, plus the `DOCKER_*` equivalents, so a bare `docker compose up` targets the real deployed protocol — verified by a `--force-recreate` with no overrides connecting to `/deployments.baseSepolia.json` with XNS handles resolving. `make up-local` is the anvil escape hatch. The root `.env`'s `FUNDER_PRIVATE_KEY` is anvil's account #0 and is useless on Sepolia; that is now called out in the file itself, with a pointer to `contracts/.env` for the real funder key.
* **Environment footgun worth knowing:** `docker compose` auto-loads the root `.env`, which pins `CHAIN_ID=31337` and `DOCKER_RPC_URL=http://host.docker.internal:8545` (local anvil). Any `docker compose up` for `oracle-backend` **without** the Base Sepolia overrides silently repoints the oracle at a dead anvil — every chain read then fails, XNS handles degrade to `null`, and the dashboard quietly reverts to `Agent <fingerprint>` labels. Correct invocation: `DOCKER_RPC_URL=https://base-sepolia-rpc.publicnode.com CHAIN_ID=84532 DOCKER_DEPLOYMENTS_FILE=/deployments.baseSepolia.json docker compose up -d oracle-backend`.

## 21. The Claude Code hook set was measured against itself: gate blind, AIS pinned at 0, memory unanchored (2026-07-30)

*Method:* the harness was tested end-to-end rather than reasoned about — `~/.claude/xibalba/tests/probe_loop.py` captures the whole loop as a diffable report (OPA truth table, AIS recomputation, vault census, per-runtime instrumentation matrix, log census). Every claim below is a measurement, not a code reading.

* **CLOSED — the BCC gate was structurally incapable of denying any tool call.** Across 792 logged decisions: **715 authorized, 0 denied, 77 fail-open**. Not luck. Every rule in `policies/bcc.rego` keys on `intent_type`, and `pretool_gate.py` emitted the *constant* label `claude_tool:<ToolName>`, hashing the real command into `intended_state_hash` per §4.2. A constant matches no rule, so `violation` was always `[]` and `allow` always `true`. Direct OPA probes proved the engine was healthy the whole time (`claude_tool_bypass` → `POLICY_VIOLATION`, `EMR_WRITE` → `HIPAA_ACCESS_CONTROL_VIOLATION`); it was simply unreachable. The gate was verifying identity, replay and freshness — real, but not behavioral policy, while logging the word "authorized" as if it were. Fixed by appending a coarse risk class to the label (`claude_tool:Bash:destructive`) derived from the payload, with the payload itself still crossing the wire only as a hash — §4.2's plaintext-never-leaves property is preserved. New `bcc.rego` §3b gates `destructive`/`credential`/`chain_write`/`privileged` on `verification_tier >= 1`; 7 new OPA tests (28 → 35).
  * **Scope stated honestly:** the classifier is a lossy one-way *signal*, trivially evadable by an adversarial agent (base64, indirection, aliasing). It is not a sandbox and must not be described as one. What it buys is a policy surface that is no longer structurally blind, plus a signed commitment ("this agent asserted it was about to do something destructive") that PostToolUse can now be reconciled against.

* **CLOSED — the agent's own AIS was pinned at exactly 0.0, and the cause was the dogfooding gap itself.** `GET /v1/agent/{did}/ais` returned `ais: 0.0` with components `{entropy: 1000, grounding: 1000, sacrifice: 0, compliance: 1000}`. `scoring-core` computes a weighted **geometric** mean, so `0^0.2` annihilates the product regardless of the other three axes. `sacrifice` derives from `metadata.token_usage.total_tokens`; the hooks emitted `{"event": ..., "source": "claude-code"}` and nothing else. **The protocol scored its own construction at zero because the harness never reported the work it did.** Fixed: `_common.work_metadata()` now carries real `token_usage` and `text_output` read from the session transcript. Measured live: `sacrifice` 0.0 → 1.0, `entropy` 1.0 → 0.075 (a real Shannon measurement rather than a default).
  * **Accounting decision, documented not buried:** `cache_read_input_tokens` is **excluded** from the token total. It counts context re-read every turn (~200k/turn), so summing it would report tens of millions of tokens for an afternoon and saturate the sacrifice curve (50k tokens = 1 proxy hour, saturating near 1000).
  * **Double-count hazard found during implementation:** `derive_sacrifice` *sums* `total_tokens` across batch entries, and a per-tool-call hook reading the whole transcript reports a monotonically growing cumulative figure. Reporting it raw would have the oracle add ~1M, then ~1.05M, ... for the same work — exactly the failure `derive.rs`'s own comment warns about. A per-session cursor (`~/.claude/xibalba/cursors/`) now reports deltas; a cursor that can't be persisted omits `token_usage` entirely rather than risk double-counting.

* **CLOSED — three of four AIS axes were fabricated-by-default.** The signed SessionStart envelope carried `derived_signals: {compliance: 1.0, entropy: 1.0, grounding: 1.0, sacrifice: 0.0}`. With no `text_output` in the payload there is nothing to compute entropy or grounding over, and `lexical_stability_score` returns a perfect `1.0` for empty text by design — so a **perfect score was being derived from no evidence**, inside a signed envelope, which is precisely the failure class this repo's no-silent-mocks rule exists to prevent. Both adapters now send real text or omit the key; `work_metadata` omits rather than defaults, so an absent signal stays absent all the way to `derive.rs`.

* **CLOSED — decision recorded (2026-08-02): the fix belongs at the signal layer, not the formula.** Considered and rejected: adding a third state (e.g. `Option<f64>`/null-vs-zero) to `AisComponentInputs` and special-casing it in `scoring-core`'s geometric mean. Rejected for two reasons. First, `scoring-core`'s own docstring already states the geometric mean's zero-annihilates behavior is intentional, not a defect — "a strong axis must not compensate for a wholly absent one" is exactly the property a trust score needs, and a null-aware formula would have to decide what an "unscoreable" AIS even returns to callers (`bcc_middleware`'s tier-gating, the dashboard, `ReputationRegistry.updateScore`) that all currently assume a single `f64`. That's a breaking API change to every consumer, not a formula tweak. Second — and this is the part the original framing missed — §21's own two CLOSED entries immediately above this one show the *actual* bug was never in the formula: `sacrifice = 0` for the dogfooding agent was caused by the harness never reporting `token_usage` at all, and `lexical_stability_score` returning a fabricated perfect `1.0` for empty text was a signal-derivation bug, not a scoring one. Both are now fixed at the source (real `token_usage`, real `text_output`, an absent signal stays absent all the way to `derive.rs` rather than defaulting). The remaining "absent vs. zero" ambiguity is a genuine completeness question, but the honest place to answer it is telemetry-submission validation (flag/reject a submission missing an expected signal class before it ever reaches scoring, distinct future work) — not by teaching the AIS formula a third value that every downstream consumer would need to learn to handle. No `scoring-core` change; keeping the current two-value (reported/not) representation is the decision.

* **CLOSED — the AIS formula had no test pinning its shape.** Replacing the weighted geometric mean with an arithmetic one left **all 9 scoring-core tests passing** (demonstrated, not surmised: patched a scratch copy and ran it). Every existing case sat either at a corner where the two agree (all components equal → both reduce to the same value) or above a tier ceiling that clipped the difference away. Two new tests close this: one asserts the geometric result on deliberately unequal components (geometric ≈653.5 vs arithmetic 680.0), one pins the single-zero annihilation property. Both **fail** under the arithmetic swap; suite 9 → 11.

* **CLOSED — doc drift on the formula, in the two files agents actually read.** `scoring-core/src/lib.rs`'s header quoted the interface contract "verbatim" and stated the **arithmetic** sum; root `CLAUDE.md` did the same. `docs/INTERFACE_CONTRACT.md` §4.3 (normative) has the geometric form, which is what the code does. `CLAUDE.md` is loaded into every agent session, so every session was reasoning about AIS with a model that would not predict the zero-annihilation behavior. Both corrected, both now state the consequence rather than just the formula.

* **CLOSED — the loop recorded intent and never outcome.** Only `SessionStart`/`PreToolUse`/`SessionEnd` were configured: the agent committed to intents it never reported the results of. That is the gap `bcc.rego` §4 names directly ("needs a *second* call after execution"). New `posttool_report.py` (`PostToolUse`) reports outcome, result size, and the **same** `intended_state_hash` the gate committed to, so intent and effect share a key and can be reconciled.

* **CLOSED — vault anchoring silently stopped, and the honest-logging design did not catch it.** 10 commit leaves exist; `anchors.jsonl` records one anchor at `leaves_through: 1`; **9 leaves have been pending since 2026-07-30T08:42Z**. More telling, `session.log` contains exactly **one** `vault:` line in its entire history, though `session_stop.py` logs on *every* branch — the 14:01Z session-end logged its telemetry and then nothing. Reading the vault is not the problem (`session_root()` measured at 0.035s). The hook is being killed before or during the chain write, producing no record at all. Fixed by moving the chain write out of the hook lifetime entirely: `anchor_vault.py` runs detached (`start_new_session=True`, the pattern the Hermes plugin already relies on to outlive a turn), spawned from BOTH `session_stop.py` (session_end) and `session_start.py` (backlog drain). The latter is what finally makes the documented retry real — the old code said "a later session retries rather than losing the evidence", but the later session died at the same step, so a backlog once formed only grew. A per-agent lock prevents two runs racing the same EOA nonce.
  * **Corrected diagnosis:** the first hypothesis was a timeout on the chain write. Measured wrong — the real anchor of all 11 backlogged leaves took **3.3s**. The hook is killed *between* the telemetry flush and the anchor call, not during it. SessionEnd now returns in **0.5s** because it only spawns; there is nothing left to kill. Backlog drained: 11 leaves anchored, tx `b189215d8a38118bb2…`.

* **CLOSED (2026-08-03) — all anchored evidence was empty; root cause was a formula bug, not a discipline gap.** All 48 leaves in the vault's history carried `test_result_hash: "unverified"` or `"unverified:stale"` — including leaves committed *after* `record_test_status.py`/`vault_commit_leaf.py`/`tree_hash.py` were built same-day as the original audit to fix exactly this. The tree-mismatch check they share, `tree_hash()`, hashed `rev-parse HEAD + diff HEAD + untracked-file contents` — and `git commit` necessarily changes both `HEAD` (new SHA) and `diff HEAD` (collapses to empty) even when zero file bytes change. A status stamped immediately pre-commit could never structurally match what the post-commit hook computed one command later, so the match rate was never going to be anything but 0%. Fixed in `scripts/tree_hash.py` by hashing the actual bytes of every tracked file (`git ls-files`) instead of a commit-relative diff — `git commit` snapshots the index into a new commit object without touching working-tree files, so this hash is byte-identical immediately before and after a commit that changes nothing further. Verified two ways: a `--self-test` harness pinning the invariance property (4/4: stable across a commit, unaffected by untracked-file churn, changes on a real staged edit, stable across a second commit), and live — the fix's own commit (`acdae8b`) is the first leaf in the vault's history to carry a real hash (`0xf14dce3e…`, attesting to 43/43 `bcc_middleware` OPA policy tests run against that exact tree) instead of `unverified`.
  * **Note, not re-opened:** all leaves anchored before this fix remain permanently `unverified`/`unverified:stale` — the vault is append-only, so this closes the mechanism going forward, not retroactively. A second, smaller honesty gap surfaced while verifying this: `record_test_status.py --finalize` re-stamps `tree_hash` to the *current* tree but does not check that every already-recorded suite entry in `.integrity-test-status` is still current — a suite result recorded hours earlier, before intervening commits, can get silently re-vouched-for by a fresh `tree_hash` at finalize time if a caller invokes `record_test_status.py` for one new suite without re-running the others. Not fixed this pass; noted for whoever picks up test-status hygiene next.

* **OPEN (architectural) — three runtimes, one DID, three incompatible partial loops.** `xibalba` telemetry is a blend of three adapters with different instrumentation levels, distinguishable only by a metadata field:

  | Runtime | Lifecycle | Pre-exec gate | Per-action telemetry | Anchors memory |
  |---|---|---|---|---|
  | Claude Code | yes | **yes** | yes *(new)* | yes |
  | Hermes | yes | **no** | yes | no |
  | agy | start only | no | no | no |

  Between them every part exists; in no single runtime do they compose. Claude Code committed to intents without outcomes; Hermes reports outcomes it never committed to. `identity.report_action()` now makes `runtime` a mandatory, always-recorded discriminator so a blended `event_count` can be partitioned instead of being read as one agent's uniform behavior — but the oracle does not yet *group* by it, and the oracle does not yet *group* by it. **Hermes tool calls are now gated** (`hermes_gate.py`, registered as a Hermes `pre_tool_call` shell hook): the runtime executed entirely ungated for its whole existence while Claude Code was gated — one DID, two different behavioral guarantees decided by which shell the operator opened. The policy logic is NOT duplicated: `pretool_gate.evaluate_tool_intent()` is the single implementation and `hermes_gate.py` is a wire adapter, because per-runtime duplication is precisely how the two diverged. Labels are namespaced (`hermes_tool:` / `claude_tool:`) and `bcc.rego` §3b matches the risk class positionally, so both reach one ruleset; `tool_runtime` is surfaced for audit. OPA tests 35 → 37.
  * **Bug found by testing rather than review:** the risk classifier keyed on `tool_name == "Bash"`, so every Hermes `terminal` command classified as risk-free even when destructive. Extraction is now keyed on the *field* (`command`/`path`/`content`…), not the tool name, which has no such blind spot across vocabularies.

* **CLOSED — the Hermes adapter discarded the payload the oracle scores on.** `integrity_telemetry`'s `on_post_llm` had the full response text in hand and sent `response_chars: len(resp)` — a length. It now sends `text_output`, capped at 4000 chars to match the Claude side so both runtimes' scores stay comparable.
  * **OPEN, upstream:** Hermes' `post_llm_call` hook does not pass token usage at all (`agent/turn_finalizer.py` forwards only session/task/turn ids, messages, model, platform), so `sacrifice` is still absent for Hermes-attributed work. Deliberately **not** estimated from character count — a fabricated measurement is worse than an absent one, and `sacrifice` is a multiplicative factor. Closing this needs usage plumbed into the hook upstream.

* **Ratified, not fixed — the PreToolUse hook is deliberately fail-open** while `bcc_middleware` steps 5–6 are deliberately fail-closed. The middleware guards production actions where a missed denial is a compliance failure; the hook sits in a developer shell where bricking every Bash call on a container restart gets the hook set disabled wholesale — trading a partial guarantee for none. Operator-confirmed. The mitigation is accounting: `session_stop.py` now logs a lifetime fail-open ratio, because the real risk was never the individual unchecked call but the 77 that accumulated unnoticed inside an 800-line log nobody re-reads.

* **CLOSED — the Verification Ladder ceiling existed in source but was not running.** `GET /v1/agent/{did}/ais` returned **839.41** for a tier-1 agent whose ceiling is 600, even though `handlers.rs` correctly calls `score_with_tier(&inputs, agent.verification_tier)` and the DB held tier 1. Cause was not a code bug: the `oracle-backend` image was built at **03:18:46**, and the ceiling commit `1c6b4d8` landed at **03:22:18** — 3.5 minutes later. The control was documented, tested, committed, and absent from the running binary. Rebuilt and redeployed; AIS now reports exactly **600.0** (raw geometric ≈770, clipped). Both the weighted geometric mean and the tier ceiling are live only as of this audit.
  * **OPEN — nothing detects this class of drift.** The dashboard image has the same problem (`integrity-mvp@0.0.0`/Vite 8.1.4 vs source `integrity-dashboard@0.0.0`/Vite 8.0.16). A security-relevant control that exists in source but not in the deployed system is *worse* than one that doesn't exist, because the tests pass and the docs are true. `make up` should compare image build time against `git log -1` and refuse or warn. Every other finding in §21 was measured against a system that might not have been the one in the tree.

* **CLOSED — dashboard down from two independent faults.** (1) `CoreFeatures.tsx` opened a `<motion.div>` and closed it with `</div>`, so Vite returned **503** for that module and the render died. (2) The real outage: two Vite servers competing for `:5173`. A stale host process running since Jul 29 held `127.0.0.1:5173` and shadowed the container; because it predated `public/XibalbaSolutionsLogo.png`, it served the SPA fallback — `index.html` **with HTTP 200** — for every logo request, so the browser got HTML where a PNG belonged.
  * **Environment footgun:** the container builds as `integrity-mvp@0.0.0` / Vite 8.1.4 while the source tree is `integrity-dashboard@0.0.0` / Vite 8.0.16. The image is stale relative to the directory it builds from, `make up` and the host dev server are **not** interchangeable, and running both silently produces the failure above.

## 22. Deployed-vs-source drift is now detectable (2026-07-30)

`make check-deploy` (`scripts/check_deploy_freshness.py`) compares each service image's build timestamp against the last commit touching the source **baked into that image**, and fails if any image predates its code. Added because §21's oracle finding was undetectable by every other signal: the tests passed, the docs were accurate, the handler was correct, and the control still wasn't running. `make up` runs it in `--warn-only` mode afterwards so an already-running stale container can't hide behind a partial rebuild.

* **Precision was the design constraint, not coverage.** Bind-mounted paths are deliberately excluded: `bcc_middleware/policies` is mounted read-only into the `opa` container, so a `.rego` edit takes effect on an `opa` restart with no rebuild, and listing it would fire a false positive on every policy change. `deployments.*.json` likewise. A checker that cries wolf gets ignored within a week, and an ignored checker is exactly how the original drift survived.
* **First run found three genuinely stale images** (`oracle-backend`, `bcc-middleware` 13h behind an app change, `userapi`), which is the point.
* **Two false positives were found and fixed by using the tool, not by reading it.** (1) Its timestamp parser trimmed fractional seconds by counting digit characters, which also counted the digits inside `-05:00` and silently dropped the offset — shifting local times 5 hours and reporting a freshly built image as STALE. Fixed and pinned with `--self-test`. (2) Comparing image build time against *commit* time flagged the ordinary edit → build → test → commit ordering as stale on every commit; it now compares against source file mtime.
* **CLOSED — content-hash comparison replaces the mtime approximation as the primary signal.** `scripts/service_content_hash.py` hashes each service's tracked source (`git rev-parse HEAD:<path>` per path, keccak256'd — a real content address, not a timing proxy). Every Dockerfile now declares `ARG SOURCE_HASH` + `LABEL source.hash=$SOURCE_HASH`; `docker-compose.yml`'s `build.args` and the root `Makefile`'s `up` target compute and pass it fresh before every `--build`. `check_deploy_freshness.py` now compares the running image's label against a fresh recomputation and reports an exact match/mismatch. The mtime path is kept only as a fallback for images built before this label existed (labeled `(approximate — image predates content-hash labeling)` in the output, so the distinction stays visible rather than silently claiming the same guarantee).

## 23. The tier ceiling made good behavior unrewardable, and voided the ZK boost (2026-07-30)

Found immediately after §21 fixed AIS reporting. While the score was pinned at 0.0 this was invisible; once the loop reported real work it became the binding constraint.

* **The measured problem.** `scoring_core::score_with_tier` clamps AIS to a per-tier ceiling (0→300, 1→600, 2→850, 3→1000). `handlers::SERVER_VERIFIED_TIER` is a hardcoded `1`, and tiers 2/3 "have no verification path implemented anywhere in this codebase" — so tier 1 was not where an agent happened to sit, it was the only value the system could produce. For `xibalba`: raw AIS **704**, reported **600**. Even with all four components perfect (raw 1000) the reported score stays 600. **No amount of good behavior could move the number.**
  * **Worse, the ZK boost was worth exactly zero.** The boost is applied *before* the clamp: 704 × 1.15 = 810 → still clipped to 600. The real Noir/Barretenberg proving pipeline, `submitZkAttestation`, the 7-day `zkBoostExpiry` — the protocol's flagship cryptographic feature bought **0 points**, and an operator running it had no way to notice.

* **CLOSED — rung 2 (DNS TXT) is built and real.** New `backend/src/verification.rs` + migration `0011_identity_verifications.sql` + three routes (`POST /v1/agent/{id}/verify/dns/challenge`, `POST .../verify/dns`, `GET .../verify`). The oracle issues its own nonce, resolves the record itself, and checks the signature with the pubkey it holds from registration — the request body only names *which* domain to inspect. Verified live: with no record published, verification fails with `no TXT record starting with 'integrity-verification=' found`, after genuinely querying both `_integrity.<domain>` and the bare domain.
  * **DNS is resolved over DoH from two independent resolvers (Cloudflare + Google) that must agree.** Plain UDP DNS from inside a container is trivially spoofable by anything on the path, and a single resolver is a single point of compromise for a check whose entire purpose is establishing trust. Disagreement is a hard refusal. It also avoids adding a DNS resolver crate for one endpoint.
  * **The signed message binds DID + domain + nonce** (`integrity-domain-verification:v1:<did>:<domain>:<nonce>`). Dropping any one weakens it materially: without the DID one agent's record verifies another; without the domain a proof replays across domains; without the nonce a record published once verifies forever. Each has a regression test.
  * **DNS verifications expire (90 days).** Namespace control is a claim about the *present* — domains lapse and change hands. Expiry is applied in the SQL that computes the tier, so a lapsed domain lowers the ceiling automatically rather than needing a sweep job.
  * **Effective tier is derived, never cached:** `agents.verification_tier` remains the registration floor, and the tier the system uses is that floor unioned with active verifications. A cached column would drift from its evidence.

* **CLOSED — the ladder is now climbable UNATTENDED, which DNS alone never was.** DNS TXT proves control but requires a human to edit a zone file, so an agent could never raise its own tier. GitHub identity proves the same thing (`control of a namespace`) against a namespace the agent can WRITE TO via API, so challenge → publish → verify runs in one command. Proven end to end on the live agent: **effective tier 1 → 2, ceiling 600 → 850, AIS 600 → 679 and no longer clamped** (raw == reported). The ZK boost is worth ~102 points again instead of zero.
  * **WHOIS was requested and deliberately not built.** WHOIS is a *public record lookup* — anyone can read any domain's WHOIS, so its existence is not evidence that a particular agent controls the domain; this oracle could "verify" `google.com` from a laptop. A proof of control requires doing something only the controller can do, and reading public data never qualifies regardless of how authoritative the source. WHOIS is also widely redacted post-GDPR. It can corroborate an already-proven claim; it cannot establish one.
  * **Repo file, not gist, after hitting a real constraint.** The first implementation published a gist and failed against the live token: `403 Resource not accessible by personal access token` — fine-grained PATs frequently cannot grant gist scope at all. Writing `.well-known/integrity-verification.txt` to a public repo the account owns is the ordinary case, is equally strong (both are namespaces only the holder can write to, and GitHub's API — not the client — is the authority on ownership), and follows the RFC 8615 convention. Gists remain a fallback. Ownership and public-visibility are both re-checked server-side, so naming someone else's repo cannot claim their namespace, and a private repo is refused because a proof nobody else can re-check defeats the purpose.
  * **Method naming was corrected before shipping** (migration 0012). GitHub proofs were initially recorded as `method='dns_txt'` because the proof *shape* is identical, producing self-contradictory audit rows (`method='dns_txt', subject='github:…'`). In a system whose product is verifiable claims, a verification record that misdescribes how it was obtained is precisely the wrong thing to ship.

* **CLOSED — rung 3 is built: real AWS Nitro TEE attestation verification.** `docs/wiki/concepts/identity-ceiling.md` specifies rung 3 as "Remote TEE attestation", and explicitly rejects the old `did:xibalba:<hardware_hash>` idea (CPU model + MAC + machine-id) as never-built ideation a host can freely fabricate. New `backend/src/attestation.rs` parses the real COSE_Sign1/CBOR wire format, verifies the ES384 signature against the embedded leaf certificate, walks the certificate chain, and pins AWS's published Nitro root by SHA-256. Routes: `POST /v1/agent/{id}/verify/tee/challenge` and `POST .../verify/tee`.
  * **Rungs 2 and 3 differ in KIND, not degree.** Rung 2 proves control of an *identifier* — a domain or GitHub account, both transferable and phishable. Rung 3 proves the agent's key lives in *measured enclave hardware* (PCRs record the exact code image), which cannot be forged without breaking the hardware root.
  * **Validated against a genuine captured document**, not a hand-crafted fixture: `integrity-sdk/tests/fixtures/aws_nitro_document.cbor`, a real Nitro document from November 2022, shared with the Python reference implementation so both are checked against identical ground truth. Six tests: verifies the real document; rejects a tampered payload; rejects a tampered signature; rejects a chain not rooted at AWS's root; asserts the bundled PEM matches the pinned fingerprint; and confirms expiry enforcement actually fires.
  * **Generation is impossible outside a real enclave and is NOT stubbed.** Producing an attestation document requires running inside a Nitro Enclave with NSM access — a hardware requirement, not a missing feature. `generate_attestation_unsupported()` exists so callers get that message rather than discovering the absence by finding nothing.
  * **Nonce binding is what makes it a proof about *this* agent.** The oracle issues a nonce; the NSM embeds it in the signed document. Without it, any valid Nitro document from any enclave anywhere would grant tier 3. Verified live: the real fixture is refused because it carries the wrong nonce *and* because production enforces certificate validity (its 2022 certs are expired) — two independent refusals, both correct.
  * **The trust root is vendored into the oracle** (`backend/trust_roots/`) rather than reached for across packages: the Docker build context is `./integrity-oracle`, so a `../../../integrity-sdk/...` `include_str!` fails at image build — and more importantly, a service should own the trust anchor it pins rather than depend on a sibling package's directory layout.

* **CLOSED — the whole ladder is validated as a system, not rung by rung.** The ladder's real failure mode was never "a rung is broken", it was "the rungs don't compose" — the ceiling silently bound at tier 1 for every agent, the ZK boost was entirely absorbed, and nothing in the suite noticed. Eight new tests in `verification::ladder_tests` assert: every tier enforces its documented ceiling (300/600/850/1000); climbing strictly increases the reported score; **the ZK boost is provably wasted below tier 3 for a strong agent** (pinned as a known property rather than left to be rediscovered); a badly-behaved tier-3 agent cannot out-score a good tier-1 one (the ceiling is a cap, never a floor); tiers compose to the maximum rather than summing; losing every proof returns to the registration floor; ceilings are strictly increasing; and an out-of-range tier clamps rather than bypassing.
  * **Live end-to-end validation against the running oracle**, with all state restored afterwards: tier 2 → ceiling 850, AIS 672.6 uncapped; revoke → tier 1, ceiling 600, AIS clipped to 600.0; grant tier 3 → ceiling 1000, uncapped again; expire → excluded from the tier query, back to the floor automatically. One result worth recording because it contradicted the expectation written into the test label: a *tier-0* verification did **not** drop the ceiling to 300 — the registration floor held at tier 1, which is correct (a weak proof must never pull an agent below its floor) and matches `effective_tier(2, &[0]) == 2`.

* **OPEN — KYC (the other rung-3 method) remains schema-only, deliberately.** `identity_verifications.method` accepts `'kyc'` and the tier math handles it, but **no provider adapter is implemented** and none is faked. Building one requires a real provider account (Persona/Stripe Identity/Sumsub); a stubbed "verified" would be exactly the silent mock this repo exists not to repeat. The schema comment pins the constraint that matters when it is built: **no raw PII in this database** — store the provider name, an opaque reference, and a receipt hash only. The oracle is already HIPAA-adjacent (see the PHI backstop in 0010) and must not acquire a second class of regulated data by accident.

* **CLOSED (2026-08-04) — evidence revocation lifecycle.** An agent can request a fresh 60-minute nonce for one owned evidence row, sign a message binding its DID, the row ID, nonce, and hex-encoded UTF-8 reason with its registered Ed25519 key, then revoke the row without deleting its audit history. Effective-tier queries already filter `revoked_at`, so the tier and AIS ceiling fall immediately. Signatures cannot be replayed across agents, evidence rows, nonces, or reasons.

* **CLOSED (2026-08-04) — provider-neutral KYC receipt verification supersedes the schema-only gap above.** `backend/src/kyc.rs` verifies nonce-bound Ed25519 receipts against operator-configured `KYC_PROVIDER_KEYS`. The initial `open_source_kyc_v1` profile requires document authenticity, biometric liveness, and sanctions/PEP screening together; a partial result cannot grant Tier 3. The Oracle persists only an opaque subject reference, provider id, check flags, validity timestamps, and receipt hash. This permits a self-hosted open-source verifier without pretending its result has identical legal effect in every jurisdiction.

* **CLOSED — decision recorded (2026-08-02): keep the hard clamp.** The alternative (scale weight, or cap only the ZK boost rather than the final score) was considered and rejected. Reasoning: `score_with_tier` exists to answer "how much can this AIS number be trusted," and a soft clamp lets an agent with a *weak, unverified* identity claim scores statistically indistinguishable from a verified one — the ceiling's entire job is to prevent exactly that, and softening it reopens the sybil/self-attestation problem the Verification Ladder was built to close. The "ZK boost worth zero below tier 3" consequence is real but is priced into the ladder's own design: `verification::ladder_tests` (`integrity-oracle/backend`) already asserts this as a deliberate, pinned property — "the ZK boost is provably wasted below tier 3 for a strong agent" — not a bug discovered after the fact. Changing the clamp now would mean rewriting eight tests that were written specifically to encode this behavior as correct, and would move every sub-tier-3 agent's live on-chain score on the next `scoring_loop.py` sync cycle — a production change this scope doesn't carry the regression coverage to make safely. The honest fix for "good behavior should be rewarded before tier 3" is **lowering the bar to reach tier 2/3** (more verification methods, e.g. finishing the schema-only KYC rung, see the OPEN item above), not softening what the ceiling means once tiers exist. No code change; the prior "open design question" framing is resolved to "current design is correct, kept as-is."

* **CLOSED — decision recorded (2026-08-02): confirmed mis-specified; NOT fixed this pass, deliberately.** `derive::lexical_stability_score` is `1 − normalized_Shannon_entropy` over word frequency, so maximally repetitive text scores 1.0 and varied text scores near 0.0 (empty text also scores a perfect 1.0 — see §21's F3, now fixed at the signal layer so empty text no longer reaches this function at all). The metric conflates two different things — "stable/predictable" and "repetitive" are not the same property, and the S_entropy axis wants the former but `lexical_stability_score` measures the latter. A genuinely correct replacement (e.g. scoring semantic/task-outcome consistency across a period rather than lexical word-frequency entropy of a single completion) is real design work this pass didn't do.

  **Why this stays open as a documented decision rather than a quick patch:** this function is implemented twice — `integrity_sdk/telemetry/derive.py` (Python, client-side re-derivation) and `integrity-oracle/backend/src/derive.rs` (Rust, the oracle's independent server-side re-check that's the actual scoring input, per `derive.rs`'s own docstring on why client-claimed signals aren't trusted). Both must change together and stay bit-identical in behavior, the same cross-implementation discipline the BCC canonicalization and token-accounting vectors already enforce elsewhere in this repo. Changing it also moves every live agent's `s_entropy` component immediately, which `bcc_middleware/app/scoring_loop.py` pushes on-chain via `ReputationRegistry.updateScore` on its next sync cycle — a formula change here is a production score change on Base Sepolia, not a local edit, and shipping one without dedicated before/after validation against real agent history (at minimum, confirming `xibalba.integrity`'s own score moves in an explicable direction) is exactly the kind of rushed change this repo's "no silent mocks, no undocumented gaps" discipline argues against. Recorded as a confirmed, scoped, two-file fix for a dedicated follow-up session — not silently dropped, not patched in a hurry.

## 24. The protocol silently failed to anchor its own development evidence for days (2026-07-31)

Found while recovering from a two-day outage in which the root filesystem went
`emergency_ro` and the previous session ran with **no shell at all** — it could write files
but never execute one. That session's findings were browser-measured and partly wrong; this
entry records what survived verification and what did not. Full detail:
`docs/design/e2e-audit-2026-07-31.md` (resolution pass, findings E10–E16).

* **The measured problem — `bcc-middleware` signed every transaction for chain 31337 while
  connected to Base Sepolia (84532).** Every `anchorRoot` and `updateScore` it attempted was
  rejected by the node. The anchor path logs the failure and returns — *"retained in logs
  only"* — so **a protocol whose entire premise is anchored, non-forgeable evidence was
  failing to anchor its own construction**, for days, while `make test` passed and `/healthz`
  answered `ok`. This is the exact class of gap the dogfooding mandate exists to catch, and
  nothing except reading container logs would have caught it.
  * **Root cause was a missing env var, not the deployments file.** `app/config.py:37` reads
    `CHAIN_ID` and defaults to `31337`. `oracle-backend` sets `CHAIN_ID` in
    `docker-compose.yml`; **`bcc-middleware` never did** — it was the one service taking
    `RPC_URL` from env without taking its chain id from the same place. After the 2026-07-29
    switch to Base Sepolia it kept signing for anvil.
  * A second, independent misconfiguration sat behind it: `DEPLOYMENTS_FILE` was hardcoded to
    `/deployments.local.json` with only that file mounted, so even with the chain id fixed the
    service would have used **anvil contract addresses on Sepolia**. Both are fixed; both were
    required. Fixing either alone would have looked like progress and produced nothing.
  * **CLOSED — proven by on-chain state change, not by absence of errors.** Container env now
    reports `CHAIN_ID=84532 DEPLOY=/deployments.baseSepolia.json` and the chain-id error is
    gone, but that alone would only show transactions were *submitted*. The evidence that they
    **succeed**:
    * **`anchorRoot` landed.** The agent's `StateAnchor.latestRoot` moved
      `0xdecb860c63dae118…` → `0x946387f7fab3a87c…`, `isAnchoredRoot(0x946387f7…) == true`,
      and `pending_batch_size` dropped to 0 on flush. The previous root still reports
      `true`, confirming the append-only property held across the write.
    * **`updateScore` landed.** `ReputationRegistry.scores(0x360e2a56…).lastUpdated` is a
      timestamp from this session (`1785484478`), which only an accepted transaction sets.
    * Nonce advancement (260 → 275) was *not* treated as proof — a reverting transaction
      consumes its nonce too. It is corroborating, not load-bearing.
  * Both roles were confirmed **before** wiring the key in, rather than discovered through a
    failed transaction: `hasRole(ANCHOR_ROLE, 0x67bA5D72…) == true` on the agent's own
    `StateAnchor`, and `hasRole(ORACLE_ROLE, …) == true` on its `ReputationRegistry` — these
    are different contracts and different roles, and `updateScore` needs the second.
  * `BCC_MERKLE_BATCH_SIZE` is now surfaced in `docker-compose.yml` (it was only reachable as
    a `config.py` default). Setting it to 1 is what made the anchor path provable in one
    commitment instead of eight — and the rarity of flushes is precisely why this defect
    stayed invisible: **the failure only manifests on flush.**

* **The test harness could record a pass and could not record a failure.** Every line of
  `make test` read `cd pkg && pytest && cd .. && $(TEST_STATUS) pkg pass || $(TEST_STATUS) pkg fail`.
  On failure `&&` short-circuits, so `cd ..` never runs and the `||` branch execs the recorder
  *from inside the package directory*, where it does not exist — it crashes. **The mechanism
  that feeds test outcomes into the anchored evidence chain could only ever write `pass`.**
  That crash then aborted the whole target at the first failing package, so one
  `bcc_middleware` failure silently skipped `integrity-userapi` and `integrity-dashboard`
  entirely.
  * An evidence system that can record success and cannot record failure does not have a
    logging gap, it has a **bias** — and it is a direct contributing cause of §19/F5's
    "every leaf says `unverified`".
  * **The trap in fixing it:** repairing only the path makes `|| … fail` exit 0, so `make test`
    would report **success on a red suite** — strictly worse than the crash. Fixed as
    `|| { $(TEST_STATUS) pkg fail; false; }` with `$(CURDIR)` on the recorder: record the
    outcome, then still fail.

* **CLOSED (2026-08-13) — test-status tree fingerprints now survive the commit boundary.**
  `scripts/tree_hash.py` is the shared implementation imported by both
  `record_test_status.py` and `vault_commit_leaf.py`; it hashes tracked file bytes rather than
  `HEAD` plus a commit-relative diff. The deterministic self-test passed **4/4**: stable across
  a commit, unaffected by untracked files, changed by a staged tracked edit, and stable across a
  second commit. This closes the algorithmic stale-status defect. It does not prove that a test
  status was externally anchored or that every future leaf will be submitted; those remain
  separate delivery and anchoring observations.

* **CLOSED — the vault-leaf importer would have written a false lineage, caught before its
  first real run.** `scripts/import_memory_dag.py` chained each leaf to its predecessor in
  file order. Measured against the real 21-leaf vault, that assumption is *half* right: leaf
  timestamps are strictly monotonic, so file order is chronological — but **chronological
  order is not ancestry**. Of 20 consecutive pairs, 19 are true git ancestor pairs and one is
  not: `6c0c9bf → d7e4deb` are *siblings* off merge-base `354c6b5` (one on
  `docs/spec-open-definitions`, one on `main`) because the developer switched branches.
  * In a recall system that is a harmless approximation. In an **evidence** system whose whole
    claim is non-forgeable lineage, an edge that is merely plausible is worse than no edge — it
    is a false statement that verifies. The importer now resolves each parent via a real
    `git merge-base --is-ancestor` check and records a second root rather than inventing a
    parent. Corrected import: `d7e4deb → 36e23d9b` (the true fork point), with `6c0c9bf` left
    as what it actually is — an unmerged branch tip.
  * Known limitation, recorded rather than hidden: `root_of_heads` folds only *named* refs, and
    only `head` is named, so it commits to the main line and not to the full frontier.

* **OPEN — the oracle serves stale anvil primitives as authoritative.** `GET /v1/agent/{did}`
  for an agent that does not exist on the configured chain returns **200**, not 404, carrying
  anvil-era addresses and `"blockchainAccountId": "eip155:31337:…"` from a Sepolia-configured
  oracle. The chain read correctly reverts `UnknownDID()`; the handler then falls back to the
  DB cache. The fallback itself is defensible — a transient RPC failure should not blank the
  dashboard — but it is **chain-agnostic**, so it will serve addresses from a *different chain*
  without saying so beyond `"primitives_source": "cache"`. For a system whose stated invariant
  is "the chain is the source of truth", that is a false answer, not a degraded one. The cache
  should record the chain id it was populated from and refuse to serve across a mismatch.
  **Do not close this by deleting the five stale rows** — that silences the symptom and
  destroys evidence.

* **CLOSED — audit reports are fire-and-forget during requests but drained on shutdown.**
  `main._report_decision_background` still schedules the audit write as
  `ensure_future(to_thread(report_decision, …))` and nothing ever awaits it during the
  request, preserving non-blocking authorization responses. `lifespan()` now retains the
  task and waits for a snapshot of all in-flight audit reports before the ASGI shutdown
  event returns. The wait is bounded at 10 seconds; reports still in flight are logged as
  a residual degraded-mode finding rather than blocking shutdown indefinitely. Surfaced
  because `test_evidence_linkage.py` was accidentally reproducing exactly that: its bare
  `TestClient(app)` tore down a fresh event loop per request and cancelled the pending task,
  giving 1 pass / 3 fail across four consecutive runs with no code change. The test is fixed
  (context-managed client), and `test_shutdown_drain.py` now proves both successful draining
  and bounded give-up logging. This closes shutdown cancellation loss, not oracle delivery
  guarantees: an oracle outage can still lose a report because the audit path remains
  best-effort and has no local durable spool or retry queue.

* **OPEN — the nonce race survives its own documented lock.** After the chain-id fix,
  `updateScore` still failed with `nonce too low: next nonce 261, tx nonce 260`, despite
  `nonce_lock.py` holding a process-wide lock across the full read → sign → broadcast → receipt
  sequence specifically to prevent it (§5). The lock being process-wide makes an in-process
  race unlikely; the leading hypothesis is a **stale nonce read from the load-balanced public
  RPC** — `contracts/.env` itself warns that `publicnode.com` rate-limits aggressively.
  **Explicitly unconfirmed**: separating the two requires a dedicated endpoint.

* **CLOSED — compose healthchecks now probe a data path, not liveness.** No service declared a
  `healthcheck:` at all. Five now do; the oracle's hits **`/v1/agents` (which touches Postgres),
  deliberately not `/healthz`** — a bare `-> "ok"` handler that answers 200 from a service that
  cannot serve a single real request. Wiring a healthcheck to it would have reproduced the
  original bug with more ceremony. Database `depends_on` were converted to
  `{condition: service_healthy}` so the oracle waits for readiness rather than start.

* **A correction to the record, kept deliberately.** The prior session's headline finding —
  "every `/v1` route returns HTTP 500" — **did not reproduce**. All routes return 200 with real
  data; the oracle's boot log is clean and contains zero sqlx errors across its whole history;
  and both named suspects (Postgres/Redis, and the uncommitted `db.rs` query) were wrong — the
  query is type-safe and demonstrably works. What the 500s actually were is **not established**,
  because the container that served them was replaced before a shell existed to inspect it. The
  honest statement is that the evidence was destroyed, not that the problem was solved. That is
  itself the argument for the healthchecks above: `/healthz` returning `ok` preserved no
  information that could distinguish "broken" from "briefly broken" after the fact.

* **OPEN — the dashboard Docker image cannot be rebuilt.** `docker compose build dashboard`
  fails at `npm install` with `Cannot read properties of null (reading 'edgesOut')` — an npm
  arborist crash, not a dependency conflict. Consequence: the running dashboard image dates
  from **2026-07-18** while its source is current, so `make check-deploy` reports it STALE and
  *cannot be made fresh*. The dashboard's own suite passes on the host (`vitest run`, 20 files
  / 68 tests), so this is a container-build problem, not broken code. Untouched by this
  session's changes — `package.json`/`package-lock.json` are unmodified. Worth noting that the
  freshness check (§22) is doing exactly its job here: it converted an invisible 13-day drift
  into a visible, actionable failure.

## 25. `integrity_sdk/mcp_server.py` exposed signing/on-chain-write tools with zero coverage from the one gate anyone trusted (2026-08-05)

Found while reviewing a *proposed, not-yet-built* idea in a different project
(`xibalba-cortex`) — an MCP server that would wrap the SDK's signing capabilities as
agent-callable tools. A Devil's Advocate review commissioned to evaluate that proposal checked
whether anything like it already existed before assessing the hypothetical, and found this
module already shipped exactly the gap the review was there to prevent. Full narrative:
`xibalba-cortex/docs/session-log/2026-08-05-integrity-coupling-session.md`. Design and
fix: `docs/design/mcp-signing-boundary.md`.

* **The measured problem — `integrity_register_agent` was a live, callable MCP tool that loaded
  a real Ed25519 identity key and could run a full on-chain registration**, triggered by
  whatever an LLM's own tool-selection reasoning decided, with no confirmation step and no
  policy gate in the path. Three more tools in the same file — `integrity_flush_telemetry`,
  `integrity_invoke_intent`, `integrity_commit_memory` — sign or write with the same lack of
  gating.
* **`~/.claude/xibalba/pretool_gate.py`'s `RISKY_TOOLS` set had zero MCP-tool-name coverage.**
  It matches five fixed strings (`Bash`, `Write`, `Edit`, `MultiEdit`, `NotebookEdit`); any
  `mcp__<server>__<tool>` call was never even evaluated, let alone gated. Confirmed by direct
  inspection, not inferred — `RISKY_TOOLS` contains no `mcp__` pattern at all.
  * Compounding factor: `pretool_gate.py`'s existing coverage is deliberately **fail-open** —
    a considered, ratified tradeoff for the Bash/Write/Edit developer-shell class (documented at
    length in its own module docstring), never intended to extend to a real signature.
* **Verified independently before any fix, not taken on the review's word:** confirmed
  `integrity_register_agent`'s handler directly (loads a PEM from
  `~/.integrity-cli/identity/<agent>/`, calls `registration.register_agent`), confirmed
  `pretool_gate.py`'s `RISKY_TOOLS` line and its fail-open comment directly, confirmed
  `bcc_middleware/app/opa_client.py`'s fail-closed posture directly, confirmed MCP's
  elicitation primitive is *not* a guaranteed human-in-the-loop block by reading its own
  docstring ("might... automatically generat[e] a response"). Also confirmed the server was
  **not currently wired into any running MCP client config on this machine** — a real,
  reachable gap, not an active incident.
* **CLOSED — fixed at two layers, not one.**
  * `integrity_sdk/mcp_server.py`: the four signing/writing tools are disabled by default at
    both discovery (`_on_list_tools` filters them out) and dispatch (`_on_call_tool` refuses to
    execute them even if called directly) — defense in depth, not one control. Gated behind
    `INTEGRITY_MCP_ALLOW_SIGNING_TOOLS=1` for supervised local experimentation only. Read-only
    tools (`integrity_agent_info`, `integrity_resolve_did`) and the local-queue-only
    `integrity_log_telemetry` remain enabled — they were never the problem.
  * `pretool_gate.py`: added `MCP_SIGNING_TOOL_NAMES` (mirrors `mcp_server.py`'s
    `_SIGNING_TOOLS`), matched by tool-name suffix so a renamed server alias doesn't evade it,
    with a new `fail_closed` parameter on `evaluate_tool_intent()` — this new coverage denies on
    every pre-verdict failure path instead of allowing, while the existing Bash/Write/Edit
    class's fail-open behavior is completely untouched.
  * New tests: `integrity-sdk/tests/test_mcp_server_signing_boundary.py` (7 tests — tools
    undiscoverable and unexecutable by default, env-var opt-in works, safe tools still
    advertised) and `~/.claude/xibalba/tests/test_pretool_gate.py` (4 tests — suffix matching,
    fail-closed denial on identity-unavailable and middleware-unreachable). Full SDK suite (252
    tests) and hooks suite (8 tests) both still pass — no regressions from either fix.
  * **Explicitly not fixed by adding a confirmation dialog.** MCP elicitation was considered and
    rejected as the mechanism — it's a structured-input request either side of the session can
    answer, not a safety property. The actual fix removes the capability from the tool surface
    entirely; a human runs `integrity-cli` directly for anything that signs.

## 26. `UltraPlonkVerifier` generated-verifier adoption and proof coverage (2026-08-12; updated 2026-08-17)

Found while triaging an uncommitted, dirty working tree on `audit/harness-loop-2026-07-30` ahead
of a repo-wide rename/stabilization pass. `contracts/src/oracle/UltraPlonkVerifier.sol` was
initially suspected to be accidental damage — its interface conformance to `IZkVerifier` had been
dropped, and `contracts/test/UltraPlonkVerifier.t.sol` was deleted in the same uncommitted diff.

* **Not damage — this is the real `bb`-generated verifier, correctly wired.** The working-tree
  contract has an actual `verify()` implementation (no more
  `PlaceholderVerifierNotYetGenerated` revert), matches `integrity-zkp/generated/UltraPlonkVerifier.sol`
  plus hand-added `assembly ("memory-safe")` annotations, and compiles clean
  (`forge build` succeeds with only pre-existing lint warnings from the generated code).
* **Dropping the `IZkVerifier` conformance was necessary, not accidental.** The generated file
  already carries Barretenberg's own baked-in `interface IVerifier` with an identical
  `verify(bytes,bytes32[]) external view returns (bool)` signature. Attempting
  `contract UltraPlonkVerifier is BaseZKHonkVerifier(...), IZkVerifier` fails to compile
  (Solidity error 6480 — diamond conflict, two base declarations of the same function). This was
  verified directly, not assumed: re-adding the explicit conformance and running `forge build`
  reproduced the compile error, then reverting confirmed clean compilation. `IZkVerifier` was
  deliberately designed (see its own docstring) to be satisfied via ABI-compatible low-level
  dispatch (`IZkVerifier(impl).verify(...)` in `VerifierRegistry.sol`), not formal inheritance —
  this is exactly what lets a reviewed generated-verifier handoff swap the placeholder for the real contract
  without touching any calling contract.
* **The deleted test file is correctly obsolete, not a regression.** It only asserted
  placeholder-only behavior (`vm.expectRevert(UltraPlonkVerifier.PlaceholderVerifierNotYetGenerated.selector)`
  on every input, including a fuzz test) — assertions that no longer hold now that `verify()` does
  real work. Restoring it as-is would fail.
* **CLOSED (2026-08-13) — direct generated-verifier real-proof coverage.** Retained fixtures live at
  `contracts/test/fixtures/ultraplonk/proof.bin` (8,000 bytes) and
  `contracts/test/fixtures/ultraplonk/public_inputs.bin` (96 bytes). The Foundry test
  `contracts/test/UltraPlonkVerifier.t.sol` reads the binary proof and exactly three caller-supplied
  `bytes32` public inputs, matching the generated ABI's `publicInputs.length == 3` requirement.
  It asserts fixture lengths and hashes, then exercises the actual generated verifier with a valid
  proof, a tampered proof, tampered public inputs, and malformed proof bytes.
  `forge test --match-path test/UltraPlonkVerifier.t.sol -vvv` returned **4 passed, 0 failed**.
  This closes direct verifier coverage only; registry forwarding, proof regeneration from a clean
  environment, and deployed/on-chain verification remain separate gaps.

## 27. AIS scoring — fail-open empty-evidence defaults inverted (2026-08-17)

Found while implementing `spec/integrity-protocol-v3.2.md` §3.1.1's AIS redefinition
(requirement N2, "earned, not granted") against the reference implementation. Verified
numerically before touching any code, not assumed from the spec's description.

* **CLOSED (rows 1–2 of §3.1.4's implementation-delta table) — `derive_entropy`,
  `derive_grounding` (`integrity-oracle/backend/src/derive.rs`, mirrored in
  `integrity_sdk/telemetry/derive.py`) and `self_reported_compliance`
  (`derive.rs` only — `derive.py`'s `derive_compliance` had the same defect inline) all
  returned **1.0 (maximum)** for an empty batch or a batch with no scoreable content.
  Missing evidence therefore read as *perfect* evidence on three of the four AIS axes —
  only `derive_sacrifice` failed closed to 0. Because `scoring-core::score` is a weighted
  **geometric** mean (`AIS = S_entropy^0.3 · S_grounding^0.3 · S_sacrifice^0.2 ·
  S_compliance^0.2`), this meant a submission carrying token counts but **no analysable
  content** — maximal entropy/grounding/compliance by default, plus a self-reported
  `sacrifice` claim — scored **r = 0.923** at 100 claimed GPU-hours, while an honest agent
  reporting real-but-mediocre telemetry across all four axes scored **0.465**. The
  content-free agent outscored the honest one roughly two-to-one, inverting the incentive
  the metric exists to create.
* **Fix:** all three now return `0.0` on empty/no-evidence input. Verified: the same
  content-free-but-token-bearing submission now scores entropy=0 and grounding=0
  regardless of claimed sacrifice — `scoring-core`'s existing geometric-mean annihilation
  (any single exact zero zeroes the product; see its own
  `any_single_zero_component_annihilates_ais` test) does the rest without needing rows
  5–6 below. New regression tests:
  `integrity-oracle/backend/src/derive.rs::content_free_submission_with_token_counts_fails_closed_on_entropy_and_grounding`
  and
  `integrity-sdk/tests/unit/test_derive.py::test_content_free_submission_with_token_counts_fails_closed_on_entropy_and_grounding`.
  Full suites green: oracle workspace 137/137 (`cargo test --workspace --lib`), SDK 262
  passed/3 skipped (`uv run pytest tests/`).
* **Still open (§3.1.4 rows 3–6, none landed in code) — do not consider this gap fully
  closed.** Compliance still falls back to the agent's own self-reported
  `policy_violation`/`flagged` metadata for every non-healthcare agent (row 3);
  `derive_sacrifice` still divides self-reported token counts by a proxy constant instead
  of requiring validator/TEE attestation (row 4); there is no declared per-component floor
  or conjunctive Θ gate (row 5) — a 90%-violation agent still reaches r≈0.631 under the
  bare geometric mean, since only an *exact* zero annihilates the product, not a small
  positive value; and the oracle's published `ais` field is still post-boost and unclamped
  (up to 1150) rather than exposing the pre-boost, `[0,1]`-clamped accessor §3.1.1 eq. 4b
  requires as the actual constraint input (row 6). Rows 3–4 are blocked on attestation
  infrastructure the whitepaper proposes for Phase III (§10.3); rows 5–6 are not code-complex but
  change AIS's output for every currently-registered agent, and this repo pushes AIS to
  chain automatically (`bcc_middleware/app/scoring_loop.py`, default 300s) and can raise a
  real `Slasher.raiseDispute` off the resulting score — landing rows 5–6 needs a dry-run
  against the live agent set first, not a direct edit. See `HANDOFF.md`'s 2026-08-17
  section (and its later addendum) for the full priority ordering.

## 28. Phase 0 identity discovery facade — local implementation closed, deployment and native ERC-8004 convergence open (2026-08-17)

The v3 rollout plan's Phase 0 originally called for an "ERC-8004-shaped" read adapter over
`XibalbaAgentRegistry`. Primary-source review and a focused Devil's Advocate pass established
that a read-only DID projection cannot honestly implement the current draft's ERC-721 token
identity, ownership, transfer, approval, wallet-proof, metadata-write, event, Reputation
Registry, or Validation Registry semantics.

* **CLOSED — bounded Integrity-native read profile.**
  `contracts/src/kernel/IntegrityIdentityReadV1.sol` provides DID, DID-hash, and
  `SovereignAgent` resolution, all seven primitive addresses, domain and registration metadata,
  the live agent-controlled `AgentProfile.profileURI`, and candidate-controller verification
  against the account's current `DEFAULT_ADMIN_ROLE`. It pins the reviewed ERC-8004 draft
  revision and returns `isERC8004Conformant() == false`.
* **CLOSED — mapping inconsistencies fail closed.** The facade verifies the registry's
  DID-to-agent and agent-to-DID mappings agree and that `SovereignAgent.agentDID()` hashes to
  the registered DID. This prevents the existing registry's duplicate-agent overwrite edge
  case from being silently projected as a valid identity.
* **CLOSED — AIS authority remains separate.** The facade returns the agent's
  `ReputationRegistry` primitive address but exposes no score or ERC-8004 feedback method.
  Agent Integrity Score (AIS) remains authoritative only through the existing Integrity
  Oracle and per-agent reputation primitive paths.
* **CLOSED — no agent migration.** The facade is read-only and projects existing registry
  records. Future genesis deployments include it as `singletons.IntegrityIdentityReadV1`;
  existing agents and primitive addresses are unchanged.
* **VERIFIED LOCALLY.** `forge test --match-contract IntegrityIdentityReadV1Test -vvv`
  returned **10 passed, 0 failed**. Coverage includes negative conformance probing, controller
  rotation, mutable/empty profile URIs, duplicate-agent stale mappings, declared-DID mismatch,
  missing DID read surfaces, unknown records, zero dependency rejection, and proof that a
  reverting profile cannot block fixed identity resolution.
* **OPEN — existing Base Sepolia deployment.** No broadcast or deployment-file mutation was
  performed. Deploying the facade against the existing registry is a separate gas-costing
  external write requiring exact approval and post-deployment bytecode/readback verification.
* **OPEN — native ERC-8004 convergence.** Exact conformance requires a separately reviewed
  registry design with version-pinned token identifiers, ownership/transfer semantics, events,
  historical treatment, wallet proof, and a selector-by-selector compatibility matrix. The
  current facade must not be marketed to generic ERC-8004/ERC-721 tooling as compatible.
* **OPEN — source-registry invariant.** `XibalbaAgentRegistry` still permits the same
  `SovereignAgent` to be registered under multiple DIDs and the factory does not enforce that
  its DID argument matches `SovereignAgent.agentDID()`. The facade detects and rejects this
  state; it does not repair the underlying registry or retroactively change deployed code.

## 29. Whitepaper v3.2 proposed-spec implementation delta (2026-08-17)

`spec/integrity-protocol-v0.5-proposed.md` now maps every substantive v3.2 semantic amendment.
It remains non-authoritative. The mapping closes a documentation gap; it does not close these
implementation gaps:

* **PARTIAL — identity and AIS defaults.** Phase 0's custom identity profile is locally tested,
  and missing entropy/grounding plus empty self-reported compliance now fail closed to zero.
  Native ERC-8004 convergence, the AIS floor gate, admissibility enforcement, pre-boost
  constraint score, versioned profile, migration, and conformance vectors remain open.
* **PLANNED — federated telemetry prover.** The current AIS Oracle remains a Trusted,
  single-operator component. No threshold validator profile or general ZK-telemetry prover exists.
* **PLANNED — stake-secured memory availability.** No accepted availability stake,
  challenge/production contract, deadline enforcement, or deterministic slashing path exists.
* **PLANNED — circuit-breaker grace modes.** No execution kernel, hard/soft constraint
  partition, monotone contraction adapter, AIS-floor precedence implementation, or bounded
  settlement staging path exists.
* **PLANNED — high-frequency channels and compiler.** No ATCP/IP channel profile,
  injective channel-head settlement implementation, or `integrity-dsl` compiler exists.
* **PLANNED — hybrid attested-host profile.** No production deployment binds attestation to
  the specific transaction with freshness and measured egress. Existing host/TEE evidence must
  not be described as extending on-chain complete mediation.

Whitepaper §1.5 (comparative architecture) and §10.4 (enabler framing) remain explanatory rather
than independent protocol clauses. Acceptance requires clause-level review, interface schemas,
tests, migration/conformance evidence, and explicit incorporation into the active specification.

### §27 addendum (2026-08-17) — real dry-run against the one live registered agent

Per §27's own "still open" note: rows 5-6 (floors/gate, pre-boost accessor) need a dry-run
against the live agent set before landing, since this repo auto-pushes AIS to chain with
slashing consequences. Ran that dry-run for real against the actually-running local stack
(`docker ps` showed `oracle-backend`/`postgres`/`bcc-middleware` etc. already up for days,
not started for this check) rather than synthetic data.

**Only one agent is registered**: `did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861`
(`xibalba.integrity`, verification_tier 1) — this repo's own dogfooding agent. `GET /v1/agent/{id}/ais`:

| Component | Value (of 1000) |
|---|---|
| entropy | 268.45 |
| grounding | 950.17 |
| sacrifice | 861.34 |
| compliance | 1000.0 |

Reported `ais: 600.0` is **not** the raw geometric mean (`268.45^0.3 * 950.17^0.3 * 861.34^0.2
* 1000^0.2 ≈ 645`, computed by hand) — it's `scoring-core::ceiling_for_tier(1) == 600.0`
clamping it down, confirmed by reading `lib.rs`'s tier-ceiling match arms directly. The
Verification Ladder tier ceiling and the proposed AIS floor/gate (§3.1.1) are two independent
capping mechanisms; this agent is already capped by the former regardless of the latter.

**What this means for the still-unmade floor-value decision (§3.1.4 row 5):** entropy is this
agent's weakest axis by a wide margin (268 vs. 950-1000 on the other three). Under the proposed
conjunctive Θ gate, **any entropy floor set above ~268 would zero this repo's own dogfooding
agent's entire score** — not a hypothetical edge case, a concrete real number from the only
agent currently live. This doesn't argue for or against any specific floor value (that decision
is explicitly not this document's to make), but it's the number a floor-value decision needs to
be checked against before landing, and it's now on record rather than needing to be re-derived.

No chain writes, no code changes, no floor values chosen. Read-only against the already-running
local stack.

**Decision (2026-08-17, explicit user call):** wait for more agents before picking floor
values or flipping enforcement on. Shadow mode (above) stays purely observational — no
numbers chosen, no code change, no chain-behavior change. Revisit trigger: a second real
agent registers (so there's an actual distribution instead of N=1), or the decision is
explicitly revisited regardless of agent count. Options considered and declined: setting
provisional floors and enforcing now anyway (rejected — an agent failing a floor zeroes
`ais`/`constraint_score`, which can trigger `Slasher.raiseDispute` via
`bcc_middleware/app/scoring_loop.py` and drop PHI-gate access via `EHRGate`/
`ComplianceGate`, too consequential to base on one data point).

## 28. Registration non-idempotency — CLOSED in both `integrity-sdk` and `integrity-cli`

**Heading corrected 2026-08-19** — this section's title previously read "fixed in
`integrity-sdk`, still open in `integrity-cli`", written before the `integrity-cli` fix (the
second bullet below) landed and never updated afterward. Verified directly against current
source before changing this line, not assumed from the body text alone: both `integrity-cli`'s
`chain.py` (`resolve_did`/`has_anchor_role`/`itk_balance`/`state_anchor_latest_root`) and
`main.py` (`_registration_progress_path`/`_load_registration_progress`/
`_save_registration_progress`) exist and match what the second bullet below describes. Nothing
left to build here — this was a stale label, not open work.

*Current State:* `integrity_sdk/registration.py`'s `register_agent()` deploys a
`SovereignAgent`/`StateAnchor` pair (steps 5-6), then mints testnet ITK, grants `ANCHOR_ROLE`,
and anchors a genesis root (steps 7-8b) before the final `registerPrimitives` (step 9). Its
only idempotency check — `resolve_did()` against `XibalbaAgentRegistry` — only starts matching
once step 9 has *already* succeeded, so every retry after a failure anywhere in steps 4-8b
deployed a fresh, throwaway pair. This is not hypothetical: it's the exact shape of five
separate real incidents on Base Sepolia across two sessions (2026-08-14, 2026-08-17 — see the
registration entry above, items 3/4/7), each leaving a real, orphaned, gas-paid
`SovereignAgent`/`StateAnchor` pair with no cleanup path.

* **CLOSED in `integrity-sdk`** — `register_agent()` now persists a
  `registration_progress.json` next to the DID's `document.json` immediately after
  `SovereignAgent`/`StateAnchor` deploy succeeds (steps 5-6), and checks it (verifying real
  bytecode via `eth_getCode` before trusting it — the same lesson the phantom-factory incident
  taught about blindly trusting a recorded address) before attempting a fresh deploy on any
  subsequent call. Steps 7 (ITK mint — NOT idempotent, a retry would double-mint) and 8b
  (genesis root anchor — re-running against an already-anchored `StateAnchor` was previously
  unverified territory, not actually protected by the `resolve_did` short-circuit the old
  comment claimed) are now also checked before re-running, via two new `chain.py` read helpers
  (`itk_balance`, `state_anchor_latest_root`). Step 8 (`grant_anchor_role`) was already safe —
  OZ's `grantRole` no-ops if already held — but is now checked first too, to skip the
  redundant transaction rather than just tolerate it. The progress file is cleared once
  `registerPrimitives` succeeds (the point `resolve_did`'s own check takes over) or once an
  early idempotent return confirms the DID is already fully registered. Two new regression
  tests against a real local anvil chain (`tests/test_registration.py`): one simulates
  `registerPrimitives` failing on the first call and succeeding on a retry, asserting the
  SAME `SovereignAgent`/`StateAnchor` addresses are reused; the other asserts a progress file
  pointing at bytecode-less addresses is discarded rather than trusted. Full suite green (264
  passed / 3 skipped, up from 262 by exactly the 2 new tests).
* **CLOSED — `integrity-cli` had its own, independent copy of this registration flow**
  (`integrity_cli/main.py`/`chain.py`, doesn't import `integrity-sdk` at all — see
  `CLAUDE.md`'s "SDK vs CLI" section) that turned out to have **no idempotency protection
  of any kind**, not even the basic `resolve_did` check the SDK had before its own fix —
  every `integrity agent register` invocation unconditionally deployed a fresh
  `SovereignAgent`/`StateAnchor` pair, even for an already-registered DID. Ported the same
  two layers from the SDK fix: `chain.py` gained `resolve_did`/`has_anchor_role`/
  `itk_balance`/`state_anchor_latest_root` (identical shape to the SDK's versions,
  duplicated per this package's existing "no sibling dependency" convention, not imported);
  `main.py`'s `agent_register` now checks `resolve_did` first (short-circuits with the
  existing registration, matching the SDK's early-return branch) and persists/resumes
  deploy progress via a new `<identity>.registration_progress.json`, with the same
  bytecode-verification-before-trusting-a-recorded-address discipline. Also factored the
  previously-duplicated oracle-POST logic (~50 lines inline, twice) into one shared
  `_post_registration_to_oracle` helper used by both the early-return and full-registration
  paths. Two new regression tests against a real local anvil chain
  (`tests/test_register_resume.py`, no Docker/cargo/oracle-backend needed unlike the
  existing `ORACLE_E2E=1` oracle test): one simulates `register_primitives` failing on the
  first `integrity agent register` invocation and succeeding on a retry, asserting the CLI
  reuses the same addresses; the other asserts a second invocation for an already-registered
  identity is a genuine no-op. Full suite green (70 passed, up from 68 by exactly the 2 new
  tests; the Docker-gated oracle e2e test was not re-run, unrelated to this change).

## 29. Phase I tracer-bullet slice — built, tested, NOT deployed (2026-08-17)

*Current State:* per explicit user authorization of
`docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md`, built the minimal slice the proposal
scoped: `contracts/src/kernel/IntegrityAccountV1Experimental.sol` +
`IntegrityKernelV1Experimental.sol`. Non-upgradeable, non-deployed (not referenced by
`Deploy.s.sol` or any script), single `CALLTYPE_SINGLE`/`EXECTYPE_DEFAULT` execution mode only,
module mutation permanently disabled after the one atomic constructor-time kernel install, one
conserved quantity (a native-value spend budget, per-operation and cumulative). Full precise
guarantee statement and what it does NOT prove:
`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`.

12 new Foundry tests (`contracts/test/IntegrityAccountV1Experimental.t.sol`), covering: in/out-of
per-op-budget, exact cumulative-budget boundary vs. one-wei-over, all three rejected execution
modes, both module-mutation entry points disabled (including against the real already-installed
kernel, not a hypothetical), the hook rejecting non-account callers and out-of-sequence calls,
and a genuine self-call reentrancy attempt against the `armed` guard. The reentrancy test was
mutation-tested, not just written and trusted: temporarily removing the `armed` check makes the
same test fail with a *different* error (`NotArmed` instead of `AlreadyArmed`), demonstrating the
nested call's `postCheck` silently corrupts the outer call's own armed state without the guard —
real evidence the guard does work, not decoration. `preCheck` gas measured live under the
whitepaper's own Table 4 budget (`<=40k`), as a regression test, not a one-off number. Full repo
suite green: 221/221 (up from 209 before this slice).

**Extended same day with a second reference adapter (reputation floor)**, per separate
authorization of `docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md`. The kernel now
enforces two conjunctive conditions: the existing native-value budget, and
`ReputationRegistry.effectiveScore(boundAccount) >= minEffectiveScore` (a precondition gate
checked once in `preCheck`, not a conserved quantity needing `postCheck` involvement). Real
multiplexing inside the one hook module the base OZ contract allows, not a second hook. Tested
against a real, standalone `ReputationRegistry` EIP-1167 clone (its implementation disables
direct initialization, confirmed by reading the constructor — deployed via `Clones.clone` the
same way `AgentPrimitivesFactory` does in production, not a bare `new`). 3 new tests: below-floor
reverts even when in-budget, the exact floor boundary succeeds, and an above-floor account is
still independently bound by the budget check. The reputation check was also mutation-tested —
removing it makes the below-floor test wrongly pass, confirmed and reverted before landing.
`preCheck` gas re-measured (the real reason the gas test is a regression test, not a one-off
number): 27,131 → 35,505, still under the 40k Table 4 budget but a real, caught increase. Full
repo suite green: 224/224. Explicitly independent of the still-deferred AIS floor/shadow-gate
decision (§27) — reads the existing oracle-pushed `effectiveScore`, doesn't touch `scoring-core`
or pick any floor value there.

**Extended again same day with the third and final named reference adapter (assurance tier)**,
per `docs/plans/2026-08-17-phase1-assurance-tier-adapter-proposal.md`. `preCheck` gains a third
conjunctive condition: `ReputationRegistry.isZkBoosted(boundAccount)` must be true. No new
external dependency (reuses the same `reputationRegistry` immutable the reputation-floor adapter
already wired in). 2 new tests (non-boosted reverts even when budget+reputation pass; an expired
boost — a genuine `block.timestamp` boundary, not a static flag — is treated as not-boosted),
both mutation-tested. Net +2 tests (added 2, removed 1 redundant test the new work made
unnecessary). Full repo suite: 226/226.

**Real, disclosed finding from this extension, not silently resolved:** with all three checks
live, `preCheck` measures ~40,129 gas — over the whitepaper's own Table 4 budget (`<=40k`). The
Phase I plan itself named this exact pressure point before this slice existed ("reputation
should be cached/snapshotted per epoch rather than read live on every call") — now confirmed
live. Per this session's own stated commitment, the gas test was renamed to document the finding
honestly (`test_preCheckGasExceedsPaperTable4BudgetWithThreeUncachedChecks`, asserting the cost
is both genuinely over 40k and hasn't regressed past a documented 42k ceiling) rather than having
its threshold quietly raised. The real fix (per-epoch score snapshotting) is out of scope for a
reference-adapter slice and would need its own proposal if pursued. Full detail:
`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`'s "Known limitation" section.

**What this explicitly does not close:** any of the rest of the real Phase I plan (module
governance, canonical intent encoding, the BCC `chain_id`/verifier-binding gap, the gas-budget
finding above) remains unbuilt/unresolved. No external audit has occurred — this slice does not
clear the Devil's Advocate review's own stated gate to Phase II. Not deployed to Base Sepolia or
anywhere else, and completing this slice is not itself grounds to deploy it — that would be a
separate, later, separately-approved decision.

**Extended same day with timelocked, atomic kernel-swap module governance — this REVERSES the
"module mutation permanently disabled" claim made above.** Per
`docs/plans/2026-08-17-phase1-module-governance-proposal.md` (which states the reversal
plainly), `installModule`/`uninstallModule` still always revert directly, but a new
`proposeKernelSwap`/`executeKernelSwap`/`cancelKernelSwap` path now reaches the same underlying
`_installModule`/`_uninstallModule` internals through a timelocked, atomic swap: propose a new
kernel, wait out a mandatory delay, then atomically uninstall the old kernel and install the new
one in one transaction (never a reachable state with zero hook modules installed). Explicitly
**single-signer-timelocked, not the plan's full "timelocked + multi-party"** — this account has
exactly one ECDSA signer, so a compromised key can still eventually force a swap, just not
instantly or silently.

A dedicated Devil's Advocate review (independent subagent, full diff + OZ base source + test
suite) ran before landing, attacking six named risk areas. Top-line verdict: add code-level
mitigations before shipping (not ship-as-is, not revert). Two real gaps were fixed in code, not
just documented: (1) the constructor accepted a zero timelock with no validation, which would
have silently voided the entire mechanism (instant swap in one transaction) — now reverts
`ZeroTimelock()`, matching the same input-validation discipline the sibling
`IntegrityKernelV1Experimental` constructor already applies; (2) `proposeKernelSwap` accepted any
non-zero address with zero interface validation, so a non-conforming address only failed after
the timelock elapsed — now probes `newKernel.isModuleType(MODULE_TYPE_HOOK)` and fails fast.
Both fixes are mutation-tested. A third, more severe finding is disclosed rather than code-fixed
because it is genuinely unfixable at this scope: a kernel that passes the interface probe but
reverts unconditionally in `preCheck` installs cleanly, then permanently bricks every future
`execute()` AND blocks every rescue swap too (the rescue's own uninstall half must call the
broken kernel's `preCheck` first) — worse than simply re-enabling `installModule` outright, since
a bad kernel there fails instantly and visibly rather than catastrophically later with no way
back. This is now a permanent regression fixture
(`test_brokenKernelPreCheckPermanentlyBricksAccountWithNoRescuePath`), not just a documented
claim, and corrects an earlier, incomplete "locked out until it requalifies" framing (that
describes only the separate, recoverable reputation-floor lockout case). The review also
confirmed and sharpened: the swap is asymmetrically mediated (removal of the old kernel is
content-gated via reputation/assurance checks; installation of the new kernel is gated only by
the interface probe and elapsed time, never by a security-content check) — so this mechanism
satisfies the whitepaper's condition (iii) for removal, not installation; and named two
reentrancy windows (both swap halves run with `_hook` storage already updated before the
module's own `onInstall`/`onUninstall` lifecycle hook fires) that remain open, disclosed rather
than closed.

14 new Foundry tests total for this extension (10 for the mechanism itself, +4 from the review's
findings and their regressions), all mutation-tested where they assert a security-relevant
guard. Full suite for this file: 31/31 (up from 17). Full repo suite: 240/240 (up from 226).
Full findings, the six-area review, and the fix-by-fix response:
`docs/plans/2026-08-17-phase1-module-governance-proposal.md`'s "Devil's Advocate review and
response" section. Still not deployed, still not externally audited, still does not clear the
Phase II gate; multi-party governance, canonical intent encoding, the BCC binding gap, and the
gas-budget finding remain open — **except the gas-budget finding, closed same day, below.**

**Extended same day with reputation epoch-snapshotting — this RESOLVES the gas-budget finding
above, for real, not just a documented mitigation.** Per
`docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md`, `IntegrityKernelV1Experimental`
no longer reads `effectiveScore`/`isZkBoosted` live on every `preCheck` call. Instead,
`refreshReputationSnapshot()` (permissionless — anyone may call it, not only the bound account)
reads `reputationRegistry.scores(boundAccount)` once and caches both derived values;
`preCheck` reads the cache and fails closed (`SnapshotStale`) if it is older than an immutable
`epochLengthSeconds` (capped at `MAX_EPOCH_LENGTH_SECONDS = 7 days`). Measured, not estimated:
**`preCheck` now costs 33,321 gas** in the steady state — under the whitepaper's own `<=40k`
Table 4 ceiling, down from the previously-measured 40,129.

**This closes the finding but does not make it free — the tradeoff is a real, disclosed one.**
Within an epoch, reputation is not merely "possibly stale," it is completely unenforced — only
the budget check still bounds behavior during that window. The design also introduces a new
liveness dependency the live-read design never had: `execute()` can now revert purely because
nobody refreshed the cache in time, for any call. And it creates a genuine interaction with the
kernel-swap mechanism above: if `moduleActionTimelockSeconds` (governance timelock) exceeds
`epochLengthSeconds` (reputation freshness window), a fully-vested swap can revert `SnapshotStale`
for a reason unrelated to reputation, and a freshly-installed kernel can be stale-on-arrival,
rejecting the account's first post-swap call. Both contracts' NatSpec now state
`epochLengthSeconds >= moduleActionTimelockSeconds` as an explicit deployment invariant — neither
contract enforces this on its own; it is operator/deploy-script discipline, not a code guarantee.

A dedicated Devil's Advocate review (independent subagent, full diff + `ReputationRegistry.sol` +
the kernel-swap mechanism + test suite) ran before landing. Two real gaps fixed in code: (1) the
kernel's local `ZK_BOOST_BPS`/`BPS_DENOMINATOR` constants (duplicated for gas efficiency) were
"verified" only by a test comparing two hardcoded literals against each other — since the
constants are `private` on the kernel, the test never actually touched the kernel at all, so a
future `ReputationRegistry` redeployment with different constants would have silently produced
wrong cached scores forever, undetected; now the constructor cross-checks against the real
registry's own values at deploy time and reverts `BoostConstantsMismatch` on divergence,
mutation-tested, plus a genuine differential test (`test_refreshedSnapshotMatchesALiveEffectiveScoreRead`)
asserting the cache equals a live read. (2) `epochLengthSeconds` had no upper bound, so "epoch-
snapshotted reputation" could be truthfully claimed by a deployment meaning, in practice, "never
re-checked"; now capped at `MAX_EPOCH_LENGTH_SECONDS = 7 days`, mutation-tested. A third gap —
zero events anywhere, undermining the keeper-refresh pattern the whole mechanism depends on — was
also closed: `ReputationSnapshotRefreshed` now emits on every refresh.

10 new Foundry tests for the mechanism itself, +4 from the review's findings and their
regressions (14 total this extension). Full suite for this file: 41/41 (up from 17 before any of
today's kernel work). Full repo suite: 250/250 (up from 209 before this slice began). Full
findings and the fix-by-fix response:
`docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md`'s "Devil's Advocate review and
response" section.

**What remains open, restated:** multi-party governance (still single-signer-timelocked),
canonical intent encoding / the BCC `chain_id`/verifier-binding gap, the two disclosed reentrancy
windows from the kernel-swap review, the no-recovery-path broken-kernel-brick class, and the new
`epochLengthSeconds`-vs-`moduleActionTimelockSeconds` deployment invariant (unenforced across the
two contracts) all remain unbuilt/unresolved. No external audit. Not deployed to Base Sepolia or
anywhere else, and none of today's work is grounds to deploy it — that remains a separate, later,
separately-approved decision.

## 30. BCC `chain_id`/`verifying_contract` binding — closes the general-purpose half of the
canonical intent encoding gap (2026-08-18)

*Current State:* per `docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md`, the
BCC commitment schema (§4.2) now requires and signs two new fields: `chain_id` (EVM chain ID) and
`verifying_contract` (the target chain's `XibalbaAgentRegistry` address). Before this, a
commitment signed once was valid, byte-for-byte, against any chain or any deployment of the
protocol sharing the signing agent's DID — `nonce` is monotonic per-agent but not
deployment-scoped, so it didn't close this. Implemented identically across `integrity-sdk/bcc.py`,
`integrity-cli/bcc.py`, and `bcc_middleware/app/{schemas,canonical}.py`; every real production
call site updated (`integrity-sdk/markets.py`'s three BCC-integrated market flows,
`integrity-sdk/telemetry/intent.py`'s `invoke_intent`, `integrity-cli/main.py`'s `agent intercept`
command, `integrity-dashboard/demo/heartbeat.py`).

`bcc_middleware/app/main.py` gained a new deployment-binding check (step 1b, before signature
verification — cheapest, no crypto, no I/O). **A real, disclosed design adjustment from the
proposal's original framing:** the proposal described both fields as an unconditional hard deny.
In implementation, `chain_id` IS enforced unconditionally (`Settings.chain_id` always has a
value). `verifying_contract` is enforced only when this deployment has a configured
`XibalbaAgentRegistry` address (`Settings.contract_address("XibalbaAgentRegistry")` returns
non-`None`) — most of the existing local/dev/test topology runs with no deployments file
configured at all (`bcc_middleware/tests/conftest.py`'s `deployments.local.json` is `touch()`ed
empty; several tests explicitly point at a nonexistent deployments file, e.g.
`test_chain_baa_anchor.py`'s "Explicit, nonexistent deployments_file" case), and making
`verifying_contract` an unconditional fail-closed check would have turned that whole existing
posture into a blanket deny — a materially larger blast radius than this slice's own proposal
disclosed ("pure Python wire-schema + middleware validation... lower blast radius"). Stated
plainly here rather than silently shipped as the originally-described unconditional check.

**What this does NOT close**, matching the proposal's own explicit deferrals: the experimental
kernel's own hook-frame replay-domain binding (account, kernel/profile, execution depth, action
digest, pre-state digest, configuration epoch — `CLAUDE_HANDOFF_2026-08-17.md` §9) is untouched,
separate, contract-side, larger scope. Binding `chain_id` into the ZK circuit's
`intent_commitment` (`integrity-zkp/src/main.nr`) is untouched — the Pedersen hash still covers
only `secret_key`, `intent_payload_hash`, `agent_id_commitment`, `nonce`; adding a public input
means a circuit change, verifying-key regen, and `UltraPlonkVerifier` regen, real cross-package
work not attempted here. A `verifying_contract` mismatch against an *unconfigured* registry is
never enforced by this slice — a real, disclosed residual, not a silent gap: an operator relying
on this binding for a production deployment must confirm `DEPLOYMENTS_FILE` actually resolves a
`XibalbaAgentRegistry` entry, or the check silently no-ops for that field.

Tests: `bcc_middleware/tests/test_deployment_binding.py` (new) covers chain_id mismatch denied,
verifying_contract mismatch denied when configured, verifying_contract NOT enforced when
unconfigured, and schema-level rejection of missing/malformed fields. `bcc_middleware/tests/
helpers.py`'s `sign_commitment` gained defaulted `chain_id`/`verifying_contract` params (sourced
from `default_settings.chain_id` and a placeholder address respectively) so the existing ~75-test
suite continues to exercise the same behavior it did before this change, without per-test edits.
`integrity-cli/tests/test_bcc.py` updated for the new required positional params and field-set
assertion. Cross-repo: `xibalba-shield/shield/integrity_exporter` calls
`integrity_sdk.bcc.build_bcc_commitment` directly and needed a matching update — see that repo's
own history for the corresponding change, tracked separately from this repo's scope.

## 31. Guardian M-of-N quorum on kernel-swap execution — closes unilateral swap *execution*, not
unilateral swap *denial* (2026-08-19)

*Current State:* per `docs/plans/2026-08-18-phase1-multiparty-kernel-governance-proposal.md`,
`IntegrityAccountV1Experimental` gained an immutable guardian set (`address[] guardians()`) and
threshold (`guardianThreshold`), set once at construction (no rotation mechanism in this slice).
`proposeKernelSwap`/`cancelKernelSwap` remain unchanged, single-signer (`onlyEntryPointOrSelf`)
— proposing/cancelling stays low-stakes by design, deliberately not gated, to avoid making swap
*denial* itself a multi-party negotiation. `executeKernelSwap` gained a fourth precondition:
`kernelSwapApprovalCount[kernelSwapNonce] >= guardianThreshold`, checked after the pre-existing
three (pending exists, address match, timelock elapsed) and before the uninstall/install
sequence — verified independently gating alongside, not instead of, those three
(`test_existingSingleSignerPreconditionsStillGateAlongsideQuorum`). A new
`approveKernelSwap(uint256 expectedNonce, address newKernel)` entry point is guardian-only,
nonce-scoped (`kernelSwapNonce` bumped once per `proposeKernelSwap`, so a stale approval from a
cancelled or already-executed proposal can never silently count toward a later one —
`test_approvalFromACancelledProposalDoesNotCountTowardARepropose`), and idempotent per guardian
per nonce (`test_approveKernelSwapDoesNotDoubleCountTheSameGuardianUnderTheSameNonce`).

**What this closes, precisely:** before this slice, a single compromised signer key, waiting out
the timelock, could force any kernel swap alone. After it, that same key can still *propose* and
start the clock, but cannot *execute* without independently convincing `guardianThreshold`
guardians — distinct keys, not derived from the account signer — to each submit their own
on-chain approval.

**What this does NOT close, disclosed and accepted, not solved:**
- **Unilateral swap denial.** `proposeKernelSwap`/`cancelKernelSwap` stay signer-only; a
  compromised or uncooperative signer can park an unwanted proposal in the single pending-swap
  slot indefinitely (never cancelling, never letting guardians act on anything), denying the
  account — including a legitimate rescue swap — for as long as the signer withholds a cancel.
  Letting guardians cancel at threshold would close this but reintroduces a stuck-negotiation
  failure mode this proposal deliberately rejected for `cancelKernelSwap`.
- **Guardian collusion or guardian-key compromise at or above threshold.** An M-of-N quorum is
  only as strong as the independence of the M keys, which the contract cannot verify or enforce
  — an operational/deployment discipline, not a code guarantee.
- **Guardian-set rotation.** The set is immutable forever at construction — simple to reason
  about, but an unreachable or permanently-departed guardian permanently raises the effective bar
  toward "impossible," never toward "insecure." A future slice would need a second, probably
  also-guardian-gated rotation mechanism if this is adopted further.
- **The two pre-existing reentrancy windows and the broken-kernel brick scenario from §29's
  tracer-bullet entry.** A malicious or buggy `newKernel` that passes the `isModuleType` probe
  can still brick the account after a fully-guardian-approved swap; quorum raises the bar for
  *who* can propose a bad swap and get it through, not whether the swap itself is safe once
  approved.
- **A second, permanent break of the "hook mediates every reachable state-changing path" claim.**
  `approveKernelSwap` is guardian-callable directly, deliberately not routed through
  `execute()`/`withHook` (gating a guardian behind the account's own hook would be circular).
  Proven empirically, not just asserted, by `test_approveKernelSwapIsNotMediatedByTheInstalledHook`
  (installs a permanently-`preCheck`-reverting kernel, shows guardian approvals still succeed).
  Both `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` and this contract's own NatSpec now
  disclose this, alongside the pre-existing swap install/uninstall mediation asymmetry.
- **A genuinely new failure mode, not a restated one: quorum-gathering can itself stale the
  reputation snapshot.** Guardian approval-gathering takes real elapsed time (the timelock, then
  M separate guardian transactions), which can exhaust the outgoing kernel's `epochLengthSeconds`
  even when the snapshot was fresh at the moment gathering began — not just via the pre-existing
  timelock-vs-epoch collision every other success-path test already routes around with a single
  upfront refresh. Regression-tested end to end, not left as a restated theoretical risk:
  `test_quorumGatheringCanStaleTheSnapshotBetweenApprovals` assembles quorum with a warp *between*
  the two guardian approvals, confirms `executeKernelSwap` reverts `SnapshotStale` (not
  `InsufficientGuardianApprovals` — full quorum was genuinely reached), then confirms the
  permissionless `refreshReputationSnapshot()` recovers it.

**Verification discipline applied:** strict red→green TDD per the proposal's process section.
Mutation-tested both new security-relevant guards — temporarily removed the
`InsufficientGuardianApprovals` threshold check (caught by
`test_executeKernelSwapRevertsBelowGuardianThreshold` and, incidentally,
`test_approvalFromACancelledProposalDoesNotCountTowardARepropose`) and the nonce-equality check in
`approveKernelSwap` (caught by `test_approveKernelSwapRevertsOnWrongNonce` — the cancelled-nonce
replay test does NOT catch this mutation, since approvals are indexed by the *current* nonce
regardless of what a guardian claims, so that guard protects intent-matching, not storage
isolation; both guards restored after confirming detection). Constructor edge cases covered:
threshold 0, threshold > guardian count, duplicate guardian address, zero-address guardian
(`test_constructorRevertsOnZeroGuardianThreshold`, `test_constructorRevertsWhenThresholdExceedsGuardianCount`,
`test_constructorRevertsOnDuplicateGuardian`, `test_constructorRevertsOnZeroAddressGuardian`).
The proposal's third named adversarial-pass item — "interaction with the existing reentrancy
windows (does a reentrant call during onInstall/onUninstall see stale or fresh approval state?)"
— is answered empirically, not left open, by `test_reentrancyDuringInstallAndUninstallObservesFreshApprovalsAndEmptyPending`:
a `ReentrancyObserverKernel` fixture plays "new kernel" (onInstall) in one swap and "old kernel"
(onUninstall) in a following one. Answer: `pendingKernelSwap` is already cleared (empty) at BOTH
callback points (`delete pendingKernelSwap` runs before either half), but
`kernelSwapApprovalCount` for the just-consumed nonce is NOT cleared alongside it — a reentrant
reader sees the full, fresh approval count next to an empty pending slot. Separately proves this
window cannot be used to *mutate* quorum state: a reentrant `proposeKernelSwap` call from inside
the callback reverts (`msg.sender` there is the kernel contract itself, neither `self` nor the
entry point) and a reentrant `approveKernelSwap` call reverts (that same address is not a
registered guardian). The two pre-existing reentrancy windows this test exercises remain open and
disclosed, per §29's tracer-bullet entry — this only closes the *quorum-specific* question the
proposal asked, not the windows themselves.

Gas measured directly from call traces, not assumed unchanged: `proposeKernelSwap` 67,886 (cold);
`approveKernelSwap` 49,771 first guardian / 27,871 second guardian (cold vs. one-less-cold slot);
`executeKernelSwap` 41,268. `IntegrityAccountV1ExperimentalTest` suite: 41 → 55 tests (+14: 9
scope-enumerated guardian-quorum tests, 4 constructor edge cases, 1 reentrancy-window
observation), all passing; full repo suite 264/264 (up from 250 before this slice). The 5
pre-existing tests that call `executeKernelSwap` on a success path were updated to gather
guardian approval first, not left broken.

**Not deployed anywhere.** Foundry-test-only, local, uncommitted at time of writing, same
standing rule as every prior Phase I slice — no push/commit/deploy without separate explicit
authorization.

## 32. Guardian emergency action — closes unilateral swap *denial*, both forms (2026-08-18)

*Current State:* per `docs/plans/2026-08-18-phase1-guardian-swap-denial-proposal.md` (Option B,
user-selected), `IntegrityAccountV1Experimental` gained a third, fully signer-independent
governance path: `guardianProposeAction(bool isCancel, address newKernel)` /
`approveGuardianAction(uint256 expectedNonce)` / `executeGuardianAction()`. Unlike
`approveKernelSwap` (§31, gates an already signer-initiated swap's *execution*), this path
requires no signer action anywhere — a guardian starts it, and it is gated by **unanimous**
approval (all of `_guardians`, not merely `guardianThreshold`), deliberately the highest bar in
the contract, since this is the one path where the signer's cooperation is never required.

**What this closes, precisely:** §31 left two denial gaps open, both now closed by one mechanism:
(1) a signer who proposes a swap and then refuses to cancel can no longer park it forever —
guardians unanimously force-cancel (`isCancel: true`); (2) a signer who is gone entirely (lost
key, unresponsive) previously left guardians with *nothing to act on at all*, since only the
signer could call `proposeKernelSwap` — guardians can now unanimously force-propose a new swap
from scratch (`isCancel: false`), with no pending swap required first.

**A real design gap found and fixed during implementation, not assumed away:** a force-proposed
swap still has to pass through the *existing* `executeKernelSwap` to actually land — and that
function was `onlyEntryPointOrSelf`, signer-only, unconditionally. An absent signer could never
call it, so the rescue would have stalled at the last step even with full guardian consensus and
an elapsed timelock. Fixed, with the user's explicit sign-off on the tradeoff (asked and answered
plainly, not decided silently): `executeKernelSwap`'s caller check now accepts the entry point,
the account itself, **or any single guardian** — `if (msg.sender != address(this) && msg.sender
!= address(entryPoint()) && !_isGuardian[msg.sender]) revert AccountUnauthorized(msg.sender);`.
This widens *who may submit* the call; it does not weaken *what is required to succeed* — the
four existing preconditions (pending exists, address match, timelock elapsed,
`kernelSwapApprovalCount[kernelSwapNonce] >= guardianThreshold`) are untouched and still
independently gate every caller. Proven, not assumed:
`test_executeKernelSwapCallableByGuardian_StillEnforcesExecutionQuorum` (a guardian calling before
quorum still hits `InsufficientGuardianApprovals`) and
`test_executeKernelSwapRevertsForUnrelatedCaller_EvenAtFullQuorum` (a non-guardian, non-signer
stranger is rejected even once every other precondition, including quorum, is satisfied).

**Deliberate design choice: force-propose requires nothing already pending, not an atomic
override.** If a swap is stuck (case 1 above) and guardians also want a different kernel
installed (case 2), they must force-cancel first, then force-propose — two separate unanimous
actions, not one combined one. Keeps each guardian action's blast radius to exactly one state
transition; `test_guardianForcePropose_RevertsIfSwapAlreadyPending` proves this is enforced, not
merely intended.

**A force-proposed swap is indistinguishable from a signer-proposed one once created** — it bumps
`kernelSwapNonce` exactly as `proposeKernelSwap` does (proven by
`test_guardianForcePropose_UnresponsiveSigner_FullRescueWithNoSignerInvolvement`, which asserts
the nonce increment directly), so it needs the *same* `guardianThreshold` M-of-N execution quorum
via the pre-existing `approveKernelSwap`, and is subject to the same timelock — no shortcut for
either. This was a deliberate design choice (share the existing bookkeeping rather than invent
parallel machinery) specifically to avoid reopening the class of bug `kernelSwapNonce` already
solved once for proposal-to-proposal replay.

**What this does NOT close, disclosed and accepted, not solved:**
- **Guardian collusion or compromise at unanimity.** Raising the bar from `guardianThreshold` to
  N-of-N raises the cost of an attack, it does not make the guardian set's honesty verifiable
  on-chain — same standing caveat as §31's own execution quorum, at a stricter threshold.
- **Guardian-set rotation.** Still absent (tracked separately,
  `docs/plans/2026-08-18-phase1-guardian-rotation-proposal.md`). An unreachable guardian now
  raises TWO bars toward impossible instead of one: the existing M-of-N execution threshold, and
  this slice's new N-of-N emergency threshold — losing even one guardian permanently makes the
  emergency path unusable, a real, disclosed cost of choosing unanimity.
- **The broken-kernel brick scenario.** A force-proposed swap's uninstall half still calls the
  outgoing kernel's `preCheck` (unchanged — `executeKernelSwap`'s uninstall/install mediation
  asymmetry from §29 is untouched by this slice). A kernel that reverts unconditionally there
  remains unrescuable by this mechanism alone; see
  `docs/plans/2026-08-18-phase1-broken-kernel-rescue-proposal.md`, which explicitly builds on this
  slice's guardian-origination machinery rather than duplicating it.
- **The two pre-existing reentrancy windows from §29.** Orthogonal — unrelated to who originates
  or authorizes a swap.
- **A third, permanent exception to "hook mediates every reachable path."** Alongside
  `approveKernelSwap` (§31), `guardianProposeAction`/`approveGuardianAction`/`executeGuardianAction`
  are guardian-callable directly, never routed through `execute()`/`withHook` — gating an
  emergency, signer-independent path behind the account's own hook would be circular. Both
  `IntegrityAccountV1Experimental.sol`'s own NatSpec and
  `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` (pending amendment — see Scope: in below)
  must disclose this as the third exception, not a silent extension of the second.

**Verification discipline applied:** mutation-tested all three security-relevant guards this
slice adds/changes, restored after confirming each was caught: (1) the unanimity check in
`executeGuardianAction` weakened to `guardianThreshold` instead of `_guardians.length` — caught by
`test_executeGuardianActionRevertsBelowUnanimity` failing with a different error
(`NoSwapPending()` instead of the expected `InsufficientGuardianActionApprovals`, since a
weakened-to-2 threshold let a force-cancel with no real pending swap slip past the approval gate
and hit the next, unrelated check instead); (2) the nonce-mismatch check in `approveGuardianAction`
removed — caught by `test_approveGuardianActionRevertsOnWrongNonce`; (3) the widened caller check
on `executeKernelSwap` removed entirely — caught by
`test_executeKernelSwapRevertsForUnrelatedCaller_EvenAtFullQuorum`. Strict red→green TDD was not
followed test-by-test for this slice (implementation and tests were written together, not
failing-test-first per function), a real deviation from this codebase's stated discipline,
disclosed here rather than silently omitted — the mutation-testing pass after the fact is what
substitutes for it, not a replacement for having done TDD, but real evidence the guards work.

Gas measured directly from call traces, not assumed unchanged. Force-cancel path:
`guardianProposeAction(true, address(0))` 49,282 (cold); `approveGuardianAction` 49,256 first
guardian / 25,356 second / 27,356 third (unanimity, so all three guardians pay, unlike
`approveKernelSwap`'s two-of-three); `executeGuardianAction` (force-cancel) 5,262 (cheap — only
clears two storage slots). Force-propose path: `guardianProposeAction(false, newKernel)` 50,310
(cold, includes the `isModuleType` probe); `approveGuardianAction` 47,256 / 27,356 / 27,356;
`executeGuardianAction` (force-propose) 65,566 (writes `pendingKernelSwap`, bumps
`kernelSwapNonce`); the subsequent `executeKernelSwap` called by a guardian (not the signer)
41,625 — matching §31's own signer-called measurement (41,268) closely, confirming the widened
caller check adds negligible cost to the already-measured function.

`IntegrityAccountV1ExperimentalTest` suite: 55 → 71 tests (+16: guardian-action propose/approve/
execute validation, both denial scenarios end-to-end with zero signer involvement, the
already-pending and nothing-pending negative cases for each action type, and two tests confirming
`executeKernelSwap`'s widened caller set doesn't weaken its existing guards). Full repo suite:
280/280 (up from 264/264 before this slice).

**Scope: in, not yet done —** `docs/design/phase1-tracer-bullet-slice-2026-08-17.md` still needs
the same disclosure this entry gives; `IntegrityAccountV1Experimental.sol`'s own NatSpec was
amended at implementation time (see the contract's guardian-emergency-action paragraph) but the
design doc was not yet updated to match, per this codebase's own standing discipline that both
must agree.

**Not deployed anywhere.** Foundry-test-only, local, uncommitted at time of writing, same
standing rule as every prior Phase I slice — no push/commit/deploy without separate explicit
authorization.

## 33. Guardian-set rotation, plus a real liveness bug found in §32's emergency path (2026-08-18)

*Current State:* per `docs/plans/2026-08-18-phase1-guardian-rotation-proposal.md`, the guardian
set is no longer permanently fixed at construction. `proposeGuardianRotation(bool isAddition,
address guardian)` / `approveGuardianRotation(uint256 expectedNonce)` /
`executeGuardianRotation()` let the CURRENT guardians add or remove one guardian at a time —
never both in a single rotation — gated by UNANIMOUS approval, same bar as §32's emergency
action. Two user decisions fixed the design, both explained in plain language before being asked
(per the user's own standing preference — see the session's earlier exchange): (1)
`guardianThreshold` itself is NEVER rotatable, immutable forever, closing off "guardians vote the
bar down toward 1" as an attack surface; (2) rotation requires unanimous approval, not the
ordinary `guardianThreshold`, since changing who the guardians ARE is at least as sensitive as
using an emergency action.

**Removal safety:** a removal that would drop the guardian count below the immutable
`guardianThreshold` is rejected outright (`GuardianRemovalWouldBreakThreshold`), tested at the
exact boundary (3 guardians, threshold 2 — first removal to exactly 2 succeeds, a second removal
to 1 reverts), not just an interior case.

**Cross-mechanism lock, enforced symmetrically:** at most one guardian-relevant governance
process may be in flight at a time. `proposeGuardianRotation` is blocked while a kernel swap or
guardian action is pending; `proposeKernelSwap` and `guardianProposeAction` are both blocked
while a rotation is pending. This is what makes it safe to keep the removal-during-a-pending-swap
question simple (block rotation entirely rather than needing to invalidate a removed guardian's
stale approval mid-swap) — by construction, a swap can never be proposed while a rotation is
pending, so the interaction the original proposal doc's "Trap 2" worried about cannot occur.
Proven in both directions by `test_crossMechanismLock_HoldsInBothDirections`, not just asserted
for one.

**A real, previously-undiscovered liveness bug in §32's mechanism was found while writing this
slice's tests, and fixed, not left disclosed-and-broken.** `executeGuardianAction` deletes
`pendingGuardianAction` and only afterward checks whether the action can actually proceed
(`NoSwapPending` for a force-cancel whose target was already cleared, `SwapAlreadyPending` for a
force-propose whose slot was filled by something else in the meantime) — but a Solidity `revert`
unwinds every state change made earlier in the SAME call, so on that revert path the earlier
`delete` never actually took effect. There was no other way to clear a pending guardian action.
Concretely: guardians unanimously agree to force-cancel a stuck swap; before they call
`executeGuardianAction`, the signer independently (and perfectly legitimately) cancels the swap
themselves. The guardian action can now never execute, and — discovered only once rotation's own
cross-mechanism lock made the consequence concrete — it permanently blocks every future
`guardianProposeAction`/`proposeGuardianRotation` call (both correctly check
`pendingGuardianAction.active`), from an entirely ordinary race, not an attack.
`proposeKernelSwap` itself is unaffected (it was never gated on guardian-action state), so this
was "guardian-side governance permanently disabled," not a full brick, but still a real,
uncaught defect in code that had already been through a mutation-testing pass. **Mutation testing
checks that guards reject bad input; it does not check that legitimate recovery paths exist for
every reachable stuck state** — a real limit of the technique worth remembering, not just a
one-off miss.

Fixed with two small, low-risk, permissionless functions: `cancelPendingGuardianAction()` (the
actual fix — closes the liveness gap) and `cancelPendingGuardianRotation()` (added for parity/
usability, not required for correctness, since rotation's own cross-mechanism lock makes its
`executeGuardianRotation` preconditions unreachable in practice). Both simply clear pending state
and never advance anything, so — same reasoning as `executeGuardianAction`/
`refreshReputationSnapshot` — there is no manipulation surface in leaving them permissionless.
The exact bug scenario is now a permanent regression fixture, not just a documented claim:
`test_cancelPendingGuardianAction_RecoversFromSignerRaceThatWouldOtherwiseBrickGovernance` drives
the signer/guardian race end to end, confirms `guardianProposeAction`/`proposeGuardianRotation`
are genuinely stuck without the fix, then confirms `cancelPendingGuardianAction` restores normal
operation.

**What this does NOT close, disclosed and accepted, not solved:**
- **Guardian collusion or compromise at unanimity threshold.** An attacker controlling every
  current guardian key can rotate itself into a permanent, self-perpetuating set the same way any
  legitimate unanimous quorum could — rotation changes WHO is trusted, it cannot make the
  underlying trust model stronger than "the guardian keys are genuinely independent," the same
  caveat every guardian mechanism in this contract already carries.
- **No batch rotation.** One add XOR one remove per rotation cycle, by design — keeps each
  rotation's blast radius to exactly one state transition, matching this contract's standing
  single-pending-slot philosophy, at the cost of needing multiple full unanimous cycles to
  replace several guardians at once.
- **Initial guardian selection at registration time** remains SDK/CLI/dashboard scope, not
  contract scope — noted in the rotation proposal doc's own "Related, deferred" section and saved
  to project memory for whenever that registration wiring happens.

**Verification discipline applied:** mutation-tested three security-relevant guards, all caught,
all restored: the unanimity check in `executeGuardianRotation` (weakened to `guardianThreshold`
— caught by `test_executeGuardianRotationRevertsBelowUnanimity`); the threshold-breaking removal
check in `proposeGuardianRotation` (removed — caught by
`test_proposeGuardianRotationRemoval_RevertsWhenItWouldDropBelowThreshold`); the cross-mechanism
lock in `proposeKernelSwap` (removed — caught by `test_crossMechanismLock_HoldsInBothDirections`).

Gas measured directly from call traces. Addition path: `proposeGuardianRotation(true, guardian)`
56,231 (cold, includes duplicate/zero-address checks); `approveGuardianRotation` 47,377 first
guardian / 27,477 second / 27,477 third (unanimity — all three pay, same shape as §32's emergency
action); `executeGuardianRotation` 50,954 (array push). Removal path:
`proposeGuardianRotation(false, guardian)` 58,395; `approveGuardianRotation` 47,377 / 27,477 /
25,477; `executeGuardianRotation` 20,976 (swap-and-pop, cheaper than a push). The liveness fix:
`cancelPendingGuardianAction()` 965 (a single `delete`).

`IntegrityAccountV1ExperimentalTest` suite: 71 → 86 tests (+15: propose/approve/execute
validation for both addition and removal, the threshold boundary, the cross-mechanism lock in
both directions, full addition/removal lifecycles proving a newly-added guardian can immediately
act and a removed one immediately cannot, and the liveness-bug regression). Full repo suite:
295/295 (up from 280/280 before this slice).

**Not deployed anywhere.** Foundry-test-only, local, uncommitted at time of writing, same
standing rule as every prior Phase I slice — no push/commit/deploy without separate explicit
authorization.

## 34. Kernel-swap reentrancy guard — closes the reentrant-call half of §29's disclosed window, corrects an imprecise prior claim (2026-08-18)

*Current State:* per `docs/plans/2026-08-18-phase1-swap-reentrancy-guard-proposal.md`, a new
`bool public swapInProgress` is set `true` around `executeKernelSwap`'s uninstall/install pair and
checked in both `_execute` and a newly-added `_fallback` override, reverting `ReentrantDuringSwap`
unconditionally while a swap is mid-flight, regardless of what `_hook` transiently points at.

**A real correction to a claim this contract had carried since §29, found while implementing, not
assumed correct because it was already written down:** the account's own NatSpec (and
`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`) described the reentrancy risk as "a
hostile `newKernel.onInstall` that reenters `execute()`." This is imprecise — `execute()` is
`onlyEntryPointOrSelf`-gated by the base OZ contract, and a kernel contract's `onInstall`/
`onUninstall` callback has caller identity equal to its OWN address (neither `self` nor the entry
point) from the account's perspective, so it could never call `execute()` directly in the first
place; that path was never actually reachable as described. The GENUINELY reachable path is
`AccountERC7579.fallback(bytes calldata)`, which — unlike `execute()` — carries NO access
restriction at all and routes through the same `withHook`-wrapped `_fallback` internal function.
This is what the guard actually closes.

**A second honest nuance, disclosed rather than glossed over:** in THIS account's current
configuration, a reentrant fallback call fails closed either way, guard or not — the account never
installs a fallback-handler module (`TYPE_FALLBACK` isn't part of this experimental account's
model, only `TYPE_HOOK`), so `AccountERC7579._fallback` always reverts
`ERC7579MissingFallbackHandler` regardless. The guard's value is proven by the REVERT REASON
changing, not by success vs. failure: without the guard, a hostile kernel's own `preCheck` still
runs (self-mediated, attacker-controlled) before the call ultimately fails for the unrelated
missing-handler reason; with the guard, the call is rejected immediately, before `preCheck` is
ever invoked. Concretely closes a currently-latent risk that becomes concrete the moment this
account (or a descendant of it) ever legitimately installs a fallback handler — forward-looking
hardening, not a fix for an exploit reachable in the account's PRESENT configuration.

**Deliberately does NOT reorder or reimplement OZ's own `_installModule`/`_uninstallModule`** —
that was the rejected, more expensive Shape A in the proposal doc (forking a vendored security
contract's internal ordering for behavior this codebase doesn't own). The guard instead makes the
actual attacker-reachable harm — a reentrant call mediated by whichever kernel `_hook` happens to
point at mid-swap — revert unconditionally, independent of `_hook`'s value.

**What this does NOT close:** a non-reentrant observation of `_hook`'s transient mid-swap state
(reading, not calling back in) is unaffected and was never the risk this closes — see the
pre-existing `test_reentrancyDuringInstallAndUninstallObservesFreshApprovalsAndEmptyPending`,
which continues to pass unchanged. The broken-kernel brick scenario, guardian collusion at
unanimity, and every other disclosed §29/§32/§33 gap are untouched — orthogonal to reentrancy.

**Verification discipline applied:** mutation-tested the guard by removing it from `_fallback` and
re-running both new tests — caught: the revert selector observed changes from
`ReentrantDuringSwap` to `ERC7579MissingFallbackHandler`, concretely proving `preCheck` genuinely
runs (self-mediated) when the guard is absent, not merely that "some revert still happens either
way." Restored after confirming detection.

Gas measured directly, diffed against an identical pre-fix build on the same test (not assumed
unchanged): no observable increase in `executeKernelSwap`'s cost at call-trace granularity (the
two `SSTORE`s toggling `swapInProgress` true then back to false within the same transaction are
cheap enough not to register at this measurement resolution).

`IntegrityAccountV1ExperimentalTest` suite: 86 → 88 tests (+2:
`test_reentrantFallbackDuringInstallIsRejected`, `test_reentrantFallbackDuringUninstallIsRejected`),
both driving a real two-swap sequence with a `ReentrantFallbackKernel` fixture playing both the
new-kernel and old-kernel role, not a hypothetical. Full repo suite: 297/297 (up from 295/295
before this slice).

**Not deployed anywhere.** Foundry-test-only, local, uncommitted at time of writing, same
standing rule as every prior Phase I slice — no push/commit/deploy without separate explicit
authorization.

## 35. Guardian emergency funds-recovery sweep — a true kernel-swap rescue is architecturally impossible; this recovers funds instead (2026-08-18)

*Current State:* per `docs/plans/2026-08-18-phase1-broken-kernel-rescue-proposal.md`, this slice
set out to close §29's broken-kernel brick scenario the way the proposal doc originally sketched
— a guardian path that bypasses the outgoing kernel's `preCheck` to force a rescue swap through.
**That approach was investigated and found genuinely impossible to build at this architectural
layer, not merely difficult, before any code was written for it — surfaced and disclosed to the
user before proceeding, not discovered partway through and quietly worked around.**
`AccountERC7579Hooked`'s `_hook` storage is `private` to that base contract; its only two
mutation paths, `_installModule`/`_uninstallModule`, are unconditionally wrapped by the `withHook`
modifier IN THEIR OWN FUNCTION BODIES — there is no override point in a subclass that can reach
`_hook` without triggering `preCheck` on whatever is currently installed. A true rescue would
require forking and reimplementing `AccountERC7579Hooked` itself, the same class of undertaking
Shape A explicitly rejected at much smaller scale for the reentrancy guard (§34) — not pursued
here either, per explicit user decision after the tradeoff was explained plainly.

**What was built instead, with the user's explicit, informed sign-off:** a guardian-unanimous
emergency funds-recovery sweep — `proposeGuardianRescueSweep(address payable to, uint256 amount,
bool sweepFullBalance)` / `approveGuardianRescueSweep(uint256 expectedNonce)` /
`executeGuardianRescueSweep()` — that performs a raw low-level native-value transfer, **never
touching `_hook`, `_installModule`, `_uninstallModule`, `execute()`, `_execute`, or `withHook` at
all.** This sidesteps the architectural wall entirely rather than attempting to defeat it. The
account itself remains permanently unable to `execute()` after this — the sweep recovers FUNDS,
it does not repair the account. Proven against the exact scenario the normal rescue-swap machinery
cannot save, not just asserted:
`test_guardianRescueSweep_RecoversFundsFromAPermanentlyBrickedAccount` installs a real
`AlwaysRevertingKernel`, confirms `execute()` is bricked, confirms a normal
propose/approve/execute rescue-swap attempt still reverts on the broken `preCheck`, then confirms
the sweep succeeds and fully drains the account's balance to a guardian-chosen recipient — the
account remains bricked for `execute()` afterward, confirmed by a final assertion, not left
implicit.

**Two real design decisions, both explained in plain language and made explicitly by the user
before implementation, not defaulted:**

1. **A separate, independently configurable `rescueTimelockSeconds` immutable**, distinct from
   `moduleActionTimelockSeconds`, and — unlike every other timelock in this contract — deliberately
   permitted to be ZERO. Reasoning surfaced to the user, not assumed: an already-bricked account
   has no normal activity a delay could interfere with, so a delay costs nothing operationally, but
   different deployments (the user specifically named different market verticals) may have
   genuinely different risk tolerances for how long a bricked account's funds should sit
   unrecoverable before a sweep can fire. This reverses this slice's own first-draft
   recommendation (the original scoping doc suggested no timelock at all) after the user pushed
   back on the reasoning — a real instance of the advisor-reconciliation discipline this session
   has applied throughout: re-examine a recommendation when new information (here, a request for
   configurability) surfaces, rather than defending the original framing.
2. **The severity of the sweep power was surfaced explicitly, not softened, before the user
   authorized it.** Because no on-chain check can distinguish "genuinely, permanently broken" from
   "reverted on some past calls," this cannot be scoped to only-when-bricked — it is disclosed as a
   general guardian-unanimous power to drain the account's ENTIRE native balance to an address of
   the guardians' choosing, reachable at ANY time, not only during a genuine emergency. This is
   the first guardian mechanism in this contract that directly moves value rather than only
   affecting governance (who is in charge, which kernel is installed) — a materially larger blast
   radius than §31/§32/§33's mechanisms, named as such before building it. Accepted by the user as
   the same tradeoff real-world social-recovery wallets make for their own backup-key quorums.

**A third, smaller decision from the original scoping doc turned out to be moot, disclosed rather
than silently dropped:** the proposal asked whether a rescue should still attempt a best-effort,
try/catch notification to the broken kernel before removing it. The user chose "try, but ignore
failure" — but the final design (a value-transfer sweep that never touches the kernel/hook system
at all) has no interaction with the outgoing kernel whatsoever, so this decision does not apply to
what was actually built. Recorded here so the decision isn't misread as having been silently
reversed.

**What this does NOT close:** the account itself is never repaired — `execute()` remains
permanently bricked after a sweep, by construction, not as an oversight. Does not close guardian
collusion/compromise at unanimity (same standing caveat as every other guardian mechanism). Does
not add any ERC-20 or other token recovery — scoped to native value only, matching this
account/kernel pair's own existing budget model (native-value-only throughout). Does not change
`proposeKernelSwap`/`executeKernelSwap` at all — the sweep is a fully independent, parallel
mechanism, deliberately NOT added to the cross-mechanism lock §33 introduced (rotation vs.
kernel-swap vs. guardian-action), since the sweep never touches `_hook`/`pendingKernelSwap`/
guardian-set state and has no correctness interaction with any of them to guard against.

**Verification discipline applied:** mutation-tested three security-relevant guards, all caught,
all restored: the unanimity check (weakened to `guardianThreshold` — caught by
`test_executeGuardianRescueSweepRevertsBelowUnanimity`); the timelock check (removed — caught by
`test_executeGuardianRescueSweepRevertsBeforeTimelockElapses`); the explicit
exceeds-balance check (removed — caught by
`test_executeGuardianRescueSweepRevertsWhenPartialAmountExceedsBalance`, which surfaced a real,
minor finding worth recording: the raw `.call` would have failed regardless due to insufficient
balance, so this specific guard's actual value is a clearer, named revert reason rather than being
the only thing preventing an overdraft — the mutation still proves the guard does something real,
just not what a first read might assume).

Gas measured directly from call traces: `proposeGuardianRescueSweep` 94,600 (cold, full-balance
sweep target); `approveGuardianRescueSweep` 47,035 first guardian / 25,135 second / 27,135 third
(unanimity — all three pay, same shape as every other unanimous mechanism in this contract);
`executeGuardianRescueSweep` 40,614.

`IntegrityAccountV1ExperimentalTest` suite: 88 → 101 tests (+13: propose/approve/execute
validation, the partial-vs-full-balance distinction, the exceeds-balance boundary, the
cancel-and-repropose escape hatch, and the definitive brick-recovery end-to-end test). Full repo
suite: 297/297 → 310/310.

**Not deployed anywhere.** Foundry-test-only, local, uncommitted at time of writing, same
standing rule as every prior Phase I slice — no push/commit/deploy without separate explicit
authorization.

## 36. ZK circuit `chain_id`/`verifying_contract` binding, plus `prover.py` wired to the real circuit for the first time (2026-08-18/19)

**Closes:** the ZK-proof half of the cross-deployment replay gap §30 already closed for the
non-ZK BCC commitment object. Before this, a `submitZkAttestation` proof built against one
`ReputationRegistry`/`XibalbaAgentRegistry` deployment (e.g. a local anvil instance, or one
testnet fork) could be replayed verbatim against any other deployment sharing the same agent's
`agent_id_commitment` — nothing in the circuit tied a proof to where it would be submitted. The
user explicitly chose to bind **both** `chain_id` and `verifying_contract` (not chain_id alone),
matching §30's precedent.

**What changed, concretely:**
- `integrity-zkp/circuit/src/main.nr` (formerly `integrity-zkp/src/main.nr` — see workspace
  restructure below): `chain_id: pub Field` and `verifying_contract: pub Field` added as new
  public inputs, folded into the `intent_commitment` Pedersen hash alongside the existing
  `DOMAIN_INTENT, secret_key, intent_payload_hash, nonce` array. `agent_id_commitment` is
  unaffected (identity is deployment-independent by design — an agent's ZK identity doesn't
  change across chains, only its per-action intent proofs do). Address/chain-ID packing is
  `Field(uint256(value))` — lossless and injective, since both are well under the BN254 scalar
  field's ~254 bits (no truncation, unlike the SHA-256-to-Field packing elsewhere in this
  circuit, which IS lossy and disclosed as such).
- 6 `#[test]` functions now (was 4): the existing valid/wrong-secret/wrong-payload/zero-nonce
  cases updated for the new ABI, plus two new `should_fail` cases
  (`test_invalid_binding_wrong_chain_id`, `test_invalid_binding_wrong_verifying_contract`)
  proving the new binding actually rejects a mismatched chain/deployment.
- `contracts/src/oracle/UltraPlonkVerifier.sol` regenerated end-to-end via the real
  `make build` pipeline (`nargo` 1.0.0-beta.22, `bb` 5.0.0-nightly.20260522 — pinned versions
  per `docs/INTERFACE_CONTRACT.md` §1, not assumed): `NUMBER_OF_PUBLIC_INPUTS` 11 → 13 (5 real
  public inputs + 8 UltraHonk pairing-point words, confirmed both by the generated constant and
  independently by `public_inputs.bin` growing from 96 to 160 bytes = 5 × 32), new `VK_HASH`.
  The manual patch step applied to every regenerated copy (add `("memory-safe")` to 5 `assembly`
  blocks, rename `HonkVerifier` → `UltraPlonkVerifier`, add the `IZkVerifier` import) was
  extracted by diffing the pre-change generated/deployed copies against each other first, not
  reconstructed from memory.
- `contracts/test/fixtures/ultraplonk/{proof.bin,public_inputs.bin}` and
  `contracts/test/UltraPlonkVerifier.t.sol`'s hardcoded length/keccak assertions and the
  hand-unrolled `bytes32[]` assembly copy (3 words → 5) all regenerated/updated from a real,
  freshly-proven fixture — not hand-edited numbers. All 4 verifier tests (valid/tampered-proof/
  tampered-input/malformed) pass against the real 5-input circuit.
- **`integrity-zkp` restructured into a two-member Nargo workspace** (`circuit/` = the real
  proving circuit, `tools/commitment_calc/` = a new small sibling package) — required because
  `integrity-sdk`'s `prover.py` needs `agent_id_commitment`/`intent_commitment` *before* it can
  write `Prover.toml` for the real circuit (that circuit takes both as public inputs to be
  checked, not computed as outputs), and this repo has no Python Pedersen-hash implementation
  anywhere. Reimplementing Barretenberg's Pedersen hash from scratch in Python was rejected as
  exactly the "two hashes, both look canonical" divergence risk `circuit/src/main.nr`'s own
  docstring warns against; `commitment_calc` instead runs the *identical* hash computation
  through the real Noir/Barretenberg toolchain (`nargo execute`'s return-value stdout line,
  `Circuit output: (0x.., 0x..)`), and its own `#[test]` pins that output against
  `circuit/Prover.toml`'s checked-in fixture. **Precisely, not overstated:** this test catches
  drift in `commitment_calc`'s *own* logic (e.g. someone reorders its array without updating the
  pinned constants) — a Noir `#[test]` cannot read another package's `Prover.toml` or call into
  another package's functions, so it does NOT by itself catch `circuit/src/main.nr`'s hash shape
  changing out from under it. What does catch that: `make build`'s `nargo execute` step against
  `circuit/`'s own checked-in `Prover.toml` fails if that fixture no longer satisfies the
  circuit's constraints — but only once `circuit/Prover.toml` is itself updated to match a hash
  change, which is a same-commit discipline (documented in README.md "Fixture values"), not a
  single CI-enforced invariant spanning both packages. Confirmed empirically (not assumed) that
  both workspace members' build output lands in one shared `<workspace_root>/target/`, which is
  what lets `prover.py` treat the workspace root as its one entry point.
- **`integrity-sdk/integrity_sdk/prover.py` rewritten to actually drive the real circuit —
  this had never happened before this session.** It previously pointed at
  `circuits/poc_commitment/`, a smaller stand-in circuit with a different ABI, and — per a
  background survey run before implementation started — was not called from anywhere else in
  the repo (no call sites, no tests). Both facts are now different: `generate_proof` shells out
  to the real `integrity-zkp` workspace (`circuit` + `commitment_calc`), and
  `integrity-sdk/tests/unit/test_prover.py` is new, real, end-to-end coverage (6 tests, no
  mocking of `nargo`/`bb`, skipped rather than faked when the toolchain isn't on PATH) — the
  first tests this module has ever had. Also fixed in the same pass: the module's
  `DEFAULT_VERIFIER_TARGET` was `"noir-recursive-no-zk"`, which uses a different internal hash
  function than the `"evm"` target `contracts/src/oracle/UltraPlonkVerifier.sol` is generated
  against — a proof built against the wrong target verifies fine locally via `bb verify` (same
  wrong vk) but would never verify on-chain. This was a latent bug in unexercised code, not
  something that had produced a bad proof in production, but is exactly the class of error that
  only surfaces once code goes from "written" to "actually run."
- `circuits/poc_commitment/` itself is now fully unreferenced by any code in this repo (dead,
  not deleted — left in place as a historical artifact per CLAUDE.md's existing framing of it as
  "an earlier placeholder"; `prover.py`'s docstring says plainly that nothing points at it
  anymore rather than leaving an orphaned circuit undisclosed).
- `.gitignore` fix (found, not introduced, by this work): a blanket `Prover.toml` rule had
  silently kept `integrity-zkp`'s real, checked-in fixture untracked by git this whole time,
  contradicting the package's own README ("The checked-in `Prover.toml` fixture..."). Added a
  scoped `!integrity-zkp/circuit/Prover.toml` exception rather than editing the README's claim
  to match the bug.
- `.github/workflows/ci.yml`'s `zkp` job updated from `nargo test` to `nargo test --workspace` —
  otherwise CI would silently stop running `commitment_calc`'s test entirely after the workspace
  restructure (nargo's un-flagged default only builds/tests the workspace's `default-member`).
  Stale `integrity-zkp/src/main.nr` path references (now `circuit/src/main.nr`) also corrected in
  `docs/INTERFACE_CONTRACT.md` §5 (which also had its "chain_id not yet bound into the ZK
  circuit" residual-gap note flipped to reflect that it's now closed) and `CLAUDE.md`'s "ZK proof
  pipeline" section — found by grepping the whole repo for the old path after the restructure,
  not left for the next session to discover as drift.

**What this does NOT close:**
- Does not change `integrity-oracle`'s verification path at all — the oracle still needs to
  independently recompute or validate `intent_commitment` against the BCC record it has on file
  for a given (agent, nonce) pair; this slice only changed what the circuit and `prover.py`
  produce, not what the oracle checks it against. Not in scope for this slice. **Verified, not
  assumed:** `integrity-oracle/backend/src/zk.rs`/`handlers.rs` treat `proof`/`public_inputs` as
  opaque byte blobs passed through to `bb verify` — no hardcoded element count anywhere in the
  oracle crate — and the oracle's own ZK test fixture (`backend/tests/fixtures/zk_smoke/`) is a
  separate, smaller Noir circuit unaffected by this circuit's ABI change. Full oracle workspace
  suite re-run after this change: 144/144 passed (126 backend + 18 scoring-core), zero
  regressions.
- Does not add a `VerifierRegistry` migration mechanism. Deliberately: nothing is deployed
  anywhere against the old (3-public-input) circuit shape, and no real proofs exist against it
  (confirmed via deployments-file inspection before this work started), so there is no live
  population to migrate. If/when this is deployed, register the new verifier as a new version;
  do not build migration machinery for zero live agents.
- Does not close the disclosed `secret_key`-is-KDF'd-not-full-Ed25519 scope limitation
  (unchanged, orthogonal to this binding) or the SHA-256-truncation lossy-packing disclosure
  (unchanged, pre-existing, orthogonal).
- Does not touch `integrity-cli`, which has no ZK code path at all (confirmed via survey: its
  one `zk`-adjacent string match is an unrelated mocked JSON field in a test).

**Verification discipline applied:** every circuit test re-run after each edit (`nargo test
--workspace`, 6/6 then re-confirmed after the workspace restructure); full `make build` pipeline
actually executed against the real toolchain (not assumed) — `nargo compile` → `execute` →
`bb write_vk` → `bb prove` → `bb verify` (real proof, real verification, both succeeded) →
`bb write_solidity_verifier`; the regenerated verifier's manual-patch transformation was
extracted by diffing the *pre-change* generated/deployed file pair, then re-diffed against the
freshly patched output to confirm the exact same transformation applied cleanly; `forge build` +
full `forge test` re-run after the verifier/fixture swap (310/310, zero regressions); the new
`integrity-sdk` prover tests actually generate and verify real UltraHonk proofs end-to-end
(not mocked) and include a negative control (tampered proof byte → `verify_proof` returns
`False`) and a binding-distinctness check (same keypair/payload, different `chain_id` →
different `intent_commitment`, same `agent_id_commitment`); full `integrity-sdk` suite re-run
(270 passed, 3 skipped, zero regressions).

**Not deployed anywhere.** Every artifact above (circuit, verifier, fixtures, `prover.py`) is
local and uncommitted at time of writing — no push/commit/deploy without separate explicit
authorization, same standing rule as every prior Phase I slice.

## 37. Epoch/timelock deployment invariant — Option B (fail-open for non-snapshotting kernels), (2026-08-19)

**Closes:** the deployment invariant both `IntegrityAccountV1Experimental` and
`IntegrityKernelV1Experimental` independently documented but neither enforced — that a kernel's
`epochLengthSeconds` must be `>= moduleActionTimelockSeconds` on the account, or a fully-vested
kernel swap can revert `SnapshotStale` for a reason unrelated to reputation, and a freshly-
installed replacement kernel can be stale-on-arrival, rejecting the account's first post-swap
`execute()` call. Previously "a deploy-time discipline, not a code-level guarantee" (both
contracts' own words); now code-level, at every point a mismatched kernel could actually enter
the account, not just genesis.

**The decision, made explicitly, not defaulted:** the proposal doc named a real fork —
Option A (require every future kernel to implement `epochLengthSeconds()`, fail closed, but
permanently narrows what kinds of kernels this account can ever hold) vs. Option B (probe via
`try`/`catch`, skip the check entirely for a kernel with no epoch concept — weaker, since
Solidity's `try`/`catch` cannot distinguish "doesn't implement this" from "implements it but is
currently reverting," but preserves generality for a legitimate future non-snapshotting kernel).
Explained in plain language, then asked directly rather than defaulted to the proposal's own
recommendation. The user chose **Option B**, matching the recommendation.

**What changed, concretely:**
- `IEpochSnapshotting` — a minimal marker interface (`epochLengthSeconds() external view returns
  (uint256)`) — added to `IntegrityAccountV1Experimental.sol`. Deliberately not a requirement
  every hook module implements.
- `_checkEpochCompatibility(address newKernel)` — a private helper that probes
  `newKernel.epochLengthSeconds()` via `try`/`catch` and reverts `EpochTooShortForTimelock` if
  the kernel implements it and its value is less than `moduleActionTimelockSeconds`; silently
  skips the check (does nothing) if the call reverts or the target has no such function.
- Called from three places: the constructor (genesis kernel — closes the case a constructor-only
  check would have missed everything BUT), `proposeKernelSwap` (the signer's normal path), and
  `guardianProposeAction`'s force-propose branch (the guardian emergency path from §32) — a
  constructor-only check would have left every subsequently swapped-in kernel unchecked, which
  defeats the point given `executeKernelSwap` exists specifically to install a *different* kernel
  later. All three probe the SAME helper, not three independent copies.
- Both contracts' NatSpec corrected precisely, not just extended: the "deploy-time discipline,
  not a code-level guarantee" line is now false for a kernel that implements the selector, and
  still true for one that doesn't — both cases stated explicitly rather than picking one to be
  accurate about.

**A significant discovery made mid-implementation, not anticipated in the scoping doc:** the
entire existing 101-test suite's shared `setUp()` fixture deliberately constructed its default
account/kernel pair with `MODULE_ACTION_TIMELOCK = 3 days` and `REPUTATION_EPOCH_LENGTH = 1 days`
— i.e., the EXACT invariant-violating configuration this feature exists to reject — because
several existing tests use that mismatch to demonstrate the pre-existing `SnapshotStale`
interaction bug this proposal's own "Why this slice" section cites as the motivation. Once the
constructor-time check landed, this fixture would have made `setUp()` itself revert on every
single test in the file. Resolved by raising `REPUTATION_EPOCH_LENGTH` to `3 days` (matching
`MODULE_ACTION_TIMELOCK` — the shared fixture is now a compliant pair) and auditing every test
that depended on the old mismatch: all of their `kernel.refreshReputationSnapshot()` calls turned
out to already sit at an exact timestamp boundary (kept as disclosed defense-in-depth rather than
removed, verified empirically, not by hand-checking the arithmetic, by actually removing them
first and confirming nothing failed, then restoring them with corrected comments rather than
leaving the file in a "probably fine" state); comments that specifically claimed "the epoch is
shorter than the timelock" as their rationale were rewritten to state the accurate current reason
(mostly: pulling a freshly-updated score into the cache, not staleness) rather than left
describing a configuration that no longer exists. Zero test logic was weakened to make this
land — every one of the 101 pre-existing tests in this file still passes unchanged in behavior,
only the shared constant and a handful of comments changed.
`test_quorumGatheringCanStaleTheSnapshotBetweenApprovals` (the proposal's own named regression to
preserve) needed no changes at all — it demonstrates staleness caused by elapsed
*quorum-gathering* time between guardian approvals, which is independent of the epoch/timelock
relationship and remains fully reachable regardless of the two values.

**New fixture, new tests:** `NonSnapshottingKernel` — a fully-conforming, working hook module
(`isModuleType` returns true for `MODULE_TYPE_HOOK`, `preCheck`/`postCheck`/`onInstall`/
`onUninstall` all succeed) that deliberately does NOT implement `epochLengthSeconds()` at all —
representing a legitimate future kernel with no reputation-epoch concept. 4 new tests: genesis
construction reverts for a mismatched pair; `proposeKernelSwap` reverts for a mismatched
`newKernel`; `guardianProposeAction`'s force-propose branch reverts identically; and a full
propose→approve→execute round trip against `NonSnapshottingKernel` succeeds end-to-end — Option
B's fail-open case proven as an explicit, asserted test outcome, not left as an accident nobody
checked.

**What this does NOT close:**
- Retroactive enforcement against an already-installed, already-violating kernel — out of scope
  by design (per the proposal doc): this only prevents *installing* a mismatched pair going
  forward.
- The Option B fail-open gap itself — disclosed, not closed: a kernel that reverts on the
  `epochLengthSeconds()` probe for a transient, unrelated reason (rather than genuinely not
  implementing it) silently skips the check rather than failing closed. Solidity's `try`/`catch`
  cannot distinguish the two cases.
- Any change to `epochLengthSeconds`' own value, `MAX_EPOCH_LENGTH_SECONDS`, or any guardian
  mechanism (§32/§33/§34/§35) — fully independent of those; this item had no dependency chain.

**Verification discipline applied:** mutation-tested `_checkEpochCompatibility`'s core comparison
(neutralized with `false && ...`, leaving the `try`/`catch` structure intact) — all three revert
tests (`test_deployingMismatchedGenesisPairRevertsAtConstruction`,
`test_proposeKernelSwapRevertsWhenNewKernelEpochShorterThanTimelock`,
`test_guardianProposeActionRevertsWhenNewKernelEpochShorterThanTimelock`) failed with distinct,
meaningful failures (a different revert reason or "did not revert as expected"), confirming the
guard does real work; restored and re-confirmed 105/105. `IntegrityAccountV1ExperimentalTest`
suite: 101 → 105 tests (+4). Full repo suite: 310/310 → 314/314.

**Not deployed anywhere.** Foundry-test-only, local, uncommitted at time of writing, same
standing rule as every prior Phase I slice — no push/commit/deploy without separate explicit
authorization.

This closes the sixth and final item of the six originally scoped. Item 7 (external audit /
deployment) remains a gate, not actionable work — nothing in this repo's own discipline
substitutes for it.

## 38. `bcc.rego` had no "financial" risk class — an unrecognized intent authorized by matching nothing, not by policy (2026-08-19)

**Context:** found while building `xibalba-quant`, a real autonomous trading agent meant to
stress-test this protocol's own mediation pipeline (separate initiative, tracked outside this
repo — see `~/.claude/plans/velvet-gathering-rivest.md`). Before building the trade executor,
its BCC (Behavioral Commitment Chain) commitments were checked against the live policy, and it
turned out `bcc_middleware/policies/bcc.rego` had zero rules for any trading/financial
`intent_type` — exactly the same failure `bcc.rego` §3b already names and fixed once before for
Claude Code's own tool calls (that section's own comment: *"792 logged decisions... authorized
715, denied 0... A gate that cannot express an opinion is not a gate"*).

**Closed:** added `"financial"` to `high_risk_tool_classes` (§3b's existing mechanism —
`agent_tool_prefixes := {"claude_tool", "hermes_tool"}`), so an intent shaped
`hermes_tool:<venue>_trade:financial` is now genuinely evaluated: it requires
`verification_tier >= 1` (same threshold as the existing destructive/credential/chain_write
classes — kept there deliberately, not raised, per the CEILING NOTE already in this file: Tier
2/3 verification isn't real yet, so a higher threshold would be an unreachable no-op dressed up
as a real policy decision) and, via `_is_agent_tool`, automatically inherits the AOS
observability requirement (real `trace_id`/`span_id`/`intent_rationale` >= 15 chars, no
exceptions). 5 new OPA tests in `bcc_test.rego`, including a regression anchor that pins the
OLD failure mode (an unclassified two-segment `hermes_tool:coinbase_trade` label still passes
through matching nothing — proving the gap was real, not assumed). Mutation-tested: removing
`"financial"` from the set makes `test_financial_intent_denied_for_unverifiable_agent` fail with
a real, distinct failure. `opa test policies/ -v`: 43 → 48 passing.

**What this does NOT check, stated plainly (per this file's own header note):** the BCC
commitment schema never carries the actual trade payload across the wire pre-execution — only
`intended_state_hash` does — so this policy cannot and does not validate venue, asset, size, or
side. That validation is the trade-executor's own job before it ever builds a commitment. This
rule only gates identity verifiability and the observability/rationale requirement, same as
every other class in this section.

**A second, separate finding from verifying this against the real running stack, not just the
OPA test suite:** the `opa` container (`docker-compose.yml`'s `opa` service) does **not
hot-reload** its policy files. It bind-mounts `bcc_middleware/policies/` but loads them once at
container start (`opa run --server ... policies/`, no `-w`/`--watch` flag) — editing the `.rego`
files on disk has no effect on a running container until it's restarted. Confirmed by querying
OPA's own `GET /v1/policies` admin endpoint directly: it kept serving the pre-edit policy
(`"financial" in raw` → `False`) for several manual test calls after the file was already
saved, which briefly produced a false-positive `authorized: true` result during verification —
caught by cross-checking the admin endpoint rather than trusting the HTTP verdict alone, not
shipped as a false "it works." `docker compose restart opa` picks up the change. Not fixed here
(no code change needed, this is expected behavior for a file-loaded OPA server) — but worth
knowing for anyone editing this policy locally: **restart `opa` after every `.rego` edit, or the
change silently doesn't apply**, and don't trust a single manual verdict without also confirming
via `/v1/policies` that the running server actually has the edit loaded.

**Also found and fixed in the same pass, unrelated to the policy itself:** `xibalba-cortex`'s
own venv (`/home/xibalba/Projects/xibalba-cortex/.venv`) had a stale, non-editable, frozen copy
of `integrity-sdk` installed in `site-packages` despite `xibalba-cortex/pyproject.toml`
declaring it as a `path` dependency (which should track the live local source) — meaning it
predated this session's own `chain_id`/`verifying_contract` binding work on
`build_bcc_commitment()` and would have raised `TypeError: unexpected keyword argument
'chain_id'` for any real caller. `uv sync` alone did not detect/fix this (the resolved lock
apparently didn't consider the path dependency stale); fixed with an explicit `uv pip install
--reinstall --no-deps -e ../integrity-core/integrity-sdk`, confirmed editable and current
afterward. Not integrity-core's own bug, but directly blocked integrity-core's own protocol
change from reaching a real downstream consumer, so recorded here rather than left silently
discovered-and-forgotten.

**Not deployed anywhere beyond this local dev stack.** Local Docker Compose only, not committed
at time of writing.

## 39. Two real bugs found registering `xibalba-quant` for real on Base Sepolia (2026-08-19)

**Context:** `xibalba-quant`'s DID already had real, live on-chain primitives deployed from
2026-07-29 (a prior, undocumented session/attempt — not part of any work tracked in this repo's
history) but was never fully registered with the oracle. Completing that registration, using the
same funded operator key already used for the Health/Shield agent, surfaced two real, distinct
bugs, neither hypothetical.

* **`docker-compose.yml`'s Docker-facing RPC endpoint was pointed at an unhealthy public RPC.**
  `.env`'s `DOCKER_RPC_URL` (consumed by `oracle-backend` and `bcc-middleware`) was
  `https://sepolia.base.org`, while the host-facing `RPC_URL` (used by `integrity-sdk` scripts
  run directly, outside Docker) was already correctly set to
  `https://base-sepolia-rpc.publicnode.com`. The former was failing with `"no backend is
  currently healthy to serve traffic"` — confirmed directly in `oracle-backend`'s own logs, not
  inferred — causing every `resolveDID`-dependent oracle read (including the registration
  endpoint) to silently degrade. **Fixed:** `DOCKER_RPC_URL` now matches the working
  `RPC_URL`. This was a live infra misconfiguration, not a code bug — flagged here because it
  would have equally broken any other agent's real registration or the periodic reputation-sync
  loop against Base Sepolia, not just this one.
* **`register_agent()`'s `resolve_did` short-circuit can skip genesis memory anchoring
  entirely, leaving a real but oracle-unregistrable agent.** The short-circuit at the top of
  `register_agent()` (added for the orphaned-pair problem §28/§18 already document) treats "the
  agent's primitives are already deployed on-chain" as "registration already fully completed,"
  and returns straight to the oracle POST — it does NOT re-check `StateAnchor.latestRoot`
  before doing so, unlike the main (non-short-circuited) path, which the code's own comment
  says explicitly should not be trusted to be automatic ("Idempotence: NOT guaranteed solely by
  step 0's resolve_did short-circuit, despite what this comment used to claim"). This is exactly
  the gap that comment already warns about, just not closed for the short-circuit branch itself.
  `xibalba-quant`'s on-chain identity was a live instance of it: primitives fully deployed, zero
  genesis root, oracle correctly refusing with `400 MemoryNotInitialized` on every registration
  attempt. **Worked around manually for this one agent** (called `chain.anchor_genesis_root()`
  directly, confirmed the root changed from `0x00...00` to a real non-zero value via
  `state_anchor_latest_root`, then re-ran `register_agent()`, which succeeded). **Not fixed in
  the SDK itself** — the short-circuit branch (`registration.py` lines ~214-243) should check
  `state_anchor_latest_root` and anchor if zero, the same way the main path already does, before
  this is considered closed. Left open rather than patched under time pressure while a live
  registration was blocked on it; a real fix belongs in its own reviewed change, not folded
  silently into an unrelated trading-agent registration.

**Verified for real, not assumed:** `GET /v1/agent/<did>` now returns `verification_tier: 1`,
`oracle_registered: true`, `has_ed25519_key: true`, `has_eth_address: true`; `GET /v1/agent/<did>
/ais` returns a real (zero-activity) score. A separate, pre-existing cosmetic issue noticed while
verifying: the returned `did_document.verificationMethod` array contains the same `#evm-1` EVM
verification method duplicated 5 times — likely a byproduct of the same partial-registration
history above (repeated `attach_evm_account` calls across multiple incomplete attempts) — not
investigated further here, noted for whoever picks up the short-circuit fix above.

**Not committed.** Both the `.env` fix and this write-up are local, uncommitted changes at time
of writing.

## 40. Phase I kernel slice promoted from `...V1Experimental` to production names — rename only, no logic change (2026-08-24)

*Current State:* per `docs/plans/2026-08-24-phase1-promotion-decision-proposal.md` (Option A,
authorized), `contracts/src/kernel/IntegrityAccountV1Experimental.sol` and
`IntegrityKernelV1Experimental.sol` are renamed to `IntegrityAccount.sol` and `IntegrityKernel.sol`
respectively (contract names, file names, and internal NatSpec cross-references — every
occurrence verified by grep before and after, none remaining). `contracts/test/
IntegrityAccountV1Experimental.t.sol` → `IntegrityAccount.t.sol`, its 146 references to the old
names mechanically replaced. **Zero logic change**: `git mv` + `sed` only, no lines of behavior
touched. Verified, not assumed: `Experimental` never appeared in any `error`/`event` identifier in
either contract (only in contract names and comments), so this is not an ABI-shape change; `forge
build` compiles clean (warnings only, pre-existing lint categories unrelated to this change); full
repo suite re-run after the rename: 314/314 passing, zero regressions, `IntegrityAccountTest`
(renamed from `IntegrityAccountV1ExperimentalTest`) itself at 105/105.

**What this does NOT change:** the contracts remain exactly as un-deployed, un-audited, and
un-formally-verified as before — promotion is a naming decision only, made because the
2026-08-24 Phase I audit found the artifact had outgrown its original "tracer bullet" framing
(six governance-hardening slices and a ZK-circuit binding since the name was chosen) with no
technical defect motivating a rebuild under the production names instead. See the proposal doc
for the full go/no-go reasoning, including why a from-scratch rebuild (Option B) was declined:
it would have discarded 314 tests and six rounds of Devil's Advocate review with no named
architectural justification, which is exactly the kind of divergence-prone path this repo's own
history (§21 above) warns against.

**Historical documents intentionally NOT rewritten:** `HANDOFF.md`, `CLAUDE_HANDOFF_2026-08-19.md`,
`docs/design/phase1-tracer-bullet-slice-2026-08-17.md`, and every dated `docs/plans/2026-08-1[78]-
phase1-*.md` proposal still refer to `IntegrityAccountV1Experimental`/`IntegrityKernelV1Experimental`
— correct as dated logs of what was true when written. Only current-state documents (this file,
README.md) were updated forward. Anyone grepping for the old names in a historical doc should not
read that as the rename having failed to land — check `contracts/src/kernel/` directly.

**What remains open for Phase I, restated from the 2026-08-24 audit — unaffected by this rename
either way:** no Base Sepolia (or any) deployment, no external/independent audit, no
machine-checked invariance argument, and the still-undecided general-value-conservation scope
question (only native ETH is conserved today; ERC-20/721/arbitrary calldata inside a zero-ETH
call remains unconstrained).

## 41. Declared multi-asset value conservation built, tested, and found genuinely over the Table 4 gas budget — real finding, not resolved (2026-08-24)

*Current State:* per `docs/plans/2026-08-24-phase1-declared-asset-conservation-proposal.md`
(authorized, "full scoped slice at once"), `IntegrityKernel` gained a single additional declared
conserved asset — an immutable `trackedToken` (ERC-20, `address(0)` disables the feature
entirely, preserving prior behavior byte-for-byte), with its own `tokenPerOpBudgetWei`/
`tokenCumulativeBudgetWei` two-tier budget, checked exactly like the existing native-ETH budget:
a live `balanceOf` snapshot in `preCheck`, a live re-read and conjunctive revert in `postCheck`.
7 new Foundry tests (in-budget transfer succeeds, per-op and cumulative reverts at their exact
boundaries, native/token budget independence in both directions, a zero-token-budget constructor
guard, the disabled-path pin), all passing; the two new guard checks (per-op, cumulative)
mutation-tested — removing either makes its own test fail differently (wrongly succeeds), both
restored before landing. Full repo suite: 321/321 (up from 314 at the promotion commit), zero
regressions to any pre-existing test.

**The gas checkpoint the proposal named as a precondition was run for real, and the finding is
genuinely negative — reported, not absorbed.** `preCheck` with `trackedToken` enabled measures
**~41,056 gas** against a genuinely COLD token-balance read — over the whitepaper's own Table 4
`<=40k` ceiling. This is real, not an estimate: `test_preCheckGasExceedsPaperTable4BudgetWithTrackedTokenLiveRead`
asserts it directly (`>40_000` and `<45_000`, a regression window matching the discipline the
earlier three-reference-adapter over-budget finding used before ITS resolution). **A first
measurement (~25,829 gas) looked like it fit — that number was wrong, an artifact of minting the
tracked token inside the same test-body transaction as the `preCheck` call, which left the
balance slot warm.** Restructured the test fixture (`tokenAccount`/`tokenKernel`/`token` now
deployed in `setUp`, mirroring exactly how `reputation`'s own storage is cold-read from every
test body) to get the representative, production-equivalent measurement before trusting any
number — the corrected, cold figure is the one reported above. This is exactly the risk the
proposal doc's own dependency-inventory section named before any Solidity existed: value
conservation is a **hard invariant** per the whitepaper's own §4.7.1 ("never enter grace...
fail-closed in every state"), so this slice cannot reuse the epoch-snapshotting cache that
rescued the reputation/assurance-tier checks from their own, earlier crossing — caching a
conserved-quantity balance would silently misstate the invariant itself, not merely widen a
staleness window on a soft precondition.

**No mitigation has been attempted within this slice's scope.** Both the kernel's contract-level
NatSpec and the guarantee-statement doc comment are updated to state the crossing plainly rather
than imply Table 4 compliance. Options for whoever picks this up next, none chosen here: (a)
accept the crossing as a disclosed Phase I boundary (ERC-4337 bundler simulation limits are a
policy question, not a hard on-chain revert, so an over-budget `preCheck` degrades UserOp
inclusion economics rather than breaking correctness — a real cost, not a safety failure); (b)
attempt a to-be-scoped mitigation (e.g., a keeper-refreshed cache with a MUCH shorter staleness
window than reputation's, if a bounded-staleness value-conservation design can be shown not to
violate §4.7.1's own hard-invariant framing — non-trivial, not attempted here); (c) drop the
tracked-token feature and treat native-ETH-only as Phase I's permanent scope after all (reverts
this slice, does not delete evidence — `IntegrityKernel`'s git history keeps this work available).

**Decision (2026-08-24): option (a), accepted as a disclosed, permanent Phase I boundary.** The
crossing is not being mitigated or reverted — `IntegrityKernel` keeps the `trackedToken` feature
exactly as built and measured above. Reasoning, stated plainly rather than left implicit: this
kernel is still Foundry-test-only and un-deployed (workstream 4, testnet deployment, remains
separately gated), so no live UserOp is affected today; the crossing's actual cost is bundler
simulation/inclusion economics under real ERC-4337 gas limits, not an on-chain correctness or
safety failure (the value-conservation guarantee itself holds regardless of `preCheck`'s exact gas
figure — a call either passes both budget checks or reverts, correctly, at 41k gas same as it
would at 33k). Matches the same "document it, don't silently absorb it" posture this repo already
applied to the earlier three-reference-adapter crossing before that one *was* resolved by
caching — the difference here is that no equivalent resolution is available (§4.7.1's hard-
invariant framing forecloses it), so this crossing is accepted rather than chased. Whoever
proceeds to workstream 3 (formal verification) or workstream 5 (external audit) should treat
this Table 4 crossing as a known, disclosed, in-scope finding to hand the auditor — not a
regression to fix first. `IntegrityKernel`'s NatSpec is not being softened to reflect
"acceptance"; the crossing stays stated as a crossing, only the decision about what to do with it
is now closed.

## 42. Halmos symbolic-verification harness built — real kernel installed via governance swap, two real cheatcode gaps found and worked around (2026-08-24)

*Current State:* per `docs/plans/2026-08-24-phase1-formal-verification-proposal.md` (workstream
3: machine-checked invariance argument, Table 8's Phase I gate) and its two follow-up scoping
docs, a working Halmos harness now exists at `contracts/test/halmos/KernelSwapHarness.t.sol`,
runnable reproducibly via `make verify-kernel`. This closes the dependency-inventory and
harness-design steps; the four target properties (native-ETH budget containment, declared-token
budget containment, reputation/assurance-tier fail-closed gating, reentrancy-guard soundness) are
the next, separately-scoped step, not attempted in this entry.

**Two of the three considered address-prediction approaches were tried and found genuinely
infeasible, not just inconvenient — real findings, reported rather than routed around:**
- **CREATE-nonce prediction:** Halmos 0.3.3 does not model plain `CREATE` addresses via real
  RLP/nonce semantics at all — confirmed by reading `halmos/sevm.py`'s `create()`, which assigns
  addresses from an internal synthetic counter unrelated to any real-world-computable formula. A
  hand-written RLP predictor, cross-validated correct against `vm.computeCreateAddress` and a real
  deployment under plain `forge test` (nonces 0–20), failed unconditionally under Halmos.
- **CREATE2-salt prediction:** Halmos's CREATE2 addressing genuinely DOES match the standard
  formula (verified directly, unbounded, symbolic salt) — the tool was never the problem here.
  The problem is structural and tool-independent: `IntegrityKernel` and `IntegrityAccount` each
  need the other's real final address embedded in their own constructor args, so both contracts'
  CREATE2 addresses depend on each other through a one-way hash — an unsolvable two-variable fixed
  point, true on real Ethereum as much as under Halmos, not something any salt choice fixes.

**The working approach (placeholder-genesis-kernel, then a real governance swap) needs no address
prediction at all**, which is exactly why it sidesteps both dead ends above. A trivial
`AlwaysPassingPlaceholderKernel` (no `boundAccount` restriction) is genesis-installed on a real,
unmodified `IntegrityAccount`; the real `IntegrityKernel` — bound to `address(account)`, already
concrete by the time it's deployed, never predicted — is installed for real through the account's
actual `proposeKernelSwap` → two guardian `approveKernelSwap` calls → `vm.warp` past the timelock
→ `executeKernelSwap` path, completely unmodified production code. Two `check_` functions, both
passing **unbounded** (Halmos's own `bounds: []`, meaning proven for literally all reachable
symbolic values, not a sampled subset) in under 1.1s combined.

**Two more real, disclosed Halmos/cheatcode compatibility gaps found and fixed, each
cross-validated against plain `forge test` before being trusted under Halmos:**
- `stdStorage`'s `checked_write` (the concrete test suite's own technique for writing
  `AgentScore.zkBoostExpiry`, no other setter exists short of a real ZK attestation) depends on
  `vm.record()`, confirmed unsupported. Fixed by writing the storage slot directly: `forge inspect
  ReputationRegistry storage-layout` gives `scores` at slot 1 (its OZ v5 `Initializable`/
  `AccessControlUpgradeable` bases use ERC-7201 namespaced storage, not the linear slot space, so
  there's no inherited-storage offset to account for); a `mapping(address => AgentScore)` entry's
  base slot is `keccak256(abi.encode(subject, uint256(1)))`, and `zkBoostExpiry` is the struct's
  third `uint256` field, so `+2`. Verified against the real `scores(address)` getter under
  concrete `forge test`, not asserted blind.
- `vm.prank`/`vm.warp`/`vm.store`/`vm.load` are all confirmed **supported** under Halmos, each
  checked directly rather than assumed — this is what makes the governance-swap sequence and the
  manual storage write both viable.
- Unrelated build-config gap: Halmos requires `forge build --ast`; without it every contract's
  artifact is silently skipped (`KeyError: 'ast'`) rather than erroring, which reads exactly like
  "no tests exist" if not caught. `Makefile`'s `verify-kernel` target always passes it.

**Toolchain:** Halmos 0.3.3, pinned in `docs/INTERFACE_CONTRACT.md`, isolated in
`contracts/.venv-halmos` (created on first `make verify-kernel` run, never installed globally) —
matches this repo's existing per-package Python isolation convention. Full repo suite unaffected:
321/321, zero regressions (the new harness files use Halmos's `check_` naming convention, which
`forge test`'s own `test`-prefix matcher never picks up).

**What remains for workstream 3:** the four target properties themselves (not attempted here);
Halmos's actual scaling behavior against a property that exercises the reputation/assurance-tier
gating logic (the harness above only proves installation succeeds, not any of the four named
guarantees); and, per the parent proposal's own acceptance criteria, a precise, bound-stated
guarantee summary added to `IntegrityKernel`'s NatSpec once properties are actually proven —
premature to write until they exist.

## 43. All four target Halmos properties proven, unbounded — workstream 3's own scaling risk resolved favorably (2026-08-24)

*Current State:* `contracts/test/halmos/KernelProperties.t.sol` now machine-checks all four
properties `docs/plans/2026-08-24-phase1-formal-verification-proposal.md` named, against the
REAL, unmodified `IntegrityKernel`/`IntegrityAccount`, installed via the real governance-swap
harness (`PRODUCTION_GAPS.md` §42). All six `check_` functions (property 1 has a second, cumulative-
sequence variant; property 2 has a second, conjunction-with-native variant) pass **unbounded**
(Halmos's own `bounds: []`) in ~7.6s combined — the scaling risk the parent proposal's own "real
risk" section named ("Halmos may not scale to this kernel's cross-contract-call-heavy code") did
not materialize. Every property is mutation-tested: the corresponding guard was disabled directly
in `IntegrityKernel.sol`, confirmed to make the property fail, then restored — full repo suite
re-verified at 321/321 after every restoration.

- **Property 1 (native-ETH budget containment).** `check_nativeBudgetContainment`: single call,
  any recipient/amount, succeeds iff within both budgets, exact balance delta. Two real scoping
  findings from the FIRST Halmos run, both fixed by narrowing the property's own domain, not by
  changing the kernel: (a) a fully symbolic recipient can legitimately be a contract that
  unconditionally reverts on any call (excluded via `code.length == 0`, matching the concrete
  suite's own `makeAddr` convention); (b) `target == address(0)` is ERC-7579's own "call self"
  convention (`ERC7579Utils.sol` remaps it to `address(this)`), not a literal zero-address
  transfer, and changes the balance-delta math entirely (excluded explicitly).
  `check_cumulativeBudgetContainmentAcrossTwoCalls`: extends to a genuine two-call sequence, since
  the single-call property structurally cannot exercise the cumulative check when
  `PER_OP_BUDGET < CUMULATIVE_BUDGET`. Needed its OWN kernel with a wider per-op-to-cumulative
  ratio (2 ether / 3 ether) — even generalizing the *ratio itself* was tried first and found
  insufficient (two 1-ether-capped calls can never sum past 3 ether, so the cumulative branch was
  silently unreachable in an earlier draft — a real scoping bug, caught before trusting the
  property, not assumed away).
- **Property 2 (declared-token budget containment + conjunction).**
  `check_tokenBudgetContainmentAndNativeConjunction` and
  `check_nativeBudgetStillEnforcedOnTokenTrackingKernel`: an ERC-20 transfer via a token-tracking
  kernel succeeds iff within the token's own per-op budget; a pure-native call on the SAME kernel
  is still independently bound by the native check, proving neither check masks the other.
- **Property 3 (reputation/assurance-tier gating cannot be bypassed while stale or below floor).**
  `check_reputationAndAssuranceTierGating`: for a symbolic base score, boost expiry, and elapsed
  time, a trivial call succeeds iff the cached snapshot is fresh, above floor, and boosted —
  generalizing four separate concrete boundary tests to every reachable combination. Found and
  fixed a genuinely surprising Solidity/Foundry interaction while scoping this, tracked down via a
  debug-revert bisection rather than assumed: caching `uint256 x = block.timestamp;` before a
  later `vm.warp(...)` and reading `x` afterward returns the POST-warp value, not the value at the
  point of assignment, in this codebase's `via_ir = true` build — reading the timestamp back from
  real contract storage (`kernel.snapshotTakenAt()`) instead sidesteps it and is more
  ground-truth-correct regardless. Worth remembering for any future property that warps forward
  after capturing a timestamp.
- **Property 4 (the `armed` reentrancy guard is sound).** `check_reentrancyGuardIsSound`:
  generalizes the single concrete self-reentrancy test
  (`test_reentrantExecuteDuringAnInFlightCallIsRejected`) to every combination of two in-budget
  amounts. Mutation-testing this one surfaced a genuinely interesting result, recorded in the
  property's own code comment: disabling only `preCheck`'s `AlreadyArmed` check does NOT make the
  property fail — the reentrant call still reverts, on `postCheck`'s own separate `NotArmed`
  check instead, since the nested call's `postCheck` clears `armed` before the outer call's
  `postCheck` runs. Containment genuinely still holds under that single mutation; the property (by
  design) proves the outcome, not which specific line catches it. Demonstrating the property has
  real teeth required disabling BOTH `armed` checks at once — only then does the reentrant call
  actually succeed and move funds, and only then does the property correctly fail.

**Toolchain, harness, and dependency-inventory work:** all already recorded in §42 and unaffected
by this entry — same pinned Halmos 0.3.3, same `contracts/.venv-halmos`, same `make verify-kernel`
reproducibility (not yet updated to include this file's checks explicitly by name; still runs
`--contract KernelSwapHarnessTest` only, a known small gap for whoever extends the Makefile target
next).

**What remains for workstream 3, restated:** a precise, bound-stated guarantee summary added to
`IntegrityKernel`'s own NatSpec (each property's exact claim and that it's bounded, not
unconditional, per Halmos's own `bounds: []` reporting convention) has NOT been written yet — the
parent proposal's own acceptance criteria named this explicitly and it remains open. Workstream 3
as a whole is not yet closed: this closes the "four target properties" deliverable specifically,
not the NatSpec documentation deliverable alongside it.

**Update (2026-08-24, same day): the NatSpec deliverable above is now also closed.**
`IntegrityKernel`'s contract-level doc comment gained a "Machine-checked properties" section
stating each of the four claims precisely, with the same bound/scope caveats this entry names
(precompile/code-length/address(0)-means-self exclusions), and correcting a now-stale line that
had called the Table 4 gas crossing (§41) "an open finding requiring its own decision" after that
decision was actually made. `make verify-kernel` now runs both `KernelSwapHarnessTest` and
`KernelPropertiesTest` (previously only the harness proof), closing the small gap this entry
itself named. Workstream 3 is fully closed as of this update.

## 44. Phase I kernel reference deploy script built and dry-run verified — not broadcast to any live network (2026-08-24)

*Current State:* per `docs/plans/2026-08-24-phase1-testnet-deployment-proposal.md` (workstream 4,
authorized 2026-08-24 after weighing its own four open design questions), `contracts/script/
DeployKernelReference.s.sol` deploys ONE experimental, non-production reference instance of the
promoted `IntegrityKernel`/`IntegrityAccount` (§40) -- explicitly NOT integrated with any real
registered agent, `XibalbaAgentRegistry` entry, or `PrimitiveSet`. Four design decisions made
explicitly, not defaulted: (1) a fresh `ReputationRegistry` clone, cloned from the network's
already-deployed, real implementation (not a redundant new implementation, not bound to any real
agent's actual reputation); (2) reuses `IntegrityAccountTest`'s own budget constants exactly, so
this deployment is provably the same configuration already exercised by 321 concrete tests and
six Halmos properties (§43), not a fresh unverified one; (3) `trackedToken` disabled, avoiding
conflating this deployment with the already-disclosed Table 4 gas crossing (§41); (4) guardian
addresses are REQUIRED env vars with no default -- this repo's existing protocol role addresses
mostly collapse to the same deployer address (verified against the live
`deployments.baseSepolia.json` before writing the script: only 2 of 6 `protocolAddresses` entries
are actually distinct), not viable for a constructor that rejects duplicate guardians, and
inventing placeholder addresses nobody controls would defeat the point of a multi-party mechanism
even for a reference deployment.

**Two real bugs found and fixed via a local dry run (anvil, chain 31337) before this was trusted,
neither caught by compilation alone:**
- **A genuine off-by-one in the CREATE-nonce address prediction**, caught only by actually running
  the script: `updateScore` is itself a separate broadcast transaction that consumes a nonce
  between the prediction read and the kernel deployment, which an early draft didn't count --
  the KERNEL ended up deployed at the address predicted for the ACCOUNT, and the reputation score
  was set for the wrong address entirely (the kernel's, not the account's -- `preCheck` checks
  `effectiveScore(boundAccount)`, where `boundAccount` is the account). Fixed by reading the
  deployer's nonce exactly once, before any further broadcast transaction, and predicting two
  nonces ahead (`updateScore`, then the kernel deployment, both precede the account's own).
- **A JSON re-serialization bug in the `domains` merge helper**, inherited uncritically from
  `DeployEHRGate.s.sol`'s own `_rawDomains` pattern: dot-path concatenation
  (`.domains.` + key) breaks when the key itself contains a literal dot (e.g.
  `"general.integrity"`), which this repo's real domain names do -- `vm.parseJsonBytes32` treats
  each embedded dot as a further path-traversal segment and reverts. Never caught before because
  `DeployEHRGate.s.sol` was written and run when the real Base Sepolia `domains` section was still
  empty (`{}`); this script's own local dry run has real domain entries and exercised the bug for
  the first time. Fixed with bracket notation (`.domains["general.integrity"]`), which addresses
  the key literally.

**Verified beyond "the script didn't revert":** after the dry run, `cast call` confirmed the
deployed account's `hook()` returns the kernel's address and the kernel's `boundAccount()` returns
the account's address -- both directions of the binding, not assumed from the absence of a
revert. Full local repo suite re-verified at 321/321 after the dry run and a clean rebuild.
`deployments.local.json` is gitignored; the dry run's local addresses are not committed anywhere,
and the local anvil instance used for it was stopped, not left running.

**Not done, and not attempted here:** any broadcast to Base Sepolia or any other live network.
Per the proposal's own scope ("this proposal covers scoping and building the script only, not
running it"), actual broadcast execution -- which spends real (if low-value) testnet ETH from the
real `FUNDER_PRIVATE_KEY` and creates a permanent public record -- requires its own separate,
explicit authorization, not granted by this entry.

**A third real finding, this one repo-wide, not specific to this script: `forge script` without
`--broadcast` still executes `vm.writeJson`.** Simulating `DeployKernelReference.s.sol` against
the REAL Base Sepolia RPC (to get a live gas estimate before requesting broadcast authorization)
silently overwrote the real, tracked `deployments.baseSepolia.json` with fictitious addresses
that were never actually deployed -- the simulation still runs `_mergeDeploymentsFile()` because
Solidity/forge-std cheatcodes like `vm.writeJson` are local filesystem operations, not on-chain
actions gated by `--broadcast`. Caught and reverted immediately (`git checkout --
deployments.baseSepolia.json`) before it could be committed or mistaken for a real deployment
record. **This is not unique to this script** -- `Deploy.s.sol`, `DeployEHRGate.s.sol`,
`DeployMarkets.s.sol`, and `DeployXnsGovernance.s.sol` all write their deployments file
unconditionally too, with no check for whether a broadcast actually happened. Anyone simulating
any of them against a live RPC (e.g. to sanity-check gas before a real run, exactly what this
entry was doing) would corrupt the same file the same way. Not fixed here -- a real, disclosed,
pre-existing gap surfaced by this session's own workflow, worth its own scoped fix (e.g. gating
the write behind `vm.isContext(VmSafe.ForgeContext.ScriptBroadcast)` or an explicit
`--sig`-passed flag) rather than folded silently into this entry.

**Real cost, measured against the live network, not estimated:** simulating against Base
Sepolia's real RPC (`https://base-sepolia-rpc.publicnode.com`) reports 5,374,892 gas at ~0.011
gwei, ~0.000059 ETH total. The real funder wallet (`cast wallet address` from the real
`FUNDER_PRIVATE_KEY`, `0x7530bd7C...`) holds ~0.0625 ETH on Base Sepolia as of this check --
`FAUCET_INFO.md`'s own balance figures are stale and describe different addresses entirely, not
the actual deploying key. Broadcast cost is not a real constraint; authorization is the only
remaining gate.
