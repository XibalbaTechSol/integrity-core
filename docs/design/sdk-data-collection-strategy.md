# integrity-sdk — architecture review and data-collection strategy

The SDK is the protocol's data boundary: every AIS score, every dispute, and every
compliance claim is downstream of what it captures and how faithfully it delivers it.
Reviewed 2026-07-29 against the current tree.

Goal set for this work: **capture all agent token usage and OTel data by default, collect
generously during development, and restrict later** — which means the collection surface
must widen while the *delivery* path gets strictly more reliable, because volume turns
today's soft failures into data loss.

---

## Part 1 — What is already right

Worth stating, because the fixes below should not disturb it:

- **Signed, replay-protected envelopes.** Ed25519 over canonical JSON, with the telemetry
  nonce kept in a separate space from the BCC nonce (`client.py`) — conflating them would
  let a spent BCC nonce block an unrelated flush.
- **The oracle re-derives signals server-side.** Client-supplied `derived_signals` are audit
  trail, not score input. This is the single most important property in the design: the SDK
  cannot inflate its own score by lying.
- **OTel GenAI semantic conventions** (`telemetry/conventions.py`) — `gen_ai.system`,
  `gen_ai.request.model`, `gen_ai.usage.input_tokens`, etc. Standard names mean standard
  tooling works, and it is the right base to extend.
- **Nonce 409 handling** re-syncs from the oracle rather than looping forever
  (`client.py:361`) — a real bug that was already found and fixed properly.

---

## Part 2 — Flaws and gaps

### F1. Token accounting double-counts (correctness bug, inflates a live score)

`telemetry/derive.py:149-153`:

```python
total_tokens += int(usage.get("total_tokens", 0) or 0)
total_tokens += int(usage.get("prompt_tokens", 0) or 0)
total_tokens += int(usage.get("completion_tokens", 0) or 0)
```

For any OpenAI-shaped payload, `total_tokens == prompt_tokens + completion_tokens`, so a
standard entry is counted **twice**. `sacrifice` is `min(log10(hours+1)/3, 1)·1000` over
these tokens, so this systematically inflates a live AIS component.

**Cross-check performed — the oracle has the identical bug.** `backend/src/derive.rs:155`
sums the same three keys in the same way. Because the oracle is the *sole authority* on AIS
(the client's numbers are audit trail only), this is not a client-side annoyance: it is a
defect in the authoritative scoring path, and because both sides are wrong in the same
direction, reconciliation cannot surface it.

**Confirmed live, not theoretical.** `integrations/langchain_callback.py:112` forwards
LangChain's `llm_output["token_usage"]` verbatim, which for OpenAI models carries all three
keys — so every LangChain agent's `sacrifice` input is inflated 2×.

**Second, opposite defect on the same signal.** `integrations/openai_integrity.py:127-128`
records tokens as *span attributes* (`GenAIAttributes.INPUT_TOKENS`/`OUTPUT_TOKENS`), while
`derive` reads `metadata["input_tokens"]`/`["output_tokens"]`. A direct-OpenAI agent may
therefore contribute **zero** tokens to sacrifice. Two integrations, two different wrong
answers for the same signal — which is the real lesson: the token path needs one normalized
representation that every integration populates, and conformance tests per provider.

**Why the tests missed it:** `derive.rs`'s cases cover `total_tokens` alone (line 289) and
`prompt`+`completion` alone (line 297) — never the all-three shape that OpenAI actually
emits.

**Fix:** prefer `total_tokens` when present; otherwise sum components. Never both. Apply to
both `derive.py` and `derive.rs` in one change, with a shared conformance vector so they
cannot drift again.

### F2. The queue is unbounded — an oracle outage becomes an OOM

`batcher.py:23-25` appends with no cap. On flush failure `client.py` re-queues the whole
drained batch while new entries keep arriving. There is no maximum size, no drop policy, and
no counter for what was lost. At today's volumes this is survivable; with "collect
everything" it is a memory leak with a network trigger.

**Fix:** bounded queue with an explicit drop policy (drop-oldest preserves recency, which is
what scoring wants), plus a `dropped_count` reported in the next successful flush so loss is
visible rather than silent.

### F3. The time-based flush never fires on its own

`batcher.should_flush()` implements an interval, but nothing calls it except
`log_telemetry` → so the interval only takes effect *when the next event arrives*. There is
**no background thread and no `atexit` hook** anywhere in `client.py` or `batcher.py`.

Consequences:
- An agent that goes quiet never flushes its tail — the most interesting moment (right
  before it stopped) is the most likely to be lost.
- A short-lived process loses everything unless it explicitly calls `flush_telemetry`. This
  is exactly why the Xibalba session hooks must call it manually, and why the OTel exporter
  needed a `force_flush` added by hand.

**Fix:** a daemon flusher thread plus `atexit`/signal handling, both idempotent and
best-effort.

### F4. No schema version in the signed envelope

The signed object is `{agent_id, nonce, otel_spans, derived_signals, zk_proof}` — no
version field. Since the whole point of this work is to widen what is collected, the oracle
needs to distinguish shapes to evolve safely, and old signed payloads must stay verifiable
forever (they are evidence).

**Fix:** add `schema_version` inside the signed object, pinned in
`INTERFACE_CONTRACT.md`, before the collection surface expands.

### F5. No Anthropic/Claude support at all

Zero references to `anthropic` anywhere in the SDK. Coverage is OpenAI, LangChain, and
`antigravity_moe` (a niche internal). The flagship agent — `xibalba.integrity`, running on
Claude — cannot have its tokens captured by any existing integration, which is the direct
blocker on "collect all agent tokens by default."

**Fix:** an Anthropic integration is the highest-value single addition, and it must capture
the Claude-specific token classes (below) that the OpenAI shape has no field for.

### F6. Inconsistent durability inside one payload

On flush failure, telemetry entries are re-queued but `trace_runs` and `custom_metrics` are
deliberately discarded as "observability sugar." That distinction is defensible today; it
stops being defensible when custom metrics carry plan-adherence and tool-outcome data used
for evaluation. One payload should not have two reliability tiers by accident.

### F7. Retry without backoff

The re-queue path retries on the next event with no delay or jitter, so a downed oracle gets
hammered proportionally to agent activity.

### F8. No async path

`requests` is synchronous. Any async agent blocks its event loop on flush. Most modern agent
frameworks are async-first.

### F9. No durable spool

The queue is in-process memory. A crash — the case where post-mortem telemetry matters most
— loses everything unsent.

### F10. Token taxonomy is too shallow to be honest about cost or effort

Only `prompt`/`completion`/`total`/`input`/`output` are recognized. Missing entirely:
**cache-read and cache-creation tokens** (large and cheap on Claude — treating them as
ordinary input misstates both cost and effort), **reasoning tokens** (extended
thinking / o-series), **tool-call tokens**, and any **cost** figure. `sacrifice` claims to
measure costly effort while being blind to the dimensions that dominate real cost.

---

## Part 3 — Collection strategy

Structured as layers so a single **collection profile** can widen or narrow the whole
surface without code changes — this is what makes "collect broadly now, restrict later"
safe rather than a promise.

### L0 — Provenance (always on, cannot be disabled)
Agent DID, session and run IDs, SDK version, schema version, framework and version, model
id and version, host fingerprint, wall-clock and monotonic timestamps. Without this, nothing
else is attributable, and attribution is the protocol's product.

### L1 — Token and cost accounting (default on — the primary ask)
Complete taxonomy per call, not a single number:

```
input_tokens, output_tokens, total_tokens
cache_read_tokens, cache_creation_tokens      # Claude; distinct cost and effort profile
reasoning_tokens                              # extended thinking / o-series
tool_tokens                                   # per tool invocation
billed_cost { amount, currency, rate_source } # explicit, never inferred downstream
model_id, model_version, provider, endpoint_region
```

Rule: **capture provider-reported values verbatim; never synthesize.** If a provider does
not report a field, it is absent — not zero. This is the same discipline the oracle already
applies by re-deriving rather than trusting, and it is what stops F1-class bugs recurring.

### L2 — OTel spans (default on)
Full GenAI conventions plus the agentic shape that makes traces meaningful: nested
`agent_run → llm_call → tool_call → retrieval`, with parent linkage, status codes, error
type and message, latency, retry count, and finish reason. This is already partially
present; the gap is completeness and consistent nesting, not the approach.

### L3 — Content (default on in development, redacted, sampled, kill-switched)
Prompts, completions, tool arguments and results, retrieved documents, system prompts.

**Redaction must be default-on with explicit opt-out — the inverse of today's opt-in
`redact_phi`.** The Shield vertical means content capture can touch PHI, and a
development-time default that quietly persists into a regulated deployment is precisely the
failure this repo's "no silent mocks" rule exists to prevent. Collect generously *and*
redact by default; those are not in tension.

Also needs: per-field size caps, sampling rate, and a single kill switch that disables the
whole layer without touching L0–L2.

### L4 — Behavioral signals
The four AIS inputs, plus the raw evidence each was derived from, so the oracle's
re-derivation can be checked against what the client saw. Also: self-consistency across
retries, refusal and safety-stop events, and plan-vs-execution divergence.

### L5 — Runtime and host
Already partly present (`telemetry/host.py`): storage flux, path entropy, destination-IP
entropy. Add process-level resource usage and, where available, GPU time — `sacrifice`
currently uses a token proxy explicitly because verified GPU hours are unavailable.

### L6 — Agent lifecycle
Session start and end, tool registration, capability changes, controller rotation, BCC
commitments and their outcomes (spec §4.4 says outcomes *should* become vault leaves — that
connects directly to the memory primitive), errors, interrupts, and human interventions.

### The control plane that makes this safe

```
INTEGRITY_COLLECTION_PROFILE = development | standard | regulated
```

- `development` — L0–L6 on, content redacted, generous sampling, large caps.
- `standard` — L0–L2, L4–L6 on; L3 sampled at a low rate.
- `regulated` — L0–L2, L4–L6 on; L3 **off**; redaction non-negotiable.

Plus, at every layer: cardinality caps on tag keys, byte caps per field and per payload,
and a documented default. Restricting later is then a profile change, not a migration.

---

## Part 4 — Suggested order

1. **F1** (token double-count) — a live scoring bug; also cross-check `derive.rs`.
2. **F4** (schema version) — must land *before* the payload shape widens.
3. **F2, F3** (bounded queue, real background flush + `atexit`) — the reliability floor that
   volume will otherwise break.
4. **F5** (Anthropic integration) + **L1** token taxonomy — the primary ask, and the two are
   the same piece of work.
5. **L2/L3** with the profile control plane and redaction-by-default.
6. **F6–F9** (durability tiers, backoff, async, disk spool) as volume rises.

Each step should ship with tests that assert on real captured payloads, not shapes — the
SDK's existing suite (140 tests) is a good base and should grow with the surface.
