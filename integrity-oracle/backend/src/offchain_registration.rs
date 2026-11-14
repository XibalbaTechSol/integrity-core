//! Off-chain agent registration: proof of possession without gas.
//!
//! On-chain registration (`POST /v1/agent/register`) is reserved for agents that use
//! smart contracts: it re-verifies a seven-address PrimitiveSet against
//! `XibalbaAgentRegistry` and requires an anchored genesis memory root. Most agents
//! (Shield-protected devices, Cortex-backed coding agents) never touch a contract, and
//! making them pay gas just to send signed telemetry is friction with no security
//! benefit — the DID already commits to the key.
//!
//! `did:integrity:<hex>` is `sha256(raw 32-byte Ed25519 pubkey)` (integrity_sdk/did.py
//! `fingerprint_for_pubkey`). So an agent proves it owns a DID by (1) presenting the
//! pubkey whose hash IS the DID and (2) signing a domain-separated, timestamped
//! statement with the matching private key. Nothing here trusts the client's word.
//!
//! The signed message is RFC 8785 canonical JSON of:
//!
//! ```json
//! {"did": "...", "domain": "integrity.agent.register.offchain.v1",
//!  "ed25519_pubkey_hex": "<64 lowercase hex, no 0x>", "timestamp": <unix seconds>}
//! ```
//!
//! The domain tag stops a signature made for telemetry, BCC, or DNS verification from
//! being replayed as a registration proof (and vice versa). Replaying a *registration*
//! proof is harmless — it can only re-register the same key to the same DID, which is
//! idempotent — so a freshness window bounds it without a nonce table.

use serde_json::json;
use sha2::{Digest, Sha256};

use crate::crypto::{canonical_json_bytes, ed25519::verify_ed25519_signature};

pub const DOMAIN: &str = "integrity.agent.register.offchain.v1";
pub const DID_PREFIX: &str = "did:integrity:";
/// Accepted clock skew, either direction. Five minutes matches common signed-request
/// practice and tolerates an unsynchronised laptop clock.
pub const MAX_SKEW_SECS: i64 = 300;
/// A proven Ed25519 key is tier 1 everywhere (spec Part 4, "Tier and evidence"): possession
/// of the key is the tier-1 evidence. DNS/GitHub/TEE verification raises it further.
pub const OFFCHAIN_TIER: i32 = 1;

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum ProofError {
    #[error("did must be 'did:integrity:' followed by 64 lowercase hex characters")]
    MalformedDid,
    #[error("ed25519_pubkey_hex must be 32 bytes of hex")]
    MalformedPubkey,
    #[error("did does not match sha256(ed25519_pubkey)")]
    DidKeyMismatch,
    #[error("timestamp is outside the accepted {MAX_SKEW_SECS}s window")]
    Stale,
    #[error("signature is malformed")]
    MalformedSignature,
    #[error("signature does not verify")]
    BadSignature,
}

/// Lowercase, `0x`-stripped hex — the single form both sides sign over.
pub fn normalize_hex(h: &str) -> String {
    h.strip_prefix("0x").unwrap_or(h).to_ascii_lowercase()
}

/// The exact bytes a client signs. Exposed so tests and clients agree on one encoding.
pub fn signing_message(did: &str, pubkey_hex: &str, timestamp: i64) -> Vec<u8> {
    canonical_json_bytes(&json!({
        "did": did,
        "domain": DOMAIN,
        "ed25519_pubkey_hex": normalize_hex(pubkey_hex),
        "timestamp": timestamp,
    }))
}

/// Verifies an off-chain registration proof and returns the raw pubkey bytes to store.
/// Checks run cheapest-first; every failure is a distinct error so clients can fix it.
pub fn verify_proof(
    did: &str,
    pubkey_hex: &str,
    timestamp: i64,
    signature_hex: &str,
    now: i64,
) -> Result<Vec<u8>, ProofError> {
    let fingerprint = did.strip_prefix(DID_PREFIX).ok_or(ProofError::MalformedDid)?;
    if fingerprint.len() != 64
        || !fingerprint.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err(ProofError::MalformedDid);
    }

    let pubkey_norm = normalize_hex(pubkey_hex);
    let pubkey = hex::decode(&pubkey_norm).map_err(|_| ProofError::MalformedPubkey)?;
    if pubkey.len() != 32 {
        return Err(ProofError::MalformedPubkey);
    }
    if hex::encode(Sha256::digest(&pubkey)) != fingerprint {
        return Err(ProofError::DidKeyMismatch);
    }

    if (now - timestamp).abs() > MAX_SKEW_SECS {
        return Err(ProofError::Stale);
    }

    let message = signing_message(did, &pubkey_norm, timestamp);
    match verify_ed25519_signature(&message, signature_hex, &pubkey_norm) {
        Ok(true) => Ok(pubkey),
        Ok(false) => Err(ProofError::BadSignature),
        // The pubkey already decoded to 32 bytes above, so an error here is the signature
        // (bad hex / wrong length) or a point that isn't a valid curve point.
        Err(crate::crypto::ed25519::Ed25519Error::MalformedPublicKey(_)) => {
            Err(ProofError::MalformedPubkey)
        }
        Err(_) => Err(ProofError::MalformedSignature),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    const NOW: i64 = 1_800_000_000;

    fn agent(seed: u8) -> (SigningKey, String, String) {
        let sk = SigningKey::from_bytes(&[seed; 32]);
        let pk = sk.verifying_key().to_bytes();
        let did = format!("{DID_PREFIX}{}", hex::encode(Sha256::digest(pk)));
        (sk, did, hex::encode(pk))
    }

    fn sign(sk: &SigningKey, did: &str, pk_hex: &str, ts: i64) -> String {
        hex::encode(sk.sign(&signing_message(did, pk_hex, ts)).to_bytes())
    }

    #[test]
    fn valid_proof_returns_the_pubkey() {
        let (sk, did, pk) = agent(7);
        let sig = sign(&sk, &did, &pk, NOW);
        assert_eq!(verify_proof(&did, &pk, NOW, &sig, NOW).unwrap(), hex::decode(&pk).unwrap());
    }

    #[test]
    fn accepts_0x_and_uppercase_pubkey_spellings() {
        let (sk, did, pk) = agent(7);
        let sig = sign(&sk, &did, &pk, NOW);
        let spelled = format!("0x{}", pk.to_ascii_uppercase());
        assert!(verify_proof(&did, &spelled, NOW, &sig, NOW).is_ok());
    }

    #[test]
    fn rejects_a_did_that_is_not_the_hash_of_the_key() {
        let (sk, _did, pk) = agent(7);
        let (_, other_did, _) = agent(8);
        let sig = sign(&sk, &other_did, &pk, NOW);
        assert_eq!(verify_proof(&other_did, &pk, NOW, &sig, NOW), Err(ProofError::DidKeyMismatch));
    }

    #[test]
    fn rejects_a_signature_from_a_different_key() {
        let (_, did, pk) = agent(7);
        let (attacker, _, _) = agent(9);
        let sig = sign(&attacker, &did, &pk, NOW);
        assert_eq!(verify_proof(&did, &pk, NOW, &sig, NOW), Err(ProofError::BadSignature));
    }

    #[test]
    fn rejects_a_signature_over_a_different_domain() {
        let (sk, did, pk) = agent(7);
        let foreign = canonical_json_bytes(&json!({
            "did": did, "domain": "integrity.telemetry.v1",
            "ed25519_pubkey_hex": pk, "timestamp": NOW,
        }));
        let sig = hex::encode(sk.sign(&foreign).to_bytes());
        assert_eq!(verify_proof(&did, &pk, NOW, &sig, NOW), Err(ProofError::BadSignature));
    }

    #[test]
    fn rejects_a_signature_bound_to_another_timestamp() {
        let (sk, did, pk) = agent(7);
        let sig = sign(&sk, &did, &pk, NOW - 10);
        assert_eq!(verify_proof(&did, &pk, NOW, &sig, NOW), Err(ProofError::BadSignature));
    }

    #[test]
    fn freshness_window_is_inclusive_and_symmetric() {
        let (sk, did, pk) = agent(7);
        for ts in [NOW - MAX_SKEW_SECS, NOW + MAX_SKEW_SECS] {
            assert!(verify_proof(&did, &pk, ts, &sign(&sk, &did, &pk, ts), NOW).is_ok());
        }
        for ts in [NOW - MAX_SKEW_SECS - 1, NOW + MAX_SKEW_SECS + 1] {
            let sig = sign(&sk, &did, &pk, ts);
            assert_eq!(verify_proof(&did, &pk, ts, &sig, NOW), Err(ProofError::Stale));
        }
    }

    #[test]
    fn rejects_malformed_inputs_with_specific_errors() {
        let (sk, did, pk) = agent(7);
        let sig = sign(&sk, &did, &pk, NOW);
        assert_eq!(verify_proof("did:web:x", &pk, NOW, &sig, NOW), Err(ProofError::MalformedDid));
        let upper = did.to_ascii_uppercase().replacen("DID:INTEGRITY:", DID_PREFIX, 1);
        assert_eq!(verify_proof(&upper, &pk, NOW, &sig, NOW), Err(ProofError::MalformedDid));
        assert_eq!(verify_proof(&did, "abcd", NOW, &sig, NOW), Err(ProofError::MalformedPubkey));
        assert_eq!(verify_proof(&did, &pk, NOW, "zz", NOW), Err(ProofError::MalformedSignature));
    }
}
