"""
Derives the four Agent Integrity Score input signals (entropy, grounding,
sacrifice, compliance) from a batch of telemetry entries, for the SDK to
attach to a `POST /v1/telemetry/ingest` call (see
docs/INTERFACE_CONTRACT.md's telemetry ingestion section).

Ownership boundary (load-bearing, see scoring-core/src/lib.rs's own module
docstring): this file produces the AIS formula's *inputs*, never the score
itself. integrity-oracle's `scoring-core` crate remains the only place the
weighted-sum formula is computed; every function here is documented as a
first-pass heuristic the SDK can compute client-side, which the oracle may
combine with its own server-side signals (verified GPU-hours, ZK
attestation state) rather than trust blindly.

All four signals are normalized to `[0.0, 1.0]` with a consistent polarity:
**1.0 always means "best/most trustworthy"**, 0.0 always means "worst" — this
matches the AIS formula's own S_entropy/S_grounding/S_sacrifice/S_compliance
polarity (see scoring-core's `AisComponentInputs` field docs: "higher is
better" for all four axes), so a caller never has to remember that one
signal is inverted relative to the others.

Every entry in `batch` is a plain dict, one per `IntegrityClient.log_telemetry`
call — see client.py for the exact shape (`metadata`, optional pre-computed
`entropy`/`grounding`). This module doesn't depend on client.py to avoid a
circular import; client.py imports this one.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional


def lexical_stability_score(text: str) -> float:
    """
    Real Shannon entropy over word-frequency distribution, normalized to
    `[0, 1]` by dividing by the maximum possible entropy for that many
    distinct words (`log2(unique_word_count)`), then INVERTED (`1 -
    normalized_entropy`) so the result reads as "how stable/consistent is
    this text" rather than "how diverse" — matching S_entropy's actual
    polarity ("rewards stability", per scoring-core's docstring).

    This is a real information-theoretic computation, not the previous
    inline heuristic (`len(set(words)) / len(words)`, a crude type-token
    ratio) that `integrations/openai_integrity.py` used to compute directly
    — that heuristic is now a call into this function, so there is exactly
    one definition of "entropy" in this SDK, not two that could silently
    drift apart.

    Empty or single-word text has no meaningful frequency distribution to
    measure entropy over, so it returns 1.0 (maximally stable) rather than
    an undefined value — a one-word response isn't erratic, there's just
    nothing to compare it against.
    """
    words = text.split()
    if len(words) <= 1:
        return 1.0

    counts = Counter(words)
    total = len(words)
    probabilities = [count / total for count in counts.values()]
    shannon_entropy = -sum(p * math.log2(p) for p in probabilities)

    max_entropy = math.log2(len(counts)) if len(counts) > 1 else 1.0
    normalized_entropy = shannon_entropy / max_entropy if max_entropy > 0 else 0.0

    return 1.0 - min(max(normalized_entropy, 0.0), 1.0)


# Deliberately crude keyword heuristic, carried over unchanged from the
# original `integrations/openai_integrity.py` implementation (just moved
# here so it has one home) — a real grounding measure would need to check
# completion claims against retrieved source documents, which requires
# integration-specific context this shared function doesn't have. Documented
# as a first-pass heuristic, not a substitute for real fact-checking.
_UNGROUNDED_MARKERS = ("hallucinate", "not sure", "i don't know", "i'm not certain")


def keyword_grounding_score(text: str) -> float:
    lowered = text.lower()
    return 0.40 if any(marker in lowered for marker in _UNGROUNDED_MARKERS) else 0.95


def _entry_entropy(entry: Dict[str, Any]) -> Optional[float]:
    """Prefers a pre-computed `entropy` field (set by an integration that
    had the completion text at hand, e.g. openai_integrity.py) over
    recomputing from `metadata.text_output` — avoids redundant work and
    lets an integration supply a better-informed value if it has one."""
    if isinstance(entry.get("entropy"), (int, float)):
        return float(entry["entropy"])
    text = entry.get("metadata", {}).get("text_output")
    if isinstance(text, str) and text:
        return lexical_stability_score(text)
    return None


def _entry_grounding(entry: Dict[str, Any]) -> Optional[float]:
    if isinstance(entry.get("grounding"), (int, float)):
        return float(entry["grounding"])
    text = entry.get("metadata", {}).get("text_output")
    if isinstance(text, str) and text:
        return keyword_grounding_score(text)
    return None


def derive_entropy(batch: List[Dict[str, Any]]) -> float:
    """Batch-mean stability score across every entry that has a completion
    text or a pre-computed value. Returns 0.0 for an empty batch or a batch
    with no scoreable entries — spec/integrity-protocol-v3.2.md §3.1.1
    requirement N2 ("earned, not granted"): absence of evidence must score
    low, not high. This mirrors integrity-oracle/backend/src/derive.rs's
    server-side recomputation, which is what the oracle actually scores on;
    a client-side default that disagreed would just be a misleading display
    value."""
    values = [v for v in (_entry_entropy(e) for e in batch) if v is not None]
    return sum(values) / len(values) if values else 0.0


def derive_grounding(batch: List[Dict[str, Any]]) -> float:
    """See `derive_entropy`'s docstring — same fail-closed rationale (spec §3.1.1 N2)."""
    values = [v for v in (_entry_grounding(e) for e in batch) if v is not None]
    return sum(values) / len(values) if values else 0.0


# Ceiling chosen so a single, realistically-sized agent session (a few dozen
# calls at typical chat-completion lengths) doesn't saturate the score, while
# a session doing meaningfully more real work scores higher — deliberately
# not tied to any specific model's context window, since this batch may mix
# providers/models.
_SACRIFICE_TOKEN_CEILING = 200_000


def _positive_int(source: Any, key: str) -> int:
    """`source[key]` as a non-negative int, or 0. Rejects bools (a `True` would otherwise
    count as 1 token), non-numerics, and negatives — a negative count is never legitimate
    and must not be able to reduce a score input."""
    if not isinstance(source, dict):
        return 0
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value) if value > 0 else 0


def entry_token_total(entry: Dict[str, Any]) -> int:
    """
    Total tokens processed for one telemetry entry.

    **Must stay byte-for-byte equivalent to integrity-oracle's
    `backend/src/derive.rs::entry_token_total`.** Both are pinned by the shared conformance
    vectors in `spec/token-accounting/vectors.json`, which both test suites read. That
    mechanism exists because these two implementations previously drifted into the *same*
    double-counting bug — summing `total_tokens` AND `prompt_tokens` AND `completion_tokens`,
    so every OpenAI-shaped entry counted twice — and because both sides were wrong
    identically, no reconciliation between them could reveal it.

    Precedence:

    1. Base is the provider-computed `total_tokens` when present, else the sum of the two
       halves. Never both: `total_tokens` already equals prompt+completion wherever it is
       reported.
    2. Anthropic-style cache tokens are **additional** to `input_tokens`, so they are added.
    3. OpenAI's `prompt_tokens_details.cached_tokens` and
       `completion_tokens_details.reasoning_tokens` are **subsets** of the halves they belong
       to, so they are never added. Getting rules 2 and 3 the same way round is the whole
       difficulty here — the two providers use opposite semantics for cache accounting.
    4. Flat top-level `input_tokens`/`output_tokens` are consulted only when `token_usage`
       yielded nothing, so one call is never counted twice.
    """
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        return 0
    usage = metadata.get("token_usage")
    usage = usage if isinstance(usage, dict) else {}

    total = _positive_int(usage, "total_tokens")
    if total == 0:
        total = (
            _positive_int(usage, "prompt_tokens")
            + _positive_int(usage, "completion_tokens")
            + _positive_int(usage, "input_tokens")
            + _positive_int(usage, "output_tokens")
        )

    # Rule 2 — additive cache classes, in both the raw Anthropic and flattened spellings.
    total += (
        _positive_int(usage, "cache_creation_input_tokens")
        + _positive_int(usage, "cache_read_input_tokens")
        + _positive_int(usage, "cache_creation_tokens")
        + _positive_int(usage, "cache_read_tokens")
    )

    # Rule 4 — flat form only as a fallback.
    if total == 0:
        total = _positive_int(metadata, "input_tokens") + _positive_int(metadata, "output_tokens")

    return total


def derive_sacrifice(batch: List[Dict[str, Any]]) -> float:
    """
    Proxy for scoring-core's "costly, hard-to-fake evidence of real resource
    commitment" axis (see `AisComponentInputs.gpu_hours_verified`'s
    docstring). The SDK has no way to independently VERIFY compute
    contribution client-side (that's exactly why the oracle's field is
    named `_verified`, not `_claimed`) — total tokens actually processed
    across the batch is the closest honestly-observable proxy available at
    this layer: it's real, it's already present in both integrations'
    telemetry (`usage.prompt_tokens`/`completion_tokens` from OpenAI,
    `token_usage` from LangChain's `llm_output`), and it can't be
    cost-free-faked the way a self-reported flag could. This is a genuinely
    weaker signal than oracle-verified GPU-hours and is documented as such —
    the oracle's own ingestion handler decides how much weight to give a
    client-reported sacrifice signal versus its own server-side evidence.
    """
    total_tokens = sum(entry_token_total(entry) for entry in batch)

    if total_tokens <= 0:
        return 0.0
    return min(math.log10(total_tokens + 1) / math.log10(_SACRIFICE_TOKEN_CEILING + 1), 1.0)


def derive_compliance(
    batch: List[Dict[str, Any]],
    *,
    compliance_gate_address: Optional[str] = None,
    covered_entity_address: Optional[str] = None,
    w3: Optional[Any] = None,
) -> float:
    """
    Combines self-reported compliance signals from the telemetry batch with
    a live on-chain `ComplianceGate.isHealthcareCompliant` read when chain
    access is available — **on-chain wins** when both are present, since a
    self-report alone is exactly the kind of unverified claim
    `ComplianceGate.sol`'s own NatSpec warns against trusting for a
    regulated-vertical agent (see contracts/src/health/ComplianceGate.sol).

    Self-reported signal: fraction of batch entries NOT flagged as a policy
    violation (`metadata.get("policy_violation")` or `metadata.get("flagged")`
    truthy), mirroring `telemetry/conventions.py`'s
    `IntegrityAttributes.COMPLIANCE_*` attribute intent.
    """
    flagged_count = 0
    total = len(batch)
    for entry in batch:
        metadata = entry.get("metadata", {})
        if metadata.get("policy_violation") or metadata.get("flagged"):
            flagged_count += 1

    # Empty batch fails closed to 0.0 (spec §3.1.1 N2) — absence of compliance
    # evidence is not evidence of compliance.
    self_reported = 1.0 - (flagged_count / total) if total > 0 else 0.0

    if compliance_gate_address and covered_entity_address and w3 is not None:
        try:
            from .. import chain as chain_module

            gate_artifact = chain_module._load_artifact("ComplianceGate")
            gate = w3.eth.contract(address=w3.to_checksum_address(compliance_gate_address), abi=gate_artifact["abi"])
            is_compliant = gate.functions.isHealthcareCompliant(
                w3.to_checksum_address(covered_entity_address)
            ).call()
            # On-chain wins: a live "not compliant" read overrides a clean
            # self-report (an agent can't talk its way out of a lapsed BAA),
            # but a live "compliant" read still can't push the score above
            # what self-reporting already earned — on-chain presence proves
            # eligibility, not good behavior within that eligibility.
            return min(self_reported, 1.0) if is_compliant else 0.0
        except Exception:
            # Chain read failures (RPC down, gate not deployed, etc) fall
            # back to the self-reported signal rather than raising — this
            # function computes an input to a score, not a security gate;
            # EHRGate.sol remains the real, fail-closed enforcement point
            # for actual PHI access, this is just a reputation input.
            pass

    return self_reported


# Decimal places every derived signal is quantized to before it is signed.
#
# This is a CORRECTNESS requirement of the signature scheme, not cosmetic
# rounding (FIXED 2026-07-17 — was silently rejecting ~20% of real, correctly
# signed telemetry with a 400).
#
# `client.flush_telemetry` signs the canonical JSON of a payload containing
# these floats, and integrity-oracle re-serializes the same payload with
# Rust's `serde_json` to check that signature. Both sides emit the "shortest
# string that round-trips back to this exact f64" — but when a float has TWO
# equally-short round-tripping representations, Python's repr (David Gay) and
# Rust's ryu are each free to pick a different one. Nothing is wrong with
# either; they simply disagree, the canonical bytes differ, and Ed25519
# verification fails on a payload that was signed perfectly correctly.
#
# Confirmed against the live oracle, not theorised: a real derived entropy of
# 0.011890908425879365 failed every time while 0.009712883245855508 passed,
# and in Python BOTH "0.011890908425879365" and "0.011890908425879366"
# round-trip to that identical f64 (hex 0x1.85a42b6789780p-7) — the exact
# two-candidate ambiguity above. The oracle's error surfaced as a confusing
# "eip191 verification error: signature must be 65 bytes, got 64", which is a
# downstream red herring: `crypto::verify_agent_signature` tries Ed25519
# first, gets `false` (not an error), and falls through to the EIP-191 branch,
# which then chokes on a 64-byte Ed25519 signature.
#
# The ambiguity is a ~17-significant-digit phenomenon; at 6 decimal places the
# shortest round-tripping representation is unique, so both languages
# necessarily agree. 6dp is also far more precision than these heuristics
# justify (see each derive_* docstring — they are first-pass client-side
# estimates the oracle independently recomputes anyway), so nothing of value
# is lost by quantizing.
#
# NOTE (real remaining gap, deliberately not papered over): this only fixes the
# floats the SDK itself generates. A caller passing an arbitrary float through
# `log_telemetry(metadata=...)` can still land on an ambiguous value and hit
# the same rejection, since that value is signed verbatim inside `otel_spans`.
# The general fix is a shared canonicalization standard with a fully specified
# number format on both sides -- RFC 8785 (JCS) mandates ECMAScript's
# Number::toString, which is deterministic -- rather than each language's own
# shortest-repr. Flagged in PRODUCTION_GAPS.md rather than silently assumed
# away, same as bcc.py's own canonicalization docstring does for a related
# non-ASCII concern.
_SIGNAL_DECIMALS = 6


def derive_ais_signals(
    batch: List[Dict[str, Any]],
    *,
    compliance_gate_address: Optional[str] = None,
    covered_entity_address: Optional[str] = None,
    w3: Optional[Any] = None,
) -> Dict[str, Any]:
    """Bundles all four derived signals into the shape
    `POST /v1/telemetry/ingest`'s `derived_signals` field expects (see
    docs/INTERFACE_CONTRACT.md).

    Every value is quantized to `_SIGNAL_DECIMALS` decimal places — see that
    constant's comment for why this is load-bearing for signature
    verification and not a cosmetic choice.
    """
    result: Dict[str, Any] = {
        "entropy": round(derive_entropy(batch), _SIGNAL_DECIMALS),
        "grounding": round(derive_grounding(batch), _SIGNAL_DECIMALS),
        "sacrifice": round(derive_sacrifice(batch), _SIGNAL_DECIMALS),
        "compliance": round(
            derive_compliance(
                batch,
                compliance_gate_address=compliance_gate_address,
                covered_entity_address=covered_entity_address,
                w3=w3,
            ),
            _SIGNAL_DECIMALS,
        ),
    }
    billed = _derive_billed_cost(batch)
    if billed is not None:
        result["billed_cost"] = billed
    return result


def _derive_billed_cost(batch: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the first provider-reported cost verbatim, if present.

    Cost is evidence, not an estimate: this deliberately does not calculate a price
    from token counts or apply a local rate table. Integrations may place a provider
    response's ``cost_usd``/``cost`` plus ``currency`` and ``rate_source`` in
    ``metadata.token_usage``.
    """
    for entry in batch:
        usage = entry.get("metadata", {}).get("token_usage", {})
        if not isinstance(usage, dict):
            continue
        amount = usage.get("cost_usd", usage.get("cost"))
        if not isinstance(amount, (int, float)):
            continue
        currency = usage.get("currency")
        rate_source = usage.get("rate_source")
        if isinstance(currency, str) and isinstance(rate_source, str):
            return {"amount": amount, "currency": currency, "rate_source": rate_source}
    return None
