---
title: Local Metrology (Client-Side AIS Signal Derivation)
created: 2026-07-09
updated: 2026-07-09
type: concept
tags: [metrics, sdk]
confidence: high
source_files:
  - integrity-sdk/integrity_sdk/telemetry/derive.py
  - integrity-sdk/integrity_sdk/integrations/openai_integrity.py
---

The [Integrity SDK](../entities/integrity-sdk.md) is a **local metrology
apparatus**: rather than shipping raw reasoning content to
[integrity-oracle](../entities/integrity-oracle.md) for scoring, it computes
first-pass [AIS](ais.md) input signals client-side, in
`telemetry/derive.py`, and forwards only the derived numbers (plus a
[redacted](observability-vtl.md) copy of the text, when needed for other
purposes). This page documents what `derive.py` actually computes today —
this supersedes the old wiki's speculative "hardware-tethered offline moat"
and "7 predictive risk indicators v2.1" content, none of which exists in
this rewrite; see the note at the bottom.

**Ownership boundary (load-bearing):** this module produces the AIS
formula's *inputs*, never the score itself. `integrity-oracle`'s
`scoring-core` crate remains the only place the weighted-sum formula
(`concepts/ais.md`) is computed — the oracle may combine these client
signals with its own server-side evidence (e.g. verified GPU-hours, ZK
attestation state) rather than trust them blindly. All four signals are
normalized to `[0.0, 1.0]` with a consistent polarity: **1.0 always means
"best/most trustworthy."**

## `derive_entropy` — real Shannon entropy, not a type-token ratio

`lexical_stability_score(text)` computes real Shannon entropy over the
word-frequency distribution of a completion, normalized by
`log2(unique_word_count)`, then **inverted** (`1 - normalized_entropy`) so
the result reads as "how stable/consistent is this text" — matching
`S_entropy`'s "rewards stability" polarity. This replaced a cruder inline
heuristic (`len(set(words)) / len(words)`) that `openai_integrity.py` used
to compute directly; there is now exactly one definition of entropy in the
SDK. Single-word/empty text returns `1.0` (nothing to compare against, not
penalized as erratic).

## `derive_grounding` — a documented placeholder heuristic

`keyword_grounding_score(text)` is a **deliberately crude keyword
heuristic**, carried over unchanged from the original integration: `0.40`
if the completion contains an ungrounded marker phrase (`"hallucinate"`,
`"not sure"`, `"i don't know"`, `"i'm not certain"`), else `0.95`. Explicitly
documented in the source as a first-pass stand-in, not a substitute for
checking completion claims against retrieved source documents — that would
need integration-specific RAG context this shared function doesn't have.

## `derive_sacrifice` — total tokens, log-scaled

Proxy for `scoring-core`'s "costly, hard-to-fake evidence of real resource
commitment" axis. The SDK cannot independently *verify* compute
contribution client-side (the oracle's own field is named
`gpu_hours_verified`, not `_claimed`) — total tokens actually processed
across a telemetry batch is the closest honestly-observable, hard-to-fake
proxy available at this layer:

```python
min(math.log10(total_tokens + 1) / math.log10(_SACRIFICE_TOKEN_CEILING + 1), 1.0)
# _SACRIFICE_TOKEN_CEILING = 200_000
```

Documented as genuinely weaker than oracle-verified GPU-hours; the oracle's
own ingestion handler decides how much weight to give it.

## `derive_compliance` — self-report, but on-chain wins

Combines a self-reported signal (fraction of batch entries *not* flagged
`policy_violation`/`flagged`) with a **live** on-chain
`ComplianceGate.isHealthcareCompliant` read when chain access is available.
On-chain wins in both directions: a live "not compliant" read overrides a
clean self-report (an agent can't talk its way out of a lapsed BAA) — but a
live "compliant" read still can't push the score above what self-reporting
already earned. A chain-read failure (RPC down, gate not deployed) falls
back to the self-reported signal rather than raising, since this function
computes a scoring *input*, not a security gate — [EHRGate](compliance-gate.md)
remains the real, fail-closed PHI-access enforcement point.

## Where it's consumed

`openai_integrity.py` calls `lexical_stability_score`/`keyword_grounding_score`
directly per-completion (setting `IntegrityAttributes.ENTROPY`/`GROUNDING`
span attributes); `client.py`'s batch flush path calls
`derive_ais_signals(batch, ...)` to populate `POST /v1/telemetry/ingest`'s
`derived_signals` field.

## What this page does NOT claim (correcting the old wiki)

The old wiki's `local-metrology.md`/`sdk-internals.md` described a
`did:xibalba:<hardware_hash>` derived from MAC address/CPU serial/`machine-id`,
an `offline_moat.db` SQLite store with HMAC-row protection, and a v2.1
"Advanced Composite Risk Scoring" layer (reconnaissance risk, compute
substitution detection, cognitive fatigue, lateral movement probability,
etc. — 7 indicators). **None of this exists in `integrity-sdk` today.**
Identity in this rewrite is a software Ed25519 keypair (see [DID](did.md));
hardware-tethered identity is explicitly future roadmap (see
[identity-ceiling](identity-ceiling.md), `[PLANNED]`). Treat the old
figures/formulas for those seven risk indicators as never-built product
ideation, not documentation of current code.

Related: [Telemetry Ingestion Pipeline](telemetry-ingestion.md) (the full
collection→batching→signing→oracle-pipeline writeup this page's formulas
feed into), [AIS](ais.md), [observability & VTL](observability-vtl.md),
[integrity-sdk](../entities/integrity-sdk.md).
