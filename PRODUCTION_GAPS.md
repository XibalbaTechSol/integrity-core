# Production Architecture Gap Analysis & Codebase Audit

Following a deep audit of the `INTEGRITY-LATEST` codebase, the following outlines the specific, technical gaps required to connect the `integrity-dashboard` UI to the backend production systems.

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
  list every agent the oracle knows about, recompute each one's pre-boost weighted AIS
  from `GET /v1/agent/{id}/ais`'s `components`/`weights` (deliberately not
  `ais / zk_boost`, to avoid float round-trip error), and sign+submit a real
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
* **CLOSED — `EHRGate` ABI + Shield wrapper functions.** `scripts/sync_abis.py` now syncs
  `EHRGate`; new `integrity_sdk/shield.py` wraps `CoveredEntityRegistry`/`SmartBAAFactory`/
  `SmartBAA`/`ComplianceGate`/`EHRGate`, reusing `markets._execute_via_agent` for every
  agent-routed call. Verified against real anvil-deployed contracts in
  `tests/test_shield.py`: a full happy path (register covered entity → create BAA → agent
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
  decision: PHI/PII redaction is now opt-in, scoped to Xibalba Shield / healthcare-vertical
  agents, who **must** pass `redact_phi=True` when constructing `IntegrityOpenAI` /
  `IntegrityLangChainCallback` — neither wrapper has any way to know an agent's
  `compliance_vertical` on its own (that's registered separately), so nothing here can safely
  auto-detect "this needs redaction." Both wrappers log a `logger.warning` naming the agent at
  construction time whenever `redact_phi` is left at its default `False`, so a misconfigured
  healthcare deployment is at least loud about it rather than silent — but there is **no
  runtime enforcement** preventing a healthcare-vertical agent from being built without
  `redact_phi=True`. This is a real, accepted residual risk from the chosen default, not an
  oversight: flagged here so it isn't lost track of, and worth a `shield.py`-level guard (e.g.
  refusing to proceed, or checking `compliance_vertical` against a resolvable registry) as a
  real follow-up rather than relying on every integrator remembering the flag.

## 4. Smart Contracts (`contracts/src`) — findings from a full-package audit, ALL CLOSED

*Current State:* 172 Foundry tests passing (up from 165), 66%+ line coverage. Web3 wallet
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
  `test_cannotReformBAAWhileDisputed`) in `test/shield/SmartBAA.t.sol`.
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
  register-handle *write* flow in the dashboard remains a deliberate deferral (CLI/SDK for now).
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
  disturbed until then. **Read-only in the UI by design:** handle *lookup* (resolve) is wired;
  the *register-handle* write flow (`XibalbaNameService.register`, a wallet-signed tx) is
  deliberately not in the dashboard yet — an explicit deferral, done via CLI/SDK, not a silent
  omission.
* **CLOSED (deployed 2026-07-26) — on-chain governance is live on Base Sepolia.**
  `IntegrityGovernance` is deployed at `0x62ef8A3B42b07FDee7498199696dae31AC2A9255` (chainId
  84532), guardian/owner = the Xibalba agent `0xabfeEaCbA00F38810E697b2970399fE03080FBeB`
  ("funder signs, agent owns"), genesis params (3-day vote / 2-day timelock / 1,000 ITK
  threshold / 10,000 ITK quorum — verified via `quorumVotes()` on-chain). Deployed via the
  incremental `script/DeployXnsGovernance.s.sol` + written into `deployments.baseSepolia.json`.
  Verified live: `GET /v1/governance/proposals` now returns 200 `[]` (was 400 MissingSingleton);
  `GovernancePanel`/`GuardianPilot` now render the live (currently empty) proposal set. The
  propose/vote *write* flow in the dashboard remains a deliberate deferral (CLI/SDK for now).
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
  `deployments.baseSepolia.json` entry. **Read-only in the UI by design:** the panels render
  live proposals + tallies; the *write* half (propose / castVote / queue / execute — all
  wallet-signed txs) is deliberately not wired into the dashboard yet (an inline note in
  `GovernancePanel` says so), done via CLI/SDK for now — an explicit deferral, not a silent gap.
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
* **Gap - Active Quarantine Enforcement (confirmed still open).** Nothing reads back
  on-chain slash/dispute state to affect a future `run_intercept` decision — OPA
  evaluation and the circuit breaker are still driven purely by this service's own request
  history. `scoring_loop.py` can now *raise* a dispute but nothing closes the loop back
  into policy enforcement.
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
`SdkTelemetryPage`, `IntelligencePage`, `CompareTracesPage`, `ShieldPage`'s Stability
Certification tab, and the dashboard's `throughput`/`events`/`radar` widgets.
`AgentContext.tsx` is confirmed real (calls `oracle.listAgents()`) — this doc previously,
incorrectly, listed it as mock; that was stale. Two real on-chain write paths already
exist via wagmi (`ShieldPage.tsx`'s BAA sign/revoke, `ExchangePage.tsx`'s market entry) —
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
  across Dashboard/Contracts/Exchange/CompareTraces/Shield/Documents/Finance/Identity.
* **CLOSED — `AuditPage.tsx` made a specific, false security claim with no mock-data
  disclosure.** Its copy asserted actions are "cryptographically hashed and anchored to
  Base L2" and "cannot be tampered with by the agent, host, or hypervisor," backed by 3
  hardcoded `LoggerContext.tsx` entries (including a fabricated tx hash) — nothing was
  hashed, nothing was anchored. Rewritten to honestly state what's real (BCC Middleware
  DOES batch-anchor approved intents, best-effort, not yet per-event) versus what this
  specific page shows (a simulated local event feed, now `SeededDataBadge`-marked, no
  real audit-trail query endpoint exists yet).
* **CLOSED — `ShieldPage.tsx`'s consent/slash actions were theater, not disclosed
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
* **CLOSED — `ShieldPage.tsx`'s "Stability Certification" tab was hardcoded despite
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
  `ShieldPage.tsx`), there's no "list every active BAA" capability to sum across. Building
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
  already being the proven pattern on `ShieldPage`'s Stability Certification tab);
  `tier` was derived from the coarse `ACTIVE`/`IDLE` status boolean and always showed
  `'AAA'` regardless of real score; worse, `teeVerified = true` was hardcoded
  unconditionally, rendering "TEE Status: Verified (Nitro)" for every agent with no
  real attestation ever performed — `NitroAttestationGenerator` raises
  `NotImplementedError` everywhere else in this codebase (this same page's own disabled
  "Regenerate Attestation Document" button already discloses that honestly). Fixed:
  real `oracle.getAis()` fetch + the same `stabilityTier()` score-banding function
  `ShieldPage` already uses, `teeVerified` set to `false` (renders the page's own
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
    (real `userapi.*` calls or already-disclosed toggles), `ShieldPage.tsx`'s Smart
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
* **(2026-07-16) `DocumentsPage.tsx` merged into `ShieldPage.tsx` as a new "Documents"
  tab, then removed as a standalone route.** Per explicit request: the page's own
  content was always HIPAA/clinical-document-flavored (`HIPAA_Compliance_Guidelines_
  2026.pdf`, `Patient_Onboarding_Protocol.docx`, `Clinical_Trial_Results_Q3.pdf`), so
  it belongs on the compliance page its filenames are about rather than a separate
  top-level nav item. Moved verbatim (banner, 3 stat cards, trend chart, document
  table) into a new `Documents` entry in `ShieldPage.tsx`'s `SUB_TABS`, keeping the
  exact same honest disclosure (`SeededDataBadge`, "Not yet implemented" banner, no
  document/RAG-indexing backend exists anywhere in this monorepo — nothing was
  silently upgraded to "real" in the move). Removed `DocumentsPage.tsx`, the
  `/documents` route (`App.tsx`), and the Sidebar nav entry; `e2e/smoke.spec.ts`'s
  `ROUTES` updated to 10 entries (was 11). `npm run build`/`tsc -b --noEmit`/
  `npm run lint` clean, 12/12 Playwright e2e green, re-verified live: the merged
  "Documents" tab renders correctly under Shield, `/documents` no longer resolves to
  anything.

## 8. CI / Autonomous Fix-Forward (`.github/workflows/ci.yml`)
*Current State:* A real CI workflow now runs every package's test suite (mirroring the root `Makefile`'s `test` target) as separate per-package jobs on push/PR to `main`. The `notify-jules-on-failure` job makes a real call to the Jules API (`POST https://jules.googleapis.com/v1alpha/sessions`, `X-Goog-Api-Key` auth, `AUTOMATION_MODE_AUTO_CREATE_PR`) — verified against `@google/jules-sdk`'s actual published source, not guessed.
* **Gap - One-time repo-owner authorization still required:** the workflow will fail loudly (not silently no-op) until (1) Jules is authorized for `XibalbaTechSol/integrity-latest` at jules.google.com (grants its GitHub App repo access), and (2) a `JULES_API_KEY` secret (from jules.google.com/settings/api) is added under repo Settings → Secrets and variables → Actions. Both are account-holder actions no automation can complete on the owner's behalf.
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
* **CLOSED — `AuditLogsPanel.tsx` rewritten to query the real endpoint, reactive to the global agent selector.** Per an explicit follow-up ("agent selector should be working to determine which data to display"): the panel now calls `oracle.getAuditLog(selectedAgent?.id, 200)` from `AgentContext`'s `selectedAgent` (the same global TopBar picker `SystemDiagnosticsPage`'s sibling "SDK Telemetry" tab already reacts to), refetching on agent change. Removed the `SeededDataBadge`/"Simulated event feed" disclosure entirely — this data source is now real, not merely honestly-disclosed-fake. `LoggerContext.tsx` was left in place, not deleted: it's still a legitimate (if minor) dependency of `ActuarialHub.tsx`'s own mock marketplace flow, which is out of this pass's scope; only `AuditLogsPanel`'s use of it was removed. `ShieldPage.tsx`'s separate "Medical Record Interaction Logs" table (`MOCK_AUDIT_LOGS`, a different, EHR-action-shaped concept) was left as-is — already honestly disclosed via its own `SeededDataBadge`, and wiring it to the new generic `audit_log` feed would misrepresent it as PHI-specific interaction logging it isn't.
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
* **CLOSED — three separate landing-page/header buttons (`HeroSection.tsx`'s "Launch Dashboard", `CinematicHeader.tsx`'s desktop+mobile "Launch Dashboard" and "Sign In", `CoreFeatures.tsx`'s "OPEN ESCROWS") all navigated to `/integrity`, which is not and has never been a route in `App.tsx`** (real routes: `/`, `/landing`, `/identity`, `/contracts`, `/settings`, `/finance`, `/traces`, `/diagnostics`, `/shield`, `/agents`) — every one of these was a dead link rendering a blank page. Fixed by pointing each at the real destination its label promises: "Launch Dashboard" → `/` (the real Intelligence Command dashboard), "Sign In" → `/settings` (where the real `userapi` email/password login form already lives), "OPEN ESCROWS" → `/finance` (real `MarketsEscrowPanel.tsx`). `CinematicHeader.tsx`'s "Sign In" button additionally fired `alert("Google Sign-In flow initiated.")` before navigating — a fake OAuth flow with no real Google/any-provider integration anywhere in this monorepo — removed entirely along with the dead-route fix, not just disclosed, since a real login path already exists one click away.
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
* **OPEN — all 7 existing agents have `latestRoot == 0`,** including the flagship `xibalba.integrity` (`StateAnchor 0x09DCBBd0D7B0f39db315a8C4f913C162D73Cc68b`, verified on Base Sepolia). They predate step 8b and remain registered, because the gate only runs at registration — so **the protocol currently has registered agents that do not satisfy its own §4.1**. Each needs one controller-signed `anchorRoot` tx to become compliant. Not a latent bug so much as a migration nobody has run; stated here so the fleet's state isn't mistaken for spec-conformant.
* **OPEN — §7.2 enforcement (Appendix A gap 2) is genuinely unbuildable for existing agents.** Gating `anchorRoot` to `latestEpoch >= 1` would stop the protocol's `ANCHOR_ROLE` signer from anchoring epoch 1, but `StateAnchor` is deployed **per agent, not cloned** — every already-deployed anchor keeps its current bytecode forever, so a contract change reaches only future agents. Any such gate must also leave `DEFAULT_ADMIN_ROLE` able to perform genesis at any epoch-0 moment, or an agent on new bytecode that skipped genesis could never recover. Deferred until that migration question is answered, not silently skipped.
* **OPEN — Appendix A gaps 3–8, untouched:** uniform minimum stake at registration; tighter ZK-boost binding (per-event / public inputs) — today it is a period-wide `BOOL_OR`; identity-ceiling clamp in scoring (`AIS_final = min(AIS, Tier_ceiling)`); lineage attestation + on-chain record (§7.4); optional ERC-8004 discovery adapter; silence-as-signal for the observability obligation.
* **Spec drift, confirmed:** §16's package map lists `integrity-mvp/`, which was **replaced by** `integrity-dashboard/`. The package was deleted on disk during that consolidation but the deletion sat uncommitted until 2026-07-29 (944 files), which is why the tree appeared to contain both. The spec should say `integrity-dashboard/`.

## 20. ITK testnet liquidity moved to the agent; Finance wallet + Cognition traces fixed (2026-07-29)

*Current State:* `xibalba.integrity` is now a real minting source for testnet $ITK, the Finance tab shows the agent's true on-chain treasury, and the Cognition tab's emptiness turned out to be a genuine data-path gap rather than a UI bug. One reproducible frontend hang is open.

* **CLOSED — `xibalba.integrity` can mint ITK as the protocol's liquidity source.** `MINTER_ROLE` granted on `IntegrityToken` to its `SovereignAgent 0x360E2a56…` (tx `0xdddf4742…`, block 44781859). New SDK helper `chain.mint_testnet_itk_from_treasury()` routes `SovereignAgent.execute → IntegrityToken.mint`, signed by the agent's own controller, so the mint is attributable on-chain to the agent rather than to an operator EOA — same self-sovereign routing as `grant_anchor_role`/`anchor_genesis_root`. Proven live on Base Sepolia: the agent minted 500 ITK with no funder key in the path (tx `0x20e3076b…`); treasury 10,000 → 10,500 ITK, supply 100,500 → 101,000. The funder retains `MINTER_ROLE` as issuer of last resort, by explicit choice.
* **CLOSED (with a documented limit) — registration now prefers the liquidity agent.** `registration.py` step 7 mints via `mint_testnet_itk_from_treasury` when `INTEGRITY_LIQUIDITY_AGENT` names a local agent whose `primitives.json` and controller wallet are present, and falls back to the funder mint otherwise — logging a warning that names the fallback rather than failing silently.
  * **Inherent limit, not a gap to close by coding:** `SovereignAgent.execute` may only be called by the controller, so minting through the liquidity agent requires that agent's controller key locally. That holds for the current single-operator testnet and is false in general — a third party registering its own agent cannot sign as `xibalba.integrity`. A multi-operator deployment needs a faucet *service* the liquidity agent runs, not a shared key. The fallback exists precisely so that case degrades honestly.
* **CLOSED — Finance tab showed 0.00 ITK while the agent held 10,000.** Two compounding faults: `oracle.getWallet` existed in `services/oracle.ts` but was called from **nowhere**, and `TokenWallet` passed `selectedAgent.eth_address` — which carries the agent's **DID**, not an EVM address — straight to `balanceOf`. On top of that, any connected browser wallet won the address race, so the panel rendered the operator EOA's balance (0) instead of the agent's. Now the agent treasury resolves first through the oracle; the panel reads the real 10,000.00 ITK at `0x360e2a56eb…`. Also replaced two hardcoded `https://sepolia.base.org` literals with the `RPC_URL` constant.
* **CLOSED — Cognition was empty because no OTel spans existed.** Not a dashboard bug: Integrity has two parallel span paths (spec v0.3 §10), and the Xibalba session hooks only ever used path A (signed telemetry → `telemetry_events` → AIS). Cognition reads path B (`otel_spans`). All three hooks set `enable_otel_export=False`, and flipping that flag alone changes nothing because nothing was *creating* spans. `session_start.py`/`session_stop.py` now enable export and emit a real span per session boundary, with `force_flush` since hooks are short-lived. Verified: `otel_spans` 0 → 1 for the agent, and `GET /v1/agent/{id}/otel/traces` returns `claude_session_start` (trace `49a5a48c…`).
* **OPEN — the dashboard's Cognition page hangs the renderer when an agent is selected.** Reproduced 4× across three fresh tabs. Narrowed: loading `#cognition` renders fine; the freeze fires on *selecting an agent from the fleet list*. Backend is not the cause — no request storm in the oracle logs during the hang, and the trace data is confirmed present at the API layer (`/v1/agent/{id}/otel/traces` returns `claude_session_start`).
  * **A first hypothesis was tested and disproved:** the Cognition panels depended on the `selectedAgent` *object*, and `DashboardProvider` re-polls every 15s creating a fresh object each time, so every effect re-ran (and re-armed its 5s interval) on every poll. That was real and is fixed (5 panels now depend on `selectedAgent?.eth_address`, matching `TokenWallet`'s existing fix) — a genuine refetch-storm reduction — but the freeze still reproduces afterwards, so it is **not** the cause. Root cause remains unknown; next step is a profile of the renderer during selection rather than more code-reading.
* **Environment footgun worth knowing:** `docker compose` auto-loads the root `.env`, which pins `CHAIN_ID=31337` and `DOCKER_RPC_URL=http://host.docker.internal:8545` (local anvil). Any `docker compose up` for `oracle-backend` **without** the Base Sepolia overrides silently repoints the oracle at a dead anvil — every chain read then fails, XNS handles degrade to `null`, and the dashboard quietly reverts to `Agent <fingerprint>` labels. Correct invocation: `DOCKER_RPC_URL=https://base-sepolia-rpc.publicnode.com CHAIN_ID=84532 DOCKER_DEPLOYMENTS_FILE=/deployments.baseSepolia.json docker compose up -d oracle-backend`.
