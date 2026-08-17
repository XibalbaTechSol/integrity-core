//! Server-side re-derivation of AIS input signals (entropy, grounding, sacrifice,
//! self-reported compliance) from the raw content already present in a signed
//! `POST /v1/telemetry/ingest` request's `otel_spans` field.
//!
//! Ownership boundary: this module produces AIS *inputs*, never the score itself —
//! `integrity-oracle/scoring-core` remains the only place the formula is computed
//! (`docs/INTERFACE_CONTRACT.md` §4.3).
//!
//! **Why this exists.** `TelemetryIngestRequest.derived_signals` is a client-computed
//! (`integrity_sdk/telemetry/derive.py`) blob inside an Ed25519/EIP-191-signed envelope.
//! The signature proves *who* sent the request, never *whether the numbers are honest*
//! — nothing before this module independently checked them. `otel_spans` (the SDK's own
//! batched `log_telemetry`/`traceable` entries, NOT real OTel protobufs — see `otlp.rs`
//! for the actual OTLP receiver, a separate and deliberately unauthenticated path) sits
//! inside that same signed envelope and already carries the raw completion text
//! (`metadata.text_output`) and token usage the SDK used to compute `derived_signals`
//! moments earlier. This module re-runs that same computation server-side — mirroring
//! `crate::phi`'s exact posture (re-check what the client already computed, as
//! defense-in-depth against a buggy-or-bypassed client-side step, rather than trusting
//! the claim) — and `handlers::ingest_telemetry` uses THESE values, not the client's, as
//! the actual AIS inputs. `derived_signals` stays in the signed envelope and is still
//! stored (in `telemetry_events.payload`) for audit-trail comparison, but becomes purely
//! advisory.
//!
//! **Two deliberate departures from a pure 1:1 port of `derive.py`, both approved
//! decisions (see the plan this module implements), not oversights:**
//! - `derive_entropy`'s caller inverts the result (`1.0 - recomputed.entropy`) before
//!   storing into `telemetry_events.performance_variance` — `scoring_core::
//!   calculate_entropy_score` treats that column as a true statistical variance (0.0 =
//!   best), but `derive.py`'s convention is 1.0 = best (a stability score). Storing the
//!   raw stability score there was backwards for every agent prior to this module.
//! - `derive_sacrifice` here returns an **hours-equivalent proxy**
//!   (`total_tokens / TOKENS_PER_GPU_HOUR_PROXY`), NOT a `[0,1]`-normalized index the way
//!   `derive.py`'s version does. `derive.py`'s pre-normalization plus
//!   `scoring_core::calculate_sacrifice_score`'s own `log10(hours+1)/3` compressed the
//!   signal twice, capping max-sacrifice agents around ~100/1000 instead of the intended
//!   ~1000-hour saturation curve. Returning a raw hours-equivalent value here makes
//!   `scoring-core`'s own log10 the *only* normalization step — no `scoring-core` edit
//!   needed, the fix is entirely in what value reaches it.
//!
//! Every function here is defensive against malformed `otel_spans` shapes: `.get()`
//! chains only, never `[]` indexing or `.unwrap()`/`.expect()`. By the time this code
//! runs, the request's signature has already been verified (see
//! `handlers::ingest_telemetry`) — a malformed entry from an authenticated agent is a
//! *shape* problem, not a spoof attempt, and must degrade to "not scoreable" (matching
//! `derive.py`'s own `Optional[float]`/`isinstance(...)` guards), never panic.

use std::collections::HashMap;

use serde_json::Value;

/// Real Shannon entropy over word-frequency distribution, normalized to `[0, 1]` by
/// dividing by the maximum possible entropy for that many distinct words
/// (`log2(unique_word_count)`), then inverted (`1 - normalized`) so the result reads as
/// "how stable/consistent is this text" — 1.0 = maximally stable. Mirrors
/// `derive.py::lexical_stability_score` field-for-field, including its edge cases:
/// empty or single-word text has no meaningful frequency distribution to measure
/// entropy over, so it returns 1.0 rather than an undefined value.
pub fn lexical_stability_score(text: &str) -> f64 {
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.len() <= 1 {
        return 1.0;
    }

    let mut counts: HashMap<&str, usize> = HashMap::new();
    for word in &words {
        *counts.entry(word).or_insert(0) += 1;
    }
    let total = words.len() as f64;

    let shannon_entropy: f64 = counts
        .values()
        .map(|&count| {
            let p = count as f64 / total;
            -p * p.log2()
        })
        .sum();

    let max_entropy = if counts.len() > 1 { (counts.len() as f64).log2() } else { 1.0 };
    let normalized_entropy = if max_entropy > 0.0 { shannon_entropy / max_entropy } else { 0.0 };

    1.0 - normalized_entropy.clamp(0.0, 1.0)
}

/// Deliberately crude keyword heuristic, mirroring `derive.py::keyword_grounding_score`
/// exactly (same four markers, same 0.40/0.95 constants) — a real grounding measure
/// would need to check completion claims against retrieved source documents, which
/// requires integration-specific context this function doesn't have. A first-pass
/// heuristic, not a substitute for real fact-checking, same as the Python original.
const UNGROUNDED_MARKERS: [&str; 4] = ["hallucinate", "not sure", "i don't know", "i'm not certain"];

pub fn keyword_grounding_score(text: &str) -> f64 {
    let lowered = text.to_lowercase();
    if UNGROUNDED_MARKERS.iter().any(|marker| lowered.contains(marker)) {
        0.40
    } else {
        0.95
    }
}

fn entry_text_output(entry: &Value) -> Option<&str> {
    entry.get("metadata")?.get("text_output")?.as_str()
}

fn entry_precomputed(entry: &Value, key: &str) -> Option<f64> {
    entry.get(key)?.as_f64()
}

fn entry_entropy(entry: &Value) -> Option<f64> {
    entry_precomputed(entry, "entropy").or_else(|| entry_text_output(entry).map(lexical_stability_score))
}

fn entry_grounding(entry: &Value) -> Option<f64> {
    entry_precomputed(entry, "grounding").or_else(|| entry_text_output(entry).map(keyword_grounding_score))
}

/// Batch-mean stability score across every entry that has a completion text or a
/// pre-computed value. Returns 0.0 for an empty batch or a batch with no scoreable
/// entries — spec/integrity-protocol-v3.2.md §3.1.1 requirement N2 ("earned, not
/// granted"): absence of evidence must score low, not high. The prior default of 1.0
/// treated "no evidence of instability" as "proof of stability", which is exactly
/// backwards — it let a submission with no analysable content buy maximal entropy
/// AND grounding for free, and because `scoring_core::score` is a weighted geometric
/// mean, a genuinely-absent axis should pull the whole score toward zero, not shield
/// it. See §3.1.4 implementation-delta rows 1-2.
pub fn derive_entropy(batch: &[Value]) -> f64 {
    let values: Vec<f64> = batch.iter().filter_map(entry_entropy).collect();
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

/// See `derive_entropy`'s doc comment — same fail-closed rationale (spec §3.1.1 N2).
pub fn derive_grounding(batch: &[Value]) -> f64 {
    let values: Vec<f64> = batch.iter().filter_map(entry_grounding).collect();
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

/// Hours-equivalent proxy for "costly, hard-to-fake evidence of real resource
/// commitment" — see this module's doc comment for why this diverges from
/// `derive.py`'s `[0,1]`-normalized version. A heuristic, documented as such (same
/// posture as `derive.py`'s own `_SACRIFICE_TOKEN_CEILING` comment): reaching
/// `scoring-core`'s ~1000-hour saturation point, summed across a 30-day reporting
/// window (`db::aggregate_for_ais`'s `SUM(gpu_hours_verified)`), requires ~50M
/// cumulative tokens — plausible for a genuinely active production agent over 30 days,
/// not trivially gamed by one session.
pub const TOKENS_PER_GPU_HOUR_PROXY: f64 = 50_000.0;

/// `source[key]` as a non-negative i64, or 0. Rejects non-numerics and negatives — a
/// negative count is never legitimate and must not be able to reduce a score input.
fn positive_i64(source: Option<&Value>, key: &str) -> i64 {
    source
        .and_then(|s| s.get(key))
        .and_then(|v| v.as_i64().or_else(|| v.as_f64().map(|f| f as i64)))
        .filter(|n| *n > 0)
        .unwrap_or(0)
}

/// Total tokens processed for one telemetry entry.
///
/// **Must stay equivalent to integrity-sdk's
/// `integrity_sdk/telemetry/derive.py::entry_token_total`.** Both are pinned by the shared
/// conformance vectors in `spec/token-accounting/vectors.json`, which both test suites read.
/// That mechanism exists because these two implementations previously drifted into the *same*
/// double-counting bug — summing `total_tokens` AND `prompt_tokens` AND `completion_tokens`,
/// so every OpenAI-shaped entry counted twice — and because both sides were wrong
/// identically, no reconciliation between them could reveal it. This function is the
/// authoritative one: the oracle computes AIS, the client's numbers are audit trail only.
///
/// Precedence:
/// 1. Base is the provider-computed `total_tokens` when present, else the sum of the two
///    halves. Never both: `total_tokens` already equals prompt+completion wherever reported.
/// 2. Anthropic-style cache tokens are ADDITIONAL to `input_tokens`, so they are added.
/// 3. OpenAI's `prompt_tokens_details.cached_tokens` and
///    `completion_tokens_details.reasoning_tokens` are SUBSETS of the halves they belong to,
///    so they are never added. Rules 2 and 3 use opposite semantics for cache accounting,
///    which is the whole difficulty here.
/// 4. Flat top-level `input_tokens`/`output_tokens` are consulted only when `token_usage`
///    yielded nothing, so one call is never counted twice.
fn entry_token_total(entry: &Value) -> i64 {
    let Some(metadata) = entry.get("metadata") else {
        return 0;
    };
    let usage = metadata.get("token_usage").filter(|v| v.is_object());

    let mut total = positive_i64(usage, "total_tokens");
    if total == 0 {
        total = positive_i64(usage, "prompt_tokens")
            + positive_i64(usage, "completion_tokens")
            + positive_i64(usage, "input_tokens")
            + positive_i64(usage, "output_tokens");
    }

    // Rule 2 — additive cache classes, raw Anthropic and flattened spellings.
    total += positive_i64(usage, "cache_creation_input_tokens")
        + positive_i64(usage, "cache_read_input_tokens")
        + positive_i64(usage, "cache_creation_tokens")
        + positive_i64(usage, "cache_read_tokens");

    // Rule 4 — flat form only as a fallback.
    if total == 0 {
        total = positive_i64(Some(metadata), "input_tokens") + positive_i64(Some(metadata), "output_tokens");
    }
    total
}

pub fn derive_sacrifice(batch: &[Value]) -> f64 {
    let total_tokens: i64 = batch.iter().map(entry_token_total).sum();
    if total_tokens <= 0 {
        0.0
    } else {
        total_tokens as f64 / TOKENS_PER_GPU_HOUR_PROXY
    }
}

fn entry_flagged(entry: &Value) -> bool {
    let Some(metadata) = entry.get("metadata") else { return false };
    let truthy = |key: &str| metadata.get(key).is_some_and(|v| v.as_bool().unwrap_or(!v.is_null() && v != &Value::Bool(false)));
    truthy("policy_violation") || truthy("flagged")
}

/// Self-reported half of `derive.py::derive_compliance`: fraction of batch entries NOT
/// flagged as a policy violation. The on-chain "wins" half needs `state.chain` (a live
/// `ComplianceGate.isHealthcareCompliant` read) and stays in `handlers.rs`, not this
/// pure module — see `handlers::ingest_telemetry`. Returns 0.0 for an empty batch
/// (spec/integrity-protocol-v3.2.md §3.1.1 N2) — absence of compliance evidence is not
/// evidence of compliance, so an agent submitting nothing must not score as "clean".
pub fn self_reported_compliance(batch: &[Value]) -> f64 {
    if batch.is_empty() {
        return 0.0;
    }
    let flagged_count = batch.iter().filter(|e| entry_flagged(e)).count();
    1.0 - (flagged_count as f64 / batch.len() as f64)
}

/// Reads `metadata.covered_entity_address` from the first batch entry that carries it —
/// deliberately read from `otel_spans[].metadata` rather than a new top-level signed
/// field: `TelemetryIngestRequest` can't gain a new field without breaking every
/// existing client's signature (the `signable` JSON is reconstructed from the struct's
/// fields; a new field changes what gets signed). `otel_spans` entries already carry
/// arbitrary `metadata` keys today (`integrity_sdk/client.py::log_telemetry`), so this
/// requires zero SDK/wire changes and degrades to the self-reported fallback for any
/// integration that doesn't set it — identical in shape to `derive.py`'s own
/// `Optional[str] = None` kwarg default for the same address.
pub fn entry_covered_entity_address(batch: &[Value]) -> Option<String> {
    batch.iter().find_map(|e| e.get("metadata")?.get("covered_entity_address")?.as_str().map(String::from))
}

/// Bundles the three pure-text/token signals for one call site in
/// `handlers::ingest_telemetry`. Compliance is deliberately NOT here — it needs
/// `state.chain` for the on-chain-wins check, so it's computed separately in
/// `handlers.rs` using `self_reported_compliance` + `entry_covered_entity_address` from
/// this module as its two building blocks.
#[derive(Debug, Clone, Copy)]
pub struct RecomputedSignals {
    pub entropy: f64,
    pub grounding: f64,
    pub sacrifice: f64,
}

pub fn recompute(batch: &[Value]) -> RecomputedSignals {
    RecomputedSignals {
        entropy: derive_entropy(batch),
        grounding: derive_grounding(batch),
        sacrifice: derive_sacrifice(batch),
    }
}

#[cfg(test)]
mod tests {
    /// Cross-language conformance: this function and integrity-sdk's
    /// `telemetry/derive.py::entry_token_total` must agree on every vector in
    /// `spec/token-accounting/vectors.json`. Both suites read that one file, so the two
    /// implementations cannot drift apart silently — which is exactly how they previously
    /// ended up sharing a double-counting bug that no reconciliation could reveal.
    #[test]
    fn token_accounting_matches_shared_conformance_vectors() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .join("spec/token-accounting/vectors.json");
        let raw = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("shared conformance vectors must be readable at {path:?}: {e}"));
        let doc: Value = serde_json::from_str(&raw).expect("vectors.json must be valid JSON");
        let vectors = doc["vectors"].as_array().expect("vectors must be an array");
        assert!(!vectors.is_empty(), "vector file must not be empty — a silently empty file would make this test vacuous");

        for v in vectors {
            let name = v["name"].as_str().unwrap_or("<unnamed>");
            let expected = v["expected"].as_i64().expect("expected must be an integer");
            let actual = entry_token_total(&v["entry"]);
            assert_eq!(
                actual, expected,
                "vector '{}' disagrees ({}): expected {}, got {}",
                name,
                v["why"].as_str().unwrap_or(""),
                expected,
                actual
            );
        }
    }

    use super::*;
    use serde_json::json;

    // --- lexical_stability_score: pinned against integrity-sdk's real derive.py ---
    // (values generated by actually running derive.py via the SDK venv, not hand-derived
    // — see this module's doc comment for why cross-language parity matters here.)

    #[test]
    fn lexical_stability_matches_python_repeated_word() {
        // python: derive.lexical_stability_score("the the the the the") == 1.0
        assert_eq!(lexical_stability_score("the the the the the"), 1.0);
    }

    #[test]
    fn lexical_stability_matches_python_all_unique_words() {
        // python: derive.lexical_stability_score("the quick brown fox jumps over lazy dog") == 0.0
        // (8 unique words out of 8 total -> normalized_entropy == 1.0 -> stability == 0.0)
        let score = lexical_stability_score("the quick brown fox jumps over lazy dog");
        assert!((score - 0.0).abs() < 1e-9, "got {score}");
    }

    #[test]
    fn lexical_stability_matches_python_mixed_repetition() {
        // python: derive.lexical_stability_score("the cat sat on the mat the cat ran") == 0.06405530255413405
        let score = lexical_stability_score("the cat sat on the mat the cat ran");
        assert!((score - 0.06405530255413405).abs() < 1e-9, "got {score}");
    }

    #[test]
    fn lexical_stability_empty_and_single_word_default_to_one() {
        assert_eq!(lexical_stability_score(""), 1.0);
        assert_eq!(lexical_stability_score("hello"), 1.0);
    }

    // --- keyword_grounding_score ---

    #[test]
    fn keyword_grounding_matches_python_ungrounded_markers() {
        for marker in ["I'm not sure", "I don't know", "let me hallucinate", "I'm not certain"] {
            assert_eq!(keyword_grounding_score(marker), 0.40, "marker: {marker}");
        }
    }

    #[test]
    fn keyword_grounding_matches_python_grounded_default() {
        assert_eq!(keyword_grounding_score("the answer is 42"), 0.95);
    }

    #[test]
    fn keyword_grounding_is_case_insensitive() {
        assert_eq!(keyword_grounding_score("I'M NOT SURE about this"), 0.40);
    }

    // --- derive_sacrifice ---

    #[test]
    fn derive_sacrifice_sums_token_usage_and_divides_by_proxy_constant() {
        let batch = vec![json!({"metadata": {"token_usage": {"total_tokens": 50000}}})];
        let score = derive_sacrifice(&batch);
        assert!((score - 1.0).abs() < 1e-9, "got {score}");
    }

    #[test]
    fn derive_sacrifice_sums_across_multiple_entries_and_fields() {
        let batch = vec![
            json!({"metadata": {"token_usage": {"prompt_tokens": 1000, "completion_tokens": 500}}}),
            json!({"metadata": {"input_tokens": 2000, "output_tokens": 500}}),
        ];
        // total = 1000 + 500 + 2000 + 500 = 4000
        let score = derive_sacrifice(&batch);
        assert!((score - 4000.0 / TOKENS_PER_GPU_HOUR_PROXY).abs() < 1e-9, "got {score}");
    }

    #[test]
    fn derive_sacrifice_zero_tokens_is_zero() {
        assert_eq!(derive_sacrifice(&[json!({"metadata": {}})]), 0.0);
        assert_eq!(derive_sacrifice(&[]), 0.0);
    }

    // --- batch defaults / adversarial robustness ---

    #[test]
    fn empty_batch_entropy_and_grounding_fail_closed_to_zero() {
        // spec §3.1.1 N2: absence of evidence must score low, not high. An attacker
        // sending empty otel_spans (or spans with no analysable text) must not receive
        // the same score as an agent who demonstrated real stability/grounding.
        assert_eq!(derive_entropy(&[]), 0.0);
        assert_eq!(derive_grounding(&[]), 0.0);
    }

    #[test]
    fn content_free_submission_with_token_counts_fails_closed_on_entropy_and_grounding() {
        // Regression for the attack this fix closes: a submission carrying token counts
        // (so derive_sacrifice is nonzero) but no analysable text_output/precomputed
        // entropy-or-grounding value must not read as maximally stable and grounded.
        // Before this fix, entropy/grounding defaulted to 1.0 here, which combined with
        // self-reported compliance's own empty-batch default let a content-free
        // submission outscore an honest agent with real, mediocre telemetry.
        let batch = vec![json!({"metadata": {"token_usage": {"total_tokens": 5_000_000}}})];
        assert_eq!(derive_entropy(&batch), 0.0);
        assert_eq!(derive_grounding(&batch), 0.0);
        assert!(derive_sacrifice(&batch) > 0.0, "sacrifice should still reflect the claimed tokens");
    }

    #[test]
    fn malformed_entries_never_panic_and_are_excluded() {
        let batch = vec![
            json!({"metadata": {"text_output": 12345}}), // wrong type, not a string
            json!({"metadata": null}),
            json!({}),
            json!("not even an object"),
            json!({"metadata": {"token_usage": "not a dict"}}),
            json!(null),
            json!(42),
        ];
        // Must not panic; must fall back to the fail-closed empty-batch default since
        // nothing here is actually scoreable (`self_reported_compliance` is exempt — it
        // counts entries, not scoreable content, and this batch is non-empty).
        assert_eq!(derive_entropy(&batch), 0.0);
        assert_eq!(derive_grounding(&batch), 0.0);
        assert_eq!(derive_sacrifice(&batch), 0.0);
        assert_eq!(self_reported_compliance(&batch), 1.0);
        assert_eq!(entry_covered_entity_address(&batch), None);
    }

    #[test]
    fn precomputed_entropy_grounding_preferred_over_recompute() {
        // Mirrors derive.py's _entry_entropy/_entry_grounding: prefer a pre-computed
        // per-entry field over recomputing from text_output.
        let batch = vec![json!({"entropy": 0.42, "grounding": 0.11, "metadata": {"text_output": "ignored text content here"}})];
        assert_eq!(derive_entropy(&batch), 0.42);
        assert_eq!(derive_grounding(&batch), 0.11);
    }

    // --- self_reported_compliance ---

    #[test]
    fn self_reported_compliance_matches_python_flagged_ratio() {
        let batch = vec![
            json!({"metadata": {"flagged": false}}),
            json!({"metadata": {"flagged": true}}),
            json!({"metadata": {"policy_violation": true}}),
            json!({"metadata": {}}),
        ];
        // 2 of 4 flagged -> 1.0 - 0.5 = 0.5
        assert_eq!(self_reported_compliance(&batch), 0.5);
    }

    #[test]
    fn self_reported_compliance_empty_batch_fails_closed_to_zero() {
        // spec §3.1.1 N2: absence of compliance evidence is not evidence of compliance.
        assert_eq!(self_reported_compliance(&[]), 0.0);
    }

    // --- entry_covered_entity_address ---

    #[test]
    fn covered_entity_address_read_from_first_carrying_entry() {
        let batch = vec![json!({"metadata": {}}), json!({"metadata": {"covered_entity_address": "0xabc123"}})];
        assert_eq!(entry_covered_entity_address(&batch), Some("0xabc123".to_string()));
    }

    #[test]
    fn covered_entity_address_absent_returns_none() {
        assert_eq!(entry_covered_entity_address(&[json!({"metadata": {}})]), None);
    }
}
