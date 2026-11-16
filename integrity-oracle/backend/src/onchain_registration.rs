//! Registration v3 on-chain path (spec Part 3, proof kind 1; phase 4 plan PR 4.3).
//!
//! An agent that is already registered off-chain (`offchain_registration`) asks the Oracle to
//! vouch for it to `AgentRegistry`. The agent signs the 32-byte EIP-712 `RegisterAgent` digest
//! with its Ed25519 key; the Oracle checks that signature against the key it already holds for
//! the DID, then signs the **same** digest with its attester key (secp256k1, `ATTESTER_ROLE`).
//! The contract's `_verifyProof` recovers that ECDSA signature and checks the role.
//!
//! The Oracle computes the digest itself from the typed fields, the configured chain id and the
//! `AgentRegistry` address in the deployments file. It never signs a digest a client supplies:
//! a client-chosen digest would let it obtain an attestation for fields the agent never saw.
//!
//! The attester has no power over an existing record (the contract only consults it on
//! `register`), so the worst a stolen attester key can do is create existence records for
//! fresh fingerprints, which the guardian set in that call controls. That is why it is a
//! dedicated key, distinct from the AIS scorer.

use alloy::primitives::{keccak256, Address, B256, U256};
use alloy::signers::local::PrivateKeySigner;
use alloy::signers::SignerSync;
use alloy::sol;
use alloy::sol_types::{eip712_domain, SolStruct};
use sha2::{Digest, Sha256};

use crate::crypto::ed25519::verify_ed25519_signature;
use crate::offchain_registration::DID_PREFIX;

/// `AgentRegistry.PROOF_ATTESTATION`.
pub const PROOF_KIND_ATTESTATION: u8 = 1;
/// The EIP-712 domain `AgentRegistry`'s constructor declares: `EIP712("IntegrityAgentRegistry", "1")`.
pub const EIP712_NAME: &str = "IntegrityAgentRegistry";
pub const EIP712_VERSION: &str = "1";

sol! {
    /// Mirrors `AgentRegistry.REGISTER_AGENT_TYPEHASH`:
    /// `RegisterAgent(bytes32 pubkey,address guardian,address actor,bytes32 domainId,bytes32 uriHash,uint256 deadline)`.
    struct RegisterAgent {
        bytes32 pubkey;
        address guardian;
        address actor;
        bytes32 domainId;
        bytes32 uriHash;
        uint256 deadline;
    }
}

/// The typed fields of one `AgentRegistry.register` call, minus the proof.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RegisterFields {
    pub pubkey: B256,
    pub guardian: Address,
    pub actor: Address,
    pub domain_id: B256,
    pub uri: String,
    pub deadline: u64,
}

/// `AgentRegistry.registerDigest(...)`: `_hashTypedDataV4(keccak256(abi.encode(TYPEHASH, ...,
/// keccak256(bytes(uri)), deadline)))` under the registry's EIP-712 domain.
pub fn register_digest(chain_id: u64, registry: Address, fields: &RegisterFields) -> B256 {
    let domain = eip712_domain! {
        name: EIP712_NAME,
        version: EIP712_VERSION,
        chain_id: chain_id,
        verifying_contract: registry,
    };
    RegisterAgent {
        pubkey: fields.pubkey,
        guardian: fields.guardian,
        actor: fields.actor,
        domainId: fields.domain_id,
        uriHash: keccak256(fields.uri.as_bytes()),
        deadline: U256::from(fields.deadline),
    }
    .eip712_signing_hash(&domain)
}

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum AttestError {
    #[error("signature is malformed")]
    MalformedSignature,
    #[error("signature does not verify against the DID's registered ed25519 key")]
    BadSignature,
}

/// Checks the agent's Ed25519 signature over the raw 32-byte digest, against the key the
/// Oracle already holds for the DID (never a key from the request).
pub fn verify_agent_signature(pubkey: &[u8], digest: &B256, signature_hex: &str) -> Result<(), AttestError> {
    match verify_ed25519_signature(digest.as_slice(), signature_hex, &hex::encode(pubkey)) {
        Ok(true) => Ok(()),
        Ok(false) => Err(AttestError::BadSignature),
        Err(_) => Err(AttestError::MalformedSignature),
    }
}

/// The attester's 65-byte `r || s || v` signature over the raw digest (no EIP-191 prefix: the
/// contract recovers against the EIP-712 digest itself). `v` is 27/28, which OpenZeppelin's
/// `ECDSA.tryRecover` accepts.
pub fn attest(attester: &PrivateKeySigner, digest: &B256) -> Result<[u8; 65], alloy::signers::Error> {
    Ok(attester.sign_hash_sync(digest)?.as_bytes())
}

/// `did:integrity:<64 lowercase hex>` -> the 32-byte fingerprint (`AgentRegistry.fingerprintOfDID`).
pub fn fingerprint_of_did(did: &str) -> Option<B256> {
    let hex_part = did.strip_prefix(DID_PREFIX)?;
    if hex_part.len() != 64 || !hex_part.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
        return None;
    }
    hex_part.parse().ok()
}

/// `sha256(pubkey) == fingerprint`, the invariant every record and off-chain row must satisfy.
pub fn pubkey_matches_fingerprint(pubkey: &[u8], fingerprint: &B256) -> bool {
    Sha256::digest(pubkey).as_slice() == fingerprint.as_slice()
}

/// Settlement eligibility (plan PR 4.3): an active (not retired) record with a bound actor.
/// An existence-only record proves the key on-chain but has no gated account to settle with.
pub fn settlement_eligible(retired_at: Option<i64>, actor: Option<&str>) -> bool {
    retired_at.is_none() && actor.is_some()
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    fn vector_fields() -> RegisterFields {
        RegisterFields {
            pubkey: B256::repeat_byte(0x11),
            guardian: Address::repeat_byte(0x22),
            actor: Address::repeat_byte(0x33),
            domain_id: B256::repeat_byte(0x44),
            uri: "ipfs://x".to_string(),
            deadline: 1_700_000_000,
        }
    }

    /// Independent vector from `eth_account.messages.encode_typed_data` (Python) with the same
    /// domain and message, so a typehash, field-order or uriHash mistake here cannot agree with
    /// itself. (The Anvil e2e additionally checks against the contract's own `registerDigest`.)
    #[test]
    fn digest_matches_independent_eip712_vector() {
        let registry: Address = "0x5FbDB2315678afecb367f032d93F642f64180aa3".parse().unwrap();
        let expected: B256 = "0x0bbab02f7088d62ff5d3fe5df3b43061122f0e797f6b1b971498a62fdffcfa69".parse().unwrap();
        assert_eq!(register_digest(31337, registry, &vector_fields()), expected);
    }

    #[test]
    fn digest_binds_every_field_and_the_domain() {
        let registry = Address::repeat_byte(0x55);
        let base = register_digest(31337, registry, &vector_fields());
        let mut f = vector_fields();
        f.actor = Address::ZERO;
        assert_ne!(register_digest(31337, registry, &f), base);
        let mut f = vector_fields();
        f.uri = "ipfs://y".into();
        assert_ne!(register_digest(31337, registry, &f), base);
        let mut f = vector_fields();
        f.deadline += 1;
        assert_ne!(register_digest(31337, registry, &f), base);
        assert_ne!(register_digest(84532, registry, &vector_fields()), base);
        assert_ne!(register_digest(31337, Address::repeat_byte(0x56), &vector_fields()), base);
    }

    #[test]
    fn attestation_recovers_to_the_attester() {
        let attester = PrivateKeySigner::random();
        let digest = B256::repeat_byte(0x9a);
        let sig = attest(&attester, &digest).unwrap();
        assert!(sig[64] == 27 || sig[64] == 28, "OpenZeppelin ECDSA wants v in {{27, 28}}");
        let parsed = alloy::primitives::Signature::try_from(&sig[..]).unwrap();
        assert_eq!(parsed.recover_address_from_prehash(&digest).unwrap(), attester.address());
    }

    #[test]
    fn agent_signature_must_be_by_the_registered_key_over_this_digest() {
        let key = SigningKey::from_bytes(&[7u8; 32]);
        let other = SigningKey::from_bytes(&[8u8; 32]);
        let pubkey = key.verifying_key().to_bytes();
        let digest = B256::repeat_byte(0x01);
        let good = hex::encode(key.sign(digest.as_slice()).to_bytes());
        assert_eq!(verify_agent_signature(&pubkey, &digest, &good), Ok(()));
        let wrong_key = hex::encode(other.sign(digest.as_slice()).to_bytes());
        assert_eq!(verify_agent_signature(&pubkey, &digest, &wrong_key), Err(AttestError::BadSignature));
        let wrong_digest = hex::encode(key.sign(B256::repeat_byte(0x02).as_slice()).to_bytes());
        assert_eq!(verify_agent_signature(&pubkey, &digest, &wrong_digest), Err(AttestError::BadSignature));
        assert_eq!(verify_agent_signature(&pubkey, &digest, "zz"), Err(AttestError::MalformedSignature));
    }

    #[test]
    fn fingerprint_parsing_matches_the_contract_rules() {
        let hex64 = "ab".repeat(32);
        assert_eq!(fingerprint_of_did(&format!("did:integrity:{hex64}")), Some(B256::repeat_byte(0xab)));
        assert_eq!(fingerprint_of_did(&format!("did:integrity:{}", hex64.to_uppercase())), None);
        assert_eq!(fingerprint_of_did(&format!("did:integrity:0x{}", &hex64[2..])), None);
        assert_eq!(fingerprint_of_did("did:integrity:abc"), None);
        assert_eq!(fingerprint_of_did(&format!("did:other:{hex64}")), None);
    }

    #[test]
    fn settlement_needs_an_active_record_with_an_actor() {
        assert!(settlement_eligible(None, Some("0x1")));
        assert!(!settlement_eligible(None, None));
        assert!(!settlement_eligible(Some(1), Some("0x1")));
    }
}
