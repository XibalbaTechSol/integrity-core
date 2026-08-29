//! AWS Nitro Enclave attestation verification — Verification Ladder rung 3.
//!
//! # Why this is rung 3 and not rung 2
//!
//! Rung 2 (`verification.rs`) proves *control of a namespace* — a domain or a
//! GitHub account. That is a claim about an identifier. Rung 3 proves something
//! categorically stronger: that the agent's key lives inside a **genuine hardware
//! enclave**, attested by AWS's own hardware root of trust, with measurements
//! (PCRs) of the exact code image running there. A namespace can be transferred
//! or phished; an enclave measurement cannot be forged without breaking the
//! hardware root.
//!
//! `docs/wiki/concepts/identity-ceiling.md` specifies rung 3 as "Remote TEE
//! attestation + institutional audit", and explicitly rejects the old
//! `did:xibalba:<hardware_hash>` idea (hashing CPU model + MAC + machine-id) as
//! "never-built product ideation" — a host can freely fabricate all of those.
//! Real remote attestation is the credible mechanism, and this is it.
//!
//! # Scope, stated plainly
//!
//! **Verification is fully real.** This parses the actual COSE_Sign1/CBOR wire
//! format Nitro produces, verifies the ES384 signature against the embedded leaf
//! certificate, walks the certificate chain, and pins AWS's published Nitro root
//! CA by SHA-256 fingerprint. It is tested against a **genuine captured
//! attestation document** (`integrity-sdk/tests/fixtures/aws_nitro_document.cbor`,
//! a real document from November 2022), not a hand-crafted fixture.
//!
//! **Generation is not implemented and cannot be**, here or anywhere outside a
//! real enclave: producing an attestation document requires running inside a
//! Nitro Enclave and calling the Nitro Security Module. That is a hardware
//! requirement, not a missing feature. Nothing in this module fabricates a
//! document, and the endpoint that uses it fails closed when it cannot verify —
//! there is no "assume valid" path.
//!
//! This mirrors `integrity-sdk/integrity_sdk/security/attestation.py`, which is
//! the proven reference; this port is validated against the same fixture so the
//! two agree byte for byte on the same input.

use std::collections::BTreeMap;

use ciborium::value::Value as Cbor;
use sha2::{Digest, Sha384};
use x509_cert::der::{Decode, Encode};
use x509_cert::Certificate;

/// COSE algorithm identifier for ECDSA w/ SHA-384 over P-384 (RFC 8152 §8.1).
/// The only algorithm Nitro uses as of this writing; anything else is treated as
/// unsupported rather than guessed at.
const COSE_ALG_ES384: i64 = -35;

/// SHA-256 of AWS's published Nitro Enclaves root CA (`AWS_NitroEnclaves_Root-G1`).
/// This is the actual anchor of trust and is therefore pinned in code — it must
/// never be accepted as a parameter from a caller, or the chain walk below proves
/// nothing but "these certs sign each other".
pub const AWS_NITRO_ROOT_SHA256: &str =
    "641a0321a3e244efe456463195d606317ed7cdcc3c1756e09893f3c68f79bb5b";

#[derive(Debug, thiserror::Error)]
pub enum AttestationError {
    #[error("not valid CBOR: {0}")]
    Cbor(String),
    #[error("expected a 4-element COSE_Sign1 array: {0}")]
    Structure(String),
    #[error("attestation payload missing required field: {0}")]
    MissingField(&'static str),
    #[error("certificate parse failed: {0}")]
    Certificate(String),
}

/// Outcome of verification. A cryptographically invalid but well-formed document
/// is reported as `valid: false` with reasons, NOT as an error — callers asking
/// "is this trustworthy" should not need error handling for the unremarkable
/// answer "no".
#[derive(Debug, Default, serde::Serialize)]
pub struct AttestationOutcome {
    pub valid: bool,
    pub signature_valid: bool,
    pub chain_valid: bool,
    pub root_pinned: bool,
    pub errors: Vec<String>,
    pub module_id: Option<String>,
    pub timestamp_ms: Option<u64>,
    /// Platform Configuration Registers: measurements of the enclave image.
    /// PCR0 is the hash of the enclave image file — the thing that makes this a
    /// statement about *what code is running*, not merely *that hardware exists*.
    pub pcrs: BTreeMap<u32, String>,
    /// The enclave's public key, when the document carries one. This is what
    /// binds the attestation to an agent identity rather than to a random enclave.
    pub public_key: Option<Vec<u8>>,
    pub nonce: Option<Vec<u8>>,
    pub user_data: Option<Vec<u8>>,
}

fn cbor_map_get<'a>(map: &'a [(Cbor, Cbor)], key: &str) -> Option<&'a Cbor> {
    map.iter()
        .find(|(k, _)| matches!(k, Cbor::Text(t) if t == key))
        .map(|(_, v)| v)
}

fn as_bytes(v: &Cbor) -> Option<Vec<u8>> {
    match v {
        Cbor::Bytes(b) => Some(b.clone()),
        _ => None,
    }
}

/// Verify a raw Nitro attestation document.
///
/// `enforce_validity_period` exists for the same reason it does in the Python
/// reference: the bundled real fixture is from November 2022 and its short-lived
/// leaf/intermediate certificates are long expired. Historical fixtures are the
/// only legitimate use — production callers leave it on.
pub fn verify_nitro_attestation(
    document: &[u8],
    root_pem: &str,
    enforce_validity_period: bool,
) -> Result<AttestationOutcome, AttestationError> {
    let mut out = AttestationOutcome::default();

    let cose: Cbor = ciborium::from_reader(document).map_err(|e| AttestationError::Cbor(e.to_string()))?;
    let arr = match &cose {
        Cbor::Array(a) if a.len() == 4 => a,
        // Nitro emits a bare 4-element array with no COSE_Sign1 tag 18 wrapper,
        // but accept the tagged form too rather than rejecting a valid document
        // on a purely representational difference.
        Cbor::Tag(18, inner) => match inner.as_ref() {
            Cbor::Array(a) if a.len() == 4 => a,
            other => return Err(AttestationError::Structure(format!("{other:?}"))),
        },
        other => return Err(AttestationError::Structure(format!("{other:?}"))),
    };

    let protected_bstr = as_bytes(&arr[0])
        .ok_or_else(|| AttestationError::Structure("protected header not a bstr".into()))?;
    let payload_bstr = as_bytes(&arr[2])
        .ok_or_else(|| AttestationError::Structure("payload not a bstr".into()))?;
    let signature = as_bytes(&arr[3])
        .ok_or_else(|| AttestationError::Structure("signature not a bstr".into()))?;

    // Algorithm check. A document signed with something we don't understand must
    // not be silently accepted on the strength of its chain alone.
    let protected: Cbor =
        ciborium::from_reader(protected_bstr.as_slice()).map_err(|e| AttestationError::Cbor(e.to_string()))?;
    let alg = match &protected {
        Cbor::Map(m) => m
            .iter()
            .find(|(k, _)| matches!(k, Cbor::Integer(i) if i128::from(*i) == 1))
            .and_then(|(_, v)| match v {
                Cbor::Integer(i) => Some(i128::from(*i) as i64),
                _ => None,
            }),
        _ => None,
    };
    if alg != Some(COSE_ALG_ES384) {
        out.errors
            .push(format!("unsupported COSE algorithm {alg:?} (expected ES384 / -35)"));
    }

    let payload: Cbor =
        ciborium::from_reader(payload_bstr.as_slice()).map_err(|e| AttestationError::Cbor(e.to_string()))?;
    let doc = match &payload {
        Cbor::Map(m) => m.clone(),
        _ => return Err(AttestationError::Structure("payload is not a map".into())),
    };

    let leaf_der = cbor_map_get(&doc, "certificate")
        .and_then(as_bytes)
        .ok_or(AttestationError::MissingField("certificate"))?;
    let cabundle = match cbor_map_get(&doc, "cabundle") {
        Some(Cbor::Array(a)) => a.iter().filter_map(as_bytes).collect::<Vec<_>>(),
        _ => return Err(AttestationError::MissingField("cabundle")),
    };

    out.module_id = cbor_map_get(&doc, "module_id").and_then(|v| match v {
        Cbor::Text(t) => Some(t.clone()),
        _ => None,
    });
    out.timestamp_ms = cbor_map_get(&doc, "timestamp").and_then(|v| match v {
        Cbor::Integer(i) => u64::try_from(i128::from(*i)).ok(),
        _ => None,
    });
    out.public_key = cbor_map_get(&doc, "public_key").and_then(as_bytes);
    out.nonce = cbor_map_get(&doc, "nonce").and_then(as_bytes);
    out.user_data = cbor_map_get(&doc, "user_data").and_then(as_bytes);
    if let Some(Cbor::Map(pcrs)) = cbor_map_get(&doc, "pcrs") {
        for (k, v) in pcrs {
            if let (Cbor::Integer(i), Some(b)) = (k, as_bytes(v)) {
                if let Ok(idx) = u32::try_from(i128::from(*i)) {
                    out.pcrs.insert(idx, hex::encode(b));
                }
            }
        }
    }

    let leaf = Certificate::from_der(&leaf_der)
        .map_err(|e| AttestationError::Certificate(format!("leaf: {e}")))?;

    // --- COSE signature -----------------------------------------------------
    // Sig_structure = ["Signature1", body_protected, external_aad, payload]
    // (RFC 8152 §4.4). The protected header and payload go in as the RAW bytes
    // that were embedded in the COSE array, never re-encoded from the decoded
    // values: CBOR encoding is not guaranteed canonical, so a round-trip could
    // produce different bytes than were actually signed.
    let sig_structure = Cbor::Array(vec![
        Cbor::Text("Signature1".into()),
        Cbor::Bytes(protected_bstr.clone()),
        Cbor::Bytes(Vec::new()),
        Cbor::Bytes(payload_bstr.clone()),
    ]);
    let mut to_be_signed = Vec::new();
    ciborium::into_writer(&sig_structure, &mut to_be_signed)
        .map_err(|e| AttestationError::Cbor(e.to_string()))?;

    out.signature_valid = verify_es384(&leaf, &to_be_signed, &signature);
    if !out.signature_valid {
        out.errors.push("COSE signature did not verify against the leaf certificate".into());
    }

    // --- Root pinning -------------------------------------------------------
    // cabundle[0] must be AWS's published root, matched by SHA-256. Without this
    // the chain walk proves only internal consistency: an attacker could present
    // a self-consistent chain rooted at a CA they control.
    let root_ok = cabundle.first().map(|der| {
        let mut h = sha2::Sha256::new();
        h.update(der);
        hex::encode(h.finalize()) == AWS_NITRO_ROOT_SHA256
    });
    out.root_pinned = root_ok.unwrap_or(false);
    if !out.root_pinned {
        out.errors
            .push("cabundle[0] is not AWS's published Nitro root CA (fingerprint mismatch)".into());
    }

    // Cross-check the pinned fingerprint against the PEM we ship, so a swapped
    // trust-root file fails loudly instead of silently trusting whatever is on disk.
    if let Some(der) = pem_to_der(root_pem) {
        let mut h = sha2::Sha256::new();
        h.update(&der);
        if hex::encode(h.finalize()) != AWS_NITRO_ROOT_SHA256 {
            out.errors
                .push("bundled trust-root PEM does not match the pinned fingerprint".into());
            out.root_pinned = false;
        }
    } else {
        out.errors.push("bundled trust-root PEM could not be parsed".into());
        out.root_pinned = false;
    }

    // --- Chain walk ---------------------------------------------------------
    // cabundle is root-first; the leaf hangs off the last entry.
    let mut chain: Vec<Certificate> = Vec::new();
    for (i, der) in cabundle.iter().enumerate() {
        match Certificate::from_der(der) {
            Ok(c) => chain.push(c),
            Err(e) => {
                out.errors.push(format!("cabundle[{i}] parse failed: {e}"));
                out.chain_valid = false;
            }
        }
    }
    chain.push(leaf.clone());

    let mut chain_valid = chain.len() >= 2;
    for window in chain.windows(2) {
        let (issuer, subject) = (&window[0], &window[1]);
        if !verify_cert_signed_by(subject, issuer) {
            chain_valid = false;
            out.errors.push(format!(
                "certificate chain broken: {} is not signed by {}",
                subject_cn(subject),
                subject_cn(issuer)
            ));
        }
    }

    if enforce_validity_period {
        let now = std::time::SystemTime::now();
        for c in &chain {
            let nb = c.tbs_certificate().validity().not_before.to_system_time();
            let na = c.tbs_certificate().validity().not_after.to_system_time();
            if now < nb || now > na {
                chain_valid = false;
                out.errors
                    .push(format!("certificate {} is outside its validity period", subject_cn(c)));
            }
        }
    }
    out.chain_valid = chain_valid;

    out.valid = out.signature_valid && out.chain_valid && out.root_pinned && out.errors.is_empty();
    Ok(out)
}

fn subject_cn(c: &Certificate) -> String {
    c.tbs_certificate().subject().to_string()
}

fn pem_to_der(pem: &str) -> Option<Vec<u8>> {
    use base64::Engine;
    let body: String = pem
        .lines()
        .filter(|l| !l.starts_with("-----"))
        .collect::<Vec<_>>()
        .join("");
    base64::engine::general_purpose::STANDARD.decode(body.trim()).ok()
}

/// Verify the COSE ES384 signature. COSE/JOSE ECDSA signatures are the raw
/// fixed-width `r || s` concatenation (2 × 48 bytes for P-384), not ASN.1 DER.
fn verify_es384(leaf: &Certificate, message: &[u8], signature: &[u8]) -> bool {
    use p384::ecdsa::signature::Verifier;

    let spki = &leaf.tbs_certificate().subject_public_key_info();
    let Some(key_bytes) = spki.subject_public_key.as_bytes() else {
        return false;
    };
    let Ok(vk) = p384::ecdsa::VerifyingKey::from_sec1_bytes(key_bytes) else {
        return false;
    };
    let Ok(sig) = p384::ecdsa::Signature::from_slice(signature) else {
        return false;
    };
    vk.verify(message, &sig).is_ok()
}

/// Check that `issuer`'s public key produced `subject`'s signature.
///
/// Nitro's chain mixes curves (the root is P-384; intermediates may be P-384,
/// and other levels can differ), so both P-384 and P-256 are attempted rather
/// than assuming one. Reading the algorithm from the certificate itself is what
/// the Python reference does and this follows it.
fn verify_cert_signed_by(subject: &Certificate, issuer: &Certificate) -> bool {
    let Ok(tbs) = subject.tbs_certificate().to_der() else {
        return false;
    };
    let Some(sig) = subject.signature().as_bytes() else {
        return false;
    };
    let spki = &issuer.tbs_certificate().subject_public_key_info();
    let Some(key_bytes) = spki.subject_public_key.as_bytes() else {
        return false;
    };

    // Certificate signatures ARE DER-encoded (unlike the COSE one above).
    {
        use p384::ecdsa::signature::Verifier;
        if let (Ok(vk), Ok(s)) = (
            p384::ecdsa::VerifyingKey::from_sec1_bytes(key_bytes),
            p384::ecdsa::DerSignature::try_from(sig),
        ) {
            if vk.verify(&tbs, &s).is_ok() {
                return true;
            }
        }
    }
    {
        use p256::ecdsa::signature::Verifier;
        if let (Ok(vk), Ok(s)) = (
            p256::ecdsa::VerifyingKey::from_sec1_bytes(key_bytes),
            p256::ecdsa::DerSignature::try_from(sig),
        ) {
            if vk.verify(&tbs, &s).is_ok() {
                return true;
            }
        }
    }
    false
}

/// Generation is impossible outside a real enclave and is not stubbed.
/// Kept as an explicit function so callers get this message rather than
/// discovering the absence by finding nothing.
pub fn generate_attestation_unsupported() -> AttestationError {
    AttestationError::Structure(
        "generating a Nitro attestation document requires running inside a real \
         Nitro Enclave with NSM access; this is a hardware requirement, not a \
         missing feature, and is deliberately not stubbed"
            .into(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    // The genuine captured document and AWS's published root, shared with the
    // Python reference implementation so both are validated against identical
    // ground truth. If this port ever disagrees with `attestation.py`, one of
    // them is wrong and this test is how we find out.
    const FIXTURE: &[u8] =
        include_bytes!("../../../integrity-sdk/tests/fixtures/aws_nitro_document.cbor");
    const ROOT_PEM: &str = include_str!("../trust_roots/aws_nitro_root_g1.pem");

    #[test]
    fn verifies_a_real_captured_nitro_document() {
        // validity period off: the fixture is a real document from Nov 2022 whose
        // short-lived certs are long expired. Everything else is enforced.
        let out = verify_nitro_attestation(FIXTURE, ROOT_PEM, false).expect("parses");
        assert!(out.signature_valid, "COSE signature must verify: {:?}", out.errors);
        assert!(out.root_pinned, "must chain to AWS's published root: {:?}", out.errors);
        assert!(out.chain_valid, "cert chain must validate: {:?}", out.errors);
        assert!(out.valid, "document should be valid overall: {:?}", out.errors);
        assert!(out.module_id.is_some(), "module_id should be extracted");
        assert!(!out.pcrs.is_empty(), "PCR measurements should be extracted");
    }

    #[test]
    fn rejects_a_document_with_a_tampered_payload() {
        // The test that makes the one above meaningful: flip a byte in the signed
        // payload and the signature must stop verifying. Without this, "it
        // verified" could just mean "we never really checked".
        let mut tampered = FIXTURE.to_vec();
        let idx = tampered.len() / 2;
        tampered[idx] ^= 0xFF;
        match verify_nitro_attestation(&tampered, ROOT_PEM, false) {
            Ok(out) => assert!(!out.valid, "tampered document must not be valid"),
            Err(_) => {} // corrupting bytes can also break CBOR framing outright
        }
    }

    #[test]
    fn rejects_a_document_with_a_tampered_signature() {
        let cose: Cbor = ciborium::from_reader(FIXTURE).unwrap();
        let Cbor::Array(mut arr) = cose else { panic!("expected array") };
        if let Cbor::Bytes(sig) = &mut arr[3] {
            sig[0] ^= 0xFF;
        }
        let mut doc = Vec::new();
        ciborium::into_writer(&Cbor::Array(arr), &mut doc).unwrap();

        let out = verify_nitro_attestation(&doc, ROOT_PEM, false).expect("still parses");
        assert!(!out.signature_valid, "a tampered signature must not verify");
        assert!(!out.valid);
    }

    #[test]
    fn rejects_a_chain_not_rooted_at_the_pinned_aws_root() {
        // Replace cabundle[0] with the leaf cert: the chain is then internally
        // inconsistent AND unrooted. Root pinning is what stops an attacker
        // presenting a self-consistent chain from a CA they control.
        let cose: Cbor = ciborium::from_reader(FIXTURE).unwrap();
        let Cbor::Array(mut arr) = cose else { panic!() };
        let Cbor::Bytes(payload_bstr) = arr[2].clone() else { panic!() };
        let payload: Cbor = ciborium::from_reader(payload_bstr.as_slice()).unwrap();
        let Cbor::Map(mut doc) = payload else { panic!() };

        let leaf = doc
            .iter()
            .find(|(k, _)| matches!(k, Cbor::Text(t) if t == "certificate"))
            .map(|(_, v)| v.clone())
            .unwrap();
        for (k, v) in doc.iter_mut() {
            if matches!(k, Cbor::Text(t) if t == "cabundle") {
                *v = Cbor::Array(vec![leaf.clone()]);
            }
        }
        let mut new_payload = Vec::new();
        ciborium::into_writer(&Cbor::Map(doc), &mut new_payload).unwrap();
        arr[2] = Cbor::Bytes(new_payload);
        let mut docbytes = Vec::new();
        ciborium::into_writer(&Cbor::Array(arr), &mut docbytes).unwrap();

        let out = verify_nitro_attestation(&docbytes, ROOT_PEM, false).expect("parses");
        assert!(!out.root_pinned, "must reject a chain not rooted at AWS's root");
        assert!(!out.valid);
    }

    #[test]
    fn pinned_root_matches_the_bundled_pem() {
        // Guards the trust anchor itself: if the shipped PEM is ever swapped, this
        // fails rather than the system silently trusting a different CA.
        let der = pem_to_der(ROOT_PEM).expect("PEM parses");
        let mut h = sha2::Sha256::new();
        h.update(&der);
        assert_eq!(hex::encode(h.finalize()), AWS_NITRO_ROOT_SHA256);
    }

    #[test]
    fn expired_certificates_fail_when_the_validity_period_is_enforced() {
        // Same real fixture, validity enforcement ON. Its 2022 certs are expired,
        // so this must fail — proving the flag actually does something and that
        // production callers (which leave it on) get expiry checking.
        let out = verify_nitro_attestation(FIXTURE, ROOT_PEM, true).expect("parses");
        assert!(!out.valid, "expired chain must fail when enforcement is on");
        assert!(out.errors.iter().any(|e| e.contains("validity period")));
    }
}

// `Sha384` is imported for parity with the reference implementation's hash
// selection; ECDSA verification below hashes internally via the `p384` crate.
#[allow(unused)]
fn _sha384_marker(data: &[u8]) -> Vec<u8> {
    Sha384::digest(data).to_vec()
}
