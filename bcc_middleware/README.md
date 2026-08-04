# bcc_middleware

Pre-execution policy gating ("Behavioral Commitment Chain") for the
Integrity Protocol. A FastAPI service that sits in front of agent actions:
agents (via `integrity-sdk` / `integrity-cli`) POST a signed intent
commitment to `POST /v1/bcc/intercept` before executing it; this service
decides authorize/deny and only then does the agent proceed.

See `docs/INTERFACE_CONTRACT.md` at the repo root for the binding
cross-package spec (§4.2 commitment schema, §6 deployments file, §7 OPA
integration). This README covers this package's internals and exactly what
still needs to be reconciled with sibling packages built in parallel.

### Where this sits in the self-sovereign model

The protocol's defining choice is that **agents own and deploy their own
on-chain contracts** (identity, reputation, a per-agent HIPAA `ComplianceGate`,
a per-agent `StateAnchor`). This middleware is the agent's *pre-execution
conscience*: before an agent acts, it commits to what it's about to do, signs
that commitment with the same DID key that controls its on-chain identity, and
this service decides allow/deny — checking real OPA policy and, for healthcare
actions, the agent's real on-chain Business Associate Agreement. The
implications for this package: (1) the signature is verified against the agent's
*self-certifying* key (the commitment carries it — see reconciliation point 2),
and (2) the BAA and anchoring checks target **per-agent** contract instances
resolved from the on-chain registry, not one global contract.

## Architecture

```
POST /v1/bcc/intercept
  │
  ├─ 0. pydantic schema validation (app/schemas.py)          -- reject malformed shape
  ├─ 1. circuit breaker check (app/circuit_breaker.py)       -- cheap, no I/O, checked first
  ├─ 2. Ed25519 signature verification (app/canonical.py)    -- untrusted agent_id claim -> hard deny
  ├─ 3. nonce replay check (app/nonce_store.py)               -- monotonic per-agent nonce
  ├─ 4. freshness / timestamp window check
  ├─ 5. OPA policy evaluation (app/opa_client.py)             -- FAIL CLOSED if OPA unreachable
  ├─ 6. on-chain BAA check, only if OPA says requires_baa     -- FAIL CLOSED if can't verify
  │     (app/baa.py, real eth_call via web3.py)
  └─ 7. admit to Merkle batch + best-effort on-chain anchor   -- NOT a gate (app/merkle.py, app/anchor.py)
```

**Fail-closed vs. best-effort — the one property to get right in this
service:**
- Steps 5 and 6 (OPA policy, on-chain BAA) are *authorization* decisions.
  If we cannot positively confirm "allowed" / "BAA active" for any reason
  — OPA down, malformed OPA response, chain RPC down, BAA contract not yet
  deployed — the request is **denied**. There is no fallback path that
  approves on error; see `app/opa_client.py` and `app/baa.py` docstrings.
- Step 7 (Merkle anchoring) happens *after* authorization is already
  decided. It's an audit trail, not a gate, so its failure is logged and
  retried later, not surfaced as a denial of an already-authorized action
  — see `app/anchor.py` docstring for the reasoning.
- The circuit breaker only counts violations **attributable to the agent**
  (bad signature, replay, an actual OPA denial, an inactive BAA). Our own
  infrastructure being down (OPA/chain unreachable) denies the request but
  never trips the breaker — otherwise an OPA outage would lock out every
  well-behaved agent in the fleet. See `app/circuit_breaker.py`.

## Running locally

### 1. Install dependencies
```bash
uv sync
```

### 2. Start a real OPA server loaded with this package's policies
```bash
opa run --server --addr=127.0.0.1:8181 policies/
```

### 3. Start a local anvil chain (for the on-chain BAA check / anchoring)
```bash
anvil --port 8545
```
Until `contracts/` has deployed `SmartBAA` / `StateAnchor` and written
`deployments.local.json` (§6), the BAA check will return `CANNOT_VERIFY`
(and therefore deny any healthcare-vertical intent) and anchoring will be
skipped (logged, not blocking) — this is the correct, documented fail-safe
behavior, not a bug.

### 4. Run the service
```bash
cp .env.example .env   # edit as needed
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. Run the test suites
```bash
opa test policies/ -v          # 28 policy unit tests
uv run pytest -q               # 75 tests: signature, merkle, circuit breaker,
                                # fail-closed OPA, reputation-sync/dispute
                                # (app/reputation.py, app/scoring_loop.py), and
                                # REAL on-chain eth_call / eth_sendTransaction
                                # tests against a local anvil + minimal fixture
                                # contracts this package deploys for itself
                                # (see tests/fixtures/foundry/ and tests/conftest.py)
```
The pytest suite starts its own throwaway `anvil` and `opa run --server`
subprocesses per session (see `tests/conftest.py`) — you don't need step 2/3
running to run `pytest`, only to run the service itself.

### Docker
```bash
docker build -t bcc-middleware .
```
Matches the root `docker-compose.yml`'s `bcc-middleware` service: port 8000,
`OPA_URL` / `ORACLE_URL` env vars, depends on the `opa` and
`oracle-backend` services.

## What's real here (per the "no silent mocks" ground rule)

- **OPA policy evaluation**: a real HTTP call to a real running OPA server
  (`app/opa_client.py`). Any failure mode — connection refused, timeout,
  non-200, malformed JSON, missing `result` key — raises
  `OPAUnavailableError`, and the caller denies. Verified by
  `tests/test_opa_fail_closed.py`, including a test that points at a TCP
  port with nothing listening at all (`opa` genuinely never started for
  that test, not mocked).
- **On-chain BAA check**: a real `eth_call` via `web3.py` (`app/baa.py`) to
  `isBAAActive(address coveredEntity, address businessAssociate) returns (bool)`
  — reconciled against the real, already-built
  `contracts/src/health/SmartBAAFactory.sol` (an earlier one-argument
  `isBAAActive(address agent)` assumption here was wrong; see `app/baa.py`'s
  module docstring for the full story of that bug and why nothing caught it
  sooner). Proven two ways: against a minimal `MockBAARegistry.sol` fixture
  this package compiles (`forge build`) and deploys for itself in
  `tests/conftest.py` for fast/cheap eth_call-plumbing coverage (see
  `tests/test_chain_baa_anchor.py`), AND against the real
  `CoveredEntityRegistry` + `SmartBAAFactory` + `SmartBAA` + `IntegrityToken`
  contracts compiled by the sibling `contracts/` package's own `forge build`
  (see `tests/test_baa_health_integration.py`).
- **Merkle anchoring**: a real `eth_sendTransaction` via `web3.py`
  (`app/anchor.py`) calling `anchorRoot(bytes32)`, signed and submitted
  against the same local anvil + a `MockStateAnchor.sol` fixture, with the
  transaction receipt checked and the contract's resulting on-chain state
  read back and asserted against the exact expected Merkle root.
- **Merkle tree construction**: real `keccak256`, real sorted-pair parent
  hashing per §4.4 (`app/merkle.py`), unit tested independently of any
  chain interaction.
- **Circuit breaker**: real lockout-on-repeated-violation logic
  (`app/circuit_breaker.py`), rebuilt cleanly from the old prototype's shape.

None of the above falls back to a hardcoded/mocked "assume success" path —
that was the explicit bug in the old prototype (`check_baa_status`'s
"STAGING MODE" allowlist, `MerkleSequencer.anchor_batch`'s print-only stub,
and `evaluate_intent_policy`'s regex fallback when OPA was unreachable) that
this rewrite was told not to repeat.

## Integration reconciliation (read before wiring up `contracts/` or `integrity-sdk`)

`docs/INTERFACE_CONTRACT.md` pins down the commitment schema, the OPA
endpoint, and the Merkle hash/pairing rule, but leaves several concrete
details unspecified since the relevant sibling packages are built in
parallel. This package picked defensible defaults and flagged them
everywhere in code comments; summarized here:

1. **Canonical JSON for the signature. ✅ RECONCILED.** The signature covers
   the signed fields as `json.dumps(fields, sort_keys=True,
   separators=(",", ":"), ensure_ascii=True)` — `ensure_ascii=True` to match
   `integrity-sdk`/`integrity-cli` byte-for-byte (the SDK pins this as the
   cross-language protocol rule). See `app/canonical.py`. Verified by a real
   SDK→middleware and CLI→middleware round-trip.

2. **DID → Ed25519 public key. ✅ RECONCILED.** `integrity-sdk`'s DID
   fingerprint is `sha256(pubkey)`, **not** the raw key — so the key can't be
   recovered from `agent_id` alone. The commitment therefore carries a signed
   `agent_public_key` (multibase, same form as the DID document's
   `publicKeyMultibase`). `app/canonical.py::public_key_from_commitment`
   decodes it and **binds** it by checking `sha256(pubkey) == fingerprint`
   (blocking key substitution) before verifying the signature. This makes each
   commitment self-verifying with no external DID-resolution round-trip. See
   [`docs/wiki/concepts/bcc.md`](../docs/wiki/concepts/bcc.md).

3. **DID → Ethereum address** (for the *agent/businessAssociate* side of the
   BAA on-chain check only). **Resolved.** `isBAAActive(coveredEntity,
   businessAssociate)` needs an address for `businessAssociate`; that address
   is the agent's **`SovereignAgent` contract address**, resolved via the
   oracle's `GET /v1/agent/{id}` in `app/chain.py::resolve_agent_primitives`
   and `agent_id_to_address` — not the EOA/wallet, and not a derivation from
   the DID pubkey. This is deliberate and load-bearing: `SmartBAAFactory`
   and downstream Integrity Health contracts (`EHRGate.checkAccess`, `ComplianceGate`)
   all treat the `SovereignAgent` contract as the acting agent (it's their
   `msg.sender`), so a BAA is "active for" the `SovereignAgent` address. This
   replaced an earlier `keccak256(pubkey_bytes)[-20:]` placeholder that
   produced an address matching nothing on-chain — that placeholder is gone
   from the code; note it here only as history so it isn't mistaken for the
   current behavior. One open dependency worth flagging: this resolution
   path requires the oracle to have already indexed the agent, so it fails
   closed (`AgentResolutionError`) if the oracle is down or hasn't caught up
   yet — a fallback that resolves `XibalbaAgentRegistry` directly on-chain
   when the oracle call fails is a reasonable follow-up, not yet built.
   `coveredEntity`, by contrast, does NOT go through this function at all —
   covered entities have no DID in this protocol; see point 4 below.

4. **On-chain function signatures this package expects `contracts/` to
   implement — RECONCILED against the real, already-built contracts:**
   ```solidity
   // contracts/src/health/SmartBAAFactory.sol (confirmed real signature)
   function isBAAActive(address coveredEntity, address businessAssociate) external view returns (bool);
   // contracts/... StateAnchor (still an assumed/unconfirmed signature)
   function anchorRoot(bytes32 root) external;
   ```
   `isBAAActive` originally shipped here as a wrong, one-argument
   `isBAAActive(address agent)` — invented before `contracts/` existed to
   check against, and never caught because there was no real contract to
   revert against a mismatched ABI. It's now fixed to the real two-argument
   signature (`app/baa.py`) and covered entity address comes from a new
   `covered_entity_address` field on `BCCCommitment` (`app/schemas.py`,
   signed over in `app/canonical.py` so it can't be swapped post-signature)
   — see `app/baa.py`'s module docstring for the full account of the bug.
   Contract addresses are read from `deployments.local.json` (§6) under keys
   `SmartBAA` and `StateAnchor` (configurable via `BAA_CONTRACT_NAME` /
   `STATE_ANCHOR_CONTRACT_NAME`); `BAA_CONTRACT_NAME` must point at the
   deployed `SmartBAAFactory` address specifically — the per-pair `SmartBAA`
   escrow instances it creates don't implement `isBAAActive` themselves.
   **Note `SmartBAA`/`SmartBAAFactory` is still not listed in §6's example
   `contracts` map** — this package needs that key added once `contracts/`
   publishes its `deployments.local.json` entry, or `BAA_CONTRACT_NAME` needs
   to be pointed at whatever key `contracts/` actually uses.

5. **Merkle leaf encoding.** §4.4 pins the hash function (keccak256) and the
   sorted-pair parent-hashing rule, but not the leaf *payload*. This
   package hashes
   `keccak256(abi.encodePacked(agent_id, intent_type, intended_state_hash, nonce, timestamp))`
   (see `app/merkle.py::leaf_hash`). Whoever consumes these leaves for
   proof verification (`integrity-oracle`, `contracts`) needs to reconstruct
   leaves identically — confirm before relying on proofs generated against
   these leaves in production.

6. **Merkle odd-node-count convention.** When a tree level has an odd
   number of nodes, this package **duplicates** the unpaired node (hashes
   it with itself) rather than promoting it unchanged — see
   `app/merkle.py` module docstring. This is the OpenZeppelin-standard
   convention and matches `integrity-oracle`'s `merkle.rs` and
   `contracts`' `StateAnchor.sol` bit-for-bit.

7. **`requires_baa` / clinical intent-type convention.** The §4.2 schema has
   no "vertical" or "domain" field to signal "this is a healthcare action,"
   so this package's `policies/bcc.rego` treats a fixed set of `intent_type`
   values (`EMR_WRITE`, `DISPENSE_MEDICATION`, `BILLING_SUBMISSION`,
   `SECURE_EMR_WRITE`, `CLINICAL_DATA_ACCESS`) as the healthcare vertical
   that requires an active on-chain BAA. `integrity-sdk`/`integrity-cli`
   need to emit these exact `intent_type` strings for clinical actions for
   the BAA gate to trigger at all. Relatedly, §4.2 also had no field for
   *which* covered entity (hospital) a healthcare-vertical commitment is
   against — needed once the real `isBAAActive(coveredEntity,
   businessAssociate)` two-arg signature was confirmed (see point 4 above).
   This package adds an extension field, `covered_entity_address`, to
   `BCCCommitment` (optional; unused by non-healthcare `intent_type`s) —
   `integrity-sdk`/`integrity-cli` need to populate and sign over it (it's
   part of the canonical signed payload, `app/canonical.py`) for any
   clinical-vertical commitment, or the BAA gate fails closed with
   `BAA_CANNOT_VERIFY` even for an agent with a genuinely active BAA.

8. **No raw-payload PHI content scanning.** The old prototype regex-scanned
   an `actual_context` blob for SSNs/DOBs/etc. The new §4.2 commitment
   schema intentionally carries only a hash pre-execution — by design, real
   PHI never crosses the wire to this service before execution. This
   package's Rego policy therefore only does structural checks (allowlist
   by `intent_type` + `agent_id`) plus defense-in-depth regex over the
   `intent_type` label itself (see `policies/bcc.rego` header comment). If a
   real content-DLP gate is wanted, it needs a different endpoint/schema
   that actually carries payload content — out of scope for this pre-
   execution, hash-only gate.

9. **READ_ONLY → destructive intent drift.** The old prototype detected an
   agent trying to "delete" something under a `READ_ONLY` commitment by
   scanning the live execution context. There is no equivalent signal in
   the pre-execution-only §4.2 schema (no runtime action stream to compare
   against). Not implemented here — flagged as a gap needing either a
   post-execution confirmation call or a runtime action log, neither of
   which exist in the current interface contract.

10. **Nonce/circuit-breaker state is in-memory, single-process.** Fine for
    the current single-replica dev/demo topology. A multi-replica
    production deployment should move both to Redis (already present in
    the broader docker-compose topology for `integrity-oracle`) so state is
    shared across replicas.

11. **Clinical allowlist. ✅ NOW DATA-DRIVEN.** `policies/bcc.rego`'s
    `authorized_clinical_agents` is the UNION of a small static demo set and a
    runtime `data.clinical_allowlist.agents` document. A real-DID agent is
    authorized by loading that data document alongside the policy
    (`opa run --server policies/ <data.json>`) — no hand-editing the policy
    file. This is the production path its own PRODUCTION NOTE called for (keep
    the data document in sync with the on-chain `DomainRegistry`/
    `ReputationRegistry` via `integrity-oracle`). 12/12 policy tests still pass.
