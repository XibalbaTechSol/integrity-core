# Auditing the Xibalba session loop against itself

**Date:** 2026-07-30
**Agent:** `did:integrity:68fed133…a861` (xibalba), verification tier 1
**Method:** end-to-end execution of the live harness, not code review
**Reproduce:** `~/.claude/xibalba/tests/probe_loop.py` (read-only; writes a diffable report)

---

## Why this was done

The dogfooding mandate says the development of Integrity Protocol *is* its primary
test — that every session must pipe its tokens, traces, tool decisions and BCC
commitments into the oracle, and that where the protocol cannot yet capture
something about its own construction, **that gap is a finding to record rather
than route around**.

The harness implementing that (`~/.claude/xibalba/`, three hooks wired through
`~/.claude/settings.json`) had been running for days and had never been
deliberately tested. This audit ran it start to finish and measured what came out.

The one-line result: **the loop was structurally sound and evidentially empty.**
It signed and transported things correctly; the things it signed said almost
nothing about what the agent had done. The agent's own trust score was `0.0`.

---

## The loop as it actually runs

```
SessionStart   session_start.py   bridge Hermes Ed25519 key → did:integrity
                                  inject SOUL.md + MEMORY.md + USER.md
                                  GET /v1/agent/{did}          (registration precondition)
                                  log_telemetry{claude_session_start} → :8080
                                  OTel span → :4317

PreToolUse     pretool_gate.py    matcher: Bash|Write|Edit|MultiEdit|NotebookEdit
                                  build_bcc_commitment(intent_type, sha256(payload))
                                  POST :8000/v1/bcc/intercept
                                  gauntlet: sig → nonce → freshness → OPA → BAA
                                  authorized → exit 0 (normal permissions still apply)
                                  denied     → permissionDecision:"deny"
                                  unreachable→ allow unchecked + log

PostToolUse    posttool_report.py [ADDED BY THIS AUDIT]
                                  outcome + result size + the SAME intended_state_hash
                                  + token_usage + text_output

SessionEnd     session_stop.py    log_telemetry{claude_session_end} + work evidence
                                  OTel span
                                  _anchor_session_vault → Base Sepolia
                                  gate accounting summary
```

Two other runtimes report to the **same DID**: Hermes (via the
`integrity_telemetry` plugin) and agy. That turns out to matter a great deal.

---

## Findings

Ordered by severity. Every one is a measurement.

### F1 — The BCC gate could not deny anything. *(critical, fixed)*

Across 792 logged decisions: **715 authorized, 0 denied, 77 fail-open.** A 0%
deny rate over that many samples is not luck.

Every rule in `policies/bcc.rego` keys on `intent_type`. The hook emitted the
**constant** label `claude_tool:<ToolName>`, hashing the real command into
`intended_state_hash` per §4.2 (so plaintext — and, in the Shield vertical, PHI —
never leaves the agent). A constant matches no rule, so `violation` was always
`[]` and `allow` always `true`.

The discriminating probe, which is what makes this a finding rather than a guess:

| `intent_type` | `allow` | `violation` |
|---|---|---|
| `claude_tool:Bash` | `true` | `[]` |
| `claude_tool:Bash` *(destructive payload)* | `true` | `[]` |
| `claude_tool_bypass` | `false` | `POLICY_VIOLATION … matches 'bypass'` |
| `EMR_WRITE` | `false` | `HIPAA_ACCESS_CONTROL_VIOLATION` |

**The policy engine was healthy the entire time.** It was simply unreachable. The
gate was performing identity + replay + freshness verification — real, and worth
having — while logging the word *"authorized"*, which reads as a behavioral
endorsement it had never made.

**Fixed** by appending a coarse risk class derived from the payload
(`claude_tool:Bash:destructive`), with the payload still crossing the wire only
as a hash. New `bcc.rego` §3b gates `destructive`/`credential`/`chain_write`/
`privileged` on `verification_tier >= 1`. OPA tests 28 → 35.

> **Scope, stated honestly:** the classifier is a lossy one-way *signal*,
> trivially evadable by an adversarial agent (base64, indirection, aliasing). It
> is **not a sandbox** and must never be described as one — an agent that wants to
> evade its own commitment layer has already defeated a pre-execution gate by
> definition. What it buys is a policy surface that is no longer structurally
> blind, plus a signed assertion that can be reconciled against what PostToolUse
> reports actually happened.

### F2 — The agent's AIS was pinned at exactly 0.0. *(critical, fixed)*

```
ais: 0.0
components: {entropy: 1000, grounding: 1000, sacrifice: 0.0, compliance: 1000}
```

`scoring-core` computes a weighted **geometric** mean, so `0^0.2 = 0` annihilates
the product no matter how perfect the other three axes are.

`sacrifice` derives from `metadata.token_usage.total_tokens`. The hooks emitted
`{"event": "...", "source": "claude-code"}` — no tokens, no text.

**The protocol scored its own construction at zero because the harness never
reported the work it did.** That is the dogfooding mandate producing exactly the
kind of finding it exists to produce.

**Fixed.** `_common.work_metadata()` now reads real `token_usage` and
`text_output` from the session transcript. Measured before → after:

| | before | after |
|---|---|---|
| `ais` | **0.0** | **600.0** *(tier-1 ceiling; raw ≈770)* |
| `entropy` | 1000 *(default)* | 528.86 *(real Shannon)* |
| `grounding` | 1000 *(default)* | 964.66 |
| `sacrifice` | **0.0** | **742.64** |
| `compliance` | 1000 | 1000 |
| `event_count` | 16 | 58 |

The components are now *measurements* that move with the work, rather than
constants. `entropy` in particular fell from a defaulted 1000 to a real ~529,
which is the point: the harness had been reporting a perfect score for an axis it
had never measured.

Two decisions worth surfacing rather than burying:

- **`cache_read_input_tokens` is excluded** from the total. It counts context
  re-read every turn (~200k/turn), so summing it would report tens of millions of
  tokens for an afternoon's work and saturate the curve (50k tokens = 1 proxy
  hour, saturating near 1000).
- **A double-count hazard found while implementing.** `derive_sacrifice` *sums*
  `total_tokens` across batch entries, and a per-tool-call hook reading the whole
  transcript reports a monotonically growing cumulative figure — it would have the
  oracle add ~1M, then ~1.05M, … for the same work. This is precisely the failure
  `derive.rs`'s own comment warns about. A per-session cursor now reports deltas;
  if the cursor can't be persisted, `token_usage` is omitted entirely rather than
  risk double-counting.

### F3 — Three of four AIS axes were fabricated by default. *(high, fixed)*

The signed SessionStart envelope carried
`derived_signals: {compliance: 1.0, entropy: 1.0, grounding: 1.0, sacrifice: 0.0}`.
With no `text_output` there is nothing to compute entropy or grounding over, and
`lexical_stability_score` returns a perfect `1.0` for empty text *by design*.

So a **perfect score was being derived from no evidence, inside a signed
envelope.** That is the exact failure class the no-silent-mocks rule exists to
prevent — the signature proves *who* sent it, never *whether the numbers mean
anything*. Both adapters now send real text or omit the key; `work_metadata`
omits rather than defaults, so an absent signal stays absent all the way through.

### F4 — Vault anchoring silently stopped, and honest logging didn't catch it. *(high, FIXED)*

10 commit leaves exist. `anchors.jsonl` records one anchor at `leaves_through: 1`.
**Nine leaves pending since 08:42Z.**

More telling: `session.log` contains exactly **one** `vault:` line in its entire
history, though `session_stop.py` logs on *every* branch — success, nothing-pending,
missing primitives, missing password, exception. The 14:01Z session-end logged its
telemetry lines and then nothing at all.

Reading the vault is not the bottleneck (`session_root()` measured at **0.035s**).
The hook is being killed before or during the chain write, producing no record.
**The honest-logging design was defeated by a path that produces no log line at
all.** 

**Fixed**, and the first hypothesis was wrong in an instructive way. I assumed a
timeout on the chain write. Measured: anchoring all 11 backlogged leaves took
**3.3s**. The hook dies *between* the telemetry flush and the anchor call, not
during it. The write now runs in a detached process (`anchor_vault.py`,
`start_new_session=True`) spawned from **both** session end and session start —
the latter is what finally makes the retry the old code documented but could
never reach, since the later session died at the same step and a backlog once
formed only ever grew. SessionEnd now returns in **0.5s**; there is nothing left
to kill. Backlog drained: 11 leaves anchored, tx `b189215d…`. Vault census now
reads **13 leaves, anchored through 13, 0 pending**.

### F5 — All anchored evidence is empty. *(medium, open)*

Every leaf carries `test_result_hash: "unverified"` (4) or `"unverified:stale"` (6).
Memory is being committed; what it commits attests to nothing.

### F6 — Doc drift on the formula, in the files agents read. *(medium, fixed)*

`scoring-core/src/lib.rs`'s header quoted the interface contract "verbatim" and
stated the **arithmetic** sum. Root `CLAUDE.md` did the same. The normative
`docs/INTERFACE_CONTRACT.md` §4.3 has the **geometric** form, which is what the
code does.

`CLAUDE.md` is loaded into every agent session — so every session was reasoning
about AIS with a model that would not predict F2's zero-annihilation behavior.
Both corrected, and both now state the *consequence*, not just the formula.

### F7 — The AIS formula had no test pinning its shape. *(medium, fixed)*

Demonstrated, not surmised: patching a scratch copy of `scoring-core` from a
geometric to an arithmetic mean left **all 9 tests passing**. Every existing case
sat either at a corner where the two formulas agree (all components equal → both
reduce to the same value) or above a tier ceiling that clipped the difference away.

The single most load-bearing number in the protocol had no test fixing its form.
Two new tests close this — one asserting the geometric result on deliberately
unequal components (≈653.5 geometric vs 680.0 arithmetic), one pinning the
single-zero annihilation property. **Both fail under the swap.** Suite 9 → 11.

### F8 — Three runtimes, one DID, three incompatible partial loops. *(critical, architectural — largely closed)*

| Runtime | Lifecycle | Pre-exec gate | Per-action telemetry | Anchors memory |
|---|---|---|---|---|
| Claude Code | yes | **yes** | yes *(added here)* | yes |
| Hermes | yes | **no** | yes | no |
| agy | start only | no | no | no |

Between them every part exists; **in no single runtime do they compose.** Claude
Code committed to intents whose outcomes it never reported; Hermes reports
outcomes it never committed to. All three flush to one umbrella DID, so
`event_count` was a blend of three incomparable instrumentation levels — any
conclusion drawn from it was uninterpretable.

`identity.report_action()` now makes `runtime` a mandatory, always-recorded
discriminator, and **Hermes tool calls are now gated** (`hermes_gate.py`, a
`pre_tool_call` shell hook). The policy logic is deliberately *not* duplicated —
`pretool_gate.evaluate_tool_intent()` is the single implementation and the Hermes
file is a wire adapter — because per-runtime duplication is exactly how the two
diverged. Labels are namespaced (`hermes_tool:` / `claude_tool:`), `bcc.rego`
matches the risk class positionally so both reach one ruleset, and `tool_runtime`
is surfaced for audit.

> **A bug review would not have caught.** The risk classifier keyed on
> `tool_name == "Bash"`, so every Hermes `terminal` command classified as
> risk-free *even when destructive* — the gate would have been installed and
> still blind. Extraction is now keyed on the input **field**
> (`command`/`path`/`content`…), which has no blind spot across tool
> vocabularies. Found by running it, not reading it.

Still open: the oracle does not yet *group* AIS by `runtime`, so the
discriminator is recorded but not yet used.

### F9 — The Hermes adapter discarded the payload the oracle scores on. *(high, fixed)*

`on_post_llm` had the full response text in hand and sent `response_chars:
len(resp)` — a length. Now sends `text_output`, capped to match the Claude side so
both runtimes' scores stay comparable.

**Open, upstream:** Hermes' `post_llm_call` passes no token usage at all
(`agent/turn_finalizer.py` forwards only ids, messages, model, platform), so
`sacrifice` is still absent for Hermes work. Deliberately **not** estimated from
character count — a fabricated measurement is worse than an absent one, and
`sacrifice` is a multiplicative factor in a geometric mean.

### F10 — Deployed images were stale relative to source. *(high, oracle fixed)*

Two independent instances of the same class, both found by running the system
rather than reading it:

- **Oracle — FIXED.** The `/ais` endpoint returned **839.41** for a tier-1 agent
  whose ceiling is **600**. The handler *does* call `score_with_tier`. Cause: the
  image was built at **03:18:46**; the ceiling commit (`1c6b4d8`) landed at
  **03:22:18** — 3.5 minutes later. The Verification Ladder was documented,
  tested, committed, and **not running**. Rebuilding and redeploying `oracle-backend`
  closed it: AIS now reports exactly **600.0** (raw geometric ≈770, clipped to the
  tier-1 ceiling). Both "new" AIS formulas — the weighted geometric mean *and* the
  Verification Ladder ceiling — are live only as of this audit.
- **Dashboard — OPEN.** The container builds as `integrity-mvp@0.0.0` / Vite 8.1.4
  while the source tree is `integrity-dashboard@0.0.0` / Vite 8.0.16.

A security-relevant control that exists in source and not in the running system is
worse than one that doesn't exist, because the tests pass and the docs are true.
**Nothing in the repo detects this.** Every other finding in this document was
measured against a system that might not have been the one in the tree — which is
why "what makes a build the deployed build?" is listed as an open architectural
question rather than a chore.

### F11 — The dashboard was down from two unrelated faults. *(fixed)*

1. `CoreFeatures.tsx` opened a `<motion.div>` and closed it with `</div>`; Vite
   returned **503** for that module and the render died.
2. The actual outage: **two Vite servers competing for `:5173`.** A stale host
   process running since Jul 29 held `127.0.0.1:5173` and shadowed the container.
   Because it predated `public/XibalbaSolutionsLogo.png`, it served the SPA
   fallback — `index.html` **with HTTP 200** — for every logo request. The browser
   got HTML where a PNG belonged and rendered alt text.

`make up` and the host dev server are **not** interchangeable, and running both
silently produces this.

---

## Ratified, not fixed: the gate is deliberately fail-open

`bcc_middleware`'s gauntlet is fail-**closed** at steps 5–6: no positive
confirmation, no authorization. The PreToolUse hook takes the opposite posture —
middleware unreachable means the tool proceeds, logged as "allowed unchecked".

The two differ on purpose. The middleware guards production actions where a missed
denial is a compliance failure. The hook sits in a developer shell where bricking
every Bash call on a container restart gets the hook set disabled wholesale —
trading a partial guarantee for none. **Operator-confirmed during this audit.**

The mitigation is accounting, not enforcement. The real risk was never the
individual unchecked call; it was the **77** that accumulated unnoticed inside an
800-line log nobody re-reads. `session_stop.py` now logs a lifetime fail-open ratio.

---

## Open architectural questions

These are the choices to iterate on. Each is a genuine fork, not an oversight.

1. **Should the gate ever see payloads?** The hash-only commitment exists so PHI
   never leaves the agent. Behavioral policy needs *something* meaningful. The
   risk-class label is one answer; a post-execution reconciliation call
   (`bcc.rego` §4) is another. They compose rather than compete — and now that
   PostToolUse reports the same `intended_state_hash` the gate committed to, the
   second is actually buildable.

2. **Should Hermes tool calls be gated?** Today a whole runtime executes ungated
   under a verifiable-behavior identity. This is the biggest hole.

3. **Is `sacrifice` the right axis to carry token counts?** It is documented as a
   *proxy*, yet the geometric mean makes it a kill switch for the entire score. A
   deliberately-proxied axis zeroing a real score may be the wrong design.

4. **Should an absent signal be 0, 1.0, or "not scoreable"?** F2 and F3 are two
   faces of this. An agent that never *reports* an axis and one that
   catastrophically failed it are currently indistinguishable. "Not scoreable" is
   arguably the honest third value; the protocol has no representation for it.

5. **What makes a build the deployed build?** F10 is not a coding error — it is the
   absence of a rule that source and running system must agree. Everything else
   here is measured against a system that may not be the one in the repo.
   *(`make check-deploy` now detects this; the policy question of whether a stale
   deploy should be a hard failure in CI remains open.)*

6. **Is reputation winnable?** The tier ceiling is now *binding*: raw AIS is 704
   and the tier-1 cap is 600, so further good behavior cannot move the reported
   score at all. The agent is limited by **identity tier, not conduct**, and per
   `identity-ceiling.md` tier 2 has no built verification path — so 600 is this
   agent's permanent maximum today. A reputation system whose score saturates on
   an unimplemented attestation step is measuring the wrong thing. This was
   invisible while AIS was 0.0 and only became visible once the loop reported
   real work.

---

## Recommended next actions

| Priority | Action | Why |
|---|---|---|
| ~~1~~ | ~~Build-staleness check~~ | **DONE** — `make check-deploy`; found 3 stale images on first run |
| ~~2~~ | ~~Move vault anchoring off the critical path~~ | **DONE** — detached `anchor_vault.py`; 0 pending |
| ~~3~~ | ~~Gate Hermes tool calls~~ | **DONE** — `hermes_gate.py`, shared policy path |
| 1 | Populate `test_result_hash` from real test runs | F5 — all 13 anchored leaves still attest to nothing |
| 2 | Have the oracle group AIS by `runtime` | F8 — the discriminator is recorded but unused |
| 3 | Decide the absent-vs-zero question and represent it | F2/F3 — needs a protocol change, not a patch |
| 4 | Build a tier-2 verification path | The ceiling is now *binding* — see below |

---

## Verification performed

| Check | Result |
|---|---|
| `opa test policies/` | **35 passed** (was 28) |
| `bcc_middleware` pytest | **99 passed** |
| `cargo test --workspace --lib` | **89 passed** (78 backend + 11 scoring-core, was 9) |
| Formula guards fail under arithmetic swap | **confirmed** — 2 fail, 9 pass |
| Token delta prevents double-count | **confirmed** — call 1 reports, calls 2–3 omit |
| Intent classifier | 8/8 cases correct |
| Live hook replay (Pre + Post) | both exit 0, telemetry flushed |
| Live AIS | **0.0 → 600.0** (tier ceiling now enforced; raw 704) |
| Vault backlog | **11 pending → 0**, anchored through leaf 13 |
| SessionEnd hook duration | blocking → **0.5s** |
| Hermes gate installed + classifying | **confirmed** live |
| `make check-deploy` | **all images fresh**; parser self-test 10/10 |
| Tier ceiling live after oracle rebuild | **confirmed** — 839.41 → 600.0 |
| Gate denies classified intents | **confirmed** — 3 of 7 `claude_tool:*` cases denied |
| Dashboard | renders, no console errors |
