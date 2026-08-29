//! Provider-neutral KYC receipt verification.
//!
//! The Oracle never receives documents, selfies, names, dates of birth, or government
//! identifiers. A self-hosted open-source verifier performs those checks in its own trust
//! domain and signs this deliberately narrow receipt with a configured Ed25519 key. The
//! signature proves which verifier made the assertion; the explicit assurance profile and
//! check flags prevent a sanctions-only lookup from being mislabeled as complete KYC.

use chrono::{DateTime, Duration, Utc};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use utoipa::ToSchema;

pub const OPEN_SOURCE_ASSURANCE_PROFILE: &str = "open_source_kyc_v1";
pub const MAX_RECEIPT_LIFETIME_DAYS: i64 = 365;

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, PartialEq, Eq)]
pub struct KycChecks {
    pub document_authenticity: bool,
    pub biometric_liveness: bool,
    pub sanctions_pep_screening: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct KycReceipt {
    /// Identifier matching a key in `KYC_PROVIDER_KEYS`.
    pub provider: String,
    /// Provider-local random reference. Must not contain a name, email, document number,
    /// or other directly identifying value.
    pub opaque_subject_reference: String,
    pub assurance_profile: String,
    pub checks: KycChecks,
    pub verified_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    /// Fresh nonce returned by the Oracle's KYC challenge endpoint.
    pub nonce: String,
    /// Hex Ed25519 signature over `receipt_message`.
    pub signature: String,
}

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum KycError {
    #[error("unsupported KYC assurance profile")]
    UnsupportedProfile,
    #[error("complete KYC requires document authenticity, biometric liveness, and sanctions/PEP screening")]
    IncompleteChecks,
    #[error("opaque subject reference must be 8-200 URL-safe characters")]
    InvalidSubjectReference,
    #[error("receipt nonce does not match the active Oracle challenge")]
    NonceMismatch,
    #[error("receipt validity window is invalid, expired, or longer than 365 days")]
    InvalidValidity,
    #[error("KYC receipt signature is malformed or invalid")]
    BadSignature,
}

pub fn receipt_message(agent_did: &str, receipt: &KycReceipt) -> String {
    format!(
        "integrity-kyc-receipt:v1:{agent_did}:{}:{}:{}:{}:{}:{}:{}:{}:{}",
        receipt.provider,
        receipt.opaque_subject_reference,
        receipt.assurance_profile,
        u8::from(receipt.checks.document_authenticity),
        u8::from(receipt.checks.biometric_liveness),
        u8::from(receipt.checks.sanctions_pep_screening),
        receipt.verified_at.timestamp(),
        receipt.expires_at.timestamp(),
        receipt.nonce,
    )
}

pub fn verify_receipt(
    receipt: &KycReceipt,
    agent_did: &str,
    expected_nonce: &str,
    provider_key: &[u8; 32],
    now: DateTime<Utc>,
) -> Result<String, KycError> {
    if receipt.assurance_profile != OPEN_SOURCE_ASSURANCE_PROFILE {
        return Err(KycError::UnsupportedProfile);
    }
    if !receipt.checks.document_authenticity
        || !receipt.checks.biometric_liveness
        || !receipt.checks.sanctions_pep_screening
    {
        return Err(KycError::IncompleteChecks);
    }
    if receipt.opaque_subject_reference.len() < 8
        || receipt.opaque_subject_reference.len() > 200
        || !receipt
            .opaque_subject_reference
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.' | b':'))
    {
        return Err(KycError::InvalidSubjectReference);
    }
    if receipt.nonce != expected_nonce {
        return Err(KycError::NonceMismatch);
    }
    if receipt.verified_at > now + Duration::minutes(5)
        || receipt.expires_at <= now
        || receipt.expires_at <= receipt.verified_at
        || receipt.expires_at - receipt.verified_at > Duration::days(MAX_RECEIPT_LIFETIME_DAYS)
    {
        return Err(KycError::InvalidValidity);
    }

    let message = receipt_message(agent_did, receipt);
    let key = VerifyingKey::from_bytes(provider_key).map_err(|_| KycError::BadSignature)?;
    let bytes = hex::decode(receipt.signature.trim_start_matches("0x"))
        .map_err(|_| KycError::BadSignature)?;
    let signature_bytes: [u8; 64] = bytes.try_into().map_err(|_| KycError::BadSignature)?;
    key.verify(message.as_bytes(), &Signature::from_bytes(&signature_bytes))
        .map_err(|_| KycError::BadSignature)?;

    let mut hash = Sha256::new();
    hash.update(message.as_bytes());
    hash.update(signature_bytes);
    Ok(hex::encode(hash.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    fn signed_receipt(now: DateTime<Utc>) -> (SigningKey, KycReceipt) {
        let key = SigningKey::from_bytes(&[9u8; 32]);
        let mut receipt = KycReceipt {
            provider: "open-kyc".to_string(),
            opaque_subject_reference: "subject_8f21a".to_string(),
            assurance_profile: OPEN_SOURCE_ASSURANCE_PROFILE.to_string(),
            checks: KycChecks {
                document_authenticity: true,
                biometric_liveness: true,
                sanctions_pep_screening: true,
            },
            verified_at: now - Duration::minutes(1),
            expires_at: now + Duration::days(90),
            nonce: "nonce-123".to_string(),
            signature: String::new(),
        };
        receipt.signature = hex::encode(
            key.sign(receipt_message("did:integrity:agent", &receipt).as_bytes())
                .to_bytes(),
        );
        (key, receipt)
    }

    #[test]
    fn verifies_complete_nonce_bound_provider_receipt() {
        let now = Utc::now();
        let (key, receipt) = signed_receipt(now);
        let hash = verify_receipt(
            &receipt,
            "did:integrity:agent",
            "nonce-123",
            &key.verifying_key().to_bytes(),
            now,
        )
        .unwrap();
        assert_eq!(hash.len(), 64);
    }

    #[test]
    fn receipt_cannot_be_replayed_or_downgraded() {
        let now = Utc::now();
        let (key, mut receipt) = signed_receipt(now);
        let public = key.verifying_key().to_bytes();
        assert_eq!(
            verify_receipt(&receipt, "did:integrity:agent", "other", &public, now),
            Err(KycError::NonceMismatch)
        );
        assert_eq!(
            verify_receipt(&receipt, "did:integrity:other", "nonce-123", &public, now),
            Err(KycError::BadSignature)
        );
        receipt.checks.biometric_liveness = false;
        assert_eq!(
            verify_receipt(&receipt, "did:integrity:agent", "nonce-123", &public, now),
            Err(KycError::IncompleteChecks)
        );
    }

    #[test]
    fn rejects_wrong_issuer_and_overlong_validity() {
        let now = Utc::now();
        let (_, mut receipt) = signed_receipt(now);
        let wrong_key = SigningKey::from_bytes(&[4u8; 32]);
        assert_eq!(
            verify_receipt(
                &receipt,
                "did:integrity:agent",
                "nonce-123",
                &wrong_key.verifying_key().to_bytes(),
                now,
            ),
            Err(KycError::BadSignature)
        );
        receipt.expires_at = receipt.verified_at + Duration::days(366);
        assert_eq!(
            verify_receipt(
                &receipt,
                "did:integrity:agent",
                "nonce-123",
                &wrong_key.verifying_key().to_bytes(),
                now,
            ),
            Err(KycError::InvalidValidity)
        );
    }
}
