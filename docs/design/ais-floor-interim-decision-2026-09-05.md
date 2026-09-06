# AIS per-component floor: interim decision (2026-09-05)

## Context

`docs/PRODUCTION_READINESS_PLAN.md` Gate 3 (Oracle scoring integrity) names an open item:
"at least an interim component-floor decision made for AIS scoring rather than indefinitely
deferred." `PRODUCTION_GAPS.md` §27's "still open" section describes the actual gap: under the
bare weighted geometric mean, only an *exact* zero on a component annihilates the whole score —
a 90%-violation agent (`penalty_ratio = 0.9`) still reaches `r ≈ 0.631`, not the near-zero result
the metric's own incentive design wants. `spec/integrity-protocol-v3.2.md` §3.1.1 eq. 4a proposes
a per-component floor + conjunctive Θ gate to close this: if any floored component (entropy,
grounding, compliance — sacrifice is deliberately unfloored, "contribution is optional") falls
below its floor, the gate fails regardless of the geometric mean's own result.

This gate is **already built and running**, but shadow-only:
`integrity-oracle/scoring-core/src/lib.rs`'s `AisEngine::score` computes `gate_entropy_pass`,
`gate_grounding_pass`, `gate_compliance_pass`, and their conjunction `gate_would_pass` on every
scoring call, using `AisFloors::default()`'s provisional thresholds (entropy 100, grounding 200,
compliance 400). These fields are reported in `AisBreakdown` for observation only — they do not
affect `ais` or `constraint_score`, are not wired into chain pushes, and cannot raise a
`Slasher.raiseDispute`.

## Why this has stayed shadow-only, and why flipping it live today would be premature, not merely undecided

Three independent reasons, each sufficient on its own:

1. **The provisional thresholds are circular by the code's own admission.** `AisFloors::default()`'s
   own doc comment states they were "chosen to sit comfortably below every component of the one
   real registered agent's current telemetry... so shadow observation starts without immediately
   flagging the repo's own dogfooding agent, not because they're believed to be the right
   permanent thresholds." Enforcing against a single agent's telemetry, using thresholds tuned to
   that same agent, would prove nothing about whether the floor is calibrated correctly for a real
   population.
2. **There is no real population to calibrate against yet.** As of this decision, this protocol has
   exactly one real registered agent on Base Sepolia (`xibalba.integrity`, per `CLAUDE.md`'s own
   "Live deployment" section and the wiki's cross-repository audit). A floor calibrated on n=1 is
   not a calibrated floor.
3. **Enforcement is consequential and hard to reverse.** `bcc_middleware/app/scoring_loop.py`
   pushes AIS to chain automatically (default every 300s) and can raise a real, on-chain
   `Slasher.raiseDispute` — which locks part of a real agent's stake — off the resulting score.
   Flipping the gate from shadow to enforced is not a reporting change; it is enabling a pipeline
   that can lock real funds based on provisional numbers. `PRODUCTION_GAPS.md` §27 already states
   this needs "a dry-run against the live agent set first, not a direct edit" — this decision
   record is that dry-run's owner and trigger, not a replacement for running it.

None of the three is a reason to defer *indefinitely* — that was the actual gap Gate 3 named.
This document is the fix for that: an explicit, dated, checkable decision with a stated
graduation path, not silence.

## The interim decision

**Keep the conjunctive floor gate in shadow/observation mode.** Do not wire `gate_would_pass`
into chain pushes, dispute-raising, or any other enforcement path until ALL of the following
graduation criteria are met:

1. **Population**: at least `AIS_FLOOR_GRADUATION_MIN_AGENTS` (5, chosen as the smallest number
   at which a single agent's telemetry can no longer single-handedly determine whether the
   floors "look reasonable," not a number derived from any formal statistical power analysis —
   revisit if that's ever done) distinct registered agents have real, chain-pushed AIS history.
2. **Observation window**: at least `AIS_FLOOR_GRADUATION_MIN_SHADOW_DAYS` (30) days of continuous
   shadow `gate_would_pass` telemetry have been collected and are available for review — so a
   human reviewing graduation can see what the floors WOULD have done against real traffic before
   committing to what they DO.
3. **Explicit human sign-off, recorded in this file** (a dated addendum below, not a silent code
   change) — criteria 1 and 2 being met is a necessary precondition to review, never a trigger
   for an automatic flip. Enabling enforcement is a real, hard-to-reverse, chain-affecting action
   (see reason 3 above) and must never happen without a human deciding it, the same standing
   discipline this whole session has applied to every other consequential action.

## Making the deferral checkable, not just documented

Silence is what made the previous state of this gap indistinguishable from "nobody is tracking
it." `scripts/check_ais_floor_graduation.py` (new, stdlib-only, zero dependency on this
package — same convention as `xibalba-cortex`'s `scripts/verify_provenance_export.py`) queries a
running oracle's real `GET /v1/agents` and reports whether criterion 1 (population) is currently
met, so a future session or operator can answer "are we even close to graduation" with one
command instead of re-deriving this whole document from memory. It does **not** check criterion 2
(the oracle does not currently expose a "how long has shadow telemetry been collected" endpoint) —
recorded here as a real, disclosed gap in the checker itself, not silently assumed satisfied.

## What this does NOT do

- Does not change `AisFloors::default()`'s provisional values — recalibrating them is exactly the
  work graduation criterion 2's review is for, not something to guess at now.
- Does not touch `bcc_middleware/app/scoring_loop.py`, chain-push logic, or dispute-raising in any
  way. Zero behavior change for any currently-registered agent.
- Does not set a calendar deadline. A population/observation-window criterion that hasn't been met
  is not "late" — the previous problem was that there was no criterion to be early or late
  against at all, not that a deadline was missed.

## Addenda (append, do not edit above)

None yet. The first addendum here should record: the graduation-check output at the time of
review, the final chosen permanent floor values (which may differ from `AisFloors::default()`'s
provisional ones), and who/what session made the enforcement decision.
