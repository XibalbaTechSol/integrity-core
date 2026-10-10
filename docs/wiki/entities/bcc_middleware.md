---
title: bcc_middleware
created: 2026-07-07
updated: 2026-10-10
type: entity
tags: [infrastructure, compliance, cryptography, metrics]
confidence: high
source_files:
  - bcc_middleware/app/main.py
  - bcc_middleware/app/canonical.py
  - bcc_middleware/app/baa.py
  - bcc_middleware/app/chain.py
  - bcc_middleware/app/anchor.py
  - bcc_middleware/app/merkle.py
  - bcc_middleware/app/reputation.py
  - bcc_middleware/app/scoring_loop.py
  - bcc_middleware/app/config.py
  - bcc_middleware/app/quarantine.py
  - bcc_middleware/app/nonce_lock.py
  - bcc_middleware/app/verification_token.py
  - bcc_middleware/app/audit.py
  - bcc_middleware/tests/test_periodic_anchor.py
  - bcc_middleware/tests/test_anchor_per_agent.py
  - bcc_middleware/tests/test_shutdown_drain.py
  - bcc_middleware/tests/test_opa_fail_closed.py
  - bcc_middleware/policies/bcc.rego
  - packs/bcc/policy.rego
  - bcc_middleware/app/pack_policy.py
  - bcc_middleware/app/clinical_allowlist.py
  - bcc_middleware/tests/test_pack_policy.py
  - bcc_middleware/tests/test_policy_engine_switch.py
---

The pre-execution policy gate (FastAPI + OPA). An agent signs a
[BCC commitment](../concepts/bcc.md) to what it's about to do and POSTs it to
`POST /v1/bcc/intercept`; this service decides allow/deny before the agent acts.
It also runs a second, independent responsibility: a periodic background loop
that pushes each agent's oracle-computed [AIS](../concepts/ais.md) on-chain and
raises slashing disputes (see "Reconciled this cycle" below) — the only place
in the monorepo that closes that loop.

## Table of contents

- [Pipeline](#pipeline)
- [Hermes runtime gate bridge (2026-08-04)](#hermes-runtime-gate-bridge-2026-08-04)
- [Reconciled this cycle (2026-07-14)](#reconciled-this-cycle-2026-07-14)
- [Reconciled 2026-07-11](#reconciled-2026-07-11)
- [Reconciled previous cycle](#reconciled-previous-cycle)
- [Async hot-path + hardening fixes, 2026-07-15](#async-hot-path-hardening-fixes-2026-07-15)
- [State](#state)
- [Resolved gap (found stale during integrity-dashboard/demo work, 2026-07-09)](#resolved-gap-found-stale-during-integrity-dashboard-demo-work-2026-07-09)
- [Evidence anchoring now targets a dedicated contract, not each agent's memory StateAnchor (B4, 2026-10-05)](#evidence-anchoring-now-targets-a-dedicated-contract-not-each-agent-s-memory-stateanchor-b4-2026-10-05)
- [Migration onto the shared signed pack: stage 1 (B2, 2026-10-07)](#migration-onto-the-shared-signed-pack-stage-1-b2-2026-10-07)
- [Signed policy pack: stage 2, loading and dual-run (B2, 2026-10-10)](#signed-policy-pack-stage-2-loading-and-dual-run-b2-2026-10-10)
- [Signed decision receipts: stage 3 (B2, 2026-10-10)](#signed-decision-receipts-stage-3-b2-2026-10-10)

## Pipeline

Schema validation → circuit breaker → **signature verification** → nonce-replay
check → freshness window → **OPA policy** (now including a
[verification-tier gate](../concepts/identity-ceiling.md)) → **on-chain BAA
check** (if OPA flags `requires_baa`) → admit to
[Merkle batch](../concepts/merkle-batching.md) + best-effort anchor.

**Fail-closed vs. best-effort** is the one property to get right: OPA and BAA are
*authorization* decisions and fail closed (any inability to positively confirm =
deny); anchoring happens after authorization and is best-effort. The circuit
breaker only counts violations attributable to the agent — an OPA/RPC outage
denies but never trips the breaker (else one outage locks out the whole fleet).

The HTTP-layer regression suite also exercises an indeterminate OPA response
whose `result.allow` value is not boolean. The middleware returns
`authorized=false` with the inspectable
`BCC_POLICY_ENGINE_UNAVAILABLE` diagnostic; it does not leak the malformed
decision into an implicit allow or an unhandled exception.

Audit decisions (allow and deny) are reported asynchronously to the oracle so an
unreachable audit endpoint cannot change the authorization response. The FastAPI
lifespan now drains in-flight audit-report tasks during shutdown, with a bounded
10-second wait, a shutdown admission gate, and explicit cleanup/logging when a report
remains stuck. This closes shutdown cancellation loss, but does not claim delivery
guarantees: an oracle outage can still lose a report because no local durable spool or
retry queue exists in the request task itself; failed reports now enter the package's
durable SQLite spool and are retried by its separate periodic worker.
Merkle anchoring also has a periodic worker: full batches still flush immediately, while
non-empty partial batches flush every `BCC_MERKLE_ANCHOR_INTERVAL_SECONDS` (default
300 seconds). Request, timer, and manual cycles are single-flight, and lifespan teardown
cancels and awaits the worker even when the application body exits exceptionally. Failed
on-chain submissions are logged but not durably queued; a graceful restart can also lose
an unflushed in-memory partial batch.
The reputation-sync loop below follows the same best-effort posture for score
pushes (a stale on-chain score, not a wrongly-trusted one) but the opposite for
disputes — see below.

When the secondary on-chain quarantine read is unavailable, the policy is
intent-scoped rather than globally fail-open: configured high-risk classes
(`chain_write`, `destructive`, `credential`, `privileged`, and clinical actions)
deny, while low-risk reads continue to the authoritative OPA decision. Configure
the classes with `BCC_QUARANTINE_FAIL_CLOSED_INTENTS`; the focused quarantine
suite covers both paths.

## Hermes runtime gate bridge (2026-08-04)

Hermes' shell-hook adapter now has a real per-session context bridge instead of
arriving at `pretool_gate.evaluate_tool_intent(...)` empty-handed:

- `integrity_telemetry` persists the latest turn rationale / assistant response in
  `~/.claude/xibalba/cache/hermes_session_context/<session_id>.json`.
- `agent/turn_finalizer.py` now forwards `last_reasoning` into `post_llm_call` so
  the plugin can prefer same-turn reasoning when a provider exposed it.
- `hermes_gate.py` reads that cache and bridges it into `INTENT_RATIONALE`
  (with `AGENT_THOUGHT` as a legacy alias) before it calls the shared pretool
  gate, preserving the single-source-of-truth BCC path.
- `tools/code_execution_tool.py` now forwards `HERMES_SESSION_ID` into nested
  sandbox tool dispatch so `execute_code` -> `terminal` keeps the session identity
  the BCC gate needs to recover trace/span context.

This is an operational repair, not a semantic completion of the protocol: the live
OPA rule now prefers the signed `intent_rationale` field, while `agent_thought`
remains a compatibility alias. The long-term contract should keep the rationale
public-safe and signed, not imply access to private chain-of-thought.

## Reconciled this cycle (2026-07-14)

- **Reputation-sync & slashing loop, new.** `app/reputation.py` +
  `app/scoring_loop.py` add a background asyncio task (started at FastAPI
  `lifespan` startup, `SCORE_SYNC_INTERVAL_SECONDS`, default 300s; also
  triggerable on-demand via `POST /v1/reputation/sync`) that lists every agent
  the oracle knows about and, per agent: (1) treats
  `GET /v1/agent/{id}/ais`'s geometric, tier-capped `ais` as authoritative,
  divides out only its reported `zk_boost`, and signs+submits a real
  `ReputationRegistry.updateScoreWithCoverage(agent, baseScore, ratioBps)`; it never reconstructs
  the formula from `components`/`weights`;
  (2) if the oracle's flagged-telemetry ratio for that agent crosses
  `DISPUTE_FLAGGED_RATIO_THRESHOLD` over a lookback window, signs+submits a
  real `Slasher.raiseDispute(agent, amount, reason)` locking
  `DISPUTE_STAKE_BPS` of the agent's available stake (subject to a per-agent
  `DISPUTE_COOLDOWN_SECONDS`). `integrity-oracle` itself stays strictly
  read-only (see its own `chain.rs` docstring) — this is what makes
  `bcc_middleware` the load-bearing signer for this role rather than a
  decorative one. Reuses `ANCHOR_SIGNER_PRIVATE_KEY` as the
  `REPUTATION_SIGNER_PRIVATE_KEY` fallback, a deliberate tradeoff on today's
  single-operator testnet deployment where oracle-signer/disputer/anchor-signer
  are already the same key (see `PRODUCTION_GAPS.md` §1 and
  [Interface Contract §7a](../../INTERFACE_CONTRACT.md#7a-reputation-sync--slashing-signer-bcc_middlewareappreputationpy-scoring_looppy)).
  Automated dispute-raising is safe to run unattended because raising only
  *locks* stake — a separate arbiter role and challenge window (see
  `Slasher.sol`'s NatSpec) is required to actually resolve/burn anything.

```mermaid
sequenceDiagram
    participant Loop as scoring_loop (periodic, 300s)
    participant Oracle as integrity-oracle
    participant RR as agent's ReputationRegistry
    participant Slasher as agent's Slasher

    Loop->>Oracle: GET /v1/agents
    loop each agent
        Loop->>Oracle: GET /v1/agent/{id}/ais
        Loop->>RR: updateScoreWithCoverage(agent, preBoostBaseScore, proofRatioBps)
        Loop->>Oracle: GET /v1/agent/{id}/telemetry/volume
        alt flagged ratio over threshold and cooldown elapsed
            Loop->>Slasher: raiseDispute(agent, amount, reason)
            Note right of Slasher: only LOCKS stake —<br/>a separate arbiter resolves/burns
        end
    end
```
- **Interface-contract §4.2 schema doc caught up to reality.** `agent_public_key`
  (required) and `covered_entity_address` (optional) have been real, signed,
  load-bearing fields in `app/schemas.py`/`app/canonical.py` since the previous
  cycle's signature-scheme/BAA reconciliation (below) — but
  `docs/INTERFACE_CONTRACT.md`'s own §4.2 JSON example never caught up and
  still showed the original 6-field shape. Fixed in the same pass as this
  entry; see [BCC](../concepts/bcc.md), which already had the correct shape.
- **Two stale artifacts found and fixed while verifying the above:**
  `.env.example`'s `BAA_CONTRACT_NAME=SmartBAA` (must be `SmartBAAFactory` —
  the per-pair `SmartBAA` escrow instances don't implement `isBAAActive`;
  the actual `app/config.py` default was already correct, only the example
  file was wrong) and `app/canonical.py`'s module docstring (still described
  the pubkey/fingerprint binding as an open "INTEGRATION FLAG" guess, now
  updated to state its actual ✅ RECONCILED status).

## Reconciled 2026-07-11

- **Verification-tier gate, real for the first time.** `input.verification_tier`
  (resolved by `app/chain.py::resolve_verification_tier` from the oracle's
  `GET /v1/agent/{id}`, fails closed to tier 0 on any lookup failure — see that
  function's docstring for why this differs from `agent_id_to_address`'s
  hard-fail) now feeds `bcc.rego`'s new `min_tier_by_intent_type` rule. This
  closes the gap [identity-ceiling.md](../concepts/identity-ceiling.md) used to
  describe as "0% enforced" — it's now enforced for the clinical intent-type
  set, as defense-in-depth on top of (not a replacement for) the existing
  allowlist. See that page for why thresholds are capped at 1 until Tier 2/3
  verification is real.
- **`verification_tier` is no longer client-asserted.** `integrity-oracle`'s
  `register_agent` handler previously stored whatever tier value the client
  sent — a real hole, since nothing stopped a client from self-asserting
  `verification_tier: 3`. It now always computes `SERVER_VERIFIED_TIER` (=1)
  itself; the client-supplied field is accepted on the wire but ignored. This
  is what makes the gate above meaningful rather than trivially bypassable.

## Reconciled previous cycle

- **Signature scheme:** the commitment carries a signed `agent_public_key`
  (multibase), bound by `sha256(pubkey) == did_fingerprint` before the Ed25519
  check — because the DID fingerprint is `sha256(pubkey)`, not the raw key.
  Canonical JSON uses RFC 8785 JCS, matching the SDK/CLI byte-for-byte.
- **BAA check:** the real two-arg
  `SmartBAAFactory.isBAAActive(coveredEntity, businessAssociate)`; the hospital
  comes from the commitment's signed `covered_entity_address`.
- **OPA clinical allowlist:** now data-driven — static demo set UNION
  `data.clinical_allowlist.agents`, so a real-DID agent is authorized by a loaded
  data document, no policy edit.

## Async hot-path + hardening fixes, 2026-07-15

`run_intercept` now wraps `resolve_verification_tier`, `check_baa_status`,
and `_flush_and_anchor` in `asyncio.to_thread(...)` — these were blocking
synchronous calls (`httpx.get`, `web3.py`, `wait_for_transaction_receipt`)
running directly inside an async FastAPI handler, stalling the whole event
loop per request. Making that concurrency real for the first time exposed
two follow-on gaps, both fixed in the same pass:

- **A genuine, reproduced race**: two concurrent requests using the same
  signer key (`anchor_root`'s Merkle-anchor tx and `reputation.py`'s
  `push_score`/`raise_dispute` tx) could both read the same starting nonce
  and submit conflicting transactions. New `app/nonce_lock.py`
  (`signer_lock(address) -> threading.Lock`, a process-wide per-address
  registry) now wraps every signed on-chain call. This one **did** reproduce
  empirically — 6/8 real `"nonce too low"` RPC failures with the lock
  temporarily removed, 0/8 with it restored (`test_nonce_lock.py`).
- **A code-level race, not empirically reproduced**: `MerkleBatcher.add`/
  `flush` had no lock of their own, and were only ever single-threaded
  before `asyncio.to_thread` made concurrent access possible. Added a
  `threading.Lock` around all mutating/reading methods. Honestly
  documented as based on a direct code-level trace of the unguarded
  multi-op sequence, not a captured failure — attempted to force it via
  `sys.setswitchinterval(0.00001)` stress testing and it did not reproduce,
  unlike the nonce race above.
- **`verification_token.py`**: replaced an unsigned, publicly-recomputable
  `sha256(...)` "verification token" (proved nothing) with an HMAC-SHA256
  keyed token (`issue_token`/`verify_token`, unforgeable without
  `BCC_VERIFICATION_SECRET`), exposed via a new `POST /v1/bcc/verify_token`
  endpoint. Bounded to `_MAX_ISSUED_TOKENS = 50_000` with oldest-first
  eviction to prevent unbounded growth.
- **`force_flush`** now returns each agent's real per-agent Merkle `root`
  (from `AnchorResult.root`) instead of the discarded full-batch root.
- **`scoring_loop.py`** now skips a redundant `push_score` call when an
  agent's score hasn't changed since the last confirmed submission
  (`_last_pushed_score` cache).
- **Test-chain-id fix**: 11 tests were failing with a chain-ID mismatch
  because the repo-root `.env` sets `CHAIN_ID=84532` (Base Sepolia)
  globally, silently overriding what local-anvil tests expect (`31337`).
  Fixed at the source: `tests/conftest.py`'s `anvil_chain` fixture now sets
  `os.environ["CHAIN_ID"]` from the real connected chain's id, so every
  `Settings()` constructed in that test session inherits it automatically.

## State

**145 pytest passed, 4 skipped + 48 OPA tests passed** (verified 2026-09-05).
Real coverage: a fail-closed test points at a dead
OPA port; `test_baa_health_integration.py` deploys the real
[Integrity Health contracts](../concepts/compliance-gate.md) on a local anvil and exercises
the real two-arg BAA call; `test_reputation.py`/`test_scoring_loop.py` cover the
reputation-sync loop above, including real `updateScore`/`raiseDispute`
transactions against `MockReputationRegistry.sol`/`MockSlasher.sol` fixtures.

## Resolved gap (found stale during `integrity-dashboard/demo` work, 2026-07-09)

This page previously said `app/chain.py::agent_id_to_address` derives the
agent's EVM address with a placeholder `keccak256(pubkey)[-20:]`. Re-read
against current source while building `integrity-dashboard/demo` (2026-07-09): this
is no longer true — `agent_id_to_address` now resolves the real
`SovereignAgent` contract address via `resolve_agent_primitives(oracle_url,
agent_id)` (an oracle lookup), matching what `EHRGate.checkAccess`/
`ComplianceGate` actually treat as `msg.sender`. Not independently re-verified
end-to-end against a live current-schema oracle this session (see
[integrity-dashboard](integrity-dashboard.md)'s demo section: no such oracle instance was
running), but the placeholder code path itself is confirmed gone from source.

## Evidence anchoring now targets a dedicated contract, not each agent's memory StateAnchor (B4, 2026-10-05)

`app/anchor.py::anchor_batch_per_agent` used to resolve each agent's OWN memory
`StateAnchor` via the oracle and anchor BCC batch sub-roots there — the same contract
C2 registration reads `latestRoot()` from as the memory root, so a flushed batch and a
memory-root anchor silently raced for the same on-chain slot. It now anchors every
agent's sub-root to one configured address,
`settings.contract_address(settings.protocol_evidence_anchor_contract_name)`
(default name `ProtocolEvidenceAnchor`, resolved from the deployments file's
`singletons` section like any other singleton) — no oracle call needed for the anchor
target anymore. See `contracts/script/DeployProtocolEvidenceAnchor.s.sol` in
[contracts](contracts.md) for the deploy side; `isAnchoredRoot` on a shared contract
still makes every individual root independently verifiable via `verifyLeaf`, even
though `latestRoot` itself no longer means anything agent-specific on this contract.
Re-verified against a real local anvil: `tests/test_anchor_per_agent.py` (3/3) and
`tests/test_chain_baa_anchor.py`'s full real-chain intercept flow (12/12).

Related: [BCC](../concepts/bcc.md),
[ComplianceGate](../concepts/compliance-gate.md),
[Merkle batching](../concepts/merkle-batching.md).

## Migration onto the shared signed pack: stage 1 (B2, 2026-10-07)

`bcc_middleware` still decides with `policies/bcc.rego` (boolean `allow`, a set of `violation`
messages, `requires_baa`); it does not yet use the signed-pack decision contract or emit receipts, and
it has no `integrity-sdk` dependency. Stage 1 of the staged migration adds `packs/bcc/`, a signed-pack
re-expression of `bcc.rego` that **is not loaded by this service yet**, and a differential harness
(`integrity-sdk/tests/unit/test_core_bcc_pack_equivalence.py`) that runs both in real OPA over 2,000+
cases and fails on any disagreement. Design and the remaining stages: `docs/design/bcc-shared-pack-migration.md`.

Finding, unreachable through this service but real in the policy: `bcc.rego` **allows** a commitment with
no `agent_id` or no `intent_type`, because a Rego rule that reads an absent field (or negates a membership
test on one) silently does not fire. This service always sends both, validated, so it is not a live
bypass; the new pack denies such input (`BCC_MALFORMED_COMMITMENT`). The pack reports one reason code
(highest priority) where `bcc.rego` reports a set; the set of denials is unchanged. `packs/bcc/controls.yaml`
cites only the controls the old policy already claimed; "every rule cites a control" is not yet met.

## Signed policy pack: stage 2, loading and dual-run (B2, 2026-10-10)

Stage 2 makes `bcc_middleware` able to load and use the signed pack. It is **off by default**: with
`BCC_POLICY_PACK_DIR` unset, `policies/bcc.rego` decides exactly as before (the 161 pre-existing tests still
pass unchanged). `app/pack_policy.py` verifies the pack (`load_pack`, trusted signers, optional pinned hash),
installs it into a **dedicated OPA** (`BCC_PACK_OPA_URL`; the installer replaces every policy under one id prefix,
so a shared OPA would let two gates overwrite each other), and decides through `integrity_sdk.core.decision.resolve`.

* **Dual-run** (pack configured, `BCC_POLICY_ENGINE=rego`): the pack is evaluated concurrently with `bcc.rego`;
  disagreements are logged (`POLICY DIVERGENCE`) and counted on `/health`; `bcc.rego` decides and the response is
  byte-identical. A failing pack is counted, never acted on.
* **Pack mode** (`BCC_POLICY_ENGINE=pack`): the pack decides. Fail closed at load (the service refuses to start) and
  at evaluation (`BCC_POLICY_ENGINE_UNAVAILABLE`, no circuit-breaker charge). Rollback is the flag.
* `requires_baa` is no longer a policy output; the gate's `CLINICAL_INTENT_TYPES` constant replaces it and is pinned
  to `bcc.rego` and the pack by tests. The BAA check still runs after policy, only for clinical intents.
* The clinical allowlist is a **hot-reloaded file** (`BCC_CLINICAL_ALLOWLIST_FILE`); an invalid file authorizes no extra
  agents rather than keeping the last good list (which would leave a revoked agent authorized).

Verified: 226 tests pass (65 new), including a pipeline-level differential in which 17 real signed scenarios give the
same outcome under `rego`, dual-run and `pack`, each also asserting its expected reason code, and 11 mutation
checks of the new guards (all caught). Not verified here: the Docker image build (no daemon; the layout was verified
by simulation and `docker compose config` validates). Not built: hot reload of the pack, receipts (stage 3).

**Finding, pre-existing and not fixed:** `PUT /v1/admin/clinical-allowlist` has no authentication and CORS is `*`, so
anyone who can reach the port can grant any agent clinical authority under `bcc.rego`. In pack mode the endpoint is
refused (409) instead of becoming a silent no-op or an unauthenticated writer of the pack's authority.
Operations: `docs/runbooks/bcc-policy-pack.md`.

## Signed decision receipts: stage 3 (B2, 2026-10-10)

With `BCC_RECEIPT_DIR` set, every decision made **after the commitment's signature verifies** (replay, expiry,
quarantine, policy deny, token budget, BAA, allow) gets a signed, hash-chained, checkpointed receipt, written by the
SDK's shared `GateReceiptWriter` (`integrity-sdk/integrity_sdk/core/receipt_writer.py`; BCC's adapter is
`app/gate_receipts.py`). Denials before the signature verifies get none: the agent id on them is unproven.

- **Strict by default.** The allow receipt is written before the commitment is admitted to a Merkle batch or given a
  token; if it cannot be written, enforce mode denies as `BCC_RECEIPT_UNAVAILABLE` (breaker not charged).
  `BCC_LENIENT_RECEIPTS=1` opts out; shadow mode never blocks. An unusable key or a log that fails verification
  refuses start.
- **The receipt names the policy that decided:** the pack hash plus the pack's code and controls in pack mode;
  `NO_PACK_HASH` and `BCC_REGO_POLICY_PERMIT/DENY` under `bcc.rego`, including dual-run.
- **Epochs** (`BCC_RECEIPT_EPOCH_MAX_RECEIPTS` / `_MAX_AGE_SECONDS`) bound memory and checkpoint cost: a new `log_id`
  and a fresh chain per epoch, with a covering checkpoint before closing. Deleting the newest epoch is undetectable
  until anchoring of closed epochs exists (`[PLANNED]`).
- **Response additions (additive):** `receipt` `{log_id, seq, hash}`, `receipt_status`; `/health` gains `receipts`.

Verified: 23 SDK + 25 BCC pipeline tests, mutation checks, and a live run (real uvicorn, OPA, signed commitments)
checked with `integrity-cli verify` (intact passes; tamper = `BAD_SIGNATURE`; truncation = `TRUNCATED`). Not built:
Shield's swap to the SDK writer; shared rulebook vectors (stage 4); anchoring of epochs. Design:
`docs/design/bcc-shared-pack-migration.md`; operations: `docs/runbooks/bcc-policy-pack.md` section 5.
