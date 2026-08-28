# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Integrity Protocol — a trust/compliance layer for AI agents on Base L2. Agents deploy and own
their own identity/reputation contracts (no privileged factory registers on their behalf); an
oracle computes a reputation score (AIS) from off-chain telemetry, boostable via a real Noir/
Barretenberg ZK proof; a policy middleware gates risky actions pre-execution. "Integrity Health"
is the HIPAA/healthcare vertical built on top of the same primitives.

This is a from-scratch rewrite of an earlier prototype. Ground rule, repeated in nearly every
contract's NatSpec and worth internalizing before touching anything: **no silent mocks** — every
piece is real and tested, or an honestly documented gap (see `PRODUCTION_GAPS.md`). The
predecessor mocked ZK proving/TEE attestation/policy evaluation while documenting them as real;
this rewrite's entire point is not repeating that.

## Repository structure

A single git repo at the root (`github.com/XibalbaTechSol/integrity-core`), but still a
Makefile-orchestrated set of independently versioned packages, each with its own dependency
lockfile (`.venv`/`uv.lock`, `node_modules`, `Cargo.lock`) — there's no root-level package
manifest tying them together, only the `Makefile`. `contracts/lib/forge-std` is a real git
submodule (`.gitmodules`); everything else is a plain tracked directory. GitHub Actions runs
per-package validation on pushes and pull requests to `main`; Playwright end-to-end coverage
still requires a separately booted local stack and is intentionally outside hosted CI. Local
`make test` / `make test-e2e` remain the pre-completion gates (see `docs/TESTING.md`).

| Package | Stack | Role |
|---|---|---|
| `contracts/` | Foundry/Solidity 0.8.28 | On-chain primitives, registries, markets, Integrity Health (HIPAA) contracts |
| `integrity-zkp/` | Noir + Barretenberg | The real ZK circuit backing on-chain reputation-boost proofs |
| `integrity-oracle/` | Rust/Axum (Cargo workspace) | Reads chain state, computes AIS, serves telemetry/market/leaderboard API |
| `integrity-sdk/` | Python | Agent-facing SDK: identity, wallet, BCC commitments, ZK proving, telemetry |
| `integrity-cli/` | Python/Typer | Developer CLI — independent reimplementation of SDK's core flows, not a wrapper around it |
| `bcc_middleware/` | Python/FastAPI + OPA | Pre-execution policy gate agents call before acting on an intent |
| `integrity-userapi/` | Python/FastAPI + Postgres | User-account service, deliberately isolated trust domain from the oracle's DB |
| `integrity-dashboard/` | React/Vite/TS | Dashboard frontend with mixed backend/direct-chain reads and explicit empty/unavailable states; Playwright is its current test surface |
| `docs/wiki/` | Markdown | Compiled long-term memory; governed by `.agents/AGENTS.md` |

Read `.agents/AGENTS.md` before any session that materially changes code — it defines a
read→work→write→lint loop against `docs/wiki/` and a continuous test-coverage loop (dispatch
background agents to close test gaps with real tests, not placeholders). Read
`docs/INTERFACE_CONTRACT.md` before changing any cross-package schema, port, or env var — it's
the pinned toolchain/contract source of truth (forge/anvil 1.7.1, cargo/rustc 1.96.0, nargo
1.0.0-beta.22, bb 5.0.0-nightly, opa 1.18.2, node/npm 22.x/10.x, python/uv 3.12/0.11).

Specification authority is layered: `spec/integrity-protocol-v0.4.md` is the accepted
normative baseline; `spec/integrity-protocol-v0.5-proposed.md` is the new non-authoritative
amendment under clause-level review; and `spec/integrity-protocol-v3.2.md` is the current
explanatory, non-normative whitepaper. The v3.2 PDF is generated output. Never implement or
claim a v0.5/v3.2 surface solely because the whitepaper describes it; check the proposal's
status, `docs/INTERFACE_CONTRACT.md` §16, `PRODUCTION_GAPS.md`, source, tests, and deployment.

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
cd contracts && forge test                      # 209 tests verified 2026-08-17
forge script script/Deploy.s.sol --rpc-url base_sepolia --broadcast --verify       # genesis deploy
forge script script/DeployMarkets.s.sol --rpc-url base_sepolia --broadcast --verify # incremental app-layer deploy

# integrity-zkp/  (Noir + Barretenberg)
cd integrity-zkp && make test              # nargo test — fast, no bb, CI-safe
cd integrity-zkp && make build             # test + prove + verify + solidity-verifier, full pipeline
                                            # individual targets: compile, execute, vk, prove, verify, solidity-verifier

# integrity-oracle/  (Cargo workspace: scoring-core + backend)
cd integrity-oracle && cargo build
cd integrity-oracle && cargo run --bin oracle-backend   # needs DATABASE_URL, REDIS_URL env vars minimum
cd integrity-oracle && cargo test --workspace --lib     # 130 tests (119 backend + 11 scoring-core)
ORACLE_E2E=1 cargo test --test e2e                      # opt-in, needs a real TEST_DATABASE_URL/TEST_REDIS_URL

# integrity-sdk/, integrity-cli/, bcc_middleware/, integrity-userapi/  (uv-managed Python)
cd <pkg> && uv venv .venv && uv pip install -e ".[dev]"
cd <pkg> && .venv/bin/python -m pytest tests/          # sdk: 262 passed/2 skipped, cli: 68 passed/1 skipped, bcc_middleware: 121 tests
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
bridge), `markets/` (agent-owned prediction markets + capital pool), `health/` (HIPAA vertical:
`ComplianceGate`, `CoveredEntityRegistry`, `EHRGate`, `SmartBAA(Factory)`,
`HIPAAGuardrailRegistry`).

`UltraPlonkVerifier.sol` is now the real `bb`-generated verifier (as of 2026-08-12), not the
placeholder — `integrity-zkp`'s `make solidity-verifier` / `bb write_solidity_verifier`
pipeline generated it, and `forge build` compiles it clean. No root `make generate-verifier`
target exists. The generated contract deliberately does
not formally inherit `IZkVerifier` (the generated file already carries Barretenberg's own
`IVerifier`, and adding `IZkVerifier` too causes a diamond-conflict compile error) — it's
satisfied via ABI-compatible low-level dispatch in `VerifierRegistry.sol` instead, which is
exactly what let the swap from placeholder to real verifier happen without touching any calling
contract. Four Foundry tests now exercise a checked-in real proof and reject malformed,
tampered-proof, and tampered-public-input cases. The generated source remains distinct from the
older fail-closed verifier deployed on Base Sepolia; see `PRODUCTION_GAPS.md` §26.

### The four foundational primitives

Concepts, not contracts: **memory** (continuity), **agent-owned contracts** (capability with
consequence — stake lives here), **authority** (delegated permission the agent cannot
self-grant), **reputation** (earned, non-forgeable standing). Beware the word: the *seven*
per-agent contracts (`PrimitiveSet`) are a different sense, and only the second concept is a
contract at all. A third sense also exists as of the kernel/adapter work (spec v3.2 §4.4,
`contracts/src/kernel/`): **kernel primitives** — value conservation, metered-rights
depletion, and replay-domain monotonicity, the invariants `IntegrityKernel` enforces so
adapter authors don't re-derive them. These belong to neither the four concepts nor the
seven-contract `PrimitiveSet`; `IntegrityKernel`/`IntegrityAccount` are a deliberately
separate architecture from `PrimitiveSet`/`XibalbaAgentRegistry`. See the naming box in
`docs/wiki/concepts/foundational-primitives.md` for all three spelled out together. AIS is a
score over reputation, not a primitive.

Authority is built only in the Integrity Health vertical so far — `SmartBAA` is already a delegation
instrument — and generalizing it is what closes the client-supplied `covered_entity_address`
hole. Termination (how an agent's standing ends) is formalized but deliberately unadopted: it
needs registry mutability, the same question the upgradeability decision faces.

Normative in `spec/integrity-protocol-v0.4.md` §4 (supersedes the v0.3 PDF). Wiki statement:
`docs/wiki/concepts/foundational-primitives.md`; derivation: `docs/design/primitive-set-coherence.md`.

### Persistent memory (primitive #1) — it gates registration

Memory is not a convenience layer here; it is the first of the four above, and the one the
others presuppose. **An agent with no anchored memory cannot register.** Every agent must
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

`integrity-zkp/circuit/src/main.nr` is the real circuit ("Intent/Key Binding") — as of
2026-08-18/19, `integrity-zkp` is a two-member Nargo workspace (`circuit/` + `tools/
commitment_calc/`, the latter an offline Pedersen-hash calculator `prover.py` shells out to
before it can write `circuit/Prover.toml` — see that package's own docstring for why). The
circuit proves (1) the prover holds the secret behind the agent's published
`agent_id_commitment`, and (2) that secret + a specific intent payload + a BCC nonce + `chain_id`
+ `verifying_contract` reproduce a public `intent_commitment` — both via Pedersen hashes, without
revealing the secret or full payload. `chain_id`/`verifying_contract` binding (closing
cross-deployment proof replay, mirroring the non-ZK BCC commitment's own binding) landed
2026-08-18/19 — see `PRODUCTION_GAPS.md` §36. `secret_key` is a KDF'd stand-in for the
real Ed25519 seed (documented scope limitation, not a mock — full in-circuit Ed25519 verification
would need a bignum/foreign-field library).

Flow: agent (`integrity-sdk`'s `prover.py`, actually wired to this real circuit as of
2026-08-18/19 — previously it pointed at a placeholder and had no call sites or tests at all)
runs `nargo execute` + `bb prove` → calls
`ReputationRegistry.submitZkAttestation(agent, proof, publicInputs, root, leaf, merkleProof)`
(only `msg.sender == agent`, to block cross-agent replay) → contract checks the leaf against an
oracle-anchored Merkle root via `StateAnchor.verifyLeaf`, then checks the proof via
`IZkVerifier.verify` (indirected through `VerifierRegistry` for per-agent verifier-version
pinning) → on success sets a 7-day `zkBoostExpiry`. `effectiveScore()` returns
`baseScore * 1.15` (`ZK_BOOST_BPS = 11_500 / 10_000`) while boosted, else plain `baseScore`.
`baseScore` itself is pushed by the oracle (`ORACLE_ROLE`) or bridged cross-chain via
`CCIPReputationBridge` (the boost itself is never bridged — must be re-earned per chain).

Two other Noir packages exist and are NOT the real pipeline: `integrity-sdk/circuits/
poc_commitment/` (an earlier placeholder, same shape as the real circuit — now fully
unreferenced by any code in the repo as of 2026-08-18/19, since `prover.py` was repointed at the
real circuit; left in place, not deleted, per this codebase's own "dead, not deleted" precedent)
and `integrity-oracle/backend/tests/fixtures/zk_smoke/` (a Rust-side test fixture only).

### AIS scoring

Computed in exactly one place, `integrity-oracle/scoring-core` (deliberately dependency-free
besides `serde`, so `backend` depends on it and never the reverse):

```
AIS = (S_entropy^wE · S_grounding^wG · S_sacrifice^wS · S_compliance^wC) · ZK_boost
wE=0.30, wG=0.30, wS=0.20, wC=0.20, ZK_boost=1.15 if a real bb-verified proof is live, else 1.0
```

A weighted **geometric** mean, not arithmetic — so **any single zero component
zeroes the entire score**. This is the most common way to misread AIS: an agent
whose telemetry omits one axis (e.g. reports no token usage, so `sacrifice`
derives to 0) scores 0.0 even with the other three axes perfect. Absent and
catastrophic are deliberately indistinguishable here — both resolve to 0, which is
consistent with proposed N2 ("earned, not granted") in
`spec/integrity-protocol-v0.5-proposed.md` §4.1 and its explanatory source at
`spec/integrity-protocol-v3.2.md` §3.1.1. That bounded implementation evidence does not
make the full proposal normative or complete; see `PRODUCTION_GAPS.md`.

As of 2026-08-17, `derive_entropy`/`derive_grounding`/`self_reported_compliance`
(`integrity-oracle/backend/src/derive.rs`, mirrored in
`integrity_sdk/telemetry/derive.py`) also fail closed to 0 on empty/no-evidence
input — previously they defaulted to 1.0 (maximum), which let a submission with
token counts but no analysable content outscore an honest, mediocre agent
(§3.1.1's worked example). `derive_sacrifice` was always the only axis that failed
closed; now three of four are. **Still open** (spec §3.1.4 rows 3–6, none landed in
code yet): compliance still falls back to the agent's own self-reported flags for
every non-healthcare agent (no independent evidence requirement), sacrifice is
still self-reported token counts rather than validator/TEE-attested, there is no
per-component floor + conjunctive gate (so a 90%-violation agent still reaches
r≈0.631 rather than being gated to 0 — the "knife's-edge zero" problem the bare
mean doesn't solve), and the reported `ais` field is still post-boost/unclamped
rather than exposing the pre-boost, [0,1]-clamped value §3.1.1 eq. 4b requires as
the actual constraint input.

`ais-equations.html` at repo root is a standalone, polished static page presenting this formula
and its components for a non-engineering audience (e.g. linked from marketing/pitch material) —
keep it in sync if the weights or formula shape change; it is not auto-generated from
`scoring-core`.

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

## Working state — check before trusting "current" claims

Do not assume `main` or this file reflects the latest worktree. Run `git status` and
`git branch --show-current` before relying on any snapshot of what is implemented, and bind exact
test-count claims to the command/date or commit that produced them.

Test-count claims for a given package drift between
this file, the README's audit section, and `SPECIFICATION.md`, and none of them are
auto-updated — treat any specific number here as approximate and re-run the package's test
suite if the exact count matters, rather than trusting whichever doc you read first.

## Known gaps / things this doc's own exploration found stale — verify before relying on them

- `contracts/.env` (populated, not just `.env.example`) exists on disk — don't commit it.
- Root `Makefile`'s `test-e2e` target comment still names
  `integrity-dashboard/e2e/global-setup.ts` as the thing that boots anvil + Postgres/Redis +
  oracle + a seeded agent — **that file does not exist**. `playwright.config.ts`'s `webServer`
  only boots `npm run dev`; the real backend stack must be started manually first (see
  `docs/TESTING.md`'s Layer 2 section, corrected 2026-08-13). `playwright.config.ts` also sets
  `reuseExistingServer: !process.env.CI`, so a leftover host dev server on the configured port
  is silently adopted instead of flagged — the same port-shadowing failure recorded as F11 in
  `docs/design/harness-loop-audit-2026-07-30.md`.

Five gaps previously listed here were **verified stale on 2026-08-13** and removed rather than
left to mislead: `integrity-dashboard/e2e/` *does* exist (16 route specs, 140 tests, a full
audit pass — see `docs/wiki/entities/integrity-dashboard.md`); `package.json` does **not**
define a `"test"` script and has no `vitest` dependency at all (a 2026-07-31 note here claimed
it did — re-verify claims like this against `package.json` directly, don't carry them forward);
`integrity-dashboard/demo/` *does* exist (`demo/pyproject.toml`, entry point `integrity-demo`);
`src/services/api.ts` no longer exists at all, so any "hardcoded mock data" warning pointing at
that file is stale; and `ethers ^6.17.0` *is* a dashboard dependency (bumped from the `^6.16.0` previously recorded
here — re-check `package.json` directly rather than trusting a version number quoted in prose).
Re-check this section against disk before trusting it — it has drifted more than once.

## Live deployment

Base Sepolia, chainId 84532. Singleton/clone-template addresses are in
`deployments.baseSepolia.json` at repo root (local-anvil equivalents in
`deployments.local.json`); per-agent primitive addresses are intentionally *not* in a static
file — always resolved live from `XibalbaAgentRegistry` on-chain. `FAUCET_INFO.md` lists the
operator addresses that need testnet funding. All protocol roles (arbitrator/disputer/
funderWallet/governance/oracleSigner/resolverSigner) currently point at one address — a
single-operator testnet setup, not representative of an eventual production key-separation
design.
