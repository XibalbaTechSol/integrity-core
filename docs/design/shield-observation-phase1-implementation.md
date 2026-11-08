# Shield observation reconciliation — Phase 1 implementation scope

**Status:** scope (not built). Implements **Phase 1 — aggregate floor** of
`docs/design/shield-observation-reconciliation.md` (#201). Phase 0 is complete
(witness ProcessInfo lineage: `xibalba-shield` #90 best-effort + #91 race-free in-kernel
`start_boottime`/`cgroup_id`; backend publication pipeline fixed — see below). This doc pins the
Oracle-side ingest + coverage extension so the next increment is turnkey.

## The one hard problem, and how Phase 1 avoids getting it wrong

The reconciliation doc (§Grounding) already states it: **Shield counts process _trees_; the Oracle
counts tool _invocations_.** A naive Oracle-side `executions_suppressed = executions_witnessed −
executions_observed` compares incompatible units and is **vacuous**:

- `executions_observed` is inflated by tool calls that spawn **no** process (Read, Edit, Write, MCP
  calls) — they never appear as a witnessed tree, so they would float the "suppressed" floor at 0.
- raw witnessed execve is inflated by **non-tool** children of the agent process: SessionStart /
  PreToolUse hooks, the statusline, MCP server launches, and the per-call gate client itself — each a
  tree with no tool-call outcome, which a naive diff would report as suppression **against the gate**.

**Resolution (Phase 1):** attribution and the witnessed↔bypass comparison happen **on the Shield
device, where both signals coexist** — the eBPF witness stream *and* `gate_receipts` — so the units
are compatible (tree ↔ gate receipt, both process-tree-rooted):

- `executions_witnessed` counts only **gate-attributed** trees (a tree whose root is a tool-call
  process the gate daemon saw), **instrumentation excluded**. Hooks/statusline/MCP-launch/gate-client
  trees are filtered out on-device, not shipped as witnessed executions.
- `executions_suppressed` is the count of **attributed trees with no gate receipt** — the full-bypass
  set Shield can see locally (it witnessed a tool-call-shaped tree the gate never authorized). Shield
  emits this **count**; the Oracle stores and exposes it. The Oracle does **not** attempt the
  per-tree join in Phase 1 — that is Phase 2 (carry the receipt chain to the Oracle for *named*
  findings + Oracle-side verification).

This keeps Phase 1 a true "floor": a trustworthy count where the gate daemon runs, degrading to
`witness_complete = false` (→ denominator `None`) where it does not — never a fabricated suppression.

## Oracle-side ingest

**Route:** `POST /v1/shield/observation` — new in `integrity-oracle/backend/src/routes.rs` +
`handlers.rs`, following the existing `/v1/shield/*` handlers (`create_shield_policy_token`,
`get_unregistered_agents`) for `State(AppState)` + admin/device auth shape.

**Auth / integrity (non-negotiable, per #201 guardrails):**
- Each record **signed with Shield's device key** (the agent cannot forge "nothing was witnessed").
  Unauthenticated ingest would let anyone forge suppression against any agent — rejected.
- **Per-device sequenced** (monotonic counter + prev-hash chain) using the **shared SDK
  `receipt_writer`** that `gate_receipts` and BCC already use — do **not** invent a new chain format.
  Signature + sequence verified on ingest; a sequence **gap** sets `witness_complete = false` for
  that agent/window.
- `witness_complete` derives from **sequence continuity + a freshness heartbeat** (the Oct 27–Nov 6
  sensor outage is exactly the case that must read as `None`, not high coverage).

**Table:** `shield_observations` (`db.rs` + a migration). Keyed by observed `agent_id`, `device_id`,
`sequence`. Each row carries: window bounds, `executions_witnessed`, `executions_suppressed`,
attribution-confidence, a process-tree fingerprint (root exe hash + cmdline digest + tree shape —
**never** raw command lines, per the `gate_receipts` privacy posture), optional gate-receipt
reference, device signature, prev-hash. **Volume:** one row per agent/window/device (Phase 1 ships
counts, not per-tree), so this is small; still add a **retention policy** (mirror the Oracle's
existing hypertable retention) and note the **Supabase 500 MB free cap** (`audit_log` was already
excluded for size) and that migrations run through the **timescale shim**
(`deploy/render/supabase_timescale_shim.sql`).

## Coverage, extended

`db::agent_anchoring_coverage` gains, per agent/window (pure aggregate, same no-drift discipline as
today — it stays a fold, now also over the matching `shield_observations` rows):

| field | meaning |
|---|---|
| `executions_witnessed` | gate-attributed trees Shield witnessed for this agent (the trusted denominator) |
| `executions_suppressed` | witnessed-and-attributed trees with no gate receipt (the full-bypass count), **or `None`** when no complete witness covers the window |
| `witness_complete` | `false` on a sequence gap / stale heartbeat → flips `coverage_ratio` to `None` rather than reporting a falsely-high ratio |

- When a **trusted, complete** witness covers the window: `coverage_ratio = executions_anchored /
  executions_witnessed`.
- Otherwise: fall back to today's self-reported denominator (`executions_observed`), **clearly
  labelled self-reported** in the response, with `witness_complete = false`.
- `executions_suppressed > 0` adds entries to the existing `findings` list (count-level in Phase 1;
  *named* root-exe/window/confidence findings arrive in Phase 2).
- **Informational only** — not an AIS input, not a `Slasher` trigger (matches `anchoring-coverage`).

## Open item carried from Track B (flagged, not silently dropped)

#201 line 66 **deliberately** kept the new ingest separate rather than unwinding the existing
**observations-as-intents** commitments (Shield's `integrity_exporter` BCC commitments emitted under
Shield's own DID on the intent path). That old path still pollutes the *intent* side of §6.10. #201
chose the clean third-witness ingest over unwinding it; **this remains open** and must be tracked, or
the ecosystem keeps two witness paths. Recommended: a follow-up to retarget those commitments at the
new observation ingest (or explicitly retire them), owned separately from this Oracle work.

## Test plan

- `db::agent_anchoring_coverage` extension: unit-fold tests over synthetic `shield_observations` +
  reconcile rows — witnessed/suppressed/`witness_complete`; **prove each can fail** (mutation-check),
  especially the `None`-on-gap switch and the self-reported-fallback label.
- Ingest: signature/sequence verification, gap → `witness_complete = false`, replay/forgery rejected.
- Oracle DB test is **opt-in**: `INVOCATION_DB_TEST=1` + `TEST_DATABASE_URL` (local PG :5436). Build
  **only** `--test anchoring_coverage_db` with `CARGO_BUILD_JOBS=1` (the full test link memory-thrashes
  ~34 min on the 5 GB box).
- Cross-repo: the Shield-side emitter (counts + on-device suppressed) is a separate `xibalba-shield`
  PR; this scope is the Oracle contract it targets.

## Phase boundary (what is NOT in Phase 1)

- Per-tree records at the Oracle + the `witnessed tree ↔ gate receipt ↔ outcome` join and **named**
  full-bypass findings → **Phase 2**.
- Turning sustained low witnessed coverage into a dispute → **Phase 3** (separate decision).
- The observations-as-intents redirect → tracked above, owned separately.

## Provenance

Grounded by reading `integrity-oracle/backend/src/{routes,handlers,db}.rs`,
`docs/design/{anchoring-coverage,shield-observation-reconciliation}.md`, and `xibalba-shield`
`gate_receipts.py` / `schemas/events.py` (post-#91). Pre-scope adversarial review (advisor +
self-review) caught the vacuous count-level `suppressed` and the stale base checkout; both are
addressed above. Devil's-Advocate engine not entitled (ENGINE_NOT_IN_PLAN) — advisor + self-review
per standing provenance.
