//! Verifiable Credential issuance. The oracle issues a signed W3C
//! `AgentIntegrityCredential` attesting an agent's current AIS, verification tier, and a
//! derived trust level. The credential is really Ed25519-signed with the oracle's issuer
//! key (a `did:key` identity) over the canonicalized credential — not a fabricated proof.
//!
//! The issuer key comes from `VC_ISSUER_SEED` (32-byte hex); absent, a fixed development
//! seed is used so local/dev issuance is deterministic. A production deployment sets a real
//! seed (and would rotate it via the DID document's verification methods).

use chrono::Utc;
use ed25519_dalek::{Signer, SigningKey};
use serde_json::{json, Value};
use uuid::Uuid;

/// Fixed dev seed (clearly not secret) used when `VC_ISSUER_SEED` is unset.
const DEV_ISSUER_SEED_HEX: &str = "9d61b19deffdc4a4c1a2a2a2b8b8b8b8c3c3c3c3d4d4d4d4e5e5e5e5f6f6f6f60";

fn issuer_signing_key() -> SigningKey {
    let hex_seed = std::env::var("VC_ISSUER_SEED").unwrap_or_else(|_| DEV_ISSUER_SEED_HEX.to_string());
    let mut seed = [0u8; 32];
    if let Ok(bytes) = hex::decode(hex_seed.trim_start_matches("0x")) {
        if bytes.len() == 32 {
            seed.copy_from_slice(&bytes);
        }
    }
    SigningKey::from_bytes(&seed)
}

/// `did:key` for the Ed25519 issuer public key: multibase base58btc of `0xed01 || pubkey`.
fn did_key(vk_bytes: &[u8]) -> String {
    let mut prefixed = Vec::with_capacity(2 + vk_bytes.len());
    prefixed.push(0xed);
    prefixed.push(0x01);
    prefixed.extend_from_slice(vk_bytes);
    format!("did:key:z{}", bs58::encode(prefixed).into_string())
}

fn trust_level(ais: i64) -> &'static str {
    if ais >= 900 {
        "AAA"
    } else if ais >= 800 {
        "AA"
    } else if ais >= 700 {
        "A"
    } else if ais >= 500 {
        "BBB"
    } else {
        "B"
    }
}

/// Builds and Ed25519-signs an `AgentIntegrityCredential` for `subject_did`.
pub fn issue_vc(subject_did: &str, ais: i64, verification_tier: i32) -> Value {
    let sk = issuer_signing_key();
    let issuer = did_key(sk.verifying_key().as_bytes());
    let now = Utc::now().to_rfc3339();

    let mut vc = json!({
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://xibalba.solutions/contexts/agent-trust/v1"
        ],
        "id": format!("urn:uuid:{}", Uuid::new_v4()),
        "type": ["VerifiableCredential", "AgentIntegrityCredential"],
        "issuer": issuer,
        "issuanceDate": now,
        "credentialSubject": {
            "id": subject_did,
            "ais_score": ais,
            "verification_tier": verification_tier,
            "trust_level": trust_level(ais)
        }
    });

    // Sign the canonicalized credential body (proof-less) with the issuer key — the same
    // canonical-JSON scheme the oracle uses to verify agent telemetry signatures.
    let canonical = crate::crypto::canonical_json_bytes(&vc);
    let sig = sk.sign(&canonical);
    let jws = base64::Engine::encode(&base64::engine::general_purpose::URL_SAFE_NO_PAD, sig.to_bytes());

    vc["proof"] = json!({
        "type": "Ed25519Signature2020",
        "created": now,
        "verificationMethod": format!("{}#{}", issuer, issuer.rsplit(':').next().unwrap_or("key-1")),
        "proofPurpose": "assertionMethod",
        "jws": jws
    });
    vc
}
