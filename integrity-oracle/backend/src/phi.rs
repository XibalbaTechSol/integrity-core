//! Defense-in-depth PHI/PII/secret backstop for `POST /v1/telemetry/ingest`
//! (`docs/INTERFACE_CONTRACT.md`, task write-up item 5).
//!
//! `integrity-sdk/integrity_sdk/security/redactor.py` already redacts this content
//! client-side, replacing matches with `[REDACTED:{CATEGORY}]` before telemetry ever
//! leaves the agent's process. This module is the second layer for when that client-side
//! step is buggy or bypassed: it re-runs (closely mirrored, not reinvented) versions of
//! the SDK's own regexes server-side and rejects (400) rather than silently persisting
//! raw PHI/PII/secret material. Belt-and-suspenders, not a replacement — see the SDK
//! module's own doc comment for why targeted masking (not a blanket strip) is the
//! design, and why this is a real, working backstop rather than a certified
//! de-identification system.
//!
//! Deliberately scans only JSON **string** leaves, not every field indiscriminately:
//! the SDK's redactor only ever touches free text (prompt/completion/span attribute
//! strings), so a structural/numeric field (e.g. a `nonce` transmitted as a JSON
//! number, not a string) was never something the client-side redactor would have
//! touched either — scanning it here would produce false positives the SDK's own
//! design doesn't intend to catch.

use std::sync::LazyLock;

use regex::Regex;

/// Each rule: (category name, compiled pattern). Mirrors
/// `integrity_sdk/security/redactor.py`'s `_RULES` list field-for-field (same
/// categories, same intent per pattern) — see that module for the rationale behind
/// each one. Not byte-identical Python regex syntax in every case (Rust's `regex`
/// crate has different flag syntax), but the same matched language.
static PHI_PATTERNS: LazyLock<Vec<(&'static str, Regex)>> = LazyLock::new(|| {
    vec![
        // Private key material — PEM blocks (RSA/EC/OpenSSH/generic). `(?s)` makes `.`
        // match newlines, since a real key block spans multiple lines.
        (
            "PRIVATE_KEY",
            Regex::new(r"(?s)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----").unwrap(),
        ),
        ("API_KEY", Regex::new(r"\bsk-[A-Za-z0-9]{20,}\b").unwrap()),
        ("API_KEY", Regex::new(r"\bAKIA[0-9A-Z]{16}\b").unwrap()),
        ("API_KEY", Regex::new(r"(?i)\bBearer\s+[A-Za-z0-9\-._~+/]{20,}=*").unwrap()),
        ("SSN", Regex::new(r"\b\d{3}-\d{2}-\d{4}\b").unwrap()),
        ("CREDIT_CARD", Regex::new(r"\b(?:\d[ -]*?){13,16}\b").unwrap()),
        ("EMAIL", Regex::new(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b").unwrap()),
        (
            "PHONE",
            Regex::new(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b").unwrap(),
        ),
        // Medical record number: "MRN"/"Medical Record Number" followed by an
        // alphanumeric identifier — no universal format, but this labeled convention
        // is a common, high-confidence structural marker.
        (
            "MRN",
            Regex::new(r"(?i)\b(?:MRN|Medical Record (?:Number|No\.?))[:\s#]*[A-Za-z0-9-]{4,}\b").unwrap(),
        ),
    ]
});

/// Scans one string for any raw (unredacted) PHI/PII/secret pattern. Returns the
/// (possibly-repeated) list of categories matched — callers that just need a yes/no
/// verdict with the distinct category set should dedup the aggregate, not this
/// per-string result.
pub fn scan_text(text: &str) -> Vec<&'static str> {
    PHI_PATTERNS.iter().filter(|(_, re)| re.is_match(text)).map(|(cat, _)| *cat).collect()
}

/// Recursively walks every JSON string leaf under `value` (objects/arrays walked,
/// numbers/bools/null skipped — see this module's doc comment for why non-string
/// fields are deliberately out of scope), appending any category hit to `found`.
pub fn scan_json_value(value: &serde_json::Value, found: &mut Vec<&'static str>) {
    match value {
        serde_json::Value::String(s) => found.extend(scan_text(s)),
        serde_json::Value::Array(items) => items.iter().for_each(|v| scan_json_value(v, found)),
        serde_json::Value::Object(map) => map.values().for_each(|v| scan_json_value(v, found)),
        serde_json::Value::Number(_) | serde_json::Value::Bool(_) | serde_json::Value::Null => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn catches_raw_ssn() {
        assert_eq!(scan_text("patient ssn is 123-45-6789"), vec!["SSN"]);
    }

    #[test]
    fn catches_raw_email() {
        assert_eq!(scan_text("contact jane.doe@example.com now"), vec!["EMAIL"]);
    }

    #[test]
    fn catches_raw_credit_card() {
        let hits = scan_text("card 4111111111111111 on file");
        assert!(hits.contains(&"CREDIT_CARD"), "expected CREDIT_CARD in {hits:?}");
    }

    #[test]
    fn catches_private_key_block() {
        let text = "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----";
        assert_eq!(scan_text(text), vec!["PRIVATE_KEY"]);
    }

    #[test]
    fn catches_openai_style_api_key() {
        assert_eq!(scan_text("token sk-abcdefghijklmnopqrstuvwx used"), vec!["API_KEY"]);
    }

    #[test]
    fn catches_aws_access_key() {
        assert_eq!(scan_text("key AKIAABCDEFGHIJKLMNOP leaked"), vec!["API_KEY"]);
    }

    #[test]
    fn catches_bearer_token() {
        assert_eq!(scan_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345"), vec!["API_KEY"]);
    }

    #[test]
    fn catches_phone_number() {
        assert_eq!(scan_text("call me at 555-123-4567"), vec!["PHONE"]);
    }

    #[test]
    fn catches_mrn() {
        assert_eq!(scan_text("MRN: A1234567"), vec!["MRN"]);
    }

    #[test]
    fn already_redacted_marker_is_not_reflagged() {
        // The backstop must not match the SDK's own redaction output — otherwise a
        // fully-compliant, already-redacted payload would be rejected.
        for category in ["SSN", "CREDIT_CARD", "EMAIL", "PHONE", "MRN", "API_KEY", "PRIVATE_KEY"] {
            let redacted = format!("the value was [REDACTED:{category}] in the transcript");
            assert!(scan_text(&redacted).is_empty(), "redaction marker for {category} was re-flagged: {redacted}");
        }
    }

    #[test]
    fn clean_text_passes() {
        assert!(scan_text("the agent called search_web with query weather").is_empty());
    }

    #[test]
    fn numeric_json_fields_are_never_scanned() {
        // A nonce/trace-id embedded as a JSON NUMBER (not a string) must never be
        // scanned — only string leaves are walked, mirroring the SDK's text-only scope.
        let payload = json!([{ "trace_id": 4111111111111111u64, "nonce": 42, "note": "fine" }]);
        let mut found = Vec::new();
        scan_json_value(&payload, &mut found);
        assert!(found.is_empty(), "numeric fields must not trigger a hit: {found:?}");
    }

    #[test]
    fn nested_otel_span_object_is_scanned() {
        let payload = json!([
            { "name": "llm_call", "attributes": { "completion": "my email is a@b.com" } }
        ]);
        let mut found = Vec::new();
        scan_json_value(&payload, &mut found);
        assert_eq!(found, vec!["EMAIL"]);
    }

    #[test]
    fn realistic_redacted_otel_payload_passes() {
        // A well-behaved client: the SDK already replaced the SSN with a marker before
        // transmitting. The backstop must not re-reject this — it only exists to catch
        // what the client-side redactor MISSED, not to double-flag its own output.
        let payload = json!([
            {
                "name": "llm_call",
                "attributes": {
                    "prompt": "patient ssn is [REDACTED:SSN], continue the intake form",
                    "completion": "Got it, proceeding without storing the SSN.",
                    "model": "gpt-4o",
                    "latency_ms": 812,
                    "token_count": 245
                }
            }
        ]);
        let mut found = Vec::new();
        scan_json_value(&payload, &mut found);
        assert!(found.is_empty(), "already-redacted, non-PHI telemetry must pass: {found:?}");
    }
}


/// Applies the configured backstop mode to a set of scan hits.
///
/// Returns `Ok(Some(categories))` when the payload should be STORED WITH FLAGS, `Ok(None)`
/// when it is clean or the backstop is disabled, and `Err(categories)` when it must be
/// rejected. Centralized so every ingestion path — signed telemetry and all three OTLP
/// receivers — applies one policy; four hand-rolled copies would drift.
pub fn apply_backstop(
    mode: crate::config::PhiBackstopMode,
    mut hits: Vec<&'static str>,
) -> Result<Option<Vec<String>>, Vec<String>> {
    use crate::config::PhiBackstopMode;

    if mode == PhiBackstopMode::Off || hits.is_empty() {
        // `Off` returns None rather than an empty Vec: NULL means "not flagged", whereas an
        // empty array would falsely assert "scanned and found clean".
        return Ok(None);
    }
    hits.sort_unstable();
    hits.dedup();
    let categories: Vec<String> = hits.into_iter().map(str::to_string).collect();
    match mode {
        PhiBackstopMode::Reject => Err(categories),
        PhiBackstopMode::Flag => Ok(Some(categories)),
        PhiBackstopMode::Off => unreachable!("handled above"),
    }
}

#[cfg(test)]
mod backstop_mode_tests {
    use super::*;
    use crate::config::PhiBackstopMode;

    fn hits() -> Vec<&'static str> {
        vec!["SSN", "SSN", "EMAIL"]
    }

    #[test]
    fn reject_mode_returns_the_categories_as_an_error() {
        let err = apply_backstop(PhiBackstopMode::Reject, hits()).unwrap_err();
        // Deduped and sorted, so the caller's message is stable rather than input-ordered.
        assert_eq!(err, vec!["EMAIL".to_string(), "SSN".to_string()]);
    }

    #[test]
    fn flag_mode_returns_categories_to_store_rather_than_erroring() {
        let flags = apply_backstop(PhiBackstopMode::Flag, hits()).unwrap();
        assert_eq!(flags, Some(vec!["EMAIL".to_string(), "SSN".to_string()]));
    }

    #[test]
    fn off_mode_stores_nothing_even_when_the_scan_matched() {
        assert_eq!(apply_backstop(PhiBackstopMode::Off, hits()).unwrap(), None);
    }

    #[test]
    fn a_clean_payload_is_never_flagged_in_any_mode() {
        // None rather than Some(vec![]): NULL means "not flagged", whereas an empty array
        // would falsely assert "scanned and found clean" on a row.
        for mode in [PhiBackstopMode::Reject, PhiBackstopMode::Flag, PhiBackstopMode::Off] {
            assert_eq!(apply_backstop(mode, vec![]).unwrap(), None, "mode {mode:?}");
        }
    }

    #[test]
    fn default_mode_is_reject_so_an_unconfigured_deployment_stays_strict() {
        let config = crate::config::Config::from_env_for_test(
            "http://localhost:8545".into(),
            "postgres://x".into(),
            "redis://x".into(),
        );
        assert_eq!(config.phi_backstop_mode, PhiBackstopMode::Reject);
    }
}
