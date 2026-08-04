# integrity-oracle

The off-chain brain of the Integrity Protocol: it ingests agent telemetry,
computes the **Agent Integrity Score (AIS)**, and independently verifies agents'
on-chain state so nothing downstream has to trust an agent's own word. Rust, Axum,
Postgres, Redis, with `alloy` for on-chain reads.

> Ground rule (repo-wide): **no silent mocks.** See
> [`../docs/INTERFACE_CONTRACT.md`](../docs/INTERFACE_CONTRACT.md).

## Workspace

A two-crate Cargo workspace, deliberately split so the scoring formula stays
trivially auditable and testable in isolation:

- **`scoring-core/`** — dependency-free (only `serde`). The **one and only** place
  the AIS formula is computed anywhere in the monorepo. Every other package reads
  the oracle's HTTP API rather than re-deriving the math.
- **`backend/`** — the Axum HTTP server, Postgres persistence, Redis rate
  limiting, ZK proof verification (shells to `bb verify`), Merkle tree building,
  and the `alloy` on-chain read client.

## The AIS formula (`scoring-core`)

```
AIS = (S_entropy·wE + S_grounding·wG + S_sacrifice·wS + S_compliance·wC) · ZK_boost
```

Default weights `wE=0.30, wG=0.30, wS=0.20, wC=0.20` (validated to sum to 1.0,
configurable via `AIS_WEIGHTS`). Each `S_*` is normalized to `[0, 1000]`;
`ZK_boost = 1.15` when a real Barretenberg proof was verified in the reporting
period. The final score is intentionally **not** clamped — a fully-boosted top
performer can exceed 1000. See
[`../docs/wiki/concepts/ais.md`](../docs/wiki/concepts/ais.md).

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/agent/register` | Register an agent — **re-verifies the claimed 7 primitives against on-chain `XibalbaAgentRegistry`, rejecting any mismatch** |
| `GET` | `/v1/agent/{id}` | Agent record + primitives (Postgres cache, backfilled from chain on miss) |
| `GET` | `/v1/agents` | List agents |
| `GET` | `/v1/agent/{id}/ais` | Full AIS breakdown (components, weights, ZK boost) |
| `POST` | `/v1/telemetry/ingest` | Ingest OTel spans + derived signals + optional ZK proof; nonce-replay-protected |
| `GET` | `/v1/agent/{id}/compliance` | Live `ComplianceGate` read (Integrity Health vertical status) |
| `GET` | `/healthz` | Liveness |

### Why register re-verifies on-chain

The self-sovereign model is only honest if the oracle doesn't just record whatever
a client claims. `POST /v1/agent/register` independently calls
`XibalbaAgentRegistry.resolveDID` and rejects the request (`400 ChainMismatch`) if
the POSTed primitive addresses don't match what the chain actually recorded. This
is the crux that makes "the chain is the source of truth" real rather than
decorative.

## On-chain client (`backend/src/chain.rs`)

Read-only, via `alloy` (the actively-maintained successor to `ethers-rs`). It
resolves an agent's 7-address `PrimitiveSet` from `XibalbaAgentRegistry`, reads
`ReputationRegistry.effectiveScore`/`isZkBoosted`, and reads
`ComplianceGate.vertical`/`isHealthcareCompliant`. The provider is stored as
`alloy::DynProvider` (a `Sized`, type-erased provider) so `sol!`-generated
contract bindings can use it. No wallet/signing in this phase — the oracle only
reads.

## Merkle anchoring

Telemetry leaves are batched into a `keccak256` Merkle tree (sorted-pair
convention, matching `StateAnchor.sol` bit-for-bit — see
[`../docs/wiki/concepts/merkle-batching.md`](../docs/wiki/concepts/merkle-batching.md)).
Because `StateAnchor` is now **per-agent**, the oracle builds one tree per epoch
across agents but submits the same root to each participating agent's own
`StateAnchor` clone — a real gas tradeoff, documented rather than hidden.

## Run

```bash
# Dependencies
docker compose up -d postgres redis          # from repo root

# Env (see backend/src/config.rs for the full set)
export DATABASE_URL=postgres://integrity:integrity_dev_only@127.0.0.1:5432/integrity
export REDIS_URL=redis://127.0.0.1:6379
export RPC_URL=http://127.0.0.1:8545
export DEPLOYMENTS_FILE=../deployments.local.json
export BIND_ADDR=0.0.0.0:8080

cargo run --bin oracle-backend
```

Migrations (`backend/migrations/0001_init.sql`) run automatically at boot,
creating `agents`, `agent_primitives`, `telemetry_events`, `merkle_roots`.

## Test

```bash
cargo test --workspace --lib      # 29 backend + 8 scoring-core, all green
```

### Real end-to-end test (opt-in)

`backend/tests/e2e.rs` stands up the **full real stack** — a live anvil running
`Deploy.s.sol`, a real agent registered on-chain via the real `integrity-sdk`
flow, real Postgres + Redis, and the real Axum server over HTTP — then asserts:
register-with-correct-primitives is accepted, register-with-fabricated-primitives
is rejected, AIS scoring works, and the live compliance read returns `healthcare`.

```bash
ORACLE_E2E=1 \
  TEST_DATABASE_URL=postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity \
  TEST_REDIS_URL=redis://127.0.0.1:6379 \
  cargo test --test e2e
```

It's opt-in (needs Postgres+Redis+anvil+forge+the SDK venv); a bare `cargo test`
skips it with a logged note rather than failing.

## Layout

```
scoring-core/src/lib.rs      the AIS formula (37 tests total incl. backend)
backend/src/
  main.rs / lib.rs           boot + router + AppState
  config.rs                  env config (+ from_env_for_test)
  chain.rs                   alloy read client
  handlers.rs / routes.rs    the 6 endpoints
  db.rs                      sqlx persistence
  merkle.rs / zk.rs          Merkle tree + bb-verify
  crypto/                    ed25519 + eip191 signature verification
  migrations/0001_init.sql
  tests/e2e.rs               real full-stack e2e
```
