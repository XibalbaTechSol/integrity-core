---
title: bcc_middleware
created: 2026-07-07
updated: 2026-08-04
type: entity
tags: [infrastructure, compliance, cryptography, metrics]
confidence: high
source_files:
  - bcc_middleware/app/main.py
  - bcc_middleware/app/canonical.py
  - bcc_middleware/app/baa.py
  - bcc_middleware/app/chain.py
  - bcc_middleware/app/merkle.py
  - bcc_middleware/app/reputation.py
  - bcc_middleware/app/scoring_loop.py
  - bcc_middleware/app/config.py
  - bcc_middleware/app/nonce_lock.py
  - bcc_middleware/app/verification_token.py
  - bcc_middleware/policies/bcc.rego
---

The pre-execution policy gate (FastAPI + OPA). An agent signs a
[BCC commitment](../concepts/bcc.md) to what it's about to do and POSTs it to
`POST /v1/bcc/intercept`; this service decides allow/deny before the agent acts.
It also runs a second, independent responsibility: a periodic background loop
that pushes each agent's oracle-computed [AIS](../concepts/ais.md) on-chain and
raises slashing disputes (see "Reconciled this cycle" below) — the only place
in the monorepo that closes that loop.

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
The reputation-sync loop below follows the same best-effort posture for score
pushes (a stale on-chain score, not a wrongly-trusted one) but the opposite for
disputes — see below.

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
  `ReputationRegistry.updateScore(agent, baseScore)`; it never reconstructs
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
        Loop->>RR: updateScore(agent, preBoostBaseScore)
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
  Canonical JSON uses `ensure_ascii=True`, matching the SDK/CLI byte-for-byte.
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

**91 pytest + 28 OPA tests** (up from 75 pytest — the hardening pass
above). Real coverage: a fail-closed test points at a dead
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

Related: [BCC](../concepts/bcc.md),
[ComplianceGate](../concepts/compliance-gate.md),
[Merkle batching](../concepts/merkle-batching.md).
