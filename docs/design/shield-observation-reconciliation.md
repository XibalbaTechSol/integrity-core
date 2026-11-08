# Shield observation reconciliation: an independent witness for anchoring coverage

**Status:** scoped (design only; no code). Owner decisions recorded below (2026-11-08).
Builds on `docs/design/anchoring-coverage.md` (the self-reported metric this makes trustworthy).

## Why this exists

`docs/design/anchoring-coverage.md` answers "of the actions an agent **actually executed**, what
fraction carried a prior signed intent?" — but its denominator, `executions_observed`, is **the
agent's own `posttool_effect` report**. The precise host that worries us (`docs/INTERFACE_CONTRACT.md`
§6.10: an agent process that skips the SDK-side commitment) is also the host that can **suppress its
own outcome report**. So coverage reads ~1.0 exactly when the agent is bypassing the gate. The number
is only as honest as the reporter.

Shield's OS-level sensor (`shield/sensors/ebpf/`, `shield/agent_core/`) is the one observer the agent
does not control: it sees a process execute regardless of what the agent reports. This design makes
that sensor the **denominator** for coverage — a witness the bypasser cannot silence — and names the
executions a witness saw that the agent never declared *or* never reported.

This is step 3's real completion, called out as "the next step" at the end of `anchoring-coverage.md`.
It remains **informational only**, like the rest of anchoring coverage: not an AIS input, not a
`Slasher` trigger (that is a separate, later decision — Phase 3).

## Grounding (the code facts that shaped this)

Established by reading both repos on 2026-11-08; verify against current code before building.

1. **The unit of observation is a process *tree*, not a process.** One agent `Bash` tool call spawns
   a whole tree (`sh` → `npm` → `node` → children). The eBPF sensor sees every `exec`; the outcome
   side counts one tool call. A naive "trees seen > outcomes ⇒ suppressed" therefore compares
   processes to tool calls and would fire on every honest `npm test`. **One witnessed action = one
   process tree rooted at a direct child of an attributed agent process.**
   - `shield/schemas/events.py` `ProcessInfo` already carries `pid`, `ppid`, `parent_name`,
     `cmdline`, `hash_sha256` — enough to build the tree — but **no process start time or cgroup**, so
     pid reuse can mis-root a tree. Adding those is Phase 0.
2. **`intended_state_hash` cannot be reconstructed from syscalls.** `docs/INTERFACE_CONTRACT.md` §4.2:
   it is the sha256 of the canonical (JCS) *intent payload* — the agent's logical tool + args. An
   OS-level view of the resulting process has no way to recompute it. So "hash the observed effect and
   match it to intent" is **not a viable correlation path** and is dropped.
3. **A signed per-action gate record already exists.** `shield/gate_receipts.py` writes a signed,
   HMAC-chained, checkpointed receipt per PreToolUse gate decision, binding `agent_did` and
   `action = f"{tool_name}\x00{tool_input_sha256}"`. This is most of the per-action bridge already
   built: a signed statement that a given tool call was gated at time T.
4. **Shield's current BCC-commitment export is "observations dressed as intents."**
   `shield/integrity_exporter/exporter.py` builds a commitment per `PolicyDecision` with
   `invocation_id = decision.invocation_id`, which for an OS-derived decision is a throwaway
   `uuid4()` (`events.py`), and submits it to the **intent/before** side (`POST /v1/bcc/intercept`).
   Worse for reuse: `self.agent_id = sdk_did.load_or_create_did(agent_label)` — the commitment is
   attributed to **Shield's own device DID**, not the observed agent. Consequences:
   - These rows land as *intents* that no outcome can reconcile, inflating `intents_without_outcome`
     on **Shield's own** coverage row (contained to that one agent id, but noise worth removing).
   - The existing path is therefore **not reusable as the witness stream**: wrong identity, throwaway
     correlation id, wrong side of §6.10. The witness must carry the *observed* agent id to a
     dedicated ingest.
5. **The Shield → Oracle pipeline is currently degraded on the primary box** (~200 "backend evidence
   publication failed"/5 min; `xibalba-core-shield-policy` failing with 401s — see
   `project-shield-deploy-incident-2026-10-24` / `project-shield-python314-venv-cutover-2026-11-06`).
   A coverage metric built on a pipeline that is not delivering measures nothing, so fixing it is
   Phase 0, not an afterthought.

## Decisions (owner, 2026-11-08)

| Question | Decision | Consequence |
|---|---|---|
| First increment | **Full build: aggregate floor + per-action findings** (Phase 0+1+2) | Larger and needs the gate daemon on the host, but gives named full-bypass findings, not just a count. The two layers stack; the floor still works where hooks do not. |
| Witness transport | **Dedicated Oracle observation ingest** (`POST /v1/shield/observation`) | Keeps the §6.10 before/after split clean — Shield is a *third*, independent witness, not a second intent source — and avoids unwinding the observations-as-intents path into the metric. |

## Design

### The witness stream
Shield emits **signed, per-device-sequenced** observation records to the new ingest. Each record is:

- signed with Shield's **device key** (the agent cannot forge "nothing was witnessed", and a verifier
  trusts the device, not the agent);
- **sequenced per device** (a monotonic counter + prev-hash chain, mirroring `gate_receipts`), so a
  **gap is detectable**. A missing or suppressed witness stream must read as **unknown**, never as
  perfect coverage;
- tagged with the **observed `agent_id`** (from `AgentRegistry`/`DeviceContext` attribution) and an
  **attribution-confidence** field;
- a **process-tree fingerprint** (root exe hash + cmdline digest + tree shape + window), not the raw
  command (privacy: same posture as `gate_receipts` hashing the input, never storing it);
- an optional **gate-receipt reference** when the tree's root tool call was gated.

Oracle side: `POST /v1/shield/observation` (new route in `integrity-oracle/backend/src/routes.rs` +
`handlers.rs`), persisted to a `shield_observations` table (`db.rs`) keyed by observed `agent_id`,
device id, and sequence. The signature and sequence are verified on ingest; a gap sets a
per-agent/window `witness_complete = false`.

### Coverage, extended
`db::agent_anchoring_coverage` gains, per agent/window:

| new field | meaning |
|---|---|
| `executions_witnessed` | process-trees Shield witnessed and attributed to this agent (the trusted denominator) |
| `executions_suppressed` | witnessed trees with **no** self-reported outcome and **no** gate receipt — the full-bypass set |
| `witness_complete` | false when the witness stream had a gap in the window; flips the denominator to `None` rather than reporting a falsely-high ratio |

When a trusted, complete witness covers the window, `coverage_ratio = executions_anchored /
executions_witnessed`. Otherwise it falls back to today's self-reported denominator, **clearly
labelled** as self-reported. `executions_suppressed > 0` adds named findings to the existing
`findings` list.

### The per-action join (Phase 2)
Carry the `gate_receipts` chain to the Oracle (ship it, or reference it from the observation record),
then join **witnessed tree ↔ gate receipt ↔ self-reported outcome** by `tool_name` + input digest,
process lineage, and time window. The classifications:

- tree witnessed, receipt present, outcome present, intent reconciled → **anchored**;
- tree witnessed, no receipt **and** no outcome → **full-bypass finding** (named: root exe, window,
  attribution confidence);
- tree witnessed, receipt present but no prior intent → the existing `outcome_without_intent` /
  unanchored case, now corroborated by an independent witness;
- low attribution confidence → **surfaced, never counted** as a finding (see guardrails).

## Guardrails (non-negotiable)

- **Witness-unavailable reads `None`, never 1.0.** Enforced by the per-device sequence + `witness_complete`.
- **Attribution confidence travels with every record.** `AgentRegistry` process→agent attribution is a
  device-local heuristic; a low-confidence tree is shown to an operator, never auto-counted as a bypass.
- **Threat model, stated plainly.** Shield runs as root / a system unit; the agent does not. This design
  defends against an *unprivileged* agent that skips the gate and suppresses its own report. A bypasser
  with **root** can stop or lie to the sensor itself and defeats it — out of scope, and said so here.
- **Informational only.** Not an AIS input, not a `Slasher` trigger. Turning sustained low witnessed
  coverage into a dispute is Phase 3, a separate decision.
- **Privacy.** Records carry hashes/digests and lineage, never raw command lines or file contents —
  the posture `gate_receipts` already holds.

## Phasing

- **Phase 0 — foundations.** Fix the Shield → Oracle pipeline (the publication failures + 401s); add
  process start-time + cgroup to `ProcessInfo` and the eBPF sensor so trees root reliably under pid
  reuse; stop/redirect the observations-as-intents commitments off the intent path (de-pollute
  `intents_without_outcome`).
- **Phase 1 — aggregate floor.** New signed/sequenced observation ingest; Shield emits per-agent/window
  witnessed-tree counts; extend `agent_anchoring_coverage` with `executions_witnessed` /
  `executions_suppressed` / `witness_complete` and the `None`-on-gap denominator switch.
- **Phase 2 — per-action findings.** Carry the `gate_receipts` chain to the Oracle; join tree ↔ receipt
  ↔ outcome; emit named full-bypass findings.
- **Phase 3 — (separate, later).** Decide whether sustained low witnessed coverage becomes a dispute
  signal. Not in scope here.

This is **cross-repo**: `integrity-oracle` (ingest, schema, coverage) in integrity-core, and the sensor
/ exporter / witness emitter in `xibalba-shield`. Expect several PRs; Phase 0 alone spans an operational
fix, a schema change, and the commitment-path redirect.

## What it does and does not prove

- **Does:** give coverage a denominator the bypasser cannot suppress, and name executions that ran with
  no declared intent *and* no self-report — the §6.10 gap, made visible per agent.
- **Does not:** defeat a root-level bypasser (threat model above); prove an intent was *honest* (a
  signed intent is still the agent's own claim); or cover hosts where Shield is not deployed (those
  windows read `None`, by design).

## Provenance

Scoped from direct reads of `integrity-oracle/backend/src/{db,routes,handlers}.rs`,
`shield/{schemas/events,integrity_exporter/exporter,gate_receipts,agent_core/*}.py`, and
`docs/INTERFACE_CONTRACT.md` §4.2/§6.10, with an advisor (stronger-model) review and self-review. The
standalone Devil's Advocate engine is not entitled in this repo (`ENGINE_NOT_IN_PLAN`); that review
posture is recorded here deliberately.
