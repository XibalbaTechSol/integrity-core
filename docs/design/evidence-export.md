# Design Scope — Compliance Evidence Export

**Roadmap:** `docs/ENTERPRISE_ADOPTION.md` Lever 4. **Status:** Phase A ✅ shipped (decision→leaf→
anchor linkage via the JOIN design); Phases B (control mapping) and C (export endpoint + report)
🔨 not built. Decisions locked: **join** (not back-fill), **multi-framework** control map,
**oracle-signed** report.

**2026-08-13 — competitive reprioritization flag:** Semantica (a direct competitor sharing the
same compliance-buyer persona) already ships a PROV-O-shaped fact-provenance export with no
cryptographic backing. `xibalba-cortex/docs/plans/2026-08-13-semantica-parity.md` scopes a
stronger, tamper-evident fact-provenance export there; this document's Phase C (action-lineage
export) is the complementary half of the same competitive answer and is recommended for
reprioritization alongside it. See that plan's "Cross-reference" section.

> **Phase A shipped:** ALLOW rows carry `metadata.leaf` (`bcc_middleware/app/main.py`); anchored
> sub-trees are reported to `POST /v1/audit/anchor` → `anchor_events` table (oracle migration
> 0007); `/v1/audit-log` LEFT JOINs them onto each decision (`anchor_root`/`anchor_tx_hash`/
> `anchored_at` on `AuditLogEntryDto`). Tests: `bcc_middleware/tests/test_evidence_linkage.py`
> (incl. the batch-filling-leaf case the back-fill would have missed). The live-DB JOIN is
> exercised only in the opt-in oracle e2e suite.

## Goal

Turn the real, existing audit trail into an **auditor-ready, control-mapped, verifiable evidence
report** for a date range — the artifact a compliance officer hands an auditor to prove "every
agent action was policy-checked, and here's cryptographic proof it wasn't tampered with after the
fact." This is the enterprise buying trigger (Lever 6 / Integrity Health wedge), built on primitives that
already exist rather than new crypto.

**Non-goal (v1):** making the audit-log DB row itself tamper-proof. The code already documents
(`PRODUCTION_GAPS.md`) that in the single-operator topology a forged `audit_log` row is possible.
The verifiable strength of the report comes from the **on-chain Merkle anchor**, not the DB — see
"Chain of custody" below. The report must state this honestly, not overclaim.

## What already exists (reuse, don't rebuild)

- **Durable decision trail:** `bcc_middleware/app/audit.py::report_decision` → oracle
  `POST /v1/audit/ingest` (`handlers.rs::ingest_audit_log`) → `audit_log` table →
  `GET /v1/audit-log` (`AuditLogEntryDto`) → `AuditLogsPanel.tsx`. Every allow / deny /
  shadow_deny is already recorded with `agent_id, source, event_type, decision, reason_code,
  detail, intent_type, created_at`.
- **A `metadata` JSONB column** on `audit_log` (`AuditLogIngestRequest.metadata`, defaults `{}`),
  currently unused by the middleware — the storage slot for anchor linkage, **no migration
  needed**.
- **Merkle batching + on-chain anchoring:** `app/merkle.py` computes leaves
  (`keccak256(abi.encodePacked(agent_id, intent_type, intended_state_hash, nonce, timestamp))`);
  `app/anchor.py::anchor_batch_per_agent` submits each agent's sub-root to its own `StateAnchor`
  clone and returns `{root, tx_hash}` per agent. `contracts` `StateAnchor.verifyLeaf(leaf,
  root, proof)` verifies membership on-chain.
- **Per-decision approval proof:** `verification_token` (`app/verification_token.py`) + the
  `POST /v1/bcc/verify_token` endpoint already prove *this middleware* approved a specific
  `(agent_id, nonce, intended_state_hash)`.

## The gap to close

1. **Decision → leaf → anchor linkage is not persisted.** At intercept time the middleware knows
   the leaf and `batch_index` but reports neither into `audit_log.metadata`. And the anchor tx
   only exists *later*, when the batch flushes. So today a decision row can't be tied to its
   on-chain proof.
2. **No control mapping.** Decisions carry `reason_code` / `intent_type`, not formal control IDs
   (HIPAA §164.312, SOC 2 CC6.1, …). Control IDs are Lever 3 (compliance packs); until those
   exist, v1 maps via a static `reason_code/intent_type → control` table.
3. **No export endpoint or renderer.** No "give me a signed report for agent X, Jan–Mar" surface.

## Chain of custody (what makes the report "verifiable")

```
BCCCommitment ──run_intercept ALLOW──▶ audit_log row (decision, reason_code, control)
      │                                        │ metadata.leaf, metadata.batch_index
      └── keccak leaf ──▶ Merkle batch ──▶ StateAnchor.anchorRoot(root)  [on-chain tx]
                                                 │
   report reader independently recomputes leaf from the row's commitment fields,
   then calls StateAnchor.verifyLeaf(leaf, anchoredRoot, proof) ── PASS = the decision
   existed at anchor time and hasn't been altered since.
```

The DB is a convenience index; the on-chain `verifyLeaf` is the trust anchor.

## Proposed implementation (phased)

### Phase A — persist the linkage (`bcc_middleware`)
- `report_decision(...)` gains a `metadata` param; on the ALLOW path, pass
  `{leaf, batch_index, verification_token}`. Thread `metadata` through
  `_report_decision_background`. (`app/audit.py`, `app/main.py`.)
- When a batch anchors (`_flush_and_anchor` / `anchor_batch_per_agent`), record the resulting
  `{root, tx_hash, leaf_index}` per leaf so a decision can be joined to its anchor. Simplest v1:
  a new best-effort oracle call `POST /v1/audit/anchor` that back-fills `audit_log.metadata`
  for the rows whose leaves were in that batch (best-effort, same non-gating posture as
  anchoring itself). Alternative: export-time join by leaf. **Open question — pick one.**

### Phase B — control mapping (`integrity-oracle` or a shared table)
- A versioned `reason_code/intent_type → {framework, control_id, control_title}` map. v1 static
  (checked-in JSON); later sourced from the Lever 3 compliance packs so it's authoritative.

### Phase C — export endpoint + report (`integrity-oracle` + `integrity-dashboard`)
- `GET /v1/evidence?agent_id=&from=&to=&framework=` → structured JSON: each decision with its
  control, its leaf, and (if anchored) `{root, tx_hash, anchored_at}` + verify instructions;
  plus a summary (counts by control, % anchored, would-be-blocks if shadow).
- Sign the report payload (oracle signer) so the export file itself is attributable.
- Dashboard: an "Export evidence" action on `HealthPage` / diagnostics that downloads JSON now,
  PDF later. Reuse `AuditLogsPanel`'s existing query plumbing.

## Files to touch
- `bcc_middleware/app/audit.py`, `app/main.py` (Phase A) — plus tests in
  `tests/test_audit*.py` / a new `tests/test_evidence_linkage.py`.
- `integrity-oracle/backend/src/handlers.rs`, `db.rs`, `openapi.rs` (Phase B/C) — plus backend
  tests; keep `spec/ais-api/v1/openapi.yaml` in sync.
- `integrity-dashboard/src/services/oracle.ts` (+ DTO), a new `EvidenceExport` component, wired into
  `HealthPage`.

## Test plan (real, no mocks)
- Middleware: an ALLOW decision persists `metadata.leaf` matching a recomputed keccak leaf; after
  a forced flush, the row carries the real anchor `tx_hash`/`root`.
- End-to-end: recompute a leaf from an exported row's fields and assert
  `StateAnchor.verifyLeaf` returns true against the anchored root (against the anvil fixture
  chain, mirroring `tests/test_anchor_per_agent.py`).
- Oracle: `/v1/evidence` returns the expected control mapping + anchor linkage for a seeded agent.

## Open questions for sign-off
1. **Anchor back-fill vs. export-time join** for decision→tx linkage (Phase A) — back-fill is
   simpler to query and render; join avoids a second write path. Lean back-fill.
2. **v1 control map scope** — ship HIPAA-only (Integrity Health wedge) first, or a thin multi-framework
   stub? Lean HIPAA-only, real and deep.
3. **Report signing** — oracle signer is fine for v1; revisit when key-separation lands (Lever 5).
