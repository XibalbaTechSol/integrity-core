# Agent Registration v3 — Phase 4: Oracle on-chain path, `handle --onchain`, trust row, legacy route retired

**Parent plan:** `docs/superpowers/plans/2026-11-14-agent-registration-v3.md` (Phase 4 outline).
**Spec:** `docs/superpowers/specs/2026-11-14-agent-registration-v3-design.md`, Parts 2–3 and 5, and the Phase 4 acceptance criterion.
**Builds on:**
- Phase 3: #221, #222, #224 and CLI v3 #225;
- the kernel archive, #226 (`afe3da79`).
**Status:** plan only. No code lands with this document.

Line references are to `origin/main` at `afe3da79` (integrity-core) and `c5357a7` (integrity-console), unless stated otherwise.

## Why these three items belong together

All three need the same piece: a v3 answer to the question "which `SovereignAgent` acts for this DID?"

- **Today the answer is a v2 cache.**
  - `integrity_cli/main.py:851-884` (`_resolve_own_sovereign_agent`) reads `primitives.sovereign_agent` from `GET /v1/agent/{did}`.
  - That field is served from the `agent_primitives` table (`handlers.rs:457` `get_agent`, read at `:475`).
  - Only the legacy `POST /v1/agent/register` writes that table (`handlers.rs:305-379`, `db::upsert_agent_primitives` at `:379`).
  - The legacy route re-verifies against `XibalbaAgentRegistry` (`handlers.rs:320`, `chain.rs:381` `resolve_primitives_by_did`), which v3 agents never touch.
- **Consequence:** a v3 agent can never use any on-chain `handle` command (`register` / `set-primary` / `release`, `main.py:887-1053`). Retiring the route without a replacement would also remove the last, already broken, source of the actor address.
- **The v3 source of truth already exists.** It is `AgentRegistry.resolveDID(did).actor`, and `integrity status` reads it (`integrity_cli/status_cmd.py:44-72`).

So the order is:
1. Resolve the actor from `AgentRegistry` in the CLI.
2. Give the Oracle a v3 on-chain record.
3. Move every caller off the legacy route.
4. Delete the legacy route.

## Order of PRs

| PR | Scope | Repo | Depends on |
|---|---|---|---|
| 4.1 | `handle` on-chain writes behind `--onchain`; actor resolved from `AgentRegistry` | core (CLI) | — |
| 4.2 | `integrity status` trust row (stake, locked, frozen) | core (CLI) | — |
| 4.3 | Oracle `POST /v1/agent/{id}/onchain/attestation` and `/onchain/sync`, `agent_onchain_records`, additive | core (Oracle) | — |
| 4.4 | SDK/CLI `register --onchain [--confined --domain ID]` | core (SDK, CLI) | 4.3 deployed; Base Sepolia `AgentRegistry` broadcast (owner) for anything beyond Anvil |
| 4.5 | Console moves `RegisterAgentModal` / `ClaimAgentModal` off the legacy route | integrity-console | 4.3 (and 4.4's flow, for on-chain registration) |
| 4.6 | Delete `POST /v1/agent/register`, the `agent_primitives` readers, `chain.rs` primitives reads, OpenAPI and docs | core (Oracle, spec, docs) | 4.3, 4.5 merged **and** the live console no longer calling it (see the open questions) |

4.1, 4.2 and 4.3 are independent and can run in parallel. None of them touches the held items:
- PR 3.4b;
- the v2 graph deletion PR;
- Codex's second identity.

## PR 4.1 — `handle` on-chain writes behind `--onchain`

**Current behaviour, with evidence:**
- `integrity handle register <handle>` (`main.py:887-917`) always does an on-chain XNS write. It needs a wallet, an RPC endpoint and the actor address. Its help text says "Reverts on-chain … if this identity isn't a real registered agent".
- `handle set-primary` (`:1002-1026`) and `handle release` (`:1029-1053`) are the same.
- The gas-free Oracle directory claim lives under a different verb, `handle claim` (`:1065-1083`, `POST /v1/xns/claim`).
- The comment block at `:1056-1063` already calls the directory "the mandatory, primary handle" and on-chain listing "separate and optional". The command shape contradicts that.
- `XibalbaNameService.register` requires `agentRegistry.isRegisteredAgent(msg.sender)` (`contracts/src/framework/XibalbaNameService.sol:79`). So on-chain handles exist only for **confined** agents, the ones with a bound actor.

**Change:**
- **`handle register <handle> [--identity N]`, default:** an Oracle directory claim for the identity's DID (the current `handle claim` body). No wallet, no RPC.
- **`handle register <handle> --onchain`:** the current XNS write.
- **`handle set-primary` / `handle release`:** these exist only on-chain, so they require `--onchain`. Without it they exit 1 (`NO`) with "on-chain only; pass --onchain".
- **`handle claim AGENT HANDLE`:** stays one release as an alias for operators claiming for another DID, then folds into `register`. That is an owner question, below.
- **`_resolve_own_sovereign_agent`:** reads `AgentRegistry.resolveDID(did).actor`, reusing `status_cmd.onchain_rows`' read path (`status_cmd.py:44-72`), in place of the Oracle `primitives` cache.
  - No record, or an actor equal to `0x0`, exits 1 with "no bound actor: on-chain handles need a confined agent (`integrity register --onchain --confined`)".
  - A read failure exits 3 (`UNVERIFIED`).
- **`--json`:** each subcommand gets `--json`, using `output.Reporter` the way `register` does (`main.py:574-605`).

**Acceptance:**
- `handle register foo` makes exactly one HTTP call, `POST /v1/xns/claim`, and opens no RPC connection.
- `handle register foo --onchain` without a bound actor exits 1 before any wallet load or RPC write.
- `set-primary` / `release` without `--onchain` exit 1.
- `grep -n "primitives" integrity-cli/integrity_cli/main.py` is empty.

**Tests that can fail (`integrity-cli/tests/test_main.py`):**
- `test_handle_register_default_is_directory_only`:
  - `httpx_mock` expects `POST /v1/xns/claim`;
  - `get_w3` is patched to raise;
  - the test **fails today**, because today's command calls `_xns_setup` → `get_w3` first.
- `test_handle_register_onchain_requires_bound_actor`: the fake `AgentRegistry` returns `actor=0x0`, the test asserts exit 1, and the wallet loader is never called.
- `test_handle_onchain_actor_comes_from_agent_registry`: the Oracle `GET /v1/agent/{did}` is mocked with a *different* `primitives.sovereign_agent`, and the test asserts that the XNS call targets the `AgentRegistry` actor.
- **Mutation proof:** revert `_resolve_own_sovereign_agent` to the Oracle read and the third test must fail. Record that in the PR body.

## PR 4.2 — `integrity status` trust row

**Current behaviour:**
- `status_cmd.py:24` hard-codes `TRUST_PENDING`.
- Every code path returns `trust = {"status": "pending"}` (`:35`, `:41`, `:72`).

**On-chain source:**
- `TrustConfig.stakeVault()`: `contracts/src/trust/TrustConfig.sol:23`.
- `StakeVault.stakeOf(agent)` returns `Stake{amount, locked, frozen}`: `StakeVault.sol:36-40`, `:111`.
- The gate reads `frozen` keyed by the actor address (`TrustConfig.sol:22`).
- Freeze is a latch that only admin `unfreeze` clears (`StakeVault.sol:29-30`, `:158`).

**Change:**
- When the actor row is `bound`, read `TrustConfig` from `singletons.TrustConfig`, then `stakeVault()`, then `stakeOf(actor)`. The trust row is:
  - `frozen`, if `frozen` is set;
  - `staked` (amount, locked, available), if `amount > 0`;
  - `unstaked`, otherwise.
- With no actor, the row is `n/a` with "trust applies to a bound actor". It is not `pending`, and it is not a failure.
- Any read failure, a missing `TrustConfig` entry, or `stakeVault == 0` makes the row `unverified`. It is never `unstaked`. The read discipline is the same one `onchain_rows` already documents at `:46`.
- The exit code is unchanged: on-chain rows stay optional evidence (`status_cmd.py:9-10`).
- Delete `TRUST_PENDING` and update the module docstring (`:5-6`).

**Acceptance:**
- A frozen actor shows `frozen`.
- A vault read that raises shows `unverified`.
- The JSON `onchain.trust` carries `amount`, `locked` and `frozen` whenever the status is `staked` or `frozen`.

**Tests that can fail (`tests/test_status_doctor.py`, extending the `status_chain` fixture at `:118`):**
- `test_status_trust_row_frozen`;
- `test_status_trust_row_unstaked`;
- `test_status_trust_row_no_actor_is_na`;
- `test_status_trust_vault_read_error_is_unverified`: this one fails if the code defaults to `unstaked` on an exception.

All four fail against today's code, which always returns `pending`.

## PR 4.3 — Oracle on-chain path (additive)

This is the parent plan's Phase 4 core and spec Part 2. It ships **before** any deletion, so the replacement exists first.
- **`POST /v1/agent/{id}/onchain/attestation`:**
  - It requires an existing off-chain row (`offchain_registration.rs`) whose key matches.
  - It verifies the agent's Ed25519 signature over the EIP-712 `RegisterAgent` digest.
  - It returns the attester's ECDSA signature over the **same** digest.
  - The attester key is distinct from the scorer (spec Part 2; `protocolAddresses.attester` from Phase 3).
- **`POST /v1/agent/{id}/onchain/sync`:**
  - It reads `AgentRegistry.resolveDID` and upserts a new `agent_onchain_records` table (actor, guardian, domain, proof kind, block).
  - The chain is the source of truth, never the request body.
- **`settlement_eligible`:** an active record with an actor.
- **`GET /v1/agent/{id}`:** gains an `onchain` object. It keeps `primitives` until 4.6, so the console keeps rendering.
- **`agent_primitives` readers:** they are **not** changed here. They are listed under 4.6.

**Acceptance:** the spec's Phase 4 criterion, verbatim. On Anvil, an agent that is registered off-chain does the following:
1. it obtains an attestation;
2. it registers in one transaction with an actor;
3. after `sync`, `GET /v1/agent/{id}` shows the on-chain record and `settlement_eligible: true`.

**Tests that can fail (`integrity-oracle/backend/tests/e2e.rs`):**
- the happy path above;
- an attestation request for a DID with **no** off-chain row is 404/409;
- a signature by a different key is 401;
- `sync` for an unregistered fingerprint writes nothing;
- `sync` ignores a forged actor in the body.

CI is the gate for `cargo test`. Locally, at most `cargo check`.

**Deploy:** merging does not deploy unless the Render service auto-deploys from `main`. Check `autoDeploy` before merging. Deploying the Oracle needs explicit owner approval.

## PR 4.4 — `register --onchain [--confined --domain ID]`

Spec Part 5, row "SDK `registration.py`, CLI `agent register`". `register` (`main.py:551-605`) stays off-chain by default.
- **`--onchain`:**
  1. call `register_offchain`, which is idempotent;
  2. call the attestation route;
  3. send one `AgentRegistry.register(...)` from the guardian wallet;
  4. call `onchain/sync`.
- **`--confined --domain ID`:** additionally deploys the `SovereignAgent` and binds it as actor, with `msg.sender` consent through its own `execute`.
- **Exit codes:**
  - 0 when the record is written and synced;
  - 1 on a contract revert (the decoded revert name is shown);
  - 3 when the Oracle or RPC is unreachable.

**Acceptance:**
- On Anvil, `register --onchain --confined --domain D` followed by `status --json` shows `onchain.record = present`, `actor = bound`, and a trust row that is not `unverified`.
- `handle register x --onchain` then succeeds. This closes the loop with 4.1.

**Tests that can fail:**
- An SDK unit test asserts that the digest the agent signs equals the digest `AgentRegistry` recomputes, using the Phase 2 golden vector.
- A CLI test asserts that, without `--onchain`, the RPC stays untouched (`get_w3` patched to raise).
- The Anvil e2e lives beside `tests/conftest.py`'s Deploy run.

**Blocked beyond Anvil:** Base Sepolia needs the owner's `AgentRegistry` broadcast, which waits on the credential rotation.

## PR 4.5 — console off the legacy route (integrity-console)

**Callers, with evidence:**
- `integrity-dashboard/src/services/oracle.ts:532`: `register: (req) => post('/v1/agent/register', req)`, with the request type at `:417-420`.
- `src/components/ui/RegisterAgentModal.tsx:388`: `oracle.register(...)`. Its preflight comment is at `src/constants.ts:19`.
- `src/components/ui/ClaimAgentModal.tsx:74`: `oracle.register(...)`.
- Both modals are mounted by `src/pages/ProtocolDashboardPage.tsx:17-18`, `:339-340`.

**Change:**
- `RegisterAgentModal` uses the 4.4 flow: off-chain registration, then the optional on-chain step through attestation, wallet transaction and sync.
- `ClaimAgentModal` becomes a call to `onchain/sync` for an already-registered record.
- `oracle.register` and `RegisterAgentRequest` are deleted.

**Acceptance:** `git grep -nE "agent/register([^/]|$)" -- integrity-dashboard/src ':!src/generated'` is empty.

**Test that can fail:** a vitest that mounts each modal with `fetch` mocked, and asserts no request URL matches `/v1/agent/register$`.

**Reminder:** console CI runs only userapi plus the dashboard build (the "never runs" memory), so this vitest must be run locally and recorded in the PR.

## PR 4.6 — retire `POST /v1/agent/register`

Spec Part 5 decides that the route is **"deleted outright … no 410 stub, no compatibility shim"**. The deprecation step is therefore a caller migration (4.5) plus a verified-zero-traffic check, not a server shim.

### Compatibility step, before the deletion PR merges

1. 4.3 and 4.5 are merged.
2. **Live caller check.** The live console deploys from `fix/ui-consistency`, not `main` (handoff 2026-11-16 §1). Until that branch carries 4.5, the live Protocol Dashboard still calls the route. Confirm one of these:
   - that branch has been updated to carry 4.5;
   - the owner accepts breaking the live register and claim modals.
3. **Traffic check.** Read Render request logs for the Oracle for `POST /v1/agent/register` over at least 7 days, and record the count in the PR body.
   - A non-zero count from an unknown source blocks the merge.
   - A 410 stub for one release is an owner override of the spec. It is listed in the open questions, not assumed.

### Caller inventory (complete as of `afe3da79` / console `c5357a7`)

| Where | File:line | Kind | Action |
|---|---|---|---|
| Oracle route | `integrity-oracle/backend/src/routes.rs:17` | definition | delete |
| Oracle handler | `handlers.rs:79-83` (`RegisterAgentRequest`), `:296-379` (`register_agent`), `:262` doc | definition | delete |
| Oracle OpenAPI | `src/openapi.rs:57` | schema registration | delete |
| Oracle e2e | `tests/e2e.rs:1013` (`oracle_e2e_register_rejects_missing_genesis_memory_root`), `:1059`, `:1071` | test | delete |
| Oracle doc comments | `db.rs:466`, `handlers.rs:421`, `:437`, `:466`, `:3562`, `offchain_registration.rs:3`, `chain.rs:5`, `:379` | prose | reword |
| Migrations | `0001_init.sql:21`, `0003_agent_did_document.sql:1`, `0022_xns_handles.sql:8` | historical comment | leave (migrations are immutable); new migration drops the table |
| Spec | `spec/ais-api/v1/openapi.yaml:9` (+ `:1001`, `:1025`, `:2501`), `spec/ais-api/v1/README.md:62`, `spec/ais-api/CHANGELOG.md:49` | spec | remove path; CHANGELOG entry |
| Oracle README | `integrity-oracle/README.md:57`, `:70` | doc | rewrite |
| PRODUCTION_GAPS | `PRODUCTION_GAPS.md:1037`, `:4151` | doc | mark superseded |
| CLI test | `integrity-cli/tests/test_client.py:33-36` | generic HTTP client test that uses the path as a sample URL | change the sample path (not a real caller) |
| Console | `oracle.ts:532`, `RegisterAgentModal.tsx:388`, `ClaimAgentModal.tsx:74` | **live caller** | PR 4.5 |
| Console docs | `integrity-dashboard/PRODUCTION_GAPS.md:45`, `src/generated/wiki-data.json` | doc / generated | regenerate the wiki data from core after 4.6 (never hand-edit) |
| xibalba-cortex | `pending_tasks_content.json:7` (prose inside a task body) | data, not a caller | none |
| xibalba-shield | — | none on `origin/main` (Shield moved off in 3.3) | none |
| SDK (core) | — | none: 3.4a deleted `registration.py`'s primitives path | none |
| Hooks snapshot `~/.local/share/xibalba-hooks` | `src/integrity-sdk/integrity_sdk/registration.py:25`, `:898`; `src.prev-bb8cc5a/…` | **stale vendored SDK (snapshot core `bb34958`, pre-3.4a)**; no hook entry point imports `integrity_sdk.registration` (grep over `~/.claude/hooks`, `~/.hermes/hooks` is empty) | not a runtime caller; disappears at the next snapshot rebuild, which is gated on 3.4b's lockstep move |

### `agent_primitives` readers, deleted or repointed in the same PR

| Reader | File:line | Replacement |
|---|---|---|
| `get_agent` | `handlers.rs:457`, `:475-480` | the 4.3 `onchain` object only; `primitives` removed from `AgentResponse` (`:96`, `:120`) |
| `compliance_view` | `handlers.rs:1190`, `:1266` | `agent_onchain_records` |
| `oracle_compliance` (gate read) | `handlers.rs:1691-1694` | actor from `agent_onchain_records` |
| `get_compliance` | `handlers.rs:2057`, `:2066-2074` | same |
| `resolve_primitives_row` | `handlers.rs:2139-2169` | delete |
| `get_agent_baas` | `handlers.rs:3423`, `:3434` | `AgentRegistry.resolve` |
| `get_agent_handle` | `handlers.rs:3531`, `:3542` | actor from `agent_onchain_records` (XNS keys on the actor) |
| `list_agents` join | `db.rs:440-446` | join `agent_onchain_records` |
| actor → agent lookup | `db.rs:380-392` | same, on the new table |
| writers | `db.rs:521-537` `upsert_agent_primitives` | delete |
| reader | `db.rs:575-585` `get_agent_primitives_on_chain` | delete |
| chain | `chain.rs:381` `resolve_primitives_by_did`, `:554` `memory_state` | delete; `resolve(fingerprint)` only |
| tests | `tests/e2e.rs:89`, `:864-887`; `tests/compliance_observed_db.rs:37` | rewrite on the new table |

**Acceptance:** this is the Phase 3 grep, now with **no** Oracle exclusion:
- `git grep -nE "XibalbaAgentRegistry|PrimitiveSet|registerPrimitives|agent_primitives|/v1/agent/register([^/]|$)" -- ':!docs/superpowers' ':!docs/archive' ':!**/migrations/**'` must be empty, apart from files the held v2 deletion PR still owns.
- If the held graph is still present, the PR body lists the remaining hits and maps each one to the held PR.

**Tests that can fail:**
- an e2e asserts that `POST /v1/agent/register` returns **404** (route gone, not 410);
- every rewritten reader test runs against `agent_onchain_records`.

**Deploy:** this PR changes the live Oracle API. Merging needs explicit owner approval if Render auto-deploys from `main`, and the Oracle deploy itself always needs it.

## Out of scope

- PR 3.4b (`verifying_contract` onto `AgentRegistry`, in lockstep with the hooks snapshot).
- The held v2 graph deletion PR, which includes the `SovereignAgent` `factory` → `registry` rename.
- Codex's second identity.
- The Base Sepolia broadcast. That is the owner's step, after the credential rotation.
- Phase 5, the spec amendment and the wiki.

## Open questions for the owner

1. **Live console.** It deploys from `fix/ui-consistency`. Should 4.5 be cherry-picked there before 4.6, or should the live register and claim modals be allowed to break?
2. **410 stub.** The spec forbids a compatibility shim. If the 7-day traffic check finds an unknown caller, do you want a one-release 410 (a spec override), or should the deletion wait?
3. **`handle claim`.** Keep it as a separate operator verb, which claims for *another* DID, or fold it into `handle register --agent DID` after one release?
4. **4.4 before the broadcast.** Ship `register --onchain` proven only on Anvil (Base Sepolia has no `AgentRegistry` yet), or hold it until the broadcast?
