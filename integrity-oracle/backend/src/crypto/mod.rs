//! Signature verification for incoming agent-signed data, and the canonical JSON
//! encoding that signatures are computed over.
//!
//! Two schemes are supported (§4.1/§4.2 of the interface contract): Ed25519 for
//! DID-identified agents, and EIP-191 for agents whose identity is an Ethereum
//! address (e.g. one backed by `contracts/`'s `SovereignAgent`). Which one
//! applies is determined by what the *registered* agent record actually has on
//! file — never by trusting a claim in the request itself, since that would let
//! an attacker pick whichever verification scheme they can forge.

pub mod eip191;
pub mod ed25519;

use serde_json::Value;

/// Canonical JSON bytes for signing/verification, implementing RFC 8785 (JSON
/// Canonicalization Scheme). This replaces the previous hand-rolled
/// `canonicalize_json` + `AsciiEscapingFormatter` approach, which tried to match
/// Python's `json.dumps(sort_keys=True, ensure_ascii=True)` but diverged on
/// float representation (~20% signature rejection) and required maintaining two
/// independent implementations of "canonical JSON" across languages.
///
/// Now both sides (Python via `jcs.canonicalize()`, Rust via `serde_jcs::to_vec()`)
/// implement the same RFC, which mandates ECMAScript's `Number::toString` for
/// floats and UTF-8 passthrough for non-ASCII — deterministic regardless of
/// language or platform.
pub fn canonical_json_bytes(value: &Value) -> Vec<u8> {
    serde_jcs::to_vec(value).expect("JCS serialization of a valid serde_json::Value cannot fail")
}

/// What an agent is currently registered to authenticate with. An agent may have
/// either, both, or (if this is ever constructed incorrectly) neither — callers
/// must handle the "neither" case explicitly rather than assuming one is always
/// present.
pub struct AgentVerificationMethods<'a> {
    pub ed25519_pubkey_hex: Option<&'a str>,
    pub eth_address_hex: Option<&'a str>,
}

#[derive(Debug, thiserror::Error)]
pub enum VerifyError {
    #[error("agent has no registered verification method")]
    NoVerificationMethod,
    #[error("ed25519 verification error: {0}")]
    Ed25519(#[from] ed25519::Ed25519Error),
    #[error("eip191 verification error: {0}")]
    Eip191(#[from] eip191::Eip191Error),
}

/// Verifies `signature_hex` over `message` against whichever verification
/// method(s) the agent is actually registered with. Tries Ed25519 first (the
/// protocol's primary DID-based scheme), then EIP-191, and only succeeds if at
/// least one registered method validates — this is a deliberate OR, not a
/// fallback-on-failure: an agent registered with both a DID key and an eth
/// address can sign with either.
///
/// Replaces the old prototype's `verify_agent_signature`, whose entire bypass —
/// skip verification if `agent_id.starts_with("agent_")` — has no analog here:
/// there is no code path that returns "verified" without checking a real signature.
pub fn verify_agent_signature(
    message: &[u8],
    signature_hex: &str,
    methods: &AgentVerificationMethods,
) -> Result<bool, VerifyError> {
    if methods.ed25519_pubkey_hex.is_none() && methods.eth_address_hex.is_none() {
        return Err(VerifyError::NoVerificationMethod);
    }

    if let Some(pubkey) = methods.ed25519_pubkey_hex {
        if ed25519::verify_ed25519_signature(message, signature_hex, pubkey)? {
            return Ok(true);
        }
    }
    if let Some(address) = methods.eth_address_hex {
        if eip191::verify_eip191_signature(message, signature_hex, address)? {
            return Ok(true);
        }
    }
    Ok(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn jcs_sorts_nested_object_keys() {
        let value = json!({"b": 1, "a": {"z": 1, "y": 2}, "c": [3, 2, 1]});
        let canonical = canonical_json_bytes(&value);
        let expected = br#"{"a":{"y":2,"z":1},"b":1,"c":[3,2,1]}"#;
        assert_eq!(canonical, expected);
    }

    #[test]
    fn jcs_is_deterministic_regardless_of_input_key_order() {
        let a = json!({"z": 1, "a": 2});
        let b = json!({"a": 2, "z": 1});
        assert_eq!(canonical_json_bytes(&a), canonical_json_bytes(&b));
    }

    #[test]
    fn jcs_passes_non_ascii_as_raw_utf8() {
        // RFC 8785 mandates raw UTF-8 passthrough for non-ASCII characters
        // (no \uXXXX escaping). This is the key behavioral change from the old
        // AsciiEscapingFormatter — and it now matches the Python `jcs` library.
        let value = json!({"name": "café 日本語"});
        let canonical = canonical_json_bytes(&value);
        let expected = "{\"name\":\"café 日本語\"}".as_bytes();
        assert_eq!(canonical, expected);
    }

    #[test]
    fn jcs_passes_astral_characters_as_raw_utf8() {
        // U+1F389 (party popper emoji) is outside the BMP. JCS emits it as
        // raw UTF-8 bytes, not as a surrogate pair escape sequence.
        let value = json!({"emoji": "\u{1f389}"});
        let canonical = canonical_json_bytes(&value);
        let expected = "{\"emoji\":\"🎉\"}".as_bytes();
        assert_eq!(canonical, expected);
    }

    #[test]
    fn jcs_still_handles_quotes_and_backslashes_correctly() {
        let value = json!({"text": "say \"hi\"\\bye"});
        let canonical = canonical_json_bytes(&value);
        let expected = br#"{"text":"say \"hi\"\\bye"}"#;
        assert_eq!(canonical, expected);
    }

    #[test]
    fn jcs_float_uses_ecmascript_number_to_string() {
        // RFC 8785 mandates ECMAScript Number::toString for floats.
        // This is the divergence that caused ~20% signature rejections.
        let value = json!({"score": 0.1});
        let canonical = canonical_json_bytes(&value);
        // ECMAScript Number::toString(0.1) => "0.1"
        let expected = br#"{"score":0.1}"#;
        assert_eq!(canonical, expected);
    }

    #[test]
    fn no_verification_method_is_a_distinct_error_not_a_default_allow() {
        let methods = AgentVerificationMethods {
            ed25519_pubkey_hex: None,
            eth_address_hex: None,
        };
        let result = verify_agent_signature(b"anything", "0xdead", &methods);
        assert!(matches!(result, Err(VerifyError::NoVerificationMethod)));
    }
}
