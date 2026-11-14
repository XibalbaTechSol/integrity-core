# Agent Registration v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every agent registers off-chain for free with a proven Ed25519 key (tier 1) and gets a non-zero AIS from signed telemetry. A later phase adds a single on-chain `AgentRegistry` for agents that use the protocol's contracts, replacing the primitives architecture entirely.

**Architecture:** Phase 1 (this plan, in detail) adds `POST /v1/agent/register/offchain` to the Oracle and scores unobserved compliance with weight 0 instead of a fabricated violation. It also adds an SDK client and CLI command, and makes Shield and Cortex register on first run. Phases 2–5 (outlined at the end) build `AgentRegistry`, delete the primitives contracts and every consumer of them, add the Oracle's attestation/sync routes, and propose the spec amendment.

**Tech Stack:** Rust (axum, sqlx/Postgres, ed25519-dalek, serde_jcs) for the Oracle; Python (integrity_sdk, typer CLI, requests) for SDK/CLI/Shield/Cortex; Solidity/Foundry in Phases 2–3.

**Spec:** `docs/superpowers/specs/2026-11-14-agent-registration-v3-design.md` (approved 2026-11-14). Executors read it alongside this plan; Part 2 is the contract for Phase 1.

## Global Constraints

- Workspace: worktree `/mnt/storage/xibalba/Projects/worktrees/integrity-core/offchain-agent-registration`, branch `feat/offchain-agent-registration`. Never edit `~/Projects/<repo>` bases. Shield and Cortex tasks each get their own worktree via `xb-wt start <repo> feat/offchain-first-run`.
- Push with `xb-wt push`. No `git stash`. Force push is denied: merge `origin/main` and fast-forward instead.
- Merge only when every `gh pr checks --json bucket` entry is `pass`, with `gh pr merge --squash --match-head-commit <sha>`.
- Signed message: RFC 8785 canonical JSON of `{"did", "domain": "integrity.agent.register.offchain.v1", "ed25519_pubkey_hex" (64 lowercase hex, no 0x), "timestamp" (unix seconds)}`.
- Freshness window: ±300 s, inclusive.
- DID: `did:integrity:` followed by `sha256(raw 32-byte pubkey)` as 64 lowercase hex.
- Tier: a proven key is **tier 1**, and a registration never lowers an existing tier.
- Rate limit: one **global** per-minute counter for the off-chain route, not per DID.
- Off-chain registration never touches chain state and never needs `FUNDER_PRIVATE_KEY`.
- Never print, log or commit private keys, `whsec`, Render or Stripe secrets.
- Run `ps aux | grep -i -E "hermes|codex|claude|shield"` before any identity-key operation.
- Don't run the integrity-sdk and integrity-cli test suites concurrently (they hang). Run `forge build --force` after contract config changes.

## Review Focus

1. **The same DID registered twice at the same moment** (a retry storm on first run). Both must end with one row: one call gets `created` and the other `already_registered`, with no 500. Covered by the DB test in Task 4 (`concurrent_registration_of_one_did_creates_one_row`).
2. **A legacy row with no key** (Hermes `68fed13…`, tier 0) registers off-chain. The key must be attached, the tier raised to 1, and any existing handle kept. Covered in Task 4 (`legacy_keyless_row_gets_key_and_tier_one`).
3. **A client sends the pubkey as `0x`-prefixed or uppercase hex.** It must sign over the normalized form and be accepted, so Python and Rust must agree byte-for-byte. Covered by the shared golden vector in Tasks 3 and 5.
4. **An Oracle on Render free that is cold or unreachable during Shield/Cortex first run.** Startup must go ahead, record the failure, and retry on the next start, never crash. Covered in Tasks 9 and 10 (`first_run_survives_unreachable_oracle`).
5. **An agent already registered with a different handle** sends a new `handle`. It must get 409 with the handle unchanged, and the key and tier must not be modified in that call (the whole transaction rolls back). Covered in Task 4 (`handle_mismatch_rolls_back_key_attach`).

---

## Phase 1 — Off-chain registration + unobserved compliance

### Task 1: Land the unobserved-compliance change (already written, uncommitted)

These files are written but uncommitted: `migrations/0025_compliance_observed.sql`, `scoring-core/src/lib.rs` (`AisWeights::without_compliance` + 3 tests), `src/db.rs` (aggregate SQL + `compliance_observed` param), `src/handlers.rs` (`oracle_compliance -> Option<f64>`, `ais_weights_for_window`, `AisResponse.compliance_observed` / `weights`), `src/error.rs` (`IdentityConflict` → 409), and `tests/e2e.rs`. `src/db.rs` also contains the unbuilt registration code that Task 2 reworks.

**Files:**
- Modify: `integrity-oracle/backend/src/db.rs` (temporarily remove the registration block, lines ~187–391, so this commit builds without it; Task 2 brings it back)
- Test: `integrity-oracle/backend/src/handlers.rs` `#[cfg(test)]` and `scoring-core/src/lib.rs` tests

**Interfaces:**
- Produces: `fn ais_weights_for_window(configured: AisWeights, event_count: i64, compliance_observed_count: i64) -> (AisWeights, bool)`, plus `AisWeights::without_compliance() -> Result<AisWeights, String>`.

- [ ] **Step 1: Add handler unit tests for `ais_weights_for_window`**

```rust
#[test]
fn window_with_no_observed_compliance_uses_renormalized_weights() {
    let (w, observed) = ais_weights_for_window(AisWeights::default(), 10, 0);
    assert!(!observed);
    assert_eq!(w, AisWeights::default().without_compliance().unwrap());
}
#[test]
fn window_with_any_observed_compliance_keeps_configured_weights() {
    let (w, observed) = ais_weights_for_window(AisWeights::default(), 10, 1);
    assert!(observed);
    assert_eq!(w, AisWeights::default());
}
#[test]
fn empty_window_keeps_configured_weights() {
    let (w, _) = ais_weights_for_window(AisWeights::default(), 0, 0);
    assert_eq!(w, AisWeights::default());
}
```

- [ ] **Step 2: Move the registration block out of `db.rs` into a scratch file** (`$SCRATCH/db_registration_block.rs`). Task 2 reworks it from there. `cargo build -p backend` must be clean.
- [ ] **Step 3: Run** `cargo test -p scoring-core && cargo test -p backend --lib`. Expected: all pass, including the 3 new tests and 36 scoring-core tests.
- [ ] **Step 4: Commit** the migration, scoring-core, db.rs, handlers.rs, error.rs and e2e.rs with message `feat(oracle): score unobserved compliance with weight 0 instead of a fabricated violation`, then `xb-wt push`.

### Task 2: Rework `db::register_agent_offchain` for v3

**Files:**
- Modify: `integrity-oracle/backend/src/db.rs` (bring the block back from scratch, reworked)
- Modify: `integrity-oracle/backend/src/offchain_registration.rs` (`OFFCHAIN_TIER`)

**Interfaces:**
- Produces:
  - `pub const OFFCHAIN_TIER: i32 = 1;` in `offchain_registration.rs` (doc comment: a proven key is tier 1 everywhere, spec Part 4 "Tier and evidence").
  - `pub enum RegistrationOutcome { Created, AlreadyRegistered, KeyAttached }`, serialized snake_case.
  - `pub enum RegistrationConflict { KeyMismatch, HandleMismatch, HandleTaken, Db(sqlx::Error) }`.
  - `pub async fn register_agent_offchain(pool: &PgPool, id: &str, ed25519_pubkey: &[u8], did_document: Option<&serde_json::Value>, handle: Option<&str>) -> Result<(AgentRow, RegistrationOutcome), RegistrationConflict>`. The tier is `OFFCHAIN_TIER` internally, not a parameter.
- Deleted and never reintroduced: `register_agent_onchain`, `has_agent_primitives`, `UpgradedToOnchain`, `AlreadyOnchain`.

- [ ] **Step 1: Restore** `ensure_handle`, `insert_or_lock_agent` and `register_agent_offchain` with these changes:
  - Drop the tier parameter.
  - Insert at `OFFCHAIN_TIER`.
  - In both the `AlreadyRegistered` and `KeyAttached` branches, run `UPDATE agents SET verification_tier = GREATEST(verification_tier, $tier) …` so a keyless tier-0 row rises to 1 and a higher tier is never lowered.
  - Call `ensure_handle` before `tx.commit()`, so a handle conflict rolls back the key attach.
- [ ] **Step 2: Run** `cargo build -p backend && cargo clippy -p backend -- -D warnings`. Expected: clean, with no dead-code warnings (Task 3 is the caller, so add `#[allow(dead_code)]` only if clippy needs it before then, and remove it in Task 3).
- [ ] **Step 3: Commit** with message `feat(oracle): off-chain agent row semantics (tier 1, idempotent, key never overwritten)`.

### Task 3: `POST /v1/agent/register/offchain` route

**Files:**
- Modify: `integrity-oracle/backend/src/handlers.rs` (new handler + request/response types)
- Modify: `integrity-oracle/backend/src/routes.rs` (add the route next to line 17)
- Modify: `integrity-oracle/backend/src/config.rs` (`registration_rate_limit_per_minute: u32`, env `REGISTRATION_RATE_LIMIT_PER_MINUTE`, default `"30"`; also in the test config at ~line 181)
- Modify: `integrity-oracle/backend/src/openapi.rs` (register path + schemas)
- Modify: `integrity-oracle/backend/src/offchain_registration.rs` (golden-vector test)
- Test: `integrity-oracle/backend/src/handlers.rs` `#[cfg(test)]`

**Interfaces:**
- Consumes: `offchain_registration::verify_proof(did, pubkey_hex, timestamp, signature_hex, now) -> Result<Vec<u8>, ProofError>`, `db::register_agent_offchain` (Task 2), `validate_xns_handle(&str) -> Result<(), AppError>` (existing), and `state.rate_limiter.hit(key, window) -> i64`.
- Produces:
  - `#[derive(Deserialize, ToSchema)] pub struct OffchainRegisterRequest { pub did: String, pub ed25519_pubkey_hex: String, pub timestamp: i64, pub signature: String, pub did_document: Option<serde_json::Value>, pub handle: Option<String> }`
  - `#[derive(Serialize, ToSchema)] pub struct OffchainRegisterResponse { pub agent_id: String, pub verification_tier: i32, pub outcome: db::RegistrationOutcome, pub handle: Option<String> }`
  - `pub async fn register_agent_offchain(State, Json<OffchainRegisterRequest>) -> Result<(StatusCode, Json<OffchainRegisterResponse>), AppError>`
- Status mapping:

  | Result | Status |
  |---|---|
  | `Created` | 201 |
  | `AlreadyRegistered`, `KeyAttached` | 200 |
  | `MalformedDid`, `MalformedPubkey`, `MalformedSignature` | 400 `BadRequest(err.to_string())` |
  | `DidKeyMismatch`, `BadSignature`, `Stale` | 401 `Unauthorized` (the message names which, through a new `AppError::ProofRejected(String)` → 401 so clients can fix clock skew) |
  | `KeyMismatch` | 409 `IdentityConflict` |
  | `HandleMismatch` | 409 `IdentityConflict` |
  | `HandleTaken` | 409 `HandleTaken` |
  | Global counter `ratelimit:register:offchain` above `registration_rate_limit_per_minute` | 429 `RateLimited` |

  The rate check runs **before** signature verification, so a flood is cheap to reject.

- [ ] **Step 1: Write the failing golden-vector test** in `offchain_registration.rs`:

```rust
#[test]
fn signing_message_golden_vector() {
    let (_, did, pk) = agent(7);
    let msg = String::from_utf8(signing_message(&did, &format!("0x{}", pk.to_uppercase()), NOW)).unwrap();
    assert_eq!(msg, format!(
        r#"{{"did":"{did}","domain":"integrity.agent.register.offchain.v1","ed25519_pubkey_hex":"{pk}","timestamp":1800000000}}"#
    ));
    // Pin the concrete key so the Python test can assert the same bytes.
    assert_eq!(pk, GOLDEN_PUBKEY_SEED7_HEX);
}
```

  Set `GOLDEN_PUBKEY_SEED7_HEX` to the hex the test prints on its first run (the Ed25519 public key of seed `[7u8; 32]`), and record it in the test's doc comment for Task 5.
- [ ] **Step 2: Write failing handler tests.** Use the in-process router with a lazy pool; follow the existing handler-test pattern in `handlers.rs`, or put the DB-touching ones in Task 4:
  - `offchain_register_rejects_stale_timestamp_with_401`
  - `offchain_register_rejects_malformed_did_with_400`
  - `offchain_register_rate_limit_returns_429_before_verifying` (set the limit to 1 and send 2 requests with garbage signatures. Expect a 400/401 first, then a 429.)
  - `offchain_register_rejects_invalid_handle_with_400`
- [ ] **Step 3: Run** `cargo test -p backend --lib offchain`. Expected: FAIL (route and handler missing).
- [ ] **Step 4: Implement** the handler, route, config field, `AppError::ProofRejected`, and openapi entries per the Interfaces block. Order inside the handler: rate limit, then `validate_xns_handle` if a handle is given, then `verify_proof(now = Utc::now().timestamp())`, then DB.
- [ ] **Step 5: Run** `cargo test -p backend --lib && cargo clippy -p backend -- -D warnings`. Expected: PASS and clean.
- [ ] **Step 6: Commit** with message `feat(oracle): POST /v1/agent/register/offchain (proof of possession, global rate limit)`.

### Task 4: Opt-in real-Postgres tests for registration

**Files:**
- Create: `integrity-oracle/backend/tests/offchain_registration_db.rs`

**Interfaces:**
- Consumes: `db::create_pool`, `db::run_migrations`, `db::register_agent_offchain`, `db::get_agent` (existing reader). Gated exactly like `tests/invocation_id_db.rs`: skip unless `OFFCHAIN_REGISTRATION_DB_TEST=1`, read `TEST_DATABASE_URL`, and use a fresh random DID per test.

- [ ] **Step 1: Write the tests.**
  - `fresh_did_is_created_at_tier_one`: outcome `Created`, `verification_tier == 1`, key stored.
  - `same_key_is_idempotent`: the second call is `AlreadyRegistered`, with one row.
  - `different_key_is_rejected_and_not_overwritten`: `Err(KeyMismatch)`, and the stored key is unchanged.
  - `legacy_keyless_row_gets_key_and_tier_one`: insert with `db::register_agent(…, None, Some(eth), 0, None)`, then register off-chain. Expect `KeyAttached`, tier 1, and the eth address kept.
  - `higher_tier_is_never_lowered`: set tier 2 via SQL, register again, and expect tier 2.
  - `handle_mismatch_rolls_back_key_attach`: a keyless row holding handle `a`; registering with handle `b` returns `Err(HandleMismatch)`, and the row still has no key and tier 0.
  - `concurrent_registration_of_one_did_creates_one_row`: `join_all` of 8 identical calls. Exactly one `Created`, 7 `AlreadyRegistered`, no errors.
- [ ] **Step 2: Run** against a local Postgres (`docker run --rm -d -p 55432:5432 -e POSTGRES_PASSWORD=pw timescale/timescaledb:latest-pg16`, then `OFFCHAIN_REGISTRATION_DB_TEST=1 TEST_DATABASE_URL=postgres://postgres:pw@127.0.0.1:55432/postgres cargo test -p backend --test offchain_registration_db`). Expected: 7 pass. Fix Task 2 code if any fail.
- [ ] **Step 3: Run** without the env var: `cargo test -p backend --test offchain_registration_db`. Expected: all print SKIP and pass.
- [ ] **Step 4: Commit** with message `test(oracle): real-Postgres proofs for off-chain registration semantics`.

### Task 5: SDK client `integrity_sdk.registration_offchain`

**Files:**
- Create: `integrity-sdk/integrity_sdk/registration_offchain.py`
- Test: `integrity-sdk/tests/unit/test_registration_offchain.py`

**Interfaces:**
- Consumes: `integrity_sdk.core.jcs.canonical_bytes`, `integrity_sdk.did.Keypair` (`.sign(bytes) -> bytes`, `.public_bytes() -> bytes`), `integrity_sdk.did.fingerprint_for_pubkey`.
- Produces:
  - `DOMAIN = "integrity.agent.register.offchain.v1"`
  - `def signing_message(did: str, pubkey_hex: str, timestamp: int) -> bytes` (normalizes the pubkey: strips `0x`, lowercases)
  - `@dataclass(frozen=True) class OffchainRegistration: agent_id: str; verification_tier: int; outcome: str; handle: str | None`
  - `class OffchainRegistrationError(RuntimeError)` with attributes `status: int | None` (None = unreachable) and `detail: str`
  - `def register_offchain(oracle_url: str, did: str, keypair: Keypair, *, handle: str | None = None, did_document: dict | None = None, timeout: float = 30.0, now: int | None = None) -> OffchainRegistration`. It raises `ValueError` before any network call if `did != "did:integrity:" + fingerprint_for_pubkey(keypair.public_bytes())`. The 30 s timeout covers a Render free cold start.

- [ ] **Step 1: Write failing tests.**
  - `test_signing_message_matches_oracle_golden_vector`: seed `bytes([7]*32)`, `NOW=1_800_000_000`, and the pubkey hex `GOLDEN_PUBKEY_SEED7_HEX` copied from Task 3. Assert the exact string from Task 3, Step 1.
  - `test_register_offchain_posts_signed_body`: mock `requests.post` and assert the URL is `…/v1/agent/register/offchain`. Assert the body has these keys: `did`, `ed25519_pubkey_hex`, `timestamp`, `signature`, plus `handle` only when given. Assert the signature verifies with `did.verify_signature`.
  - `test_register_offchain_maps_201_and_200`: both return `OffchainRegistration`.
  - `test_register_offchain_raises_with_status_on_409`: the error carries `status == 409`.
  - `test_register_offchain_unreachable_raises_status_none`: `requests.ConnectionError` gives `status is None`.
  - `test_register_offchain_rejects_did_not_matching_key`: raises `ValueError`, and no post is made.
- [ ] **Step 2: Run** `cd integrity-sdk && uv run pytest tests/unit/test_registration_offchain.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the module per the Interfaces block.
- [ ] **Step 4: Run** the same command. Expected: 6 pass.
- [ ] **Step 5: Commit** with message `feat(sdk): off-chain registration client (shared golden vector with the Oracle)`.

### Task 6: CLI `integrity agent register` becomes off-chain

**Files:**
- Modify: `integrity-cli/integrity_cli/main.py:630` (`agent_register`)
- Modify: `integrity-cli/tests/test_main.py` (replace the three primitives-flow register tests at ~110/151/164)
- Delete: `integrity-cli/tests/test_register_oracle_e2e.py` (primitives flow; the spec removes it)

**Interfaces:**
- Consumes: `register_offchain` (Task 5), and the CLI's existing identity loader for `--identity` (the one `integrity identity keygen` writes).
- Produces: `integrity agent register [--identity NAME] [--handle H] [--oracle-url URL]`.
  - On success it prints `registered <did> tier=<n> (<outcome>)` and exits 0.
  - On an Oracle error it prints the status and detail and exits 1.
  - The `--alias/--desc/--domain/--vertical/--rpc-url/--deployments-file/--skip-oracle/--auto-register-domain` options are removed. `--onchain` arrives in Phase 4.

- [ ] **Step 1: Write failing tests** with `register_offchain` monkeypatched:
  - `test_agent_register_is_offchain_and_needs_no_funder`: no `FUNDER_PRIVATE_KEY` in the env. Exits 0, and the output contains `tier=1`.
  - `test_agent_register_passes_handle`
  - `test_agent_register_reports_conflict_exit_1`
- [ ] **Step 2: Run** `cd integrity-cli && uv run pytest tests/test_main.py -q -k agent_register`. Expected: FAIL.
- [ ] **Step 3: Implement.** Delete the primitives code path from `agent_register` and any helpers only it used. Leave `domain register` and `xns register` alone (Phase 3 handles them).
- [ ] **Step 4: Run** `uv run pytest -q` for integrity-cli alone (not concurrently with the SDK suite). Expected: PASS.
- [ ] **Step 5: Commit** with message `feat(cli): agent register is off-chain by default; primitives flow removed`.

### Task 7: PR, merge, deploy the Oracle

- [ ] **Step 1:** `git fetch origin && git merge origin/main`. Resolve any conflicts, rerun `cargo test -p backend --lib`, then `xb-wt push`.
- [ ] **Step 2:** `gh pr create --base main --head feat/offchain-agent-registration`. Title: `feat: off-chain agent registration + unobserved compliance (v3 phase 1)`. The body links the spec and lists Tasks 1–6.
- [ ] **Step 3:** Wait for CI. Run `gh pr checks <n> --json name,bucket`. Every bucket must be `pass`. Then `gh pr merge <n> --squash --match-head-commit <sha>`. After that, confirm `main` CI is green.
- [ ] **Step 4:** Check the Render Oracle service's autoDeploy with `get_service`. If it is off, trigger a deploy of the merge commit with `trigger_deploy`, and wait for `live` with `get_deploy`.
- [ ] **Step 5: Verify live.** `curl -s -o /dev/null -w '%{http_code}' -X POST $ORACLE/v1/agent/register/offchain -d '{}' -H 'content-type: application/json'` returns `400` or `422`, not `404`. Render logs show migration `0025` applied.

### Task 8: Register Claude, Codex and Hermes; fix the hook status check

**Files (not in git; back up to `~/.local/share/xibalba-hooks/backup-2026-11-14/` first):**
- Modify: `~/.claude/xibalba/_common.py` `oracle_agent_status` (~line 130)
- Modify: `~/.claude/xibalba/identity.py` (~line 340) so its register path calls `register_offchain` and no longer needs `FUNDER_PRIVATE_KEY` or the wallet

**Interfaces:**
- `oracle_agent_status(did) -> "ok" | "unregistered" | "keyless" | "unreachable"`. It returns `"ok"` only when GET `/v1/agent/{did}` is 200 **and** `oracle_registered` **and** `has_ed25519_key`. A 200 without a key is `"keyless"`, since telemetry signatures can't verify.

- [ ] **Step 1:** Run `ps aux | grep -i -E "hermes|codex|claude"` and note any running process that holds each identity. Registration only reads the keys; never move or regenerate them.
- [ ] **Step 2:** Update `oracle_agent_status` and `identity.py` as above. Run the hook tests in `~/.claude/xibalba` (they currently pass, and the 2 unchecked-warning tests must still pass).
- [ ] **Step 3: Register Claude** with the SDK from the hooks venv. Load the key with `INTEGRITY_PROFILE_ROOT=/home/xibalba/.claude`, then call `register_offchain(ORACLE, did, keypair)`. Expected: `did:integrity:f07438ae…`, outcome `created`, tier 1.
- [ ] **Step 4: Register Codex.** Find its key store through its harness profile root. Read only; if the store is empty, stop and report instead of minting a key.
- [ ] **Step 5: Claim Hermes** `68fed13…` with `INTEGRITY_PROFILE_ROOT=/home/xibalba/.hermes`. Expected outcome `key_attached`, tier 1.
- [ ] **Step 6: Proof.** Start a Claude session (or run the post-tool hook once), so signed telemetry is sent. Then:
  - Ingest returns 2xx in `~/.claude/xibalba/session.log`, and there is no new "not confirmed registered" line.
  - `GET /v1/agent/did:integrity:f07438ae…/ais` shows `ais > 0`, `zone != "red"` and `compliance_observed: false`.
- [ ] **Step 7:** Update memory `project_dev_shell_gate_runtime_2026-11-14.md`: registration is no longer on hold, and record the three outcomes.

### Task 9: Cortex registers on first `connect` (xibalba-cortex, own PR)

**Files** (worktree from `xb-wt start xibalba-cortex feat/offchain-first-run`):
- Modify: `src/xibalba_cortex/connect.py:60` (`connect`)
- Test: `tests/test_connect.py` (create it if absent; follow the existing test layout)

**Interfaces:**
- `connect(..., oracle_url: str | None = None)`. The default is `os.environ.get("ORACLE_URL")`. After `write_did_file`, when an `oracle_url` is set, call `register_offchain(oracle_url, did, keypair)`.
- The result gains `"oracle_registration"`: `{"status": "registered", "tier": n, "outcome": o}` | `{"status": "failed", "http_status": s|None, "detail": d}` | `{"status": "skipped"}`. `connect` never raises because of the Oracle.

- [ ] **Step 1: Write failing tests:**
  - `first_run_registers_offchain`
  - `first_run_survives_unreachable_oracle` (the status is `failed`, `http_status` is None, and the DID file is still written)
  - `no_oracle_url_skips`
- [ ] **Step 2: Run, fail, implement, run, pass.** Use `uv run pytest tests/test_connect.py -q`. This needs the integrity-sdk version from Task 7's merge, so bump the dependency per the repo's existing pin style. Cortex e2e needs a sibling integrity-core checkout.
- [ ] **Step 3:** Commit, push, open the PR, and merge on green per the Global Constraints.

### Task 10: Shield exporter registers on first `shield run` (xibalba-shield, own PR)

**Files** (worktree from `xb-wt start xibalba-shield feat/offchain-first-run`):
- Modify: `shield/integrity_exporter/__init__.py` (or the module defining `IntegrityExporter`): a `register_offchain_once()` method called at exporter start from `shield/cli.py:553`
- Modify: `scripts/register_with_oracle.py`: replace the primitives flow with a call to `register_offchain`, and drop the `FUNDER_PRIVATE_KEY` / `INTEGRITY_WALLET_PASSWORD` requirements and the orphan-contracts warning
- Test: `tests/test_integrity_exporter_registration.py`

**Interfaces:**
- `IntegrityExporter.register_offchain_once() -> dict`, with the same result shape as Task 9's `oracle_registration`.
  - It runs when `ORACLE_URL` is set and the exporter's DID has no success stamp at `<did_home>/<agent>/oracle_registered.json`. On success it writes that stamp: `{did, oracle_url, tier, at}`.
  - A failure is logged at WARNING and retried on the next start. It never blocks the sensor.

- [ ] **Step 1: Write failing tests:**
  - `first_run_registers_and_stamps`
  - `second_run_with_stamp_does_not_call_oracle`
  - `first_run_survives_unreachable_oracle`
  - `stamp_for_a_different_oracle_url_reregisters`
- [ ] **Step 2: Run, fail, implement, run, pass** (`uv run pytest tests/test_integrity_exporter_registration.py -q`). Run `scripts/wiki_toc.py --check` if any wiki page changes.
- [ ] **Step 3:** Commit, push, open the PR, and merge on green. Do **not** deploy Shield to Render as part of this task; deploy only when the owner asks.

---

## Phases 2–5 (outline; each gets its own detailed plan when Phase 1 is merged)

**Phase 2 — `AgentRegistry` contract** (`contracts/src/identity/AgentRegistry.sol` + Foundry tests and invariants). It implements spec Part 3:
- `register(pubkey, guardian, actor, domainId, uri, proofKind, proof, consent)` with proof kinds 1 (EIP-712 `RegisterAgent` attestation from an `ATTESTER_ROLE` signer) and 2 (Ed25519 verifier slot, disabled while unset).
- Fingerprint key via the SHA-256 precompile; first write wins.
- `isGatedAccount` codehash pin; actor consent via `msg.sender` or EIP-1271 `BindActor`.
- An actor requires a domain with a configured `PolicyRegistry` policy.
- Two-step `proposeGuardian` / `acceptGuardian`; `setActor` / `clearActor` / `setUri` / `setDomain`; irreversible `retire`.
- Reads: `resolve`, `resolveAgent`, `isRegisteredAgent`.

The acceptance tests are spec Phase 2's list, verbatim.

**Phase 3 — Consumer migration, deletions, policy-pack compiler, fresh deploy.**
- Repoint every consumer in spec Part 5.
- Delete `AgentPrimitivesFactory`, the clones, `XibalbaAgentRegistry`, `SovereignAgent.updateAIS`, and the SDK `registration.py` primitives path with its tests and docs.
- `SovereignAgent` takes the registry address directly.
- Add the `integrity_sdk` pack on-chain-section compiler: §4.4c leaves and root against the golden vector, plus per-call proofs.
- Rewrite `Deploy.s.sol` and `test_trust_wiring.py`, then do a fresh Base Sepolia deploy.
- Acceptance: the repo-wide grep is empty, and a confined call inside the map succeeds while one outside reverts.

**Phase 4 — Oracle on-chain path.**
- Delete `POST /v1/agent/register`, its request types, the primitives verification, the `agent_primitives` table and its readers (`oracle_compliance`'s gate read, settlement, AIS cross-checks), and `chain.rs` `resolve_primitives_by_did` / `memory_state`.
- Add `POST /v1/agent/{id}/onchain/attestation`, which signs `RegisterAgent` only for a row already registered off-chain with the same key.
- Add `POST /v1/agent/{id}/onchain/sync`, which writes a new `agent_onchain_records` table.
- `settlement_eligible` = an active record with an actor.
- Add SDK/CLI `register --onchain [--confined --domain ID]`.

**Phase 5 — Spec amendment + wiki.** A proposed (non-authoritative) amendment to v0.3 §4.1 / §6 / §7.1 and INTERFACE_CONTRACT §6.1–§6.3a, plus wiki pages, citing the Phase 1–4 code as implementation evidence.

**Follow-on (not in this design):** a gate-receipt evidence PR that turns confined agents' on-chain allow/deny outcomes and Shield gate receipts into observed compliance.
