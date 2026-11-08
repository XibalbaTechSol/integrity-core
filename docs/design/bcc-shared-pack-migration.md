# BCC onto the shared signed pack and receipts (B2)

**Status:** stages 1 and 2 of 4 delivered; stages 3-4 are `[PLANNED]`. **Owner decision recorded:** staged
migration, chosen over "receipts on today's unsigned Rego" and over "conformance vectors first"
(2026-10-06). Execution authority is `docs/ecosystem/INTEGRITY_ECOSYSTEM_PLAN.md` B2; this page is the design behind it.

## Decisions recorded (owner, 2026-10-10)

| Question | Decision | Consequence stated |
|---|---|---|
| Rollout | **Dual-run, then a flag** | Two evaluations per request until cutover; the pack cannot change a response while `bcc.rego` decides. Rollback is the flag. |
| Who signs the pack | **Reuse Shield's operator key** (the design recommended a separate BCC key) | One leaked key signs policy both products trust. Mitigated, not removed, by pinning the pack hash. |
| Clinical allowlist | **Hot-reloaded config file** | Oracle sync stays `[PLANNED]`. An invalid file authorizes no extra agents. |
| BCC receipts | **Strict, as for Shield** | A receipt that cannot be recorded denies the request (observe/shadow never blocks). A disk fault takes the gate down; that cost was accepted for Shield. |
| "Same compiled pack" (stage 4) | **Shared rulebook vectors** | One set of `(policy result -> expected decision)` vectors that BCC's CI and Shield's CI both run through `resolve()`. Not a unified pack. |

## Why this is not a wiring job

Shield's gate already evaluates a signed pack through the shared decision contract
(`integrity_sdk.core.decision` / `core.packs` / `core.opa`) and, since xibalba-shield #48, writes
signed receipts. `bcc_middleware` does neither:

| | Shield gate | `bcc_middleware` today |
|---|---|---|
| Policy | signed pack, hash verified before use | `policies/bcc.rego` (353 lines), queried at `/v1/data/integrity/bcc` |
| Result | `{decision, reason_code, controls}` via `resolve()` | boolean `allow` + a *set* of `violation` messages + `requires_baa` |
| No-match / error | pack-declared default, fail closed | hand-written fail-closed in `opa_client.py` |
| Receipts | signed, chained, checkpointed | none |
| `integrity-sdk` dependency | yes | **none** (re-implements canonicalization and base58) |

So "BCC receipts" cannot honestly be built first: a receipt names a `pack_hash`, and a hash of an
unsigned Rego bundle is not a verified pack. The plan already says so: *"BCC and Shield do not yet
evaluate one shared compiled pack."* The shared pack in `packs/hipaa` is six lines (one
`NO_ACTIVE_BAA` rule); BCC's real authorization is `bcc.rego`.

## Stage 1 (delivered): a ported pack and a differential harness

* `packs/bcc/` re-expresses `bcc.rego` in the decision contract. **bcc_middleware does not load it
  yet.**
* `integrity-sdk/tests/unit/test_core_bcc_pack_equivalence.py` runs both policies in two real OPA
  servers over 2,000+ deterministic cases and fails on any disagreement. "Equivalent" means: the same
  allow/deny verdict (the security property); a reason code that is recomputed from the *old* policy's
  messages and a priority table, not read back from the pack; and the same clinical intent set and
  authorized agents. Coverage guards fail the build if the corpus stops exercising a rule or a feasible
  pair of rules (priority is only observable when two fire together).
* Mutation-checked: 14 of 15 deliberate breakages fail the harness; the fifteenth swaps the order of
  two codes that cannot fire together, which no test can observe (the harness asserts that they
  cannot).

### Deliberate differences from `bcc.rego`

1. **One reason code, not a set of messages.** When several rules fire the pack reports the
   highest-priority code (`_priority` in `policy.rego`). The *set of denials is unchanged*; only which
   code is reported when several fire is now defined. Codes are the prefixes `bcc.rego` already used.
2. **The clinical allowlist is an input** (`input.clinical_allowlist`), not `data.clinical_allowlist`.
   A signed pack is immutable and `OpaClient` owns what OPA holds. It must be gate-supplied, never
   forwarded from the agent's own claim.
3. **`requires_baa` is not an output** (the contract admits exactly `decision`, `reason_code`,
   `controls`). It moves to a constant in the gate, pinned to the pack by a test.
4. **Free-text detail is not in the result.** The gate formats it from its own input.
5. **A malformed commitment is denied** (`BCC_MALFORMED_COMMITMENT`, reported first). See below.

### Finding: `bcc.rego` fails open on a commitment with no `agent_id` or no `intent_type`

Found by the harness, not by reading. In Rego a rule that reads an absent field, or negates a
membership test on one (`not input.agent_id in S` is **undefined**, not true), silently does not fire.
With `agent_id` absent, `bcc.rego` allows a tier-0 `SECURE_EMR_WRITE`; with `intent_type` absent, every
rule is inert and it allows anything. **This is not a live bypass:** `bcc_middleware` requires both
fields and validates `agent_id` as a DID before OPA is called. It is still a policy that cannot be
trusted on its own, and the migration's first duty is to not carry it forward. The pack denies; the
test pins the old behaviour so repairing `bcc.rego` (not planned, since it is being replaced) would
prompt deleting the divergence. The same fault existed in my own faithful first port; the harness
caught that too.

## Stages 2-4 (`[PLANNED]`)

**Stage 2 (delivered): BCC loads the pack, in dual-run, behind a flag.** `bcc_middleware/app/pack_policy.py`,
`app/clinical_allowlist.py`, and the `_policy_outcome` layer in `app/main.py`; runbook
`docs/runbooks/bcc-policy-pack.md`. Everything is optional and off by default, so with no pack configured BCC
behaves as before (the 161 pre-existing tests pass unchanged; 226 pass with the 65 new ones).

* **Packaging.** `integrity-sdk` is a path dependency (`bcc_middleware/pyproject.toml`, `uv.lock`); the SDK core adds
  only `base58`, `cryptography`, `jcs`, `pycryptodome`, `pyyaml`. The image build context moved to the repository
  root (`Dockerfile`, `Dockerfile.dockerignore`, `docker-compose.yml`), and the SDK is now part of the
  stale-image check (`scripts/check_deploy_freshness.py`).
* **Behaviour.** Dual-run evaluates the pack concurrently with `bcc.rego` and logs and counts any disagreement;
  `BCC_POLICY_ENGINE=pack` makes the pack decide. Policy still runs before the on-chain BAA check, only for clinical
  intents, so a request the policy denies still costs no chain call. `requires_baa` is the gate's constant
  `CLINICAL_INTENT_TYPES`, pinned to `bcc.rego` and the pack by tests. Deny strings keep their shape
  (`OPA_REJECTION: <CODE>: ...`).
* **Failure postures.** Loading is fail-closed (in pack mode the service refuses to start). Evaluation is
  fail-closed and never charges the agent's circuit breaker. A pack OPA that restarted and forgot the pack gets one
  throttled re-install; until then the pack's default deny applies.
* **Verification.** A pipeline-level differential sends 17 real signed commitments through `run_intercept` under
  `rego`, dual-run and `pack`; all three must agree, byte-for-byte for dual-run, and each scenario states its
  expected reason code. 11 mutation checks of the new guards were all caught. **Not verified here:** the Docker image
  build and the pulled `opa-bcc-pack` image tag (no Docker daemon in the build environment). The image layout was
  verified by simulating the exact `uv sync --frozen --no-dev` layout, and `docker compose config` validates.

### Findings from stage 2

1. **Sharing one OPA corrupts both gates.** `OpaClient.install` deletes and replaces every policy under one fixed id
   prefix, and every pack's file is `policy.rego`, so two gates' packs on one OPA overwrite each other. BCC therefore
   requires `BCC_PACK_OPA_URL` with no fallback to `OPA_URL`, and compose gets a dedicated `opa-bcc-pack`.
2. **`PUT /v1/admin/clinical-allowlist` has no authentication** and CORS is `*`. Anyone who can reach BCC's port can
   grant any agent clinical authority under `bcc.rego`. Pre-existing; **fixed separately** (every `/v1/admin/*` route
   now requires `BCC_ADMIN_TOKEN`). In pack mode the endpoint also returns 409, so it is neither a silent no-op nor a
   writer of the pack's authority.
3. **A second `__post_init__` silently replaces the first.** `Settings` already had one, so the engine validation I
   first added would have been dead code. Merged into the existing method, with a test.
4. **`BCC_SHADOW_MODE` defaults to true.** By default BCC records would-be denials but blocks nothing, so strict
   receipts (stage 3) will not block anything until an operator turns enforcement on.

### Stage 3 (delivered): one receipt writer, and BCC emits receipts

`GateReceiptWriter` moved from Shield into `integrity-sdk` (`integrity_sdk/core/receipt_writer.py`; stdlib and `core`
only, so the import hygiene rule holds) with epoch rotation added. `bcc_middleware/app/gate_receipts.py` adapts it
(the blocking `fsync` runs in a thread, off the event loop). Shield keeps its own copy until a follow-up swaps it for
the SDK's after a pin bump `[PLANNED]`; a golden vector (fixed key, timestamps and inputs -> pinned receipt hashes)
lets Shield pin the same values so the two cannot drift.

Decisions applied (owner, 2026-10-10): receipts for **authenticated outcomes only**; log scaling by **epochs**;
**strict** like Shield.

* **What gets a receipt:** everything after the Ed25519 signature verifies (replay, expiry, quarantine, policy deny,
  token budget, BAA, allow). Not the breaker, chain/contract mismatch or bad-signature denials: until the signature
  verifies `agent_id` is whatever the caller typed, and a signed receipt naming a real agent for a forged request
  would be evidence the protocol manufactured against the wrong party.
* **Strict, before admission.** The allow receipt is written before the commitment is admitted to the Merkle batch
  and before the verification token is issued. If it cannot be written, enforce mode denies as
  `BCC_RECEIPT_UNAVAILABLE` with nothing to undo and without charging the agent's breaker. `BCC_LENIENT_RECEIPTS=1`
  lets the allow through (`receipt_status: "failed"`, CRITICAL log). Shadow mode never blocks. A denial that cannot
  be recorded stays a denial.
* **The receipt names the policy that decided.** Pack mode: the pack hash and the pack's specific reason code and
  controls. `bcc.rego` (including dual-run, where the pack is only advisory): the all-zero `NO_PACK_HASH` sentinel and
  `BCC_REGO_POLICY_PERMIT/DENY`.
* **Epochs.** At `BCC_RECEIPT_EPOCH_MAX_RECEIPTS` (50,000) or `BCC_RECEIPT_EPOCH_MAX_AGE_SECONDS` (86,400) the epoch is
  closed with a covering checkpoint and a new one opens with a new `log_id` and a fresh chain. No format or verifier
  change. Cost, stated: nothing links epoch N to N+1 in the files; deleting a *middle* epoch is refused at start, but
  deleting the *newest* epoch(s) cannot be seen from the files alone. **Closed epochs can now be anchored** (2026-10-11,
  `BCC_RECEIPT_ANCHOR_ENABLED`; runbook section 7), which makes their removal detectable against the chain; the open epoch is
  covered only once it closes. Start-up verifies only
  the newest epoch; `verify_epoch_directory` is the full offline audit.
* **Accepted cost:** the token budget is charged before the receipt, so a receipt outage costs an agent budget for
  requests we then refuse. Bounded by the budget; clears at the daily reset.

Verified: 23 SDK tests and 25 BCC pipeline tests; mutation checks (7 on the writer, 12 on the pipeline, the survivors
strengthened and re-caught); and a live run: real uvicorn BCC, real OPA, real signed commitments over HTTP, checked
with `integrity-cli verify` (intact passes; a flipped decision is `BAD_SIGNATURE`; a truncated tail is `TRUNCATED`).

### Stage 4 (delivered here; Shield's half is xibalba-shield's PR): shared decision vectors

`integrity-sdk/tests/conformance/decision_vectors.json` is the single statement of how a policy result is
interpreted: 63 vectors, 49 `scope: result` (run by every gate) and 14 `scope: resolve` (plumbing a gate reaches
without an evaluator result: no pack, evaluator error, unknown event class, shadow mode, bad mode). It covers the
three declared defaults, explicit permit/deny/log_only, control pass-through, every malformed shape (missing or
unknown fields, wrong types, the reason-code charset and 64/65 length edge, a trailing newline, a Unicode look-alike,
the reserved `INTEGRITY_` prefix, string/list/number/boolean results, falsy non-objects) and shadow never blocking.
**Expectations are written by hand, not generated from `resolve()`**, so the file can disagree with the code.

It runs in three places: the SDK (through `resolve()`, `tests/unit/test_core_decision_vectors.py`), BCC (through its own
`PackPolicy.decide_sync` with only the OPA transport stubbed, `bcc_middleware/tests/test_decision_vectors.py`), and
Shield (through `PolicyEngine.evaluate_with_basis`, in its own repo, pinned to an integrity-core ref that carries the
file). Running it through each gate's own glue, rather than only through `resolve()`, is the point: that is where a
gate can disagree with the contract while `resolve()` is right.

What it found: before this stage Shield's engine only treated a result as a decision when it had both `decision` and
`reason_code`, and treated any non-object result as "no rule matched". So a result of `{"decision": "deny"}` or the
string `"deny"` took the event class's default (`log_only` or `permit` for some classes) instead of failing closed as
BCC and the contract do. Fixed in Shield's PR; the vectors are what make that fix stay fixed. Twelve vectors failed
in Shield at first: ten were this fail-open; two (`{}`) are a documented, pinned Shield exception, because its evaluator
returns the whole package object (display variables carry Rego defaults), so an object with none of
`decision`/`reason_code`/`controls` means "no rule matched" there. Exceptions live in the vector file (`exceptions`), are
validated by the SDK runner, and are capped at two.

Verified: 66 SDK tests and 50 BCC tests; 17 mutations of `resolve()` and 4 of BCC's glue are caught (one first survivor,
the defensive invalid-default branch, got its own vector; a Shield-style filter in BCC's glue fails 12 vectors).

### Gap carried forward, stated

`packs/bcc/controls.yaml` cites only the two controls the old policy already claimed (HIPAA
164.312(a)(1) for the allowlist and tier gates, 164.312(b) for the AOS audit fields). The intent-label
pattern checks and the token budget cite none. Gate B-local's "every rule cites a control" is **not**
met for this pack; closing it is a compliance-owner decision, and the evidence does not certify legal
compliance (`docs/CONTROLS_MATRIX.md` section 0).

**Now machine-checked (2026-10-11).** `test_the_rules_that_cite_no_control_are_exactly_the_known_gap` pins the four codes that cite
no control (`BCC_MALFORMED_COMMITMENT`, `HIPAA_TECHNICAL_SAFEGUARD_FAILURE`, `POLICY_VIOLATION`, `TOKEN_BUDGET_OPA`) with the
reason for each, so a new rule must either cite a control or be added to that list on purpose. The gap itself stays open on
purpose: `docs/CONTROLS_MATRIX.md` maps only access control and audit controls, and citing a HIPAA sub-control for the others
would be inventing a compliance claim that the compliance owner has not made.

## Stage 5 (design + SDK delivered): the daemonless in-process engine

**Why this stage exists.** Stages 2-4 removed the policy *fork* (one decision contract, one signed
pack, one receipt writer) but not the OPA *daemon*. Both gates still evaluate by HTTP to a separate
`opa` server. That server is the failure point this whole effort keeps hitting: it sleeps or dies
independently of the gate, it is a shared namespace where one gate's pack can refuse another's
(the 2026-10-24 live outage was exactly this), and on a free cloud host it adds a cold-start to a
decision that must answer in milliseconds. "BCC and OPA could be one thing" (owner, 2026-11-06) is
the decision to remove it.

**Decision recorded (owner, 2026-11-06).**

| Question | Decision | Consequence stated |
|---|---|---|
| Engine source | **OPA's own `opa build -t wasm`**, not a Rego reimplementation | `rego-cpp`/`regopy` could not even load `packs/bcc` (`Invalid collection` on `_primary`); `regorus` is not on PyPI; `opa-wasm` needs Wasmer (absent here). OPA-compiled wasm is the only path with OPA fidelity. Proven equivalent, not assumed — see below. |
| Where the wasm lives | **Inside the signed pack**, as `policy.wasm` | `pack_hash` already covers every file, so the signature covers the wasm with no new mechanism. A device runs verified bytes, never a compile it did itself. This is the cross-repo contract change. |
| Committed or built | **Built at sign time, never committed** | `build_pack_wasm` runs before `sign_pack` in the signing runbook. The repo's `packs/bcc` stays Rego-only source; the signed, wasm-bearing pack is the build artifact (the same way `pack-config/pack/` already is). `GOLDEN_PACK_HASH` and the committed pack are unchanged. |
| Rollout | **New engine behind `BCC_POLICY_ENGINE=wasm`**, OPA server modes untouched | `rego` (default), `pack` (OPA server), and now `wasm` (in-process). Rollback is flipping the value back. Dual-run against `bcc.rego` is unchanged and orthogonal. |

**What was built in the SDK (this change).** `integrity_sdk.core.wasm_engine.WasmPolicyClient` mirrors
`OpaClient`'s surface exactly (`install` / `query` / `decide` / `installed_pack_hash`, raising the same
`OpaError`), so `app/pack_policy.py` selects one or the other with no other change to the gate's control
flow or failure handling. `integrity_sdk.core.wasm_build` has `build_pack_wasm` (compile, for the
signing step) and `verify_pack_wasm` (rebuild from the verified Rego and compare — the audit that
closes the one gap signing cannot: that the shipped wasm is the compile of the signed Rego; OPA wasm
output is byte-reproducible for a pinned OPA version). `wasmtime` is an optional extra
(`integrity-sdk[wasm]`); import hygiene keeps it out of the dependency-light core.

**Failure postures (per the repo rule).**

- Fail closed everywhere: no `policy.wasm`, a module that will not load, a trap, an `opa_abort`, an
  unsupported builtin, or malformed output all raise `OpaError`, which `decide` turns into the pack's
  deny. Nothing in this client can allow.
- Host builtins are an allowlist: only `sprintf`, and only the `%v/%s/%d/%%` subset the policies use,
  reproduced exactly. A pack that needs any other builtin (`crypto.sha256`, `semver.is_valid`, …) is
  refused at install (`WASM_UNSUPPORTED_BUILTIN`), never evaluated approximately. `net.cidr_contains`,
  `strings.reverse`, `json.is_valid` compile natively into the module and need no host support (checked).
- No shared state between evaluations: each query runs on a fresh instance.

**Equivalence is tested, not claimed.** `tests/unit/test_core_wasm_engine.py` runs `WasmPolicyClient`
and a real `opa` server over the stage-1 equivalence corpus (the same cases, never a mock of OPA) and
asserts identical raw results on every case; each safety property above has a mutation that must fail a
test. In-process evaluation measured well under 1 ms/call versus a network round-trip.

### Stage 5 — delivered, and what remains

**Delivered.**

- **BCC wiring (done).** `app/config.py` validates `BCC_POLICY_ENGINE` as `rego|pack|wasm` and exposes
  `pack_is_decider` (pack|wasm) and `uses_opa_server` (everything but wasm — dual-run still needs the
  server); `app/pack_policy.py` selects `WasmPolicyClient` or `OpaClient` with no other change to the
  gate's control flow. A gate now selects the engine; `wasm` needs no `BCC_PACK_OPA_URL`.
- **Signing-runbook step + OPA version pin (done).** `integrity pack build-wasm` (compile before sign)
  and `integrity pack verify-wasm` (reload the signed pack and rebuild from its Rego to compare) are CLI
  commands, and `docs/runbooks/bcc-policy-pack.md` §1/§4a sequence them. Byte-reproducibility holds only
  per OPA build, so `wasm_build` refuses any OPA but the pinned `PINNED_OPA_VERSION` (`1.18.2`, the version
  `scripts/install_toolchain.sh` installs; a test asserts the constant cannot drift from that script).
  `build_pack_wasm`/`verify_pack_wasm` shell out to `opa` only, so building/auditing a pack needs the pinned
  opa but **not** the `[wasm]` runtime extra; `WASM_FILE` moved to `core.packs` to keep that decoupling.

**Remaining (`[PLANNED]`).**

- **Shield.** Shield can adopt the same engine (its `gate_daemon` keeps a warm `PolicyEngine`); that is
  a xibalba-shield change, out of scope here. The pack it loads is unaffected by an added `policy.wasm`
  — `load_pack` hashes whatever files are present — so a wasm-bearing pack is backward-compatible with
  an OPA-server gate that ignores the file.
