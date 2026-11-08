# Anchoring coverage: are agents actually anchoring intent?

**Status:** built (Oracle endpoint + aggregate). The per-invocation matching it builds on
(`db::reconcile_agent_intent_outcome`, `GET /v1/agent/{id}/reconciliation`) predates this.

## The question this answers

The whole point of the BCC gate is that an agent **declares a signed intent before it acts**
(`docs/INTERFACE_CONTRACT.md` §4.2: `invocation_id`, `intended_state_hash`, signature). But a gate
only proves intent for the calls that go *through* it. An agent's own process can skip the SDK-side
commitment (the contract names this exact risk in §6.10). So "we have a gate" is not the same as
"agents are anchoring their intent." The second is a measurement, and this is it:

> Of the actions an agent **actually executed** (outcomes the system observed), what fraction carried
> a **prior signed intent** that reconciled to them?

An execution with no matching prior intent is not a number buried in a table — it is a **finding**:
the agent did something it never declared.

## Where it sits (before/after the action)

`docs/INTERFACE_CONTRACT.md` §6.10 splits the Oracle trust domain by before/after the action:
`bcc_middleware` is the BEFORE half (the signed intent), `integrity-oracle` is the AFTER half
(outcomes, telemetry). Anchoring coverage is an Oracle (after) read that reconciles the two: it needs
both the intent side (BCC's signed ALLOW rows in `audit_log`) and the outcome side (`posttool_effect`
rows and `claude_tool_result` spans), both keyed by `invocation_id`.

## What it computes

`GET /v1/agent/{id}/anchoring-coverage` → `db::agent_anchoring_coverage`, aggregating the most recent
500 reconciliation rows (reported back as `considered`, so the ratio is never mistaken for all-time):

| field | meaning |
|---|---|
| `executions_observed` | actions actually executed and reported (an outcome side is present) |
| `executions_anchored` | observed executions with a matching prior signed intent (`reconciled`) |
| `executions_unanchored` | observed executions with **no** prior intent (`outcome_without_intent`) |
| `executions_conflicted` | observed executions whose intent hash disagreed (`correlation_conflict`) |
| `intents_without_outcome` | authorized intents that never produced an outcome — surfaced, **not** counted against coverage (the action may simply not have run) |
| `coverage_ratio` | `executions_anchored / executions_observed`; `None` when nothing was observed (never silently 0) |
| `findings` | the unanchored and conflicted executions themselves (capped at 50) — the actions that ran without a clean prior signed intent |

The matching logic lives in exactly one place (`reconcile_agent_intent_outcome`); this is a pure
aggregate over its rows, so the two cannot drift.

## What it does and does not prove

- **Does:** make visible, as one number per agent, the bypass gap §6.10 warns about. A coverage below
  1.0 means executions happened that no signed intent reconciled to — each is named in `findings`.
- **Does not:** prove the *honesty* of an intent (a signed intent is the agent's own claim; it proves
  the claim was made, unmodified and fresh, not that it was truthful), and does not prove coverage of
  actions the Oracle never observed at all. An agent host compromised enough to skip the gate can also
  suppress the outcome report; closing that is **Shield's** job (an OS-level sensor the agent does not
  control sees the execution regardless), and reconciling Shield's observations here is the next step.
- **Informational only**, like `anchor_coverage.rs`'s on-chain signal: it is not an AIS input and not a
  `Slasher` trigger. Turning a sustained low coverage into a dispute is a separate, later decision.

## Relation to the other two steps

This is step 3 of the "remove failure points while keeping agents anchoring intent" work
(owner, 2026-11-06). Step 1 (`feat/bcc-tier-cache`, PR #193) took the Oracle off the synchronous
gate path; step 2 (`feat/wasm-policy-engine`, PR #197) put the policy engine in-process so the gate
has no OPA daemon to fail. Those make the gate *reliable*; this step makes its *coverage measurable*.
