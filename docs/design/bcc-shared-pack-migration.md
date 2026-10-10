# BCC onto the shared signed pack and receipts (B2)

**Status:** stages 1 and 2 of 4 delivered; stages 3-4 are `[PLANNED]`. **Owner decision recorded:** staged
migration, chosen over "receipts on today's unsigned Rego" and over "conformance vectors first"
(2026-10-06). Execution authority is `docs/EXECUTION_PLAN.md` B2; this page is the design behind it.

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
   grant any agent clinical authority under `bcc.rego`. Pre-existing; **not fixed here.** In pack mode the endpoint
   returns 409, so it is neither a silent no-op nor an unauthenticated way to write the pack's authority. Fixing the
   endpoint for the default mode is a separate change that should not wait for the cutover.
3. **A second `__post_init__` silently replaces the first.** `Settings` already had one, so the engine validation I
   first added would have been dead code. Merged into the existing method, with a test.
4. **`BCC_SHADOW_MODE` defaults to true.** By default BCC records would-be denials but blocks nothing, so strict
   receipts (stage 3) will not block anything until an operator turns enforcement on.

**Stage 3: one receipt writer.** `shield/gate_receipts.py` is Shield-local today. BCC must not get a
second copy: move `GateReceiptWriter` into `integrity-sdk` (stdlib and `core` only, so the import
hygiene rule holds) and have both gates use it. BCC is an async, concurrent HTTP service, so the writer's
single lock plus a blocking `fsync` must run off the event loop (a thread). Strict, per the owner's decision.
The receipt records the final decision *after* the BAA check, with the pack hash that decided.

**Stage 4: shared rulebook vectors.** One JSON file of `(policy result -> expected decision)` cases covering
the contract's rules (no match takes the pack default, a malformed result denies, reserved reason codes are
rejected, deny wins, shadow mode never blocks), evaluated through `resolve()` by BCC's CI and Shield's CI.
This is what "BCC and Shield evaluate the same compiled pack" is taken to mean (decision recorded above): the
two gates keep different packs over different inputs, and what they must share is how any policy result is
interpreted.

### Gap carried forward, stated

`packs/bcc/controls.yaml` cites only the two controls the old policy already claimed (HIPAA
164.312(a)(1) for the allowlist and tier gates, 164.312(b) for the AOS audit fields). The intent-label
pattern checks and the token budget cite none. Gate B-local's "every rule cites a control" is **not**
met for this pack; closing it is a compliance-owner decision, and the evidence does not certify legal
compliance (`docs/CONTROLS_MATRIX.md` section 0).
