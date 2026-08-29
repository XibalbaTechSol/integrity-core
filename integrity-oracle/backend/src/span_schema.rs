//! Structural validation for `otel_spans` entries, gated behind
//! `schema_version >= 3` (see `handlers::MAX_TELEMETRY_SCHEMA_VERSION`).
//!
//! Versions 1/2 keep accepting `otel_spans` as fully opaque `serde_json::Value` —
//! those signatures must keep verifying forever (same rule that already applies to
//! `TelemetryIngestRequest::schema_version` itself). Version 3 is the first shape
//! where the oracle validates span *structure* before `derive::recompute`/`phi::
//! scan_json_value` ever see it, rather than defending only against known-bad
//! *content* inside an unconstrained blob.
//!
//! This only allowlists keys and bounds sizes — it never re-derives or duplicates
//! `derive.rs`'s reading logic. A span that passes here can still fail to yield a
//! scoreable entropy/grounding value (e.g. `metadata.text_output` absent); that's
//! `derive.rs`'s fail-closed-to-0 concern, not this module's.

use serde_json::Value;

pub const MAX_SPANS_PER_BATCH: usize = 500;
pub const MAX_TEXT_OUTPUT_BYTES: usize = 32_768;
pub const MAX_CUSTOM_PROPERTIES: usize = 16;
pub const MAX_CUSTOM_VALUE_BYTES: usize = 4_096;

const KNOWN_TOKEN_USAGE_KEYS: &[&str] = &[
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "prompt_tokens_details",
    "completion_tokens_details",
];

const KNOWN_METADATA_KEYS: &[&str] =
    &["text_output", "token_usage", "flagged", "policy_violation", "covered_entity_address", "custom"];

const KNOWN_ENTRY_KEYS: &[&str] = &["entropy", "grounding", "metadata"];

#[derive(Debug, PartialEq, Eq)]
pub struct SchemaViolation(pub String);

impl std::fmt::Display for SchemaViolation {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for SchemaViolation {}

fn reject(msg: impl Into<String>) -> SchemaViolation {
    SchemaViolation(msg.into())
}

fn check_unit_interval(entry: &Value, key: &str) -> Result<(), SchemaViolation> {
    match entry.get(key) {
        None | Some(Value::Null) => Ok(()),
        Some(Value::Number(n)) => match n.as_f64() {
            Some(f) if (0.0..=1.0).contains(&f) => Ok(()),
            _ => Err(reject(format!("`{key}` must be a number in [0, 1]"))),
        },
        Some(_) => Err(reject(format!("`{key}` must be a number in [0, 1]"))),
    }
}

fn check_no_unknown_keys(obj: &serde_json::Map<String, Value>, allowed: &[&str], context: &str) -> Result<(), SchemaViolation> {
    for key in obj.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(reject(format!("unknown key `{key}` in {context} (schema_version 3 allowlists: {allowed:?})")));
        }
    }
    Ok(())
}

fn check_token_usage(usage: &Value) -> Result<(), SchemaViolation> {
    let Value::Object(map) = usage else {
        return Err(reject("`metadata.token_usage` must be an object"));
    };
    check_no_unknown_keys(map, KNOWN_TOKEN_USAGE_KEYS, "metadata.token_usage")?;
    for key in [
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ] {
        if let Some(v) = map.get(key) {
            let numeric_nonneg = v.as_i64().map(|n| n >= 0).unwrap_or(false) || v.as_f64().map(|f| f >= 0.0).unwrap_or(false);
            if !numeric_nonneg {
                return Err(reject(format!("`metadata.token_usage.{key}` must be a non-negative number")));
            }
        }
    }
    Ok(())
}

fn check_custom(custom: &Value) -> Result<(), SchemaViolation> {
    let Value::Object(map) = custom else {
        return Err(reject("`metadata.custom` must be an object"));
    };
    if map.len() > MAX_CUSTOM_PROPERTIES {
        return Err(reject(format!(
            "`metadata.custom` has {} properties, exceeds max {MAX_CUSTOM_PROPERTIES}",
            map.len()
        )));
    }
    for (key, value) in map {
        let within_bounds = match value {
            Value::String(s) => s.len() <= MAX_CUSTOM_VALUE_BYTES,
            Value::Number(_) | Value::Bool(_) => true,
            _ => false,
        };
        if !within_bounds {
            return Err(reject(format!(
                "`metadata.custom.{key}` must be a string (<= {MAX_CUSTOM_VALUE_BYTES} bytes), number, or boolean"
            )));
        }
    }
    Ok(())
}

fn check_metadata(metadata: &Value) -> Result<(), SchemaViolation> {
    let Value::Object(map) = metadata else {
        return Err(reject("`metadata` must be an object"));
    };
    check_no_unknown_keys(map, KNOWN_METADATA_KEYS, "metadata")?;

    if let Some(text) = map.get("text_output") {
        match text {
            Value::String(s) if s.len() <= MAX_TEXT_OUTPUT_BYTES => {}
            Value::String(_) => return Err(reject(format!("`metadata.text_output` exceeds {MAX_TEXT_OUTPUT_BYTES} bytes"))),
            _ => return Err(reject("`metadata.text_output` must be a string")),
        }
    }
    if let Some(usage) = map.get("token_usage") {
        check_token_usage(usage)?;
    }
    for key in ["flagged", "policy_violation"] {
        if let Some(v) = map.get(key) {
            if !v.is_boolean() {
                return Err(reject(format!("`metadata.{key}` must be a boolean")));
            }
        }
    }
    if let Some(addr) = map.get("covered_entity_address") {
        match addr.as_str() {
            Some(s) if s.len() == 42 && s.starts_with("0x") && s[2..].chars().all(|c| c.is_ascii_hexdigit()) => {}
            _ => return Err(reject("`metadata.covered_entity_address` must be a 0x-prefixed 20-byte hex address")),
        }
    }
    if let Some(custom) = map.get("custom") {
        check_custom(custom)?;
    }
    Ok(())
}

fn check_entry(entry: &Value) -> Result<(), SchemaViolation> {
    let Value::Object(map) = entry else {
        return Err(reject("each otel_spans entry must be an object"));
    };
    check_no_unknown_keys(map, KNOWN_ENTRY_KEYS, "otel_spans entry")?;
    check_unit_interval(entry, "entropy")?;
    check_unit_interval(entry, "grounding")?;
    if let Some(metadata) = map.get("metadata") {
        check_metadata(metadata)?;
    }
    Ok(())
}

/// Validates an entire `otel_spans` batch against the schema_version 3 shape.
/// Called only when the request declares `schema_version >= 3` — see
/// `handlers::ingest_telemetry`. Returns the first violation found; does not
/// attempt to collect every error in one pass (matching this codebase's existing
/// PHI-scan-then-fail posture rather than a full multi-error validation report).
pub fn validate_batch(batch: &[Value]) -> Result<(), SchemaViolation> {
    if batch.len() > MAX_SPANS_PER_BATCH {
        return Err(reject(format!("otel_spans has {} entries, exceeds max {MAX_SPANS_PER_BATCH}", batch.len())));
    }
    for entry in batch {
        check_entry(entry)?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn empty_batch_is_valid() {
        assert!(validate_batch(&[]).is_ok());
    }

    #[test]
    fn minimal_valid_entry() {
        let batch = vec![json!({"metadata": {"text_output": "hello", "token_usage": {"total_tokens": 10}}})];
        assert!(validate_batch(&batch).is_ok());
    }

    #[test]
    fn precomputed_entropy_grounding_in_range() {
        let batch = vec![json!({"entropy": 0.5, "grounding": 1.0})];
        assert!(validate_batch(&batch).is_ok());
    }

    #[test]
    fn entropy_out_of_range_rejected() {
        let batch = vec![json!({"entropy": 1.5})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn unknown_top_level_key_rejected() {
        let batch = vec![json!({"unexpected_field": "value"})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn unknown_metadata_key_rejected() {
        let batch = vec![json!({"metadata": {"secret_backdoor": "value"}})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn custom_bucket_allows_bounded_extra_fields() {
        let batch = vec![json!({"metadata": {"custom": {"trace_source": "langchain", "retries": 2, "cached": true}}})];
        assert!(validate_batch(&batch).is_ok());
    }

    #[test]
    fn custom_bucket_rejects_nested_object() {
        let batch = vec![json!({"metadata": {"custom": {"nested": {"a": 1}}}})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn custom_bucket_rejects_too_many_properties() {
        let mut props = serde_json::Map::new();
        for i in 0..(MAX_CUSTOM_PROPERTIES + 1) {
            props.insert(format!("k{i}"), json!(i));
        }
        let batch = vec![json!({"metadata": {"custom": Value::Object(props)}})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn text_output_over_limit_rejected() {
        let big = "a".repeat(MAX_TEXT_OUTPUT_BYTES + 1);
        let batch = vec![json!({"metadata": {"text_output": big}})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn negative_token_count_rejected() {
        let batch = vec![json!({"metadata": {"token_usage": {"total_tokens": -5}}})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn malformed_covered_entity_address_rejected() {
        let batch = vec![json!({"metadata": {"covered_entity_address": "not-an-address"}})];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn valid_covered_entity_address_accepted() {
        let batch = vec![json!({"metadata": {"covered_entity_address": "0x1234567890123456789012345678901234567890"}})];
        assert!(validate_batch(&batch).is_ok());
    }

    #[test]
    fn batch_over_max_spans_rejected() {
        let batch = vec![json!({}); MAX_SPANS_PER_BATCH + 1];
        assert!(validate_batch(&batch).is_err());
    }

    #[test]
    fn flagged_must_be_boolean() {
        let batch = vec![json!({"metadata": {"flagged": "yes"}})];
        assert!(validate_batch(&batch).is_err());
    }
}
