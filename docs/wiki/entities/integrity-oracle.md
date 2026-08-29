---
title: integrity-oracle
created: 2026-07-07
updated: 2026-08-04
type: entity
tags: [infrastructure, metrics, layer-2, tokenomics]
confidence: high
source_files:
  - integrity-oracle/scoring-core/src/lib.rs
  - integrity-oracle/backend/src/handlers.rs
  - integrity-oracle/backend/src/derive.rs
  - integrity-oracle/backend/src/otlp.rs
  - integrity-oracle/backend/src/chain.rs
  - integrity-oracle/backend/src/db.rs
  - integrity-oracle/backend/src/phi.rs
  - integrity-oracle/backend/src/vc.rs
  - integrity-oracle/backend/src/verification.rs
  - integrity-oracle/backend/src/attestation.rs
  - integrity-oracle/backend/src/kyc.rs
  - integrity-oracle/backend/src/crypto/mod.rs
  - integrity-oracle/backend/src/openapi.rs
  - integrity-oracle/backend/migrations/0001_init.sql
  - integrity-oracle/backend/migrations/0002_markets_and_judge.sql
  - integrity-oracle/backend/migrations/0003_agent_did_document.sql
---

The off-chain brain (Rust, Axum, Postgres, Redis, `alloy`): it ingests agent
telemetry, computes the [Agent Integrity Score](../concepts/ais.md), and
independently verifies agents' on-chain state — including, as of this pass, the
[market/application layer](../concepts/agent-primitives.md) (§6.9) — so nothing
downstream has to trust an agent's own word. Per §6.10 of the interface contract,
this is the **only** backend that ever reads on-chain state.

## Table of contents

- [Workspace](#workspace)
- [HTTP API](#http-api)
  - [GET /v1/agent/{id}/telemetry, GET /v1/agent/{id}/traces](#get-v1-agent-id-telemetry-get-v1-agent-id-traces)
  - [GET /v1/markets, GET /v1/markets/{id} (§6.9)](#get-v1-markets-get-v1-markets-id-6-9)
  - [GET /v1/leaderboard](#get-v1-leaderboard)
  - [Contract-ownership + Integrity Health reads: GET /v1/agent/{id}/contracts, /baas](#contract-ownership-integrity-health-reads-get-v1-agent-id-contracts-baas)
  - [Verifiable Credentials: GET /v1/agent/{id}/vc](#verifiable-credentials-get-v1-agent-id-vc)
  - [Network benchmarks + protocol stats: GET /v1/benchmarks, /v1/stats](#network-benchmarks-protocol-stats-get-v1-benchmarks-v1-stats)
  - [XNS resolution: GET /v1/xns/resolve?handle=, GET /v1/agent/{id}/handle](#xns-resolution-get-v1-xns-resolve-handle-get-v1-agent-id-handle)
  - [Governance: GET /v1/governance/proposals](#governance-get-v1-governance-proposals)
  - [GET /v1/agent/{id}/wallet](#get-v1-agent-id-wallet)
  - [Server-side telemetry-signal re-derivation (derive.rs)](#server-side-telemetry-signal-re-derivation-derive-rs)
  - [The OTLP/gRPC path (otlp.rs) — separate from telemetryevents, unauthenticated](#the-otlp-grpc-path-otlp-rs-separate-from-telemetryevents-unauthenticated)
  - [PHI backstop on POST /v1/telemetry/ingest](#phi-backstop-on-post-v1-telemetry-ingest)
  - [Judge evaluations (storage only — no judge implementation)](#judge-evaluations-storage-only-no-judge-implementation)
- [On-chain client (chain.rs)](#on-chain-client-chain-rs)
- [Anchoring](#anchoring)
- [Canonical JSON signing — real cross-language bug fixed 2026-07-11](#canonical-json-signing-real-cross-language-bug-fixed-2026-07-11)
- [State](#state)

## Workspace

- **`scoring-core`** — dependency-free; the **one** place the AIS formula is
  computed. Everyone else reads the HTTP API.
- **`backend`** — Axum server, sqlx persistence, Redis rate limiting,
  `bb verify` ZK verification, Merkle building, and the `alloy` on-chain read
  client.

## HTTP API

```
POST /v1/agent/register
GET  /v1/agent/{id}
GET  /v1/agents
GET  /v1/agent/{id}/ais
GET  /v1/agent/{id}/ais/history
GET  /v1/agent/{id}/compliance
GET  /v1/agent/{id}/wallet
GET  /v1/agent/{id}/telemetry
GET  /v1/agent/{id}/telemetry/volume
GET  /v1/agent/{id}/otel/volume
GET  /v1/agent/{id}/traces
GET  /v1/agent/{id}/contracts
GET  /v1/agent/{id}/baas
GET  /v1/agent/{id}/vc
GET  /v1/agent/{id}/handle
POST /v1/agent/{id}/verify/dns/challenge
POST /v1/agent/{id}/verify/dns
POST /v1/agent/{id}/verify/github/challenge
POST /v1/agent/{id}/verify/github
POST /v1/agent/{id}/verify/tee/challenge
POST /v1/agent/{id}/verify/tee
POST /v1/agent/{id}/verify/kyc/challenge
POST /v1/agent/{id}/verify/kyc
GET  /v1/agent/{id}/verify
POST /v1/agent/{id}/verify/{verification_id}/revoke/challenge
POST /v1/agent/{id}/verify/{verification_id}/revoke
GET  /v1/traces/{trace_id}
POST /v1/telemetry/ingest
GET  /v1/markets
GET  /v1/markets/{id}
GET  /v1/leaderboard
GET  /v1/benchmarks
GET  /v1/stats
GET  /v1/xns/resolve?handle=<h>
GET  /v1/governance/proposals
GET  /v1/stream
GET  /v1/agent/{id}/stream
GET  /healthz
```

Full request-pipeline order for `POST /v1/telemetry/ingest` (PHI scan →
agent lookup → rate limit → signature → server-side re-derivation → ZK →
compliance → nonce replay → storage):
[Telemetry Ingestion Pipeline](../concepts/telemetry-ingestion.md).

### `GET /v1/agent/{id}/telemetry`, `GET /v1/agent/{id}/traces`

Real history queries returning lists of past telemetry events and judge traces respectively, queried directly from Postgres (`telemetry_events` and `judge_evaluations` tables) and returned as structured DTO arrays. Used by the Dashboard UI to render live feeds and historical execution logs.


**The honesty crux:** `POST /v1/agent/register` independently calls
`XibalbaAgentRegistry.resolveDID` and rejects (`400`) if the client's claimed
[7 primitives](../concepts/agent-primitives.md) don't match on-chain state. This
is what makes "the chain is the source of truth" real, not decorative.
Request body (`RegisterAgentRequest`, `handlers.rs`): `did` (required — not
`agent_id`), `did_document`, `primitives` (exactly the 7 `PrimitiveSetDto`
fields), `ed25519_pubkey_hex`/`eth_address_hex` (`Option<String>` each, but
the handler 400s if *both* are absent), `verification_tier` (`i32`, defaults
to `0`). Now documented in `docs/INTERFACE_CONTRACT.md` §6.3 — it was silent
on this schema until 2026-07-09, which is how `integrity-sdk`'s client drifted
from it undetected (see [integrity-sdk](integrity-sdk.md)'s "Fixed 2026-07-09"
note).

On 2026-07-16, we enhanced `chain.rs` (`resolve_primitives_by_did`) to log the actual RPC contract call error details when `resolveDID` fails instead of silently mapping them to `UnknownDid`. This resolves a major diagnostic visibility gap during stack startup and network resolution.

### `GET /v1/markets`, `GET /v1/markets/{id}` (§6.9)

Real reads of every `IntegrityMarket` clone via `MarketFactory`. Enumeration is
concurrent (`futures::future::join_all`), not a serial loop, and cached in Postgres
(`markets_cache` + a single-row `markets_index_sync` marker) behind a 30s staleness
window (`handlers::MARKETS_CACHE_STALENESS_SECS`) — a documented tradeoff between RPC
load and freshness, not silent staleness. On a cache miss/stale hit, `list_markets`
re-enumerates `MarketFactory.allMarketsCount()` (not just refreshes existing rows) so a
newly-created market is actually discovered.

`GET /v1/markets/{id}` (`{id}` = the market's contract address) returns `question`,
`outcomeCount`, `resolved`, `winningOutcome`, `resolveDeadline`, `totalStaked`, and
`outcomeStaked` per outcome (the real pari-mutuel pool — cheap public-getter reads).
An optional `?agent=0x...` query param adds a real, single `getPosition` read as
`your_position`. **Documented gap:** enumerating every holder's position across a
market requires indexing `PositionEntered` events, which this pass does not build —
`positions_note` in the response says so explicitly rather than silently omitting it.

Uint256 amounts (`min_ais_to_enter`, `total_staked`, `outcome_staked[i]`) are always
decimal **strings** in both the DB (`TEXT`, not a numeric type sqlx isn't configured
for) and the JSON DTOs — a `uint256` can exceed both `i64` and `f64`'s safe integer
range.

**Contract-vs-brief discrepancy found while building this:** `MarketFactory` has no
`allMarkets() returns (address[])` getter — `address[] public allMarkets` only
auto-generates an indexed `allMarkets(uint256) returns (address)` getter. Enumeration
is `allMarketsCount()` + concurrent `allMarkets(i)` reads
(`ChainClient::all_market_addresses`). By-creator listing uses the real
`getMarketsByCreator(address) returns (address[])` function, not the
`marketsByCreator` mapping's auto-getter (which also needs an index).

### `GET /v1/leaderboard`

Ranks agents by real `ReputationRegistry.effectiveScore` (decimal string, same
`ChainClient::effective_score` method `chain.rs` already had). **No fabricated P&L**:
`realized_pnl` is always `null` — computing it for real would require indexing
`IntegrityMarket` `PositionEntered`/`MarketResolved`/`PayoutClaimed` events across
every market, out of scope for this pass. An honestly-incomplete ranking, not a silent
mock. Only agents with a resolvable on-chain `PrimitiveSet` (cached, or live-resolved
and cached on the fly) appear.

### Contract-ownership + Integrity Health reads: `GET /v1/agent/{id}/contracts`, `/baas`

`/contracts` returns the `IntegrityMarket` clones an agent deployed and owns
(`MarketFactory.getMarketsByCreator` on its `SovereignAgent`, then live per-market
reads). `/baas` enumerates the `SmartBAA` escrows where the agent is the business
associate, from `SmartBAAFactory.BAACreated` logs (no reverse index exists on-chain,
so the event log is the only enumeration path) + each escrow's live status. Both are
real on-chain reads; `/baas` returns a clean `MissingSingleton` (400) where the Integrity Health
`SmartBAAFactory` isn't deployed.

### Verifiable Credentials: `GET /v1/agent/{id}/vc`

Issues a signed **W3C Verifiable Credential** (`AgentIntegrityCredential`) for the
agent's current AIS + verification tier — a real Ed25519 `Ed25519Signature2020` proof
over the canonicalized credential, signed by the oracle's issuer key (`crate::vc`,
`VC_ISSUER_SEED` env, `did:key` issuer). Not a mock: the returned JSON-LD credential is
independently verifiable against the issuer's public key. Consumed by the dashboard's
`DIDExplorer`.

### Network benchmarks + protocol stats: `GET /v1/benchmarks`, `/v1/stats`

`/benchmarks` aggregates network-wide telemetry per model (`db::benchmark_by_model`,
`GROUP BY payload->>'model' HAVING COUNT >= 3`) into a per-model/provider stability +
grounding benchmark (a simulated AIS from the same entropy/grounding math scoring-core
uses). `/stats` is the minimal protocol-wide singleton supplement the dashboard can't
cheaply derive from its per-agent loop: marketplace volume (sum of cached market
`total_staked`) + `A2ACapitalPool` escrow/release totals; `tvl` is composed client-side
for a single source of truth.

### XNS resolution: `GET /v1/xns/resolve?handle=<h>`, `GET /v1/agent/{id}/handle`

Live reads of the `XibalbaNameService` singleton. `/xns/resolve` maps a human handle →
`SovereignAgent` (and, best-effort via `db::did_by_sovereign_agent`, the reverse DID);
`resolve_handle` gates on `handleExists` first since the contract's `resolve()` reverts
on an unclaimed handle, so an unregistered handle returns a null address, not an error.
`/agent/{id}/handle` is the reverse: an agent's `primaryHandle`. Both return
`MissingSingleton` (**HTTP 400**) until XNS is deployed on the target network — an honest
"not deployed", never a fabricated handle. Consumed by `XNSSearchService` + `DIDExplorer`.

### Governance: `GET /v1/governance/proposals`

Live enumeration of `IntegrityGovernance` proposals by index (`ChainClient::read_proposals`:
`proposalCount()` then `getProposal(i)` + `state(i)` for `i in 1..=count`, 1-based,
newest-first — an index loop, deliberately not log-scanning). Each DTO carries proposer,
target, FOR/AGAINST tallies (decimal-string wei of ITK), the timelock ETA, and the
derived `state` (`Active`/`Defeated`/`Succeeded`/`Queued`/`Executed`/`Expired`/`Canceled`).
Returns `MissingSingleton` (**HTTP 400**) until `IntegrityGovernance` is deployed; the
dashboard's `GovernancePanel`/`GuardianPilot` degrade to their honest "Not Yet Live"
state on that (never a live-but-empty proposal list). See [Governance](../concepts/governance.md).

### `GET /v1/agent/{id}/wallet`

Real `IntegrityToken.balanceOf(sovereignAgent)` read (decimal string), plus open
positions: a real `getPosition` read against every cached market for that agent's
`SovereignAgent` address, filtered to `amount > 0 && !claimed`. **Documented gap:**
`transaction_history` is always `null` — transfer/stake/payout history requires
indexing on-chain events (`Transfer`, `PositionEntered`, `PayoutClaimed`, ...), not
built this pass.

### Server-side telemetry-signal re-derivation (`derive.rs`)

`POST /v1/telemetry/ingest` does not trust a client's self-reported
`derived_signals` — it independently recomputes entropy/grounding/sacrifice
server-side from the same signed request's raw `otel_spans` content
(`backend/src/derive.rs`, mirroring `integrity_sdk/telemetry/derive.py`'s
algorithms closely enough that results agree), and derives compliance
separately via a live on-chain "wins" check. Only the oracle's own
recomputation feeds `telemetry_events`/[AIS](../concepts/ais.md) — the
client's claim is stored purely as an audit-trail comparison. Two
polarity/calibration bugs were fixed at this exact call site in the same
pass: `performance_variance` was receiving the SDK's stability-score
polarity (1.0=best) into a column `scoring-core` treats as a true variance
(0.0=best) — backwards for every agent until fixed; and `gpu_hours_verified`
now receives an hours-equivalent proxy rather than a pre-normalized `[0,1]`
index, removing a double-log-compression that capped max-sacrifice agents
around ~100/1000 instead of ~1000. Full pipeline-order writeup (this is
step 5 of an 11-step ordered handler sequence — PHI scan, agent lookup,
rate limit, and signature verification all run first):
[Telemetry Ingestion Pipeline](../concepts/telemetry-ingestion.md). Formula
and trust-model detail: [AIS](../concepts/ais.md).

### The OTLP/gRPC path (`otlp.rs`) — separate from telemetry_events, unauthenticated

Lights up the SDK's already-real `OTLPSpanExporter`/`OTLPMetricExporter`
(`telemetry/core.py::init_telemetry`, gRPC `localhost:4317`), which
previously exported into a void — nothing listened on that port. Real spans
arrive with **no Ed25519/secp256k1 signature envelope** (unlike
`POST /v1/telemetry/ingest`), so this deliberately does NOT touch
`telemetry_events`/AIS — feeding unauthenticated spans into scoring would
let anyone move an agent's score. Trace export is fully implemented
(PHI-scanned via the same `crate::phi` backstop, persisted to a separate
`otel_spans` table, broadcast over SSE); metrics export is accepted (so the
SDK's metric exporter gets a real gRPC response) but not yet parsed or
persisted.

### PHI backstop on `POST /v1/telemetry/ingest`

`src/phi.rs` mirrors `integrity-sdk/integrity_sdk/security/redactor.py`'s regex
categories (`PRIVATE_KEY`, `API_KEY`, `SSN`, `CREDIT_CARD`, `EMAIL`, `PHONE`, `MRN`)
as a server-side defense-in-depth backstop: it recursively scans every JSON **string**
leaf in `otel_spans` (and an optional `judge_evaluation`), and rejects (`400`,
`AppError::PhiDetected`) if any raw, unredacted pattern is found — belt-and-suspenders
for a buggy/bypassed client, never a replacement for the SDK's own client-side
redaction. Runs before any DB/RPC work in `ingest_telemetry`, so it fails fast. Only
string values are scanned (numeric/structural fields are skipped) — the SDK's redactor
never touches those either, so scanning them here would just produce false positives
on values nobody was ever going to redact.

### Judge evaluations (storage only — no judge implementation)

`TelemetryIngestRequest.judge_evaluation` (optional) persists into the new
`judge_evaluations` table (`run_id`, `judge_model`, `verdict`, `score`,
`rationale_summary`, linked to the telemetry event). **Deliberately NOT part of the
signed envelope** — `ingest_telemetry`'s `signable` JSON (what `crypto::verify_agent_signature`
checks) does not include this field, so adding a judge evaluation never requires a
client to re-sign, and no existing client's signature breaks. It rides along as an
unauthenticated sidecar on an otherwise-authenticated request. No judge/rubric
implementation exists anywhere in this codebase — this is plumbing only, per the task
scope (a Xibalba Solutions product decision not yet made).

## On-chain client (`chain.rs`)

Read-only via `alloy` (stored as `DynProvider` so `sol!` bindings work): resolves
an agent's `PrimitiveSet`, reads `ReputationRegistry.effectiveScore`/`isZkBoosted`,
`ComplianceGate.vertical`/`isHealthcareCompliant`, `MarketFactory` enumeration,
per-market `IntegrityMarket` view state, `getPosition`, `IntegrityToken.balanceOf`,
`SmartBAAFactory`/`SmartBAA` (Integrity Health), and — new — `XibalbaNameService`
(`resolve_handle`/`primary_handle`) and `IntegrityGovernance` (`read_proposals`).
Optional singleton addresses (`MarketFactory`, `IntegrityToken`, `A2ACapitalPool`,
`SmartBAAFactory`, `XibalbaNameService`, `IntegrityGovernance`) are `Option<Address>`
in the deployments-file parse (`Singletons`), not required: a deployments file that
predates any of them still parses, and handlers needing an absent one return a clean
`ChainError::MissingSingleton` — mapped to **HTTP 400** in `error.rs` (a deployment-shape
fact, not a transient RPC failure), shared across the market/health/XNS/governance
endpoints — instead of this client failing to even connect.

## Anchoring

Telemetry leaves batched into a keccak256 [Merkle tree](../concepts/merkle-batching.md);
because `StateAnchor` is per-agent, the same epoch root is submitted to each
participating agent's own `StateAnchor` clone — a documented gas tradeoff.

## Canonical JSON signing — real cross-language bug fixed 2026-07-11

`crypto::canonical_json_bytes` (the byte representation `ingest_telemetry`
verifies an agent's telemetry-envelope signature against) used
`serde_json`'s default compact formatter, which emits non-ASCII string
content as raw UTF-8. Every producer this oracle must verify against
(`integrity-sdk/integrity_sdk/bcc.py`, `bcc_middleware/app/canonical.py`)
instead pins Python's `ensure_ascii=True` (non-ASCII escaped as `\uXXXX`,
surrogate pairs for astral code points) — both modules' own docstrings
explicitly warned a Rust implementation using a different default here
would produce a different signature, and this one did. Was masked until
now because nothing successfully reached signature verification at all
(see [integrity-sdk](integrity-sdk.md)'s matching fix — the SDK's own
request used to fail JSON deserialization before ever reaching this check).
Fixed with a custom `AsciiEscapingFormatter` overriding only
`write_string_fragment` (the rest of `serde_json::ser::Formatter`'s default
methods, which `CompactFormatter` also just uses unmodified, are
inherited).

**Second fix (2026-07-30):** The float re-serialization bug. While the ASCII fix handled strings, `serde_json` by default parses floating-point numbers into 64-bit floats (`f64`) and then re-serializes them. This caused complex latency numbers (e.g., `1785382891.2774885`) sent by the Python client to be subtly reformatted by Rust's `Ryu` float formatter, breaking the signature verification on full telemetry syncs. Fixed by:
1. Modifying `ingest_telemetry` to extract the signable payload from the exact, raw parsed JSON `serde_json::Value` (by stripping `signature` and `judge_evaluation`) rather than rebuilding the object via `serde_json::json!({})`.
2. Enabling the `arbitrary_precision` feature in `serde_json`, which forces the JSON parser to treat all numbers as opaque strings during deserialization and preserve their exact literal representations during canonical re-serialization, guaranteeing a byte-for-byte match with Python.

## State

**80 backend + scoring-core lib tests** (confirmed via a real run — 72
backend, 8 scoring-core; up from 54 with the `derive.rs` re-derivation
module's own parity-with-`derive.py` unit tests among the additions),
including `src/phi.rs` unit tests covering
every PHI category, the already-redacted-marker non-reflag case, and the
numeric-vs-string-field scan boundary), plus a real full-stack e2e (`tests/e2e.rs`,
**9 tests**, opt-in via `ORACLE_E2E=1`) that stands up live anvil + `Deploy.s.sol` (which now
deploys the market layer as part of genesis) + a real SDK-registered agent + Postgres
+ Redis + the HTTP server, and asserts accept-correct / reject-fabricated primitives,
AIS scoring, the live compliance read, a real (empty, pre-any-market) `GET
/v1/markets`, a real one-entry `GET /v1/leaderboard`, a real `GET
/v1/agent/{id}/wallet` balance read, the PHI backstop's real HTTP-level 400, and —
new — `oracle_e2e_recomputed_grounding_overrides_inflated_client_claim`, proving an
agent that claims an inflated grounding score while its own signed `otel_spans`
contain hallucination markers gets the oracle's real, low recomputation stored and
scored, never the client's claim.
**Documented follow-up, not built this pass:** a full market lifecycle e2e
(`enterPosition`/`resolve`/`claimPayout` through a second real registered agent) —
out of scope for this task; the light e2e above proves the real binding/parse/handler
path without that heavier setup.

Related: [Telemetry Ingestion Pipeline](../concepts/telemetry-ingestion.md),
[AIS](../concepts/ais.md),
[agent primitives](../concepts/agent-primitives.md),
[Interface Contract](../../INTERFACE_CONTRACT.md).
