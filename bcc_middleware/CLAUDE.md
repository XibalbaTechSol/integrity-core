# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FastAPI service implementing the "Behavioral Commitment Chain" (BCC) — the
pre-execution policy gate of Integrity Protocol. Agents (via `integrity-sdk`
/ `integrity-cli`) POST a signed intent commitment to `POST /v1/bcc/intercept`
before executing an action; this service authorizes or denies, then the
agent proceeds only on authorization. It also runs a periodic background loop
that pushes oracle-computed reputation scores on-chain and raises slashing
disputes — the only place in the monorepo that closes that loop (see
`app/reputation.py`'s module docstring).

Sibling packages: see `/home/xibalba/Projects/integrity-core/CLAUDE.md` for
the full monorepo. `docs/INTERFACE_CONTRACT.md` at the repo root is the
binding cross-package spec (§4.2 commitment schema, §6 deployments file, §7
OPA integration) — read it before changing any schema/endpoint/env var this
package shares with `integrity-sdk`, `integrity-cli`, `integrity-oracle`, or
`contracts`.

## Commands

```bash
uv sync                                          # install deps
cp .env.example .env                             # then edit as needed

opa run --server --addr=127.0.0.1:8181 policies/ # 1. real OPA server
anvil --port 8545                                # 2. local chain (for BAA check / anchoring)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000   # 3. the service

opa test policies/ -v                            # 28 OPA policy unit tests
uv run pytest -q                                 # 75 tests — see below
uv run pytest tests/test_merkle.py::test_name    # single test
```

The pytest suite is self-contained: `tests/conftest.py`'s `anvil_chain`
fixture starts its own throwaway `anvil` subprocess per session and deploys
fixture contracts (`tests/fixtures/foundry/src/Mock{BAARegistry,StateAnchor,
ReputationRegistry,Slasher}.sol`, compiled via a real `forge build`) against
it; `real_opa_server` / `always_allow_requires_baa_opa_server` fixtures start
real `opa run --server` subprocesses loaded with either the actual
`policies/*.rego` or a trivial throwaway policy. You do **not** need OPA or
anvil already running to run `pytest` — only to run the service itself.
`forge` and `opa` binaries must be on `PATH` for the fixture-contract build
and the OPA subprocess to work.

Docker: `docker build -t bcc-middleware .` matches the root
`docker-compose.yml`'s `bcc-middleware` service (port 8000, depends on `opa`
and `oracle-backend`).

## Architecture

### Request pipeline (`app/main.py::run_intercept`)

`POST /v1/bcc/intercept` runs a fixed, ordered gauntlet — each stage is
cheapest-and-most-certain-first:

```
0. pydantic schema validation (app/schemas.py)
1. circuit breaker check (app/circuit_breaker.py)   -- cheap, no I/O, checked first
2. Ed25519 signature verification (app/canonical.py) -- untrusted agent_id -> hard deny
3. nonce replay check (app/nonce_store.py)           -- monotonic per-agent nonce
4. freshness / timestamp window check
4b. active quarantine check (app/quarantine.py)      -- denies only on a POSITIVELY
    CONFIRMED locked-stake dispute; fails OPEN (unlike step 6) since it runs on every
    request, not just a narrow intent class -- see app/quarantine.py's docstring
5. OPA policy evaluation (app/opa_client.py)         -- FAIL CLOSED if OPA unreachable
6. on-chain BAA check, only if OPA says requires_baa -- FAIL CLOSED if can't verify
   (app/baa.py, real eth_call via web3.py)
7. admit to Merkle batch + best-effort on-chain anchor -- NOT a gate (app/merkle.py, app/anchor.py)
```

**The one property to preserve in any change here: fail-closed vs.
best-effort.**
- Steps 5–6 are *authorization* decisions. Any failure to positively confirm
  "allowed" / "BAA active" — OPA down, malformed response, chain RPC down,
  contract not deployed — **denies** the request. There is no error path
  that approves.
- Step 7 (Merkle anchoring) runs *after* authorization is already decided.
  Its failure is logged/retried, never surfaced as a denial of an
  already-authorized action.
- The circuit breaker (`app/circuit_breaker.py`) only counts violations
  *attributable to the agent* (bad signature, replay, an actual OPA denial,
  an inactive BAA). Infra being down (OPA/chain unreachable) denies the
  request but never trips the breaker — otherwise an OPA outage would lock
  out every well-behaved agent.

Every deny path encodes its reason as `SOME_CODE: detail` in the response
`reason` field (`BCC_INVALID_SIGNATURE`, `BCC_NONCE_REPLAY`, `BCC_EXPIRED`,
`AGENT_QUARANTINED`, `BCC_POLICY_ENGINE_UNAVAILABLE`,
`OPA_REJECTION`, `BAA_INACTIVE`, `BAA_CANNOT_VERIFY`, `CIRCUIT_BREAKER_OPEN`) so
callers/tests can pattern-match on failure category.

### Reputation sync loop (`app/reputation.py`, `app/scoring_loop.py`)

A background asyncio task (started in `app/main.py`'s lifespan, interval
`SCORE_SYNC_INTERVAL_SECONDS`) that lists every agent from the oracle
(`GET /v1/agents`), and for each: pushes its oracle-computed AIS base score
to that agent's `ReputationRegistry` clone via a real signed
`updateScore(agent, baseScore)` tx, and — if the oracle's flagged-telemetry
ratio for that agent crosses `DISPUTE_FLAGGED_RATIO_THRESHOLD` over the
lookback bucket — raises a `Slasher.raiseDispute(...)` tx (subject to a
per-agent cooldown). `POST /v1/reputation/sync` triggers one cycle manually
(ops/test hook). This lives in `bcc_middleware` rather than a new service
because on today's single-operator testnet deployment, the oracle-signer,
disputer, and this service's existing `ANCHOR_SIGNER_PRIVATE_KEY` are the
same key — see `app/reputation.py`'s module docstring for the full
reasoning, including why automated dispute-raising is safe (raising only
*locks* stake; a separate arbiter role is required to actually resolve/burn).
`base_score` pushed must be the Oracle-authoritative, tier-capped AIS with only
the response's reported ZK multiplier divided out. Never reconstruct it from
`components`/`weights`: `integrity-oracle/scoring-core` is the sole geometric
formula implementation — see `scoring_loop.py::_base_score_from_ais_response`.

### Config (`app/config.py`)

Single `Settings` dataclass, entirely env-var driven (`.env` via
`python-dotenv` for local dev), see `.env.example` for the full set and
defaults. `Settings.contract_address(name)` resolves a deployed address from
`DEPLOYMENTS_FILE` (default `../deployments.local.json`), checking
`singletons` → `cloneTemplates` → legacy flat `contracts` in that order.
Per-agent primitive instances (a given agent's own `ReputationRegistry`,
`StateAnchor`, `Slasher` clones) are deliberately **not** in that file —
they're resolved live via the oracle (`app/chain.py::resolve_agent_primitives`),
since the protocol's clone-per-agent model means there's no single static
address for these.

### State is in-memory, single-process (accepted, not a bug)

`nonce_store.py`, `circuit_breaker.py`, and `scoring_loop.py`'s dispute
cooldown all hold process-local state. Fine for the current single-replica
dev/demo topology; a multi-replica deployment should move this to Redis
(already present in the broader docker-compose topology for
`integrity-oracle`).

## Integration contracts worth knowing before touching schema/chain code

- **Signature covers canonical JSON** (`json.dumps(fields, sort_keys=True,
  separators=(",", ":"), ensure_ascii=True)`) — must byte-for-byte match
  `integrity-sdk`/`integrity-cli`'s canonicalization (`app/canonical.py`).
- **DID → pubkey binding**: the commitment carries a signed
  `agent_public_key` (multibase); `canonical.py::public_key_from_commitment`
  checks `sha256(pubkey) == agent_id` before trusting it — this makes each
  commitment self-verifying with no external DID-resolution round-trip.
- **BAA check is keyed on `(coveredEntity, businessAssociate)`**, where
  `businessAssociate` is the agent's `SovereignAgent` contract address (not
  its EOA, not a pubkey derivation) — resolved via the oracle. `BAA_CONTRACT_NAME`
  must point at the deployed `SmartBAAFactory` (implements `isBAAActive`),
  not a per-pair `SmartBAA` escrow instance. See `app/baa.py`'s module
  docstring for the history of a since-fixed signature mismatch bug here.
- **Merkle leaf encoding**: `keccak256(abi.encodePacked(agent_id,
  intent_type, intended_state_hash, nonce, timestamp))`, sorted-pair parent
  hashing with odd-node duplication (OpenZeppelin convention) — must match
  `integrity-oracle`'s `merkle.rs` and `contracts`' `StateAnchor.sol`
  bit-for-bit (`app/merkle.py`).
- **Healthcare-vertical intent types** (`EMR_WRITE`, `DISPENSE_MEDICATION`,
  `BILLING_SUBMISSION`, `SECURE_EMR_WRITE`, `CLINICAL_DATA_ACCESS`) are what
  trigger the on-chain BAA gate in `policies/bcc.rego` — there's no separate
  "vertical" field in the commitment schema.
- **Clinical agent allowlist is data-driven**: `policies/bcc.rego`'s
  `authorized_clinical_agents` unions a small static demo set with a runtime
  `data.clinical_allowlist.agents` document loaded alongside the policy
  (`opa run --server policies/ <data.json>`) — extend via that data document,
  not by editing the policy file.

Full reconciliation history/details (numbered list of every cross-package
ambiguity and how it was resolved) live in `README.md`'s "Integration
reconciliation" section — read it before changing `app/canonical.py`,
`app/baa.py`, `app/merkle.py`, or `policies/bcc.rego`.
