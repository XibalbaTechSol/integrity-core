# BCC onto the shared signed pack and receipts (B2)

**Status:** stage 1 of 4 delivered; stages 2-4 are `[PLANNED]`. **Owner decision recorded:** staged
migration, chosen over "receipts on today's unsigned Rego" and over "conformance vectors first"
(2026-10-06). Execution authority is `docs/EXECUTION_PLAN.md` B2; this page is the design behind it.

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

**Stage 2: BCC loads the pack and decides through `resolve()`.** Add `integrity-sdk` as a dependency
(this changes `bcc_middleware/pyproject.toml`, `uv.lock`, the Dockerfile build context, which today
copies only the service directory, and the CI job). Load with `load_pack` against a configured trusted
pack signer, install through `OpaClient`, replace `opa_client.evaluate` with `query` + `resolve`.
Ordering is preserved: policy first, the on-chain BAA check after, only for clinical intents, so a
request the policy denies still costs no chain call. The final decision (after BAA) is what gets a
receipt. Existing deny strings (`OPA_REJECTION`, `BAA_INACTIVE`, ...) keep their shape; the reason code
becomes the detail. A differential run of old-vs-new through the *HTTP intercept path* (not only the
policies) gates the switch.

**Stage 3: one receipt writer.** `shield/gate_receipts.py` is Shield-local today. BCC must not get a
second copy: move `GateReceiptWriter` into `integrity-sdk` (stdlib and `core` only, so the import
hygiene rule holds) and have both gates use it. BCC specifics to decide then: it is an async, concurrent
HTTP service (the writer's single lock plus a blocking `fsync` must not stall the event loop; run it in
a thread), and the strict-by-default posture decided for Shield applies unless the owner says otherwise.

**Stage 4: shared conformance vectors.** One JSON file of `(input, expected decision)` evaluated by
BCC's CI and Shield's CI.

### Open question for the owner

"BCC and Shield evaluate the same compiled pack" needs a definition. BCC's vocabulary is *intent
commitments* (`EMR_WRITE`, `claude_tool:<Tool>:<risk>`); Shield's is *agent events* (`agent_event`,
`process`, ...). `packs/bcc` and Shield's `regulated` pack are different policies over different
inputs. Two readings: (a) both gates load the same pack(s) in `packs/` (`base`, `hipaa`) for the
overlapping rules and keep gate-specific packs for the rest, with vectors over the shared one; or
(b) the vectors are over the decision *contract* (every pack, every gate, same `resolve()` semantics).
Stage 4 cannot start until this is settled; stages 2-3 do not depend on it.

### Gap carried forward, stated

`packs/bcc/controls.yaml` cites only the two controls the old policy already claimed (HIPAA
164.312(a)(1) for the allowlist and tier gates, 164.312(b) for the AOS audit fields). The intent-label
pattern checks and the token budget cite none. Gate B-local's "every rule cites a control" is **not**
met for this pack; closing it is a compliance-owner decision, and the evidence does not certify legal
compliance (`docs/CONTROLS_MATRIX.md` section 0).
