# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Integrity Protocol — a trust/compliance layer for AI agents on Base L2. Agents deploy and own
their own identity/reputation contracts (no privileged factory registers on their behalf); an
oracle computes a reputation score (AIS) from off-chain telemetry, boostable via a real Noir/
Barretenberg ZK proof; a policy middleware gates risky actions pre-execution. "Xibalba Shield"
is the HIPAA/healthcare vertical built on top of the same primitives.

This is a from-scratch rewrite of an earlier prototype. Ground rule, repeated in nearly every
contract's NatSpec and worth internalizing before touching anything: **no silent mocks** — every
piece is real and tested, or an honestly documented gap (see `PRODUCTION_GAPS.md`). The
predecessor mocked ZK proving/TEE attestation/policy evaluation while documenting them as real;
this rewrite's entire point is not repeating that.

## Repository structure

A single git repo at the root (`github.com/XibalbaTechSol/integrity-latest`), but still a
Makefile-orchestrated set of independently versioned packages, each with its own dependency
lockfile (`.venv`/`uv.lock`, `node_modules`, `Cargo.lock`) — there's no root-level package
manifest tying them together, only the `Makefile`. `contracts/lib/forge-std` is a real git
submodule (`.gitmodules`); everything else is a plain tracked directory. No CI exists yet —
`make test` / `make test-e2e`, run by a human or agent before calling a change done, is the
enforcement mechanism (see `docs/TESTING.md`).

| Package | Stack | Role |
|---|---|---|
| `contracts/` | Foundry/Solidity 0.8.28 | On-chain primitives, registries, markets, Shield (HIPAA) contracts |
| `integrity-zkp/` | Noir + Barretenberg | The real ZK circuit backing on-chain reputation-boost proofs |
| `integrity-oracle/` | Rust/Axum (Cargo workspace) | Reads chain state, computes AIS, serves telemetry/market/leaderboard API |
| `integrity-sdk/` | Python | Agent-facing SDK: identity, wallet, BCC commitments, ZK proving, telemetry |
| `integrity-cli/` | Python/Typer | Developer CLI — independent reimplementation of SDK's core flows, not a wrapper around it |
| `bcc_middleware/` | Python/FastAPI + OPA | Pre-execution policy gate agents call before acting on an intent |
| `integrity-userapi/` | Python/FastAPI + Postgres | User-account service, deliberately isolated trust domain from the oracle's DB |
| `integrity-dashboard/` | React/Vite/TS | Dashboard frontend — see "Known gaps" below, much of it is still mock data |
| `docs/wiki/` | Markdown | Compiled long-term memory; governed by `.agents/AGENTS.md` |

Read `.agents/AGENTS.md` before any session that materially changes code — it defines a
read→work→write→lint loop against `docs/wiki/` and a continuous test-coverage loop (dispatch
background agents to close test gaps with real tests, not placeholders). Read
`docs/INTERFACE_CONTRACT.md` before changing any cross-package schema, port, or env var — it's
the pinned toolchain/contract source of truth (forge/anvil 1.7.1, cargo/rustc 1.96.0, nargo
1.0.0-beta.22, bb 5.0.0-nightly, opa 1.18.2, node/npm 22.x/10.x, python/uv 3.12/0.11).

## Common commands

Root `Makefile` targets (each just `cd`s into a package and runs its native tool):

```bash
make setup      # install every package's dependencies
make chain      # start a local anvil chain + run contracts/script/Deploy.s.sol against it
make sync-abis  # forge build, then trim ABIs into scripts/sync_abis.py's output for Python callers
make up         # docker-compose: postgres, redis, opa, oracle-backend, bcc-middleware, dashboard, userapi(+its own postgres)
make test       # every package's real test suite (forge/nargo/cargo/pytest x4/npm)
make test-e2e   # real-browser Playwright e2e against a freshly booted stack (integrity-dashboard)
make demo       # integrity-dashboard/demo scenario engine against live Base Sepolia by default — needs FUNDER_PRIVATE_KEY + INTEGRITY_WALLET_PASSWORD
```

Per-package, when iterating on one piece:

```bash
# contracts/  (Foundry, solc 0.8.28, via_ir=true)
cd contracts && forge build
cd contracts && forge test                      # 165 tests
forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast --verify       # genesis deploy
forge script script/DeployMarkets.s.sol --rpc-url base_sepolia --broadcast --verify # incremental app-layer deploy

# integrity-zkp/  (Noir + Barretenberg)
cd integrity-zkp && make test              # nargo test — fast, no bb, CI-safe
cd integrity-zkp && make build             # test + prove + verify + solidity-verifier, full pipeline
                                            # individual targets: compile, execute, vk, prove, verify, solidity-verifier

# integrity-oracle/  (Cargo workspace: scoring-core + backend)
cd integrity-oracle && cargo build
cd integrity-oracle && cargo run --bin oracle-backend   # needs DATABASE_URL, REDIS_URL env vars minimum
cd integrity-oracle && cargo test --workspace --lib     # 37 tests (29 backend + 8 scoring-core)
ORACLE_E2E=1 cargo test --test e2e                      # opt-in, needs a real TEST_DATABASE_URL/TEST_REDIS_URL

# integrity-sdk/, integrity-cli/, bcc_middleware/, integrity-userapi/  (uv-managed Python)
cd <pkg> && uv venv .venv && uv pip install -e ".[dev]"
cd <pkg> && .venv/bin/python -m pytest tests/          # sdk: 97 tests, cli: 49 tests, bcc_middleware: 49 tests
cd bcc_middleware && opa test policies/ -v             # 12 OPA policy tests, separate from pytest

# integrity-dashboard/  (Vite/React 19/TS)
cd integrity-dashboard && npm run dev
cd integrity-dashboard && npm run build     # tsc -b && vite build
cd integrity-dashboard && npm run lint      # oxlint
```

To run a single test: `forge test --match-test <name>` / `forge test --match-contract <Contract>`;
`nargo test <name>`; `cargo test <name>`; `pytest tests/test_file.py::test_name`.

## Architecture

### On-chain: per-agent clones, not a global singleton

Not a classic upgradeable-proxy system. `AgentPrimitivesFactory` clones (EIP-1167) 5 shared
implementation contracts per agent — `ReputationRegistry`, `Slasher`, `VerifierRegistry`,
`ComplianceGate`, `AgentProfile` — then atomically registers all 7 addresses (those 5 clones +
the agent's own directly-deployed `SovereignAgent` and `StateAnchor`) into
`XibalbaAgentRegistry`, the canonical DID↔primitive-set index every downstream contract
(`EHRGate`, `IntegrityMarket`, `A2ACapitalPool`, `CCIPReputationBridge`) resolves through live,
rather than holding a single global registry address. `contracts/foundry.toml` sets
`via_ir = true` specifically because `registerPrimitives` clones+initializes 5 contracts in one
call and hits stack-too-deep otherwise.

Contract groups: `core/` (`SovereignAgent`, `IAccount`), `framework/` (registry/factory/profile/
domain/name-service), `oracle/` (reputation, slashing, ZK verifier plumbing, $ITK token, CCIP
bridge), `markets/` (agent-owned prediction markets + capital pool), `shield/` (HIPAA vertical:
`ComplianceGate`, `CoveredEntityRegistry`, `EHRGate`, `SmartBAA(Factory)`,
`HIPAAGuardrailRegistry`).

`UltraPlonkVerifier.sol` is an explicit placeholder that reverts (fails *closed*) until replaced
wholesale by `make generate-verifier`, which runs `integrity-zkp`'s `bb write_solidity_verifier`
pipeline — comment in the file says "WILL BE REPLACED WHOLESALE, NOT EDITED."

### Persistent memory is a foundational primitive (spec v0.3 §4.1) — it gates registration

Memory is not a convenience layer here; it ranks with identity, commitment, stake, and
observability. **An agent with no anchored memory cannot register.** Every agent must
anchor a *genesis memory root* on its own `StateAnchor` — signed by the agent's controller,
never by the protocol — and the oracle independently re-reads `StateAnchor.latestRoot` on
`POST /v1/agent/register`, refusing a zero root with `400 MemoryNotInitialized`
(`ChainClient::memory_state` → `AppError::MemoryNotInitialized`). `integrity-sdk`'s
`registration.py` does this as step 8b, *before* `registerPrimitives`, per the spec's
required ordering.

Note it needs no 8th contract — the PrimitiveSet stays 7 addresses, and memory rides on
`StateAnchor` (primitive #2). Agent-authorized genesis works because `StateAnchor`'s admin
*is* the `SovereignAgent`, which the constructor grants `ANCHOR_ROLE`. The empty-vault
sentinel `keccak256("integrity.trust-vault.genesis.v1")` is pinned in
`docs/INTERFACE_CONTRACT.md` §4.4a — derive it, never copy the hex.

Two things remain open and are recorded in `PRODUCTION_GAPS.md` §19: contract-level
enforcement that `ANCHOR_ROLE` cannot anchor epoch 1 (blocked because `StateAnchor` is
deployed *per agent*, so a contract change reaches only future agents), and lineage
attestation. All 7 agents registered before this change still report `latestRoot == 0`.

### ZK proof pipeline (the reputation boost)

`integrity-zkp/src/main.nr` is the real circuit ("Intent/Key Binding"): proves (1) the prover
holds the secret behind the agent's published `agent_id_commitment`, and (2) that secret + a
specific intent payload + a BCC nonce reproduce a public `intent_commitment` — both via Pedersen
hashes, without revealing the secret or full payload. `secret_key` is a KDF'd stand-in for the
real Ed25519 seed (documented scope limitation, not a mock — full in-circuit Ed25519 verification
would need a bignum/foreign-field library).

Flow: agent (`integrity-sdk`'s `prover.py`) runs `nargo execute` + `bb prove` → calls
`ReputationRegistry.submitZkAttestation(agent, proof, publicInputs, root, leaf, merkleProof)`
(only `msg.sender == agent`, to block cross-agent replay) → contract checks the leaf against an
oracle-anchored Merkle root via `StateAnchor.verifyLeaf`, then checks the proof via
`IZkVerifier.verify` (indirected through `VerifierRegistry` for per-agent verifier-version
pinning) → on success sets a 7-day `zkBoostExpiry`. `effectiveScore()` returns
`baseScore * 1.15` (`ZK_BOOST_BPS = 11_500 / 10_000`) while boosted, else plain `baseScore`.
`baseScore` itself is pushed by the oracle (`ORACLE_ROLE`) or bridged cross-chain via
`CCIPReputationBridge` (the boost itself is never bridged — must be re-earned per chain).

Two other Noir packages exist and are NOT the real pipeline: `integrity-sdk/circuits/
poc_commitment/` (an earlier placeholder, same shape as the real circuit) and
`integrity-oracle/backend/tests/fixtures/zk_smoke/` (a Rust-side test fixture only).

### AIS scoring

Computed in exactly one place, `integrity-oracle/scoring-core` (deliberately dependency-free
besides `serde`, so `backend` depends on it and never the reverse):

```
AIS = (S_entropy·wE + S_grounding·wG + S_sacrifice·wS + S_compliance·wC) · ZK_boost
wE=0.30, wG=0.30, wS=0.20, wC=0.20, ZK_boost=1.15 if a real bb-verified proof is live, else 1.0
```

### Oracle service

Rust/Axum, `alloy` (not `ethers-rs` — repo comment notes ethers-rs is in maintenance mode and
alloy is Foundry's own successor lib) for **read-only** chain access — this service never signs
or submits transactions. Routes live in `backend/src/routes.rs` under `/v1/agent/*`,
`/v1/telemetry/ingest`, `/v1/markets*`, `/v1/leaderboard`. Notably, `POST /v1/agent/register`
re-verifies a client-claimed 7-address PrimitiveSet against `XibalbaAgentRegistry.resolveDID`
on-chain and rejects mismatches — this is what makes "the chain is the source of truth" real
rather than decorative. Config is entirely env-var driven (`DATABASE_URL`, `REDIS_URL`,
`RPC_URL`, `DEPLOYMENTS_FILE`, etc., see `backend/src/config.rs`) — switch `RPC_URL` +
`DEPLOYMENTS_FILE` to target Base Sepolia vs. local anvil.

### BCC signatures (shared wire format across SDK, CLI, and bcc_middleware)

A canonical-JSON, sorted-key, `ensure_ascii=True`, Ed25519-signed commitment object
(`agent_id`, `intent_type`, `intended_state_hash`, `nonce`, `timestamp`,
`covered_entity_address`, `agent_public_key`, `signature`) — the DID is `sha256(pubkey)`, so
`agent_public_key` is carried in the payload and bound (`sha256(pubkey) == fingerprint`) before
signature verification, blocking key substitution. Canonicalized identically in
`integrity_sdk/bcc.py`, `integrity_cli/bcc.py`, and `bcc_middleware/app/canonical.py`. Full
schema at `docs/wiki/concepts/bcc.md`. One documented, unfixed gap: Rust's `serde_json` doesn't
escape non-ASCII by default while the Python side's `ensure_ascii=True` does — non-ASCII
telemetry content could produce disagreeing canonical bytes between the oracle and SDK.

### SDK vs CLI

`integrity-cli` does **not** import `integrity-sdk` — it carries its own copies of identity/
wallet/chain/BCC logic, kept wire-compatible via cross-package round-trip tests. Don't assume a
change in one automatically applies to the other.

## Known gaps / things this doc's own exploration found stale — verify before relying on them

- `integrity-dashboard/package.json` has no `test` script, though root `Makefile`'s `test` target and
  `docs/TESTING.md` both invoke `cd integrity-dashboard && npm test`.
- `integrity-dashboard/demo/` (the Python scenario engine `make demo` depends on) does not exist yet on
  disk, despite being referenced by the root README, Makefile, `docs/TESTING.md`,
  `.agents/AGENTS.md`, and `docs/INTERFACE_CONTRACT.md` §11.
- `integrity-dashboard/src/services/api.ts` and `AgentContext.tsx` are currently hardcoded mock data,
  not real calls to `integrity-oracle` — despite `docs/wiki/entities/integrity-dashboard.md`
  describing a much more built-out frontend (real axios API clients, JWT auth, a Playwright
  `e2e/` suite) whose files don't currently exist in the tree. Trust the code over that wiki page
  until reconciled. No wagmi/viem/ethers wallet-connection library is present in the frontend at
  all yet.
- `contracts/.env` (populated, not just `.env.example`) exists on disk — don't commit it.

## Live deployment

Base Sepolia, chainId 84532. Singleton/clone-template addresses are in
`deployments.baseSepolia.json` at repo root (local-anvil equivalents in
`deployments.local.json`); per-agent primitive addresses are intentionally *not* in a static
file — always resolved live from `XibalbaAgentRegistry` on-chain. `FAUCET_INFO.md` lists the
operator addresses that need testnet funding. All protocol roles (arbitrator/disputer/
funderWallet/governance/oracleSigner/resolverSigner) currently point at one address — a
single-operator testnet setup, not representative of an eventual production key-separation
design.
