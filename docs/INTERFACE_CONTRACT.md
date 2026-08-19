# Integrity Protocol — Interface Contract (v1)

This document is the single source of truth for how integrity-core packages and internal services talk to each other. Every package is being rebuilt from scratch in parallel by a different engineer (human or agent) — if something isn't pinned down here, packages will drift and stop interoperating. When in doubt, follow this doc over any assumption from the old codebase.

Repo documentation precedence is:

1. `README.md` defines repo-level ownership, current package status, and source-of-truth pointers.
2. This file defines internal schemas, ports, env vars, service boundaries, and cross-package call conventions inside integrity-core.
3. `spec/integrity-protocol-v0.4.md` is the accepted normative protocol;
   `spec/integrity-protocol-v0.5-proposed.md` is a non-authoritative review candidate;
   `spec/integrity-protocol-v3.2.md` is the explanatory, non-normative whitepaper; and
   the remaining `spec/` subtrees define externally-supported wire surfaces. A generated
   PDF is publication output, not an interface contract.
4. `docs/wiki/` is the compiled long-term knowledge layer generated out to the GitHub Wiki and `integrity-dashboard/`'s browser wiki.

Scope: this rewrite covers **six protocol core packages**:
`contracts/`, `integrity-zkp/`, `integrity-oracle/`, `integrity-sdk/`,
`integrity-cli/`, `bcc_middleware/` — plus `integrity-dashboard/`, the original integrity-core dashboard/landing app (its `demo/` subdirectory is the multi-vertical investor/developer closed-loop scenario engine, see §11 — merged from the former separate `integrity-dashboard/` + `integrity-demo/` packages on 2026-07-09), `integrity-userapi/`, a dedicated user-accounts/auth backend kept strictly separate from the oracle (see §13), and `integrity-framework/`, a reputation-derivatives package reviving the old repo's marketplace/lending concept (see §12, not yet built). Everything else from the old repo (marketing site, unrelated scaffolding, legacy backups, stray installer scripts) is intentionally left out.

External repositories are deliberately outside this interface contract. `xibalba-shield` is the
endpoint-security evidence producer, and `xibalba-cortex` is the local cognitive store. They
consume public integrity-core interfaces; integrity-core's protocol packages must not import,
call, or require either external repo. `integrity-dashboard/` is the operator web presentation
layer — a component of this repository, not an external one; it consumes the same public
interfaces as any other consumer, with no privileged path. The cross-repository dependency
map is `docs/architecture/ecosystem-dependencies.md` and `docs/wiki/architecture/ecosystem-dependencies.md`.

Ground rule for this rewrite: **no silent mocks**. Every previously-stubbed
piece (ZK proving, TEE attestation, OPA policy evaluation, on-chain BAA
checks, Merkle anchoring) must be a real, working implementation, tested
against the real toolchain below — not a hardcoded return value. If something
truly cannot be made real in this environment (e.g. real AWS Nitro hardware
attestation, which requires physical/cloud enclave hardware we don't have),
implement the real *verification* logic against the real wire format, use a
real published test vector as a fixture, and say so explicitly in a comment
and in that package's README — don't fake the check silently.

## 1. Toolchain (confirmed installed in this dev environment)

| Tool | Version | Used by |
|---|---|---|
| `forge` / `anvil` (Foundry) | 1.7.1 | contracts |
| `cargo` / `rustc` | 1.96.0 | integrity-oracle |
| `nargo` (Noir) | 1.0.0-beta.22 | integrity-zkp, integrity-oracle circuits |
| `bb` (Barretenberg) | 5.0.0-nightly | integrity-zkp, integrity-oracle (proof gen/verify) |
| `opa` | 1.18.2 | bcc_middleware, integrity-sdk |
| `node` / `npm` | 22.x / 10.x | integrity-dashboard, contracts (npm-based deps) |
| `python` / `uv` | 3.12 / 0.11 | integrity-sdk, integrity-cli, bcc_middleware |

All of these are on `PATH` (added to `~/.bashrc`). Use them for real — compile
the circuits, run `bb prove`/`bb verify`, run `forge test`, run `opa eval`
against real policies. Don't write code you haven't run.

## 2. Ports & local endpoints (dev/docker-compose defaults)

| Service | Port | Package |
|---|---|---|
| Postgres | 5432 | integrity-oracle |
| Redis | 6379 | integrity-oracle |
| Anvil (local EVM chain) | 8545 | contracts |
| OPA server | 8181 | bcc_middleware |
| BCC Middleware (FastAPI) | 8000 | bcc_middleware |
| Integrity Oracle backend (Axum) | 8080 | integrity-oracle |
| Integrity Oracle OTLP/gRPC receiver | 4317 | integrity-oracle |
| Integrity User API (FastAPI) | 8090 | integrity-userapi |
| Postgres (userapi) | 5435 | integrity-userapi |
| Integrity Dashboard (Vite dev) | 5173 | integrity-dashboard |

## 3. Environment variables (shared names — use exactly these)

- `DATABASE_URL` — Postgres connection string (oracle). Must point at a
  `timescale/timescaledb` instance, not plain `postgres` — migration 0004 runs
  `CREATE EXTENSION timescaledb` (see `docker-compose.yml`'s `postgres` service and
  §1's OTLP receiver below).
- `REDIS_URL` — Redis connection string (oracle)
- `OTLP_GRPC_ADDR` — bind address for the oracle's real OTLP/gRPC receiver
  (`integrity-oracle/backend/src/otlp.rs`), defaults to `0.0.0.0:4317` — the standard
  OTLP/gRPC port `integrity-sdk`'s `OTLPSpanExporter`/`OTLPMetricExporter` already
  target by default. A second listener, separate from the oracle's HTTP `BIND_ADDR`.
- `KYC_PROVIDER_KEYS` — comma-separated trusted KYC receipt issuers in
  `provider=hex-ed25519-public-key` form. Empty disables KYC receipt acceptance. Keys
  belong to independently operated commercial or self-hosted open-source verification
  stacks; clients never supply trust roots in requests.
- `RPC_URL` — EVM RPC endpoint, defaults to `http://localhost:8545` (anvil) for local dev
- `CHAIN_ID` — `31337` for local anvil
- `OPA_URL` — `http://localhost:8181` (bcc_middleware, sdk)
- `BCC_MIDDLEWARE_URL` — `http://localhost:8000` (sdk, cli)
- `ORACLE_URL` — `http://localhost:8080` (sdk, cli, bcc_middleware)
- `USERAPI_URL` — `http://localhost:8090` (dashboard; integrity-userapi's own
  outbound calls to `ORACLE_URL` for agent data, never the reverse — see
  §6.10 on the backend split)
- `RESOLVER_ADDRESS` / `RESOLVER_PRIVATE_KEY` — the demo/market resolver
  signer (see §6.9's `RESOLVER_ROLE` trust boundary). Defaults to the
  deployer/funder for a single-operator testnet deployment, same posture as
  `ORACLE_SIGNER_ADDRESS` etc below.
- `DEPLOYMENTS_FILE` — path to `deployments.local.json` (see §6.6), defaults to repo root
- `BASE_SEPOLIA_RPC_URL` — RPC endpoint for the `base_sepolia` entry in
  `contracts/foundry.toml`'s `[rpc_endpoints]` (already configured there,
  referenced as `${BASE_SEPOLIA_RPC_URL}`). Needed by anything deploying or
  reading from the Base Sepolia testnet deployment rather than local anvil.
  The corresponding deployments file for that network is
  `deployments.baseSepolia.json` (also whitelisted in `foundry.toml`'s
  `fs_permissions`, same shape as §6.6).
- Signing keys are **dev-only**, read from `.env` files that are
  `.gitignore`d in every package. Never commit a populated `.env`. Only
  commit `.env.example` with placeholder values.
  `contracts/.env.example` does not exist yet as of this revision — the
  keys below describe the intended Base Sepolia deploy flow per the
  self-sovereign model (§6), not a file that's already checked in:
  - `DEPLOYER_PRIVATE_KEY` — deploys the protocol `singletons` and
    `cloneTemplates` (§6.6), once per network.
  - `ORACLE_SIGNER_PRIVATE_KEY` — the `oracleSigner` address wired into
    every agent's `ReputationRegistry`/`StateAnchor` at registration
    (§6.1, §6.3 step 3).
  - `GOVERNANCE_PRIVATE_KEY` — the `governance` address that is every
    agent's `Slasher` arbiter (§6.2) — never the agent's own key.
  - `DISPUTER_PRIVATE_KEY` — the protocol's `disputer` signer for
    `Slasher.raiseDispute` (§6.2). At runtime, this role is actually held by
    `bcc_middleware`'s `REPUTATION_SIGNER_PRIVATE_KEY` (falls back to
    `ANCHOR_SIGNER_PRIVATE_KEY`) — see §7a — not a separate standalone process; this
    entry describes the on-chain role granted at deploy time, not a second service.
  - `FUNDER_PRIVATE_KEY` — funds new agent wallets with enough native gas
    to self-deploy their `SovereignAgent`/`StateAnchor` and call
    `registerPrimitives` (§6.3), since under the self-sovereign model no
    shared factory pays those gas costs on the agent's behalf. Corresponds
    to `protocolAddresses.funderWallet` in the deployments file (§6.6).
  - Per-agent controller keys are **not** protocol env vars at all —
    they're generated/held client-side by whatever created the agent
    (`integrity-sdk`, `integrity-cli`), since the whole point of the
    self-sovereign model is that the protocol never custodies them.

## 4. Core data contracts

### 4.1 DID Document (produced/consumed by integrity-sdk, integrity-oracle)
```json
{
  "id": "did:integrity:<hex-pubkey-fingerprint>",
  "controller": "did:integrity:<hex-pubkey-fingerprint>",
  "created": "<ISO8601>",
  "verificationMethod": [{
    "id": "did:integrity:<fingerprint>#key-1",
    "type": "Ed25519VerificationKey2020",
    "publicKeyMultibase": "<base58/multibase-encoded pubkey>"
  }]
}
```
Real Ed25519 only (via the `cryptography` library) — no HMAC pseudo-signature fallback.

### 4.2 BCC Commitment (the "Behavioral Commitment Chain" intent-lock object)
```json
{
  "agent_id": "did:integrity:...",
  "intent_type": "string, e.g. 'payment' | 'data_access' | 'contract_call'",
  "intended_state_hash": "0x<32-byte hex, sha256 of the canonical intent payload>",
  "nonce": "monotonic per-agent integer",
  "timestamp": "<unix ms>",
  "agent_public_key": "z<multibase base58btc, multicodec ed25519-pub || raw 32-byte pubkey>",
  "covered_entity_address": "0x<20-byte hex EVM address> | null",
  "intent_rationale": "public-safe intent rationale, signed and preferred by policy",
  "chain_id": "EVM chain ID this commitment is scoped to (int, required)",
  "verifying_contract": "0x<20-byte hex EVM address> of the target chain's XibalbaAgentRegistry (required)",
  "signature": "0x<hex, Ed25519 sig over the above fields except signature itself, canonical JSON>"
}
```
This exact shape is POSTed by `integrity-sdk` and `integrity-cli` to
`bcc_middleware`'s `POST /v1/bcc/intercept`. Field names are load-bearing —
don't rename them per-package.

Five fields were added after this doc's original draft, all now **✅
RECONCILED** and required by `bcc_middleware`'s real implementation
(`app/schemas.py`, `app/canonical.py`) — not carried in isolation, but
included in the signed payload, so neither can be swapped post-signature:

- `agent_public_key` — **required**. `integrity-sdk`'s DID fingerprint is
  `sha256(pubkey)`, not the raw public key, so a verifier holding only
  `agent_id` cannot recover the key needed to check `signature`. The agent
  therefore carries its own public key here, same multibase form as the DID
  document's `publicKeyMultibase` (§4.1: `"z" + base58btc(0xed 0x01 ||
  raw_pubkey)`). The receiving service must bind it before trusting it:
  `sha256(decoded_pubkey) == agent_id`'s fingerprint, or reject — this is
  what makes trusting a *carried* key safe (a substituted key can't also
  produce a sha256 preimage collision on the victim's fingerprint).
- `covered_entity_address` — **optional**; `null`/omitted for non-healthcare
  intent types. `contracts`' real `SmartBAAFactory.isBAAActive` takes two
  addresses, `coveredEntity` and `businessAssociate` (the agent), not one —
  this field names *which* covered entity (hospital) a healthcare-vertical
  commitment (`EMR_WRITE`, `DISPENSE_MEDICATION`, `BILLING_SUBMISSION`,
  `SECURE_EMR_WRITE`, `CLINICAL_DATA_ACCESS`) is claiming access against. Any
  commitment whose `intent_type` causes OPA to set `requires_baa := true`
  MUST carry it, or the on-chain BAA check fails closed with
  `BAA_CANNOT_VERIFY` regardless of the agent's actual BAA status. Deliberately
  an address, not a DID: covered entities are registered directly by EVM
  address in `contracts/src/health/CoveredEntityRegistry.sol` and have no DID
  layer of their own.

- `intent_rationale` — **required for agent tool calls**. This is the public-safe,
  signed intent explanation that `bcc_middleware`'s AOS policy gates on. The
  legacy `agent_thought` field is still accepted as an alias for compatibility,
  but new callers should populate `intent_rationale` and let `agent_thought`
  mirror it only if they need backwards compatibility.

- `chain_id` / `verifying_contract` — **both required**
  (docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md).
  Before these, a commitment signed once was valid, byte-for-byte, against
  any chain or any deployment of the protocol sharing the signing agent's
  DID — `nonce` is monotonic per-agent but not deployment-scoped, so it
  didn't close this. `chain_id` is the EVM chain ID the commitment is scoped
  to; `verifying_contract` is that chain's `XibalbaAgentRegistry` address —
  the one address every downstream primitive in this architecture already
  resolves through, so binding to it (rather than a per-intent-type
  contract) keeps this general-purpose. `bcc_middleware` denies a
  `chain_id` mismatch unconditionally; it denies a `verifying_contract`
  mismatch only when it has a configured registry address (see
  `bcc_middleware/app/main.py`'s deployment-binding check — a disclosed
  limitation so a local/dev/test topology with no deployments file
  configured isn't turned into a blanket deny). This does **not** close the
  experimental kernel's own hook-frame replay-domain binding (a separate,
  contract-side concern — see `CLAUDE_HANDOFF_2026-08-17.md` §9) or bind
  `chain_id` into the ZK circuit's `intent_commitment`
  (`integrity-zkp/src/main.nr` — a real, larger, cross-package residual gap,
  not attempted here).

**Canonicalization, pinned:** the signature covers every field above except
`signature` itself, serialized as `json.dumps(fields, sort_keys=True,
separators=(",", ":"), ensure_ascii=True)` (UTF-8 bytes). `ensure_ascii=True`
specifically — not the RFC 8785/JCS default — because it's the byte-for-byte
rule `integrity-sdk`, `integrity-cli`, and `bcc_middleware` all independently
implement today; a mismatch here silently breaks every signature on non-ASCII
content. (`integrity-oracle`'s Rust-side `serde_json` does not escape
non-ASCII by default and does not yet participate in this signature scheme —
see `PRODUCTION_GAPS.md` for that gap if it ever needs to.)

### 4.3 Agent Integrity Score (AIS)
Formula (from the product spec, keep as-is):
`AIS = (S_entropy^wE * S_grounding^wG * S_sacrifice^wS * S_compliance^wC) * ZK_boost`

Default weights (must sum to 1.0, make them configurable but ship this default):
`wE = 0.30, wG = 0.30, wS = 0.20, wC = 0.20`. `ZK_boost` is `1.15` when a real
Barretenberg proof was verified for the reporting period, else `1.0`. This
formula lives in `integrity-oracle/scoring-core` and is the only place it's computed —
other packages call the oracle's `/v1/agent/{id}/ais` endpoint rather than recompute it.

**Input-signal trust:** the four `S_*` inputs (`performance_variance`, `hgi_raw`,
`gpu_hours_verified`, `penalty_ratio`) are **not** taken from a client's self-reported
`derived_signals` in `POST /v1/telemetry/ingest`. The oracle independently recomputes
entropy/grounding/sacrifice server-side from the same request's `otel_spans` content
(`integrity-oracle/backend/src/derive.rs`, mirroring `integrity_sdk/telemetry/derive.py`'s
algorithms), and does the on-chain `ComplianceGate` "wins" check itself rather than
trusting an SDK-side opt-in. A client's signature proves who sent a request; it was
never proof the claimed numbers were honest, and this is the layer that closes that gap.
`derived_signals` is still part of the signed envelope (so old clients don't break) and
is still stored, but purely as an audit trail (`telemetry_events.payload.derived_signals`
vs. `payload.oracle_recomputed_signals`) — it does not feed the formula. See
[`docs/wiki/concepts/ais.md`](wiki/concepts/ais.md) for the full data-flow diagram and
`PRODUCTION_GAPS.md` §1a for what's still open (ZK-boost is a period-wide, not per-event,
binding). The oracle-to-chain score push is implemented by `bcc_middleware` §7a.

### 4.2a Signed telemetry envelope version

The signed object of `POST /v1/telemetry/ingest` carries `schema_version`, an integer
**inside the signature**:

```
schema_version = 1          # integrity_sdk.client.TELEMETRY_SCHEMA_VERSION
                            # backend::handlers::MAX_TELEMETRY_SCHEMA_VERSION
```

Both constants must move together. Rules, all load-bearing:

- **Inside the signed object, not beside it.** A version outside the signature could be
  rewritten in transit to make the oracle reinterpret a payload under different rules.
- **An absent `schema_version` is the pre-versioning envelope and stays valid forever.**
  Signed payloads are evidence; old evidence must remain verifiable. The oracle therefore
  rebuilds the signable bytes **without the key** when a request omits it — serializing it as
  `null` would change the canonical JSON and reject every historical signature.
- **A version above `MAX_TELEMETRY_SCHEMA_VERSION` is refused (400), not parsed.** Misreading
  a future shape and storing it as signed evidence is worse than rejecting it.
- Bumping the version is therefore a coordinated change: raise the SDK constant, raise the
  oracle's maximum, and deploy the oracle **first** so it can accept the new shape before any
  agent emits it.

Covered by `oracle_e2e_telemetry_schema_version_is_signed_and_backward_compatible`, which
asserts all four: legacy accepted, v1 accepted, unknown refused, and an injected version
failing verification.

### 4.4 Merkle tree convention (must match between integrity-oracle and contracts)
- Hash function: `keccak256` (not SHA-256) — this tree's root gets verified on-chain in
  `StateAnchor.sol`, and keccak256 is native/cheap in the EVM.
- Leaf hashing: `keccak256(abi.encodePacked(leafData))`.
- Parent hashing: sort the pair of child hashes ascending before concatenating
  (`keccak256(a < b ? a,b : b,a)`) — the standard OpenZeppelin `MerkleProof` convention.
  This avoids second-preimage ordering ambiguity and lets contracts use OZ's
  `MerkleProof.verify` directly instead of a custom verifier.

> **⚠ UNPINNED: odd-width levels.** The three rules above are everything this
> section has ever specified. It says nothing about a level with an odd number of
> nodes, and the three implementations filled that silence differently:
> `integrity-oracle/backend/src/merkle.rs` and `bcc_middleware/app/merkle.py`
> **duplicate** the odd node; `integrity_sdk/vault.py` **promotes** it unchanged.
> All three are compliant with this section as written, and all three claim to
> match the others "bit-for-bit" — an unfalsifiable claim until conformance
> vectors exist. Nothing is broken today only because each component builds,
> anchors and verifies within its own tree; the first cross-system verification
> breaks. Duplication also makes `[A,B,C]` and `[A,B,C,C]` produce the identical
> root, which contradicts `StateAnchor.sol`'s own NatSpec claim that the root is
> "a true function of the *set* of leaves."
> Recorded as E9 in [`docs/design/e2e-audit-2026-07-31.md`](design/e2e-audit-2026-07-31.md);
> proposed amendment + migration in
> [`docs/design/merkle-standardization.md`](design/merkle-standardization.md).
> **Do not add a fourth implementation until this is resolved.**

### 4.4a Genesis memory root (spec v0.3 §4.1/§7.2) — cross-package constant

Registration requires `StateAnchor.latestRoot != bytes32(0)` (§6), but an
**empty-but-initialized Trust Vault is valid at birth** — and `anchorRoot` reverts on
`bytes32(0)` (`EmptyRoot`). An agent registering with nothing yet in its vault therefore
needs a defined, non-zero root meaning "initialized, empty":

```
GENESIS_VAULT_ROOT = keccak256("integrity.trust-vault.genesis.v1")
                   = 0x… (computed identically in every package — never hardcode a literal)
```

Every package MUST derive it by hashing that exact ASCII string, not by copying a hex
literal — the same discipline §4.4's hashing rules exist to enforce, and the reason this
constant lives here rather than in `registration.py`. Defined in:
`integrity_sdk/chain.py::GENESIS_VAULT_SEED`.

It is a *sentinel*, not a commitment to any content: an agent whose vault already has
entries at registration time should anchor its real vault root instead. The oracle's §7.1
gate checks only that the root is non-zero — it deliberately does **not** require this
specific value, so a genuinely non-empty vault at birth is equally valid.

Authorization (§7.2): the genesis root (epoch 0→1) must be anchored by the agent itself —
its controller via `SovereignAgent.execute`, which works because `StateAnchor`'s admin is
the `SovereignAgent` contract and the constructor grants it `ANCHOR_ROLE`. No Solidity
change is needed for this; **enforcement** that the protocol's `ANCHOR_ROLE` signer cannot
anchor epoch 1 is still `[PLANNED]` (Appendix A gap 2), since `StateAnchor` is deployed
per-agent and already-deployed anchors keep their current bytecode.

### 4.4b Memory DAG node schema (spec §7.4 lineage) — `[VERIFIED 2026-08-05]`

Design: [`docs/design/memory-dag.md`](design/memory-dag.md). Implementation:
`integrity_sdk/memory_dag.py`. Written 2026-07-31 with no shell available and left
unexecuted; run and confirmed 2026-08-05 — `tests/test_memory_dag.py` passes
21/21, including the cross-runtime provenance acceptance test (step 7 of the
design doc's order-of-work). This section is now binding.

§4.4's tree commits to a flat *set* — its sorted-pair rule exists precisely to make
leaf position meaningless, so it cannot express that one memory derives from
another. Lineage needs a DAG, not a bigger tree.

**Node preimage** (canonical JSON per §4.2's rule — `sort_keys=True`,
`separators=(",",":")`, `ensure_ascii=True`; deliberately the same encoding, not a
second one):

```
{ schema, agent_id, kind, content_hash, parents[], edge_type, timestamp, source }
node_id = "0x" + keccak256(canonical(preimage))
schema  = "integrity.memory.node.v1"
```

Three rules are load-bearing:

- **`parents` is ordered and positional** — `parents[0]` is the superseded version.
  It MUST NOT be sorted. Sorting it would erase lineage semantics exactly the way
  §4.4's sorted pairs erase leaf position; the two layers have deliberately
  opposite rules, and conflating them is the failure mode to guard against.
- **`parents` may reference only already-stored nodes**, which are therefore always
  older. This single rule makes the graph acyclic *by construction* — no cycle
  detection exists or is needed.
- **Semantic `[[links]]` are committed inside `content_hash`, never as `parents`.**
  Wiki links may be cyclic and may dangle (naming a memory that does not exist yet
  is explicitly allowed); both are fine as content and both would be fatal as hash
  edges.

**Anchoring.** A head node id is a 32-byte value, so `root_of_heads()` (a §4.4 tree
over current ref heads) satisfies the existing §6 / §7.1 gate
`StateAnchor.latestRoot != bytes32(0)` unchanged — **no contract change, no oracle
change**, and §4.4a's `GENESIS_VAULT_ROOT` sentinel remains valid as the empty head.
Because each node commits to its parents, anchoring one head transitively commits
its whole reachable history.

### 4.5 Trace tree view (`GET /v1/traces/{trace_id}`)
LangSmith-style nested run-tree reconstruction over the real spans in `otel_spans`
(`integrity-oracle/backend/src/trace_tree.rs`) — the flat, start-time-ordered rows
`db::get_otel_spans_for_trace` returns, reassembled into a parent/child tree by
`parent_span_id`. Top-level route (not `/v1/agent/{id}/traces/...`): a `trace_id` is a
global OTel identifier, not scoped to one agent. Same unauthenticated-data caveat as
`otel_spans` generally (§1a in `PRODUCTION_GAPS.md`) — a span whose claimed parent isn't
present in the queried set is surfaced as a root rather than erroring, and a chain
deeper than `trace_tree::MAX_TREE_DEPTH` (500) is truncated with `truncated: true` in
the response rather than silently cut. 404 on an unknown `trace_id` means "nothing was
ever ingested under that ID," not an access-control decision.

**Known tooling gotcha, not an API behavior:** `integrity-oracle/backend/src/openapi.rs`
splits its `#[derive(OpenApi)] paths(...)` list across two structs
(`ApiDocCore`/`ApiDocExtra`, merged via `combined_openapi()`) because utoipa 5.5.0
silently drops the last entry once a single `paths(...)` list exceeds 15 items —
confirmed by direct testing (macro expansion is correct; the drop happens in utoipa's
runtime aggregation). Doesn't affect the live server at all (only the separate
`gen_openapi` dev binary calls this code), but **any future new endpoint must go in
whichever of the two structs currently has room**, not just be appended to
`ApiDocCore`, or it will silently vanish from the generated spec the same way.

## 5. Zero-knowledge proving pipeline (must be real, end-to-end)

1. Circuit lives in `integrity-zkp/src/main.nr` (Noir). It proves: "I know a
   private Ed25519-derived secret and an intent payload whose hash equals the
   public `intended_state_hash`, without revealing the secret or full payload."
   Keep the circuit's constraint logic real — no `assert(true)`-style shortcuts.
2. Compile with `nargo compile` (produces the ACIR bytecode).
3. Generate a proving/verification key and Solidity verifier with `bb`:
   `bb write_vk`, and `bb write_solidity_verifier` to emit a real
   `contracts/src/oracle/UltraPlonkVerifier.sol` (generated file — replace the
   old hand-written always-true stub entirely).
4. `integrity-sdk`'s `prover.py` shells out to `nargo execute` + `bb prove` to
   produce a real proof for a given commitment, and can call `bb verify`
   locally before submission.
5. `contracts`' verifier contract is the on-chain source of truth; `integrity-oracle`
   also verifies proofs off-chain for scoring purposes using the same `bb verify` flow
   (or a Rust binding) — no independent/duplicate mock verifier.

Since this requires re-running `nargo`/`bb` commands as part of the build,
document the exact commands in `integrity-zkp/README.md` and wire them into
that package's Makefile target so CI actually exercises them.

## 6. On-chain architecture: per-agent primitives, not a singleton registry

**This section supersedes the old singleton model.** The old `contracts/`
had one shared `ReputationRegistry`, one shared `Slasher`, one shared
`StateAnchor`, and an admin-controlled `AgentFactory` that registered each
new agent into that shared state. That model is gone. It has been replaced
end-to-end (127/127 `forge test` passing) with a **self-sovereign
per-agent model**: every agent deploys and owns its own 7 "primitive"
contracts at registration time, and there is no longer a global
`ReputationRegistry`/`Slasher`/`StateAnchor` address to hardcode anywhere.
`AgentFactory.sol` has been deleted; its replacement is
`AgentPrimitivesFactory.sol` (§6.3).

### 6.1 The seven primitives

| # | Contract | Deploy mode | Purpose |
|---|---|---|---|
| 1 | `SovereignAgent` (`core/SovereignAgent.sol`) | **Direct**, by the agent's own EVM wallet | The agent's on-chain account: identity (DID), controller, `execute()`, cached AIS. Its address is the agent's canonical identity everywhere downstream. |
| 2 | `StateAnchor` (`oracle/StateAnchor.sol`) | **Direct**, by the agent's own EVM wallet (constructor `admin` = the just-deployed `SovereignAgent` address) | Anchors Merkle roots of this agent's off-chain Trust Vault state (§4.4) so individual leaves can be proven on demand. |
| 3 | `ReputationRegistry` (`oracle/ReputationRegistry.sol`) | EIP-1167 clone | This agent's AIS ledger: oracle-pushed `baseScore` plus a self-earned `ZK_boost` from a verified Barretenberg proof (§4.3). |
| 4 | `Slasher` (`oracle/Slasher.sol`) | EIP-1167 clone | Holds this agent's $ITK collateral; dispute-gated, arbiter-resolved slashing. |
| 5 | `VerifierRegistry` (`oracle/VerifierRegistry.sol`) | EIP-1167 clone | This agent's versioned pointer to whichever `IZkVerifier` implementation it currently trusts, so a global circuit upgrade doesn't force every agent onto a new version simultaneously. |
| 6 | `ComplianceGate` (`health/ComplianceGate.sol`) | EIP-1167 clone | This agent's regulated-industry (Integrity Health) compliance declaration + a single live-verified `isHealthcareCompliant` read. |
| 7 | `AgentProfile` (`framework/AgentProfile.sol`) | EIP-1167 clone | Domain-membership pointer (`primaryDomain`) + off-chain metadata URI (`profileURI`). |

Only #1 and #2 are fully, independently deployed (their own bytecode, their
own address derivation) — directly by the agent's own wallet, which is
itself the cryptographic proof of self-sovereign control (nobody else's
transaction created them). #3–#7 are cheap EIP-1167 minimal-proxy clones of
5 shared implementation contracts, deployed by `AgentPrimitivesFactory` in
one registration transaction.

`XibalbaAgentRegistry.sol` (reshaped from its previous role) is the
canonical index of all 7 addresses per agent, via a `PrimitiveSet` struct:
```solidity
struct PrimitiveSet {
    address sovereignAgent;
    address stateAnchor;
    address reputationRegistry;
    address slasher;
    address verifierRegistry;
    address complianceGate;
    address agentProfile;
}
```
It is keyed both by `keccak256(bytes(did))` (`resolveDID`/`resolveDIDHash`)
and by the agent's `SovereignAgent` address (`resolveAgent`,
`isRegisteredAgent`) — the latter is what downstream consumers use, since
that's the address that arrives as `msg.sender` on every other call (e.g.
`EHRGate.checkAccess`, §6.4). `registerPrimitives` is restricted to
`REGISTRAR_ROLE`, granted only to `AgentPrimitivesFactory` — no other
contract should hold it.

### 6.1a Integrity identity read profile v1 and ERC-8004 boundary

`contracts/src/kernel/IntegrityIdentityReadV1.sol` is a read-only discovery
facade over `XibalbaAgentRegistry`. Its interface profile is
`keccak256("xibalba.integrity.identity-read.v1")`. It is informed by the
ERC-8004 draft at
`ethereum/ERCs@503591a6e80e6e1affdd6403341e25269141f046/ERCS/erc-8004.md`,
but it is deliberately **not** an ERC-8004 Identity Registry or ERC-721
implementation. ERC-8004 remains Draft at that revision.

The supported local read surface is:

```solidity
resolveDID(string did)         -> IdentityView
resolveDIDHash(bytes32 hash)   -> IdentityView
resolveAgent(address account)  -> IdentityView
profileURI(bytes32 didHash)    -> string
isController(address account, address candidate) -> bool
isERC8004Conformant()          -> false
```

`IdentityView` returns the canonical DID hash, `SovereignAgent`, domain,
registration timestamp, and all seven primitive addresses. The separate
`profileURI` read returns the live `AgentProfile.profileURI`; a malformed or
reverting profile therefore cannot block fixed identity resolution. The URI
is mutable, unbounded, agent-controlled, and unverified; consumers MUST fetch
and validate its document under their own policy. The facade fails closed
when the registry's DID-to-agent and
agent-to-DID mappings disagree, when the subject has no readable
`agentDID()`, or when the subject's declared DID hashes to a different value.

The facade exposes none of ERC-8004/ERC-721's `agentId`, `ownerOf`,
`tokenURI`, transfer, approval, wallet-proof, metadata-write, event, ERC-165,
Reputation Registry, or Validation Registry semantics. The registry's
`AgentRecord.controller` is a registration-time snapshot and is not returned
as current ownership. `isController` instead verifies a caller-supplied
candidate against the `SovereignAgent`'s live `DEFAULT_ADMIN_ROLE`.

Agent Integrity Score (AIS) remains an Integrity-native reputation signal:
the facade returns the agent's `ReputationRegistry` primitive address but
does not read, translate, or publish AIS through ERC-8004 feedback methods.
Execution-control code, including the future kernel, MUST continue reading
fixed identity and reputation state directly from `XibalbaAgentRegistry` and
the resolved Integrity primitive. It MUST NOT put dynamic URI reads or this
discovery facade in the execution gate.

Existing agents require no migration: the facade has no write surface and
projects existing canonical records. Actual native ERC-8004 convergence is
deferred until a separately reviewed registry design can provide exact token
identity, ownership/transfer semantics, events, historical treatment, and a
version-pinned compatibility matrix without relabeling Integrity semantics.

### 6.2 Call-routing convention

Every clone's `DEFAULT_ADMIN_ROLE` is the agent's own `SovereignAgent`
**contract address**, never the raw controller EOA. An agent that wants to
change its `VerifierRegistry` pointer, update its `ComplianceGate`
self-declared flags, or update its `AgentProfile` metadata routes that call
through `SovereignAgent.execute(target, value, data)`, which checks
`onlyController` (the EOA) before forwarding — so control ultimately still
traces back to the controller key, but every clone only ever sees the
`SovereignAgent` contract as its admin. This is deliberate: it means a
compromise of the raw EOA's signing key is recoverable by
`rotateController`, without having to re-point every clone's admin role
individually.

**Exception — the `AgentPrimitivesFactory.registerPrimitives` call itself
is EOA-signed directly**, not routed through `execute`, because
`SovereignAgent` cannot route a call to register itself (that would be
circular: the account doesn't have an admin-recognized `execute` path
until after it exists). Instead, `registerPrimitives` verifies the caller
by checking that `msg.sender` holds `DEFAULT_ADMIN_ROLE` on the
`SovereignAgent` it claims to own
(`sa.hasRole(sa.DEFAULT_ADMIN_ROLE(), msg.sender)`) — this is the one
bootstrap exception to the "route everything through `execute`" rule.

`Slasher` is a partial exception to "admin = SovereignAgent": its
`DEFAULT_ADMIN_ROLE` (arbiter) is `governance` — the protocol's, not the
agent's — passed in at `AgentPrimitivesFactory` construction time, because
an agent must never be able to arbitrate its own slashing dispute (see the
NatSpec on `Slasher.sol`). `DISPUTER_ROLE` is likewise a protocol-held
signer (`disputer`), separate from `governance`, so a bridge/oracle
compromise and a governance-key compromise are independently revocable.
`ReputationRegistry`'s `ORACLE_ROLE` and `Slasher`'s `DISPUTER_ROLE` follow
the same pattern: protocol-held signers, distinct from both the agent's
admin role and each other.

### 6.3 Registration sequence

`AgentPrimitivesFactory` (`framework/AgentPrimitivesFactory.sol`) replaces
the deleted `AgentFactory.sol`. The real end-to-end sequence (mirrored
exactly by `contracts/test/AgentPrimitivesFactory.t.sol`, and the sequence
`integrity-sdk` will implement against real Base Sepolia transactions) is:

1. The agent's own wallet deploys `SovereignAgent` directly:
   `new SovereignAgent(did, controller, oracleSigner, factory)`.
2. The same wallet deploys `StateAnchor` directly, passing the just-deployed
   `SovereignAgent` address as `admin`:
   `new StateAnchor(address(sovereignAgent))`.
3. The wallet calls `SovereignAgent.execute(stateAnchor, 0,
   abi.encodeCall(AccessControl.grantRole, (ANCHOR_ROLE, oracleSigner)))` —
   routing the grant through the agent's own account (per §6.2) to give the
   protocol's oracle signer `ANCHOR_ROLE` on this agent's `StateAnchor`, so
   the oracle can anchor Merkle roots on the agent's behalf.
4. The wallet calls `AgentPrimitivesFactory.registerPrimitives(sovereignAgent,
   stateAnchor, did, domainId, vertical, profileURI)` (EOA-signed directly,
   per the §6.2 bootstrap exception). This single transaction:
   - verifies the caller controls the claimed `SovereignAgent`,
   - verifies `domainRegistry.canJoin(domainId, msg.sender)`,
   - clones and initializes all 5 remaining primitives with the
     `SovereignAgent` address as their admin (protocol-held roles —
     `oracleSigner`, `disputer`, `governance` — come from the factory's own
     immutables, never from the registering agent),
   - calls `XibalbaAgentRegistry.registerPrimitives` to atomically record
     the full `PrimitiveSet`,
   - calls `DomainRegistry.recordJoin` to mark the `SovereignAgent` address
     as a member of `domainId`,
   - emits `PrimitivesRegistered` with all 7 addresses.

No consumer can ever observe an agent that only half-exists: registration
either completes all 5 clones + both registry writes in one transaction, or
reverts entirely.

**Step 5 — off-chain: oracle independent re-verification.** After the
4 on-chain steps above, `integrity-sdk`'s `registration.register_agent()`
POSTs to `integrity-oracle`'s `POST /v1/agent/register`
(`integrity-oracle/backend/src/handlers.rs`'s `RegisterAgentRequest`), which
independently re-derives the agent's primitives from
`XibalbaAgentRegistry.resolveDID` on-chain and rejects (`400`) if the
client's claim doesn't match byte-for-byte — this is what makes the agent
"really" registered from the protocol's point of view, not just on-chain
from the SDK's own say-so. This schema was previously undocumented here
(silent gap, not a deliberate omission) — that silence is exactly how
`integrity-sdk`'s payload drifted from the oracle's real struct undetected
until 2026-07-09 (see `docs/wiki/WIKI_LOG.md`'s entry of that date). The real
JSON shape, pinned to the actual Rust struct:

```jsonc
// POST /v1/agent/register
{
  "did": "did:integrity:<sha256-hex-fingerprint>",   // required — NOT "agent_id"
  "did_document": { /* §4.1 DID Document, verbatim */ },
  "primitives": {
    // exactly these 7 fields (checksummed hex addresses) — nothing else;
    // extra fields are silently ignored by serde, but don't rely on that
    "sovereign_agent": "0x...",
    "state_anchor": "0x...",
    "reputation_registry": "0x...",
    "slasher": "0x...",
    "verifier_registry": "0x...",
    "compliance_gate": "0x...",
    "agent_profile": "0x..."
  },
  "ed25519_pubkey_hex": "0x...",   // optional, but the handler 400s if this
  "eth_address_hex": "0x...",      // AND eth_address_hex are both absent —
                                    // integrity-sdk always sends both
  "verification_tier": 0           // accepted for wire compatibility but ignored;
                                    // the server assigns the registration floor
                                    // and evidence-backed checks raise effective tier
}
```

`integrity-cli`'s `agent register` command hand-builds this same POST body
independently (it does not import `integrity_sdk.registration` — see
`entities/integrity-cli.md`'s "no sibling dependency" note) and had the
identical `agent_id`-vs-`did` drift until it was fixed in lockstep on
2026-07-09, the same day as the SDK fix above — both client implementations
now conform to this exact schema.

`integrity-sdk`'s `registration.py` sends this exact shape as of the
2026-07-09 fix (it previously sent `{"agent_id", "did_document",
"primitives": <the full AgentRegistration dataclass, extra fields and
all>}`, which 422'd on the missing `did` field and would then 400 on the
missing pubkey/address fields even if `did` were fixed alone — never caught
because every test up to that point ran with `skip_oracle_registration=True`).

### 6.3a Verification ladder and evidence revocation

Registration establishes only the tier-1 floor. The Oracle derives the effective tier
from that floor plus active, unexpired, unrevoked evidence:

- Tier 2: dual-resolver DNS TXT proof or a signed challenge read from a GitHub repository
  that GitHub reports as owned by the claimed login. Evidence expires after 90 days.
- Tier 3: a nonce-bound AWS Nitro COSE/CBOR attestation whose certificate chain reaches
  AWS's Nitro root. Evidence expires after 30 days.
- KYC: a nonce-bound receipt signed by a key in `KYC_PROVIDER_KEYS`. The
  `open_source_kyc_v1` profile requires affirmative document-authenticity, biometric-
  liveness, and sanctions/PEP checks. The Oracle stores only an opaque subject reference,
  explicit check flags, validity timestamps, provider id, and receipt hash—never raw PII.

The route pairs are `POST /v1/agent/{id}/verify/{dns|github|tee|kyc}/challenge` and
`POST /v1/agent/{id}/verify/{dns|github|tee|kyc}`. Current evidence and the derived tier
are returned by `GET /v1/agent/{id}/verify`.

KYC uses `POST /v1/agent/{id}/verify/kyc/challenge` with `{"provider":"open-kyc"}`
and `POST /v1/agent/{id}/verify/kyc` with a signed receipt. The exact signed bytes are:

```text
integrity-kyc-receipt:v1:<agent_did>:<provider>:<opaque_subject_reference>:<assurance_profile>:<document_authenticity_0_or_1>:<biometric_liveness_0_or_1>:<sanctions_pep_screening_0_or_1>:<verified_at_unix>:<expires_at_unix>:<nonce>
```

`opaque_subject_reference` is restricted to 8–200 URL-safe characters. Receipts must be
currently valid, cannot begin more than five minutes in the future, and cannot last longer
than 365 days. A configured issuer signature proves which verifier asserted the checks; it
does not imply that every jurisdiction treats the profile as legally equivalent.

Evidence revocation is agent-authorized and audit-preserving:

1. `POST /v1/agent/{id}/verify/{verification_id}/revoke/challenge` returns a fresh
   60-minute nonce.
2. The client signs the UTF-8 bytes of
   `integrity-verification-revoke:v1:<did>:<verification_id>:<nonce>:<hex-utf8-reason>`
   with the Ed25519 key registered for the DID.
3. `POST /v1/agent/{id}/verify/{verification_id}/revoke` accepts
   `{"signature":"<hex>","reason":"<1-500 UTF-8 bytes>"}`. It sets `revoked_at`
   and `revoked_reason`, consumes the nonce, and returns the newly derived
   `effective_tier`; it never deletes the evidence row.

### 6.4 `EHRGate` reputation resolution (was: one immutable global registry)

`health/EHRGate.sol` used to hold one immutable global `ReputationRegistry`
address, read once at construction. Now that every agent owns its own
`ReputationRegistry` clone, there is no single address to point at.
`EHRGate` instead holds the shared `XibalbaAgentRegistry` and resolves
`msg.sender`'s own clone on every call:
```solidity
if (!registry.isRegisteredAgent(msg.sender)) return false;
address reputationRegistry = registry.resolveAgent(msg.sender).primitives.reputationRegistry;
if (ReputationRegistry(reputationRegistry).effectiveScore(msg.sender) < minAisThreshold) return false;
```
This resolution is itself a meaningful check, not just plumbing: an address
that was never registered through `AgentPrimitivesFactory` has no entry in
`XibalbaAgentRegistry`, so `checkAccess` returns `false` before it can even
reach the reputation check — closing off any hand-rolled contract that only
pretends to be a Sovereign Agent. All three of `EHRGate`'s gates (patient
consent, active BAA, AIS ≥ `minAisThreshold`) are required simultaneously;
consent alone is necessary but not sufficient.

### 6.5 Known gap: `CCIPReputationBridge` is unwired

`oracle/CCIPReputationBridge.sol` predates the per-agent clone model and
still assumes one global, immutable `ReputationRegistry` — its
`registry.getAgent(agent)` / `registry.updateScoreByBridge(agent, baseScore)`
calls no longer resolve to "the" registry for an arbitrary agent now that
every agent has its own clone. This is a documented, honest gap, not a
silently broken feature: the contract is **not** deployed by the deploy
script and **not** referenced by `AgentPrimitivesFactory`. It needs to be
reworked to resolve each agent's own `ReputationRegistry` clone via
`XibalbaAgentRegistry` before reading/writing a score, before it can be
wired back in. Don't build cross-chain reputation sync against this
contract as it stands today.

### 6.6 Deployments file shape

Local/dev deployments get written to `deployments.local.json` at the repo
root (gitignored). **This shape has changed** — it is no longer a flat list
of contract addresses, because most of those addresses no longer exist as
singletons:
```json
{
  "chainId": 31337,
  "singletons": {
    "IntegrityToken": "0x...",
    "IntegrityGovernance": "0x...",
    "UltraPlonkVerifier": "0x...",
    "XibalbaAgentRegistry": "0x...",
    "IntegrityIdentityReadV1": "0x...",
    "XibalbaNameService": "0x...",
    "DomainRegistry": "0x...",
    "AgentPrimitivesFactory": "0x...",
    "CoveredEntityRegistry": "0x...",
    "SmartBAAFactory": "0x...",
    "HIPAAGuardrailRegistry": "0x..."
  },
  "cloneTemplates": {
    "ReputationRegistry": "0x...",
    "Slasher": "0x...",
    "VerifierRegistry": "0x...",
    "ComplianceGate": "0x...",
    "AgentProfile": "0x..."
  },
  "protocolAddresses": {
    "oracleSigner": "0x...",
    "governance": "0x...",
    "funderWallet": "0x...",
    "resolverSigner": "0x..."
  }
}
```

**`XibalbaNameService` + `IntegrityGovernance` (optional singletons)**: both are
deployed by genesis `Deploy.s.sol` but their Base Sepolia broadcast is deferred, so
`deployments.baseSepolia.json` may legitimately omit either key. The oracle parses them
as `Option<Address>`; endpoints that need an absent one (`/v1/xns/resolve`,
`/v1/agent/{id}/handle`, `/v1/governance/proposals`) return `ChainError::MissingSingleton`
→ **HTTP 400** (a deployment-shape fact, not a transient failure — same mapping as the
market/health singletons) rather than fabricating a result. Dashboard consumers degrade to
an honest "not deployed" state on that 400.

`IntegrityIdentityReadV1` is also wired into future genesis deployments but
has not been broadcast to the existing Base Sepolia deployment. Its absence
there is an honest deployment-state gap, not a reason to rerun genesis or
migrate existing agents. Any incremental broadcast and deployment-file
mutation require separate approval and post-deployment readback.

**Market/application layer additions (§6.9)**: `singletons.MarketFactory` and
`singletons.A2ACapitalPool` (protocol-level, deployed once), plus
`cloneTemplates.IntegrityMarket` (the shared implementation `MarketFactory`
clones per-market — the sixth clone template, alongside the five identity
ones above). These are written by a SEPARATE, INCREMENTAL script,
`contracts/script/DeployMarkets.s.sol` — not genesis `Deploy.s.sol` — because
by the time the market layer was added, the genesis singletons already had
real registered agents on them; re-running `Deploy.s.sol` would redeploy
`IntegrityToken`/`XibalbaAgentRegistry`/etc from scratch and orphan every one
of them. `DeployMarkets.s.sol` reads the existing deployments file, deploys
only the new contracts against the existing `IntegrityToken`/
`XibalbaAgentRegistry` addresses, and merges the new fields into the same
file (every pre-existing field is re-serialized unchanged). This is now the
general pattern for any future protocol-layer addition after genesis: a new,
narrowly-scoped incremental script, never a re-run of `Deploy.s.sol` against
a live network.
- `singletons` — protocol-level contracts that exist exactly once, deployed
  by governance, unchanged from before except for the removal of
  `AgentFactory` (deleted) and `ReputationRegistry`/`Slasher`/`StateAnchor`
  (no longer singletons — see below) and the addition of
  `AgentPrimitivesFactory`.
- `cloneTemplates` — the 5 shared implementation contracts every agent's
  EIP-1167 clones delegatecall into (§6.1, #3–#7). These are deployed once
  with `_disableInitializers()` already called, so they can never be
  initialized/hijacked directly — only clones of them can be. Note
  `SovereignAgent` and `StateAnchor` do **not** appear here: they aren't
  clone templates, they're fully independent bytecode the agent deploys
  itself (§6.1).
- `protocolAddresses` — signer/governance addresses the deploy flow wires
  into `AgentPrimitivesFactory`'s constructor (`oracleSigner`, `governance`,
  and a `funderWallet` intended to gas-fund new agent wallets on Base
  Sepolia, since agents now sign their own deployment transactions instead
  of a shared factory paying for them).

**Per-agent primitive addresses are deliberately NOT in this static file.**
There is no fixed set of them — a new set of 7 is created every time an
agent registers. `integrity-oracle` is now built and is exactly this
resolution layer: `GET /v1/agent/{id}` resolves a given agent's primitives
live from `XibalbaAgentRegistry.resolveAgent`/`resolveDID` on-chain (via
`alloy`, see `integrity-oracle/backend/src/chain.rs`), independently
re-verifying anything a client claims rather than trusting it. Any package
needing an agent's primitive addresses should call the oracle's HTTP API
(what `bcc_middleware`'s `agent_id_to_address`/`resolve_agent_primitives`
does) rather than querying `XibalbaAgentRegistry` directly — the oracle is
the one place that owns turning a DID into live on-chain primitive state.

`integrity-oracle`, `integrity-sdk`, `integrity-cli`, and `integrity-dashboard`
read the *singleton and template* addresses from this file rather than
hardcoding them; per-agent addresses are always resolved live (or, once
built, via the oracle's cache) rather than read from any static file.

### 6.7 Integrity Health / regulated-industry compliance wiring

`health/ComplianceGate.sol` (primitive #6, §6.1) is the concrete wire
between the core protocol and the Integrity Health (HIPAA) vertical, and it
is worth spelling out because it has two halves that must never be
confused with each other:

- **Live-verified compliance** — `isHealthcareCompliant(coveredEntity)`
  returns `true` only if (a) the agent declared `Vertical.Healthcare` at
  registration (`ComplianceGate.vertical`, set once in `initialize` from
  `AgentPrimitivesFactory.registerPrimitives`'s `vertical` parameter) *and*
  (b) a live on-chain read against the real `CoveredEntityRegistry`
  (`isActiveCoveredEntity`) and `SmartBAAFactory` (`isBAAActive`) both
  pass. `CoveredEntityRegistry` and `SmartBAAFactory` addresses are baked
  into `ComplianceGate`'s implementation contract as constructor
  immutables (shared across every agent's clone, same pattern as
  `AgentProfile`'s `domainRegistry`), so every clone reads the same,
  correct Integrity Health registries without a per-agent storage write. This is a
  read path only — `ComplianceGate` does **not** replace `EHRGate` as the
  PHI-access enforcement boundary; `EHRGate.checkAccess` still performs its
  own independent live checks (patient consent, BAA, AIS threshold — §6.4)
  at access time. `ComplianceGate` is a read-optimized compliance summary
  for callers like integrity-oracle's `S_compliance` AIS component or
  integrity-dashboard's Integrity Health page, not a second enforcement point.
- **Self-declared compliance** — `hipaaEligible`, `zdrEnabled`,
  `externalWebAccessDeclared`, `dataResidencyRegion`, set via
  `setSelfDeclaredCompliance` (routed through `SovereignAgent.execute`,
  per §6.2 — `ComplianceGate`'s admin is the agent's own `SovereignAgent`).
  These mirror `integrity_sdk/telemetry/conventions.py`'s
  `IntegrityAttributes.COMPLIANCE_HIPAA_ELIGIBLE` /
  `COMPLIANCE_ZDR_ENABLED` / `COMPLIANCE_EXTERNAL_WEB_ACCESS` /
  `COMPLIANCE_DATA_RESIDENCY_REGION` span attributes — i.e. they are an
  on-chain mirror of an off-chain-attested claim the agent makes about
  itself. `isHealthcareCompliant` never reads any of these fields. Treat
  them as "what the agent says about itself" vs. "what the chain actually
  verified" — a consumer that needs an enforceable guarantee (e.g. gating
  PHI access) must use the live-verified boolean or `EHRGate`, never the
  self-declared flags.

### 6.8 Agent Contract Ownership — a formal protocol primitive

**This is the protocol's core architectural thesis, stated once, formally,
so every future package builds on it consistently rather than
reinventing it ad hoc.** Integrity Protocol agents do not merely *use*
smart contracts the way a normal dApp user does — they **own and deploy**
them, and that ownership is itself the cryptographic substrate the rest of
the protocol (reputation, compliance, markets) is built on. Two deployment
modes are both first-class, and any future primitive or application layer
must pick one of them explicitly rather than a third, undocumented pattern:

1. **Direct deployment.** The agent's own EVM wallet signs and broadcasts
   the contract-creation transaction itself. The deployment signature *is*
   the proof of self-sovereign control — nobody else's key could have
   produced it. This is how `SovereignAgent` and `StateAnchor` work (§6.1,
   primitives #1–#2), and it is available to any agent for a fully custom,
   hand-authored contract too, with no protocol factory involved at all —
   an agent can deploy literally anything from its own wallet.
2. **Factory-mediated clone deployment.** The agent calls a shared,
   protocol-level factory to cheaply clone (EIP-1167) and initialize its
   own instance of a shared implementation contract. The agent still ends
   up as that clone's owner/admin (`DEFAULT_ADMIN_ROLE` = the agent's
   `SovereignAgent` address, per §6.2's call-routing convention) — the
   factory only pays the one-time cost of the shared implementation's
   bytecode once, not per agent. This is how primitives #3–#7 work
   (`AgentPrimitivesFactory`), and — critically — it is **not limited to
   identity primitives**. `MarketFactory` (§6.9) applies the exact same
   pattern one layer up, at the *application* level: any registered agent
   can deploy and own its own customized `IntegrityMarket` instance the
   same way it owns its `ReputationRegistry` clone. This is the concrete
   proof that "agents own their contracts" is a general protocol property,
   not a one-off fact about identity.

**Why this matters beyond mechanics:** it inverts the usual "platform owns
the contract, users are just addresses in someone else's system" model.
Trust earned by one agent-owned contract (a market it created, a
reputation ledger it accrued) is portable and composable, because it's
genuinely the agent's own on-chain footprint — not a row in a platform
database the agent has no control over. Any future application layer
(lending, insurance, whatever comes after `integrity-framework`, §12)
should extend this same two-mode pattern rather than introducing a third,
platform-owned model. `integrity-dashboard`'s Contracts/Factory-IDE page
(§9) is expected to expose BOTH modes to a human operator/developer: a
"deploy from template" path calling a factory, and a "deploy custom" path
where the agent's own wallet broadcasts a contract the developer authored
directly.

### 6.9 Market / application layer (`contracts/src/markets/`)

The first concrete application of §6.8's second mode beyond identity.
Global infrastructure, deployed via the incremental `DeployMarkets.s.sol`
script (§6.6):

- **`IntegrityMarket.sol`** — an EIP-1167 clone template (like primitives
  #3–#7), NOT a singleton. One clone = one market. Backs both prediction
  markets (N outcomes) and binary options (the 2-outcome case) as the same
  mechanism. `enterPosition` gates entry on the caller's LIVE
  `ReputationRegistry.effectiveScore` (resolved via `XibalbaAgentRegistry`,
  same pattern as `EHRGate.checkAccess`, §6.4) and records a
  `bccCommitmentHash` binding the position to the agent's off-chain BCC
  commitment (§4.2) — the position is provably the agent's own
  pre-committed call, not a reaction to information obtained afterward.
  Payout is pari-mutuel across the full pool on `resolve`.
  - ***Trust boundary, documented not hidden***: `resolve()` is gated to
    `RESOLVER_ROLE`, set by the market's creator at deploy time (itself, a
    delegate, or the protocol's demo/oracle signer). For the
    investor/developer Dashboard this is a clearly-labeled demo resolver, not a
    live price-feed oracle network (Chainlink/UMA) — staking, AIS-gating,
    BCC-commitment binding, and payout are all real; only ground-truth
    outcome resolution is a documented, swappable trust boundary. A
    production deployment swaps `RESOLVER_ROLE`'s holder; the contract's
    interface doesn't change.
  - Fraud/misreporting (a BCC-committed intent not matching an agent's
    actual position) is deliberately NOT handled inside this contract — the
    oracle is expected to compare telemetry/BCC commitments against
    on-chain positions and raise a dispute on the offending agent's own
    `Slasher` clone (the existing mechanism, §6.1 primitive #4). This keeps
    `IntegrityMarket` a small, auditable escrow rather than a second
    slashing engine.
- **`MarketFactory.sol`** — the factory (singleton) any registered agent
  calls to deploy+own its own `IntegrityMarket` clone. Deliberately
  ungated (no curator role, unlike `SmartBAAFactory`'s entity-registry
  check) — restricting *who* may create a market would undercut §6.8's
  thesis. Discovery/quality (e.g. surfacing markets by creator AIS) is a
  dashboard/oracle-index concern, not an on-chain gate.
- **`A2ACapitalPool.sol`** — a global singleton (deliberately NOT
  agent-clonable like `IntegrityMarket` — a capital pool is a shared
  many-allocator-to-many-agent venue, not an application one party
  authors and owns). Real on-chain agent-to-agent capital allocation:
  `allocate` escrows ITK from an allocator (a human wallet, or another
  agent's `SovereignAgent`) earmarked for a target agent, gated on that
  target's live AIS; `release` pays out (re-checking the AIS gate);
  `clawback` reclaims still-escrowed (pre-release) funds. Post-release
  misconduct has no fund-reversal path in this contract by design — the
  punitive lever is the target agent's own `Slasher`; `flagBreach` records
  a non-fund-moving history marker for dashboard/leaderboard display.
- **`ComplianceGate.Vertical`** (§6.7) extended: `{ None, Healthcare,
  PredictionMarket, Trading, CapitalAllocation }`. New values are
  additive-only (existing numeric ids never change). Like `Healthcare`'s
  self-declared flags, these have no live-verified `is*Compliant` check of
  their own yet — they're a self-declared operating-domain badge for
  dashboard/discovery, and do **not** gate `IntegrityMarket`/
  `A2ACapitalPool` participation, which only ever check live AIS.

### 6.10 Backend responsibility split (two trust domains, not three peer services)

As of the multi-vertical Dashboard, protocol-facing HTTP is split across two
**trust domains** — not three interchangeable peer services, a framing
this section used to have and which undersold how tightly the first two
pieces below are coupled — with one hard rule: **only `integrity-oracle`
ever reads on-chain state.** No other backend queries a chain RPC or a
contract directly.

- **The Oracle trust domain — one domain, two processes, split by
  before/after the action:**
  - **`bcc_middleware`** (§7, Python/FastAPI) — the BEFORE-the-action
    half: pre-execution BCC/OPA policy gating, real on-chain BAA checks,
    Merkle anchoring. An agent's own process could simply skip calling an
    SDK-side check, which is why this can't live in `integrity-sdk` — it
    has to be a service the agent cannot bypass or tamper with, and it
    does real on-chain reads/writes, which is Oracle's territory, not a
    peer concern.
  - **`integrity-oracle`** (§2, Rust/Axum) — the AFTER-the-action half
    (plus always-on reads): agent registration re-verification, telemetry
    ingest, AIS computation, and live reads of markets, positions,
    allocations, wallet balances, and a derived leaderboard (§6.9). No
    demo-orchestration logic lives here — it is a read/verify layer over
    real on-chain + telemetry state, nothing else.
  - These two keep separate codebases/processes (no forced rewrite —
    `bcc_middleware` stays Python, `integrity-oracle` stays Rust) but are
    organizationally one deployment group and one trust boundary: both
    independently re-verify what a client claims against real on-chain/
    policy state rather than trusting it.
- **`integrity-userapi`** (FastAPI + Postgres, §13) — a second, separate
  trust domain: user-facing data ONLY — accounts/auth, developer API
  keys, which DIDs a human user has claimed as "theirs," and a record of
  demo runs a user requested. It never calls a contract or a chain RPC;
  anything protocol-related it needs, it fetches from `integrity-oracle`
  over HTTP (`ORACLE_URL`). This keeps the oracle's scope narrow and
  auditable and keeps user-account concerns (passwords, sessions,
  ownership) out of a service whose whole job is being a trustworthy
  on-chain-state verifier.

`integrity-dashboard` (the one dashboard/landing app, §9) is the only client
expected to talk to both the Oracle trust domain and `integrity-userapi`
directly.

## 7. OPA policy integration (must be real, no "assume success" fallback)

- `bcc_middleware/policies/*.rego` holds the real Rego policies (carry over the
  HIPAA guardrail logic from the old repo, cleaned up).
- Both `bcc_middleware` and `integrity-sdk` evaluate policy by calling a real,
  running OPA server's REST API: `POST {OPA_URL}/v1/data/integrity/bcc/allow`
  with the intent as `input`. No local regex-only fallback path — if OPA is
  unreachable, the request must fail closed (deny), not silently approve.
- Ship a `bcc_middleware/policies/*_test.rego` suite runnable via `opa test .`

## 7a. Reputation sync & slashing signer (`bcc_middleware/app/reputation.py`, `scoring_loop.py`)

`bcc_middleware` is also the protocol's oracle-signer/disputer for on-chain reputation —
not just the pre-execution BCC policy gate §7 describes. A periodic background loop
(started at FastAPI `lifespan` startup, `SCORE_SYNC_INTERVAL_SECONDS`, default 300s;
also triggerable on-demand via `POST /v1/reputation/sync`) lists every agent the oracle
knows about and, per agent:

1. Treats `GET /v1/agent/{id}/ais`'s final `ais` as authoritative and removes only its
   reported `zk_boost` (`baseScore = round(ais / zk_boost)`) before signing and submitting
   `ReputationRegistry.updateScore(agent, baseScore)`. It MUST NOT recompute from
   `components`/`weights`: doing so duplicates the canonical Rust formula and loses the
   Oracle's already-applied effective identity-tier ceiling. The contract independently
   earns and applies its own on-chain ZK boost.
2. Reads `GET /v1/agent/{id}/telemetry/volume`'s flagged-event ratio over a lookback
   window (`DISPUTE_LOOKBACK_BUCKET`); if it crosses `DISPUTE_FLAGGED_RATIO_THRESHOLD`
   with at least `DISPUTE_MIN_EVENTS` samples, signs+submits a real
   `Slasher.raiseDispute(agent, amount, reason)` locking `DISPUTE_STAKE_BPS` of the
   agent's currently-available stake, subject to a `DISPUTE_COOLDOWN_SECONDS` per-agent
   cooldown.

Reuses the existing `ANCHOR_SIGNER_PRIVATE_KEY` (Merkle-anchoring signer) by default via
`REPUTATION_SIGNER_PRIVATE_KEY`'s fallback, rather than a dedicated key — a deliberate,
user-made tradeoff documented in `PRODUCTION_GAPS.md` §1. `integrity-oracle` itself
remains read-only; it never signs or submits a transaction (see `chain.rs`).

## 8. TEE attestation (honest real-verification scope)

We do not have real Nitro/SGX hardware in this environment, so we cannot
*generate* genuine attestation documents. But the *verification* code must be
real: parse the actual AWS Nitro Enclave COSE_Sign1/CBOR attestation format,
verify the COSE signature against the embedded leaf certificate, and verify
the certificate chain up to AWS's published Nitro root CA. Use AWS's publicly
documented example attestation document as a test fixture (cite the source in
a code comment). Document explicitly in `integrity-sdk/security/attestation.py`
and its README that proof *generation* needs real enclave hardware we don't
have, while verification is fully implemented and tested against the fixture.
Do not leave literal placeholder strings like the old `"MRENCLAVE_STUB"`.

## 9. Directory layout (top level)

```
integrity-core/
  docs/INTERFACE_CONTRACT.md   <- this file
  docker-compose.yml
  Makefile
  .gitignore
  README.md
  contracts/
  integrity-zkp/
  integrity-oracle/
  integrity-sdk/
  integrity-cli/
  bcc_middleware/
  integrity-userapi/
  integrity-dashboard/            <- the ONE dashboard/landing app
    src/                     (React/Vite/TS — every product page)
    demo/                    (Python closed-loop scenario engine, §11 — a
                               script this package runs, not a second app)
```

`integrity-dashboard/` and `integrity-demo/` (below in §11's prose, and
anywhere else in this doc) were two separate packages until 2026-07-09,
when they were merged into `integrity-dashboard/` — one deployed app, per the
"exactly one user-facing product surface" rule. Any reference elsewhere in
this document to either old name means the corresponding piece of
`integrity-dashboard/`.

Each package keeps its own README, its own `.env.example`, its own test
suite, and its own CI-runnable `make test` / `make build` targets, wired into
the root `Makefile` and `docker-compose.yml`.

## 10. Code style

Same languages/frameworks as the old repo per package (Solidity/Foundry,
Noir, Rust/Axum, Python SDK+CLI, FastAPI, React/Vite/TypeScript). Code must
be commented for a human reader: explain *why*, not *what* — skip comments
that just restate the code, but do explain non-obvious cryptographic/protocol
invariants, since this is exactly the kind of code where a subtle mistake
(e.g. hash ordering, signature domain separation) is a real vulnerability.

## 11. integrity-dashboard/demo/ (multi-vertical investor/developer closed-loop Dashboard)

Lives at `integrity-dashboard/demo/` — a Python subdirectory of the one
dashboard app package (§9), not a standalone top-level package (it was
`integrity-demo/` until the 2026-07-09 merge). It has no UI of its own: a
runnable script/CLI entrypoint (`make demo` from the repo root) that
drives real on-chain activity for `integrity-dashboard`'s dashboard pages to
display — the dashboard reads the results back out via `integrity-oracle`
(live chain reads) and `integrity-userapi` (`GET /demo/runs`), it does not
embed or launch this script itself.

Purpose: prove the whole stack works end-to-end, across MULTIPLE verticals,
by running a small fleet of real agents through a real, repeated loop — not
a static mockup, not canned data, not a single-vertical toy. This is the
flagship demonstration of §6.8's thesis (agents own their contracts, and
that ownership underwrites real financial + regulated actions) — the
target audience is investors and developers, so every step must be
independently verifiable (real tx hashes, real BaseScan links when run
against Base Sepolia), not narrated-but-faked.

**Agent fleet** (each REALLY self-registers all 7 primitives via
`integrity-sdk`'s `registration.register_agent`, real wallet, real minted
ITK — see §6.3): an honest, well-grounded agent whose AIS climbs and wins
real market calls; a reckless/overleveraged agent whose AIS decays; an
agent exercising the real Integrity Health/healthcare vertical (`§6.7`, real
`CoveredEntity` + `SmartBAA` + `EHRGate` access flow); and a scenario
demonstrating what a BCC-commitment/on-chain-action mismatch would surface
once oracle-side detection exists (honestly labeled if not yet automated —
never a faked slash event).

**Loop, generalized across verticals**: an agent signs a real BCC
Commitment (§4.2) for its intended action → `bcc_middleware`'s
`/v1/bcc/intercept` (real OPA evaluation, real circuit breaker) → the
action lands on a real vertical contract (`IntegrityMarket`/
`A2ACapitalPool` from §6.9, or `EHRGate` for the healthcare vertical) →
real telemetry reported to `integrity-oracle` → the oracle recomputes AIS
(§4.3) and (for markets/allocation) the demo's resolver settles real ITK
payouts → the fleet's *next* actions are chosen with awareness of each
agent's own current score — closing the loop. Capital visibly reallocates
toward the trustworthy agent via `A2ACapitalPool` as the loop progresses.

This package depends on the real, running `integrity-sdk` and deployed
`contracts/` (both required); `bcc_middleware`/`integrity-oracle` are
strongly preferred for full realism but the SDK's lower-level,
non-BCC-gated functions (`markets.enter_position`, etc.) let the core
chain mechanics be proven even if those services aren't up in a given
environment — any such gap must be stated explicitly in this package's own
`README.md`, never silently skipped. It holds the demo `RESOLVER_ROLE`
(§6.9) via a dedicated signer (`RESOLVER_PRIVATE_KEY`, §3). It has its own
`README.md` with exact run instructions (which services need to be up, in
what order, for local anvil vs. Base Sepolia) and its own real test
coverage for the scenario logic (not the sibling services, which are
tested in their own packages). `integrity-userapi` (§13) may record that a
user triggered a given demo run (`POST /demo/run`), but orchestrating the
run itself is entirely this package's job, not the user API's.

## 12. integrity-framework/ (reputation-derivatives — not yet built)

Referenced in §1's scope list but not part of this rewrite's current
phases (§6.8–§6.10, §11, §13 cover the multi-vertical Dashboard that now
supersedes what this package was originally scoped to explore). Concept
carried over from the old repo: a marketplace/lending layer over agent
reputation (e.g. AIS-collateralized credit, reputation derivatives). Any
future work here should build on §6.8's agent-contract-ownership pattern
(agents deploying/owning their own lending-position contracts via a
factory, the same way `MarketFactory`/`A2ACapitalPool` do today) rather
than introducing a new ownership model. Marked here explicitly as
**not yet built** per the "no silent mocks" ground rule — do not assume
any `integrity-framework/` code exists.

## 13. integrity-userapi/ (user accounts — strictly non-chain)

Purpose: own user-facing data (accounts, auth, developer API keys,
agent-ownership claims, demo-run history) with zero smart-contract or
chain-RPC access of its own — see §6.10 for the full three-backend split
rationale. FastAPI + a real Postgres (never sqlite/mocked in tests).

Real schema (illustrative, see the package's own migrations for the
authoritative shape): `users` (email, hashed password), `api_keys`
(hashed key, `ais_trust_ceiling` — mirrors the old dashboard's
developer-key convention of capping dev-issued agents at a fixed AIS
ceiling), `user_agents` (a user_id ↔ agent DID ownership POINTER only —
never a cache of full agent state, which always comes live from
`integrity-oracle`), `demo_runs` (status/history of `integrity-dashboard/demo/`
invocations a user requested).

Core endpoints: `POST /auth/register`, `POST /auth/login`, `GET /me`,
`POST /api-keys` (returns the raw key exactly once, stores only its
hash), `GET /api-keys`, `DELETE /api-keys/{id}`, `GET /me/agents` (fans
out to `integrity-oracle`'s `GET /v1/agent/{id}` for live data per owned
DID — never duplicates it locally), `POST /me/agents`, `POST /demo/run`,
`GET /demo/runs`.

Hard rule, worth repeating from §6.10 because it is the one invariant this
whole package exists to preserve: if a change to this package would
require importing `web3`/`alloy`-equivalent tooling or reading a
`deployments.*.json` file, that change belongs in `integrity-oracle`
instead.

**Postgres, wiring, tests (as of 2026-07-09):** `docker-compose.yml` has a
dedicated `userapi-postgres` service (`postgres:16-alpine`,
`integrity`/`integrity_dev_only`, db `integrity_userapi`, host port
`5435`) — deliberately its own instance/port, never sharing
integrity-oracle's `postgres` service (5432) or its ad hoc e2e-test
convention (5434, see `integrity-oracle/README.md`), since two separate
Postgres instances per trust domain is the whole point of the §6.10 split.
The `userapi` app service builds `integrity-userapi/Dockerfile` (uv-based,
same pattern as `bcc_middleware/Dockerfile`) and exposes 8090. 33 real
pytest tests in `integrity-userapi/tests/` run against a real Postgres via
this same server (a separate `integrity_userapi_test` database,
auto-created by `tests/conftest.py` on first run) — unlike
`integrity-oracle`'s opt-in/env-gated e2e test, this suite has no skip
path: it fails hard (connection refused at collection time) if
`userapi-postgres` isn't reachable, since "pytest green against a real
Postgres" is this package's stated completion gate, not an optional extra.
The `GET /me/agents` tri-state (live data / not found / oracle
unreachable) is tested against a real local HTTP server standing in for
`integrity-oracle`, never a mock of `app/oracle_client.py`'s internals.

**CORS (added 2026-07-09, real gap found wiring `integrity-dashboard`'s auth
swap):** this service had no CORS policy at all before — every request
from a browser-hosted `integrity-dashboard` (served by Vite on its own port,
never the same origin as this API) would be blocked outright. Fixed with
`fastapi.middleware.cors.CORSMiddleware` in `app/main.py`
(`allow_origins=["*"]`, `allow_credentials=False` — every authenticated
request here carries a `Authorization: Bearer <jwt>` header, never a
cookie, so a wildcard origin is safe; combining a wildcard origin with
`allow_credentials=True` is invalid per the CORS spec anyway). Verified:
`integrity-userapi`'s 33 pytest tests still pass unchanged after the
addition (CORS is a browser-enforced concern, invisible to a server-side
test client), and a real cross-origin browser call from `integrity-dashboard`
(Playwright, `e2e/auth.spec.ts`) now succeeds end-to-end.

## 14. integrity-dashboard's real integration with integrity-userapi (auth swap, 2026-07-09)

Per §13's "one unified app" rule and the previously-pending item this
section resolves: `integrity-dashboard`'s dashboard now authenticates against
this service for real (`src/lib/api/userapi.ts`, `src/auth/AuthContext.tsx`)
— the Firebase-based `AuthContext`/`AuthGate`/`firebase.ts` from the
original scaffold are gone, not left running alongside a second auth
system. A JWT from `POST /auth/login`/`POST /auth/register` is stored in
`localStorage` and attached to every `userapiClient` request via an axios
request interceptor (`src/lib/api/client.ts`). Only account-scoped routes
(`/account` — API keys, owned-agent pointers, demo-run history) sit behind
a real session check; Landing, the agent list/detail, markets,
leaderboard, and wallet stay public — real protocol data doesn't require
an account to read, matching investor/developer intent. `integrity-dashboard/e2e/global-setup.ts`
now boots a real `integrity-userapi` instance (its own ephemeral Postgres
database on the same E2E container, real `uvicorn` process) alongside the
oracle, so `e2e/auth.spec.ts` exercises real registration, real login, and
a real 401 on bad credentials against this actual service — not a mock.

### Real oracle wire-shape corrections found while wiring this (integrity-oracle untouched, worked around client-side)

Running the pre-existing Playwright suite for the first time (before this
pass's fixes) surfaced that `integrity-dashboard`'s `lib/api/types.ts` had
drifted from what `integrity-oracle/backend/src/handlers.rs` actually
serializes — 4 of 5 specs failed. Documented here because it's a
cross-package contract fact, not just an `integrity-dashboard`-internal detail:

- `GET /v1/agents` returns `{id, verification_tier, created_at}`
  (`AgentSummary`) — no `ais`/`alias`/`zk_proof_verified`/`registered_at`/
  `last_active` fields ever existed in this response; those were an
  unverified assumption in the original dashboard scaffold.
- `GET /v1/agent/{id}` (`AgentResponse`) never returns a `did_document` —
  `POST /v1/agent/register`'s `RegisterAgentRequest.did_document` is
  accepted on the way in but never persisted or returned by any GET. A
  real, confirmed gap (not fixed here — out of `integrity-dashboard`'s scope to
  fix the oracle).
- `PrimitiveSetDto`'s own doc comment in `handlers.rs` claims its fields
  match the dashboard "field-for-field (camelCase)" — this is incorrect;
  the struct has no `#[serde(rename_all = "camelCase")]`, so it actually
  serializes snake_case (`sovereign_agent`, `state_anchor`, ...). Worth
  fixing the stale comment (or adding the attribute) in a future
  `integrity-oracle` pass; `integrity-dashboard` now assumes the real snake_case
  shape.
- `ComplianceResponse` fields are `is_compliant`/`covered_entity`
  (snake_case), not the `isCompliant`/`coveredEntity` the original
  dashboard scaffold guessed.
- `AisResponse.weights` (`scoring_core::AisWeights`) fields are
  `w_entropy`/`w_grounding`/`w_sacrifice`/`w_compliance`, and there is no
  `history` array anywhere in the response — the dashboard's old AIS
  sparkline was reading a field the oracle never sends.

`GET /v1/markets`, `GET /v1/markets/{id}`, `GET /v1/leaderboard`, and
`GET /v1/agent/{id}/wallet` had no prior dashboard assumption to drift from
(first-time consumers) and match `handlers.rs` as documented in §6.9. Note that
`GET /v1/agent/{id}/wallet` now returns a `WalletResponse` containing not just balances, but also
arrays for `transaction_history` and `allowances` to power the Finance UI.
`integrity-oracle` exposes **no** `A2ACapitalPool` read endpoint at all
(confirmed against `routes.rs`) — `integrity-dashboard`'s Capital Allocation page
states this as a real, visible gap rather than fabricating live pool data.

## 15. Financial action, session integrity & Xibalba Shield wire-format additions (2026-08-01)

Normative source: [`spec/integrity-protocol-v0.4.md`](../spec/integrity-protocol-v0.4.md) §21–§22
and [`spec/xibalba-shield-v1.md`](../spec/xibalba-shield-v1.md). Everything in this section is
`[PLANNED]` — no package implements any of it yet. Recorded here because these are exactly the
kind of cross-package schema facts this document exists to pin *before* two packages drift into
incompatible guesses about a shared shape, per this file's own purpose.

### 15.1 `intent_type` namespace extensions (extends §4.2's BCC Commitment)

`BCC Commitment.intent_type` already accepts any string — no schema change is required for
either table below to become valid today. What's pinned here is the **vocabulary**, so
`bcc_middleware`'s policy packs (`docs/ENTERPRISE_ADOPTION.md` Lever 3) and any future export
tooling can pattern-match a stable enum instead of ad hoc strings per integrator.

**Financial** (protocol spec §21.2): `payment_authorize`, `payment_capture`,
`payment_transfer`, `payment_stablecoin`, `payment_escrow_lock`, `payment_escrow_release`,
`payment_refund`, `payment_dispute`, `fx_convert`, `limit_reserve`, `limit_release`,
`wallet_sign`.

**Xibalba Shield security events** (Shield spec §5.6): `shadow_agent_detected`,
`agent_contained`, `connection_blocked`, `guardrail_denied`, `phi_access_attempt`,
`device_posture_change`.

### 15.2 Action Receipt (formalized name for an existing pairing, not a new object)

An **Action Receipt** is the existing join of a `bcc_middleware` policy decision to its
`anchor_events` row by leaf hash (`docs/design/evidence-export.md` Phase A). No new field, no
new table. The name exists so this pairing can be referenced by external audit-trail schemas
(the AAT-shape research this addition is based on) without a package inventing a second,
parallel concept for the same evidence.

### 15.3 `session_integrity_v1` (optional, additive Action Receipt extension)

```json
{
  "risk_threshold_profile_id": "session_term_v1",
  "R_session": 0.0,
  "action_ladder": "M|S|H|T|K",
  "drift_score": 0.0,
  "pin_hash": "0x...",
  "hard_override": null
}
```

Absence on any given commitment means "not yet implemented for this commitment," never "passed
a session-integrity check that does not exist." See protocol spec §22.7 for the full definition
and §22 for the risk model this field summarizes.

### 15.4 Xibalba Shield event schemas — where they live

`ProcessActivity` / `FileActivity` / `NetworkFlow` / `AgentEvent` / `PolicyDecision` are defined
in full in [`spec/xibalba-shield-v1.md`](../spec/xibalba-shield-v1.md) §5 — **not duplicated
here**, to avoid the exact two-copies-drift failure mode this document exists to prevent. A
`PolicyDecision` becomes a BCC commitment via the §15.1 `intent_type`s above; the mapping is
Shield spec §4.5, not a new oracle endpoint. `integrity-oracle` requires **no route changes** to
receive Shield telemetry — it arrives through the existing `POST /v1/bcc/intercept` and
telemetry-ingest paths (§2, §4.2 above) like any other agent's traffic.

## 16. Whitepaper v3.2 / proposed v0.5 interface status (2026-08-17)

Normative status: [`spec/integrity-protocol-v0.5-proposed.md`](../spec/integrity-protocol-v0.5-proposed.md)
is a review candidate, not an active interface version. No package may emit a v0.5 profile
identifier or claim v3.2 conformance merely because a related local mechanism exists.

| Proposed surface | Current internal interface status |
|---|---|
| Identity read profile | **LOCAL / TESTED:** `IntegrityIdentityReadV1` is defined in §6.1a; custom and explicitly non-ERC-8004; not deployed to Base Sepolia. |
| AIS fail-closed evidence | **PARTIAL:** empty entropy/grounding and empty self-reported compliance default to zero; no accepted `ais/v0.5-*` profile, floor vector, pre-boost constraint score, or migration wire field exists. |
| Federated telemetry prover | **PLANNED:** no validator-set, threshold-signature, disagreement, rotation, or quorum wire schema exists. The current Oracle remains Trusted and single-operator. |
| Memory availability escrow | **PLANNED:** no challenge/stake/deadline/production/slashing schema or contract exists in integrity-core. |
| Grace-mode adapter | **PLANNED:** no hard/soft partition, contraction-function, freshness, recovery, or staged-settlement schema exists. |
| High-frequency channel / `integrity-dsl` | **PLANNED:** no channel-head envelope, settlement interface, compiler manifest, or generated-adapter profile exists. |
| Attested-host profile | **PLANNED:** existing TEE-related evidence does not satisfy the v3.2 transaction/session binding, freshness, measured-egress, or joint-boundary requirements. |

The next interface revision for any planned row must define a versioned schema, authority and
replay domain, fail-closed behavior, conformance vectors, and migration rule before package code
or documentation treats the surface as available.
