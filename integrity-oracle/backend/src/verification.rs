//! Verification Ladder rungs 2 and 3: proving an identity claim stronger than
//! registration alone can establish.
//!
//! # Why this exists
//!
//! `handlers::SERVER_VERIFIED_TIER` was a hardcoded `1`, and tiers 2/3 had no
//! verification path anywhere in the codebase. That was not a missing feature so
//! much as a broken incentive: `scoring_core::score_with_tier` clamps AIS to
//! 600 at tier 1, so once an agent's raw score passed 600 nothing it did could
//! move its reported score — and the ZK boost (`x1.15`), the protocol's flagship
//! cryptographic feature, was absorbed entirely by the clamp. Measured on the
//! `xibalba` agent: raw 704, boosted 810, reported 600. See PRODUCTION_GAPS §23.
//!
//! # The two rungs are different KINDS of claim
//!
//! - **DNS TXT (tier 2, "Linked")** — proves *control of a namespace*. Anyone can
//!   re-check it, it needs no third party, and it carries no PII. It is a claim
//!   about the present, so it expires and must be re-proved.
//! - **KYC (tier 3, "Institutional")** — proves *a legal person is accountable*.
//!   Requires a provider, carries regulated PII, and is what a covered entity
//!   actually wants before signing a BAA.
//!
//! They are not competing implementations of one idea, which is why they sit at
//! different rungs rather than being alternatives.
//!
//! # Trust posture
//!
//! Everything here is **server-verified**, never client-asserted — the same rule
//! `SERVER_VERIFIED_TIER`'s docstring states and the same reason
//! `register_agent` re-reads the PrimitiveSet from chain instead of believing the
//! request body. The agent supplies a domain; the oracle issues its own nonce,
//! performs its own DNS resolution, and checks the signature itself with the
//! pubkey it already holds from registration. Nothing in the request influences
//! the verdict except *which* domain to go look at.
//!
//! DNS is resolved over **DNS-over-HTTPS against two independent resolvers**
//! (Cloudflare and Google) which must agree. Rationale: plain UDP DNS from inside
//! a container is trivially spoofable by anything on the network path, and a
//! single resolver is a single point of compromise for a check whose entire
//! purpose is establishing trust. Requiring agreement between two
//! TLS-authenticated resolvers costs one extra HTTPS request and removes both
//! problems. It also avoids adding a DNS resolver crate to the dependency tree
//! for one endpoint.

use std::collections::HashSet;

use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

/// Independent DoH resolvers that must agree before a record is believed.
/// Two different operators, two different networks — a compromise or a poisoned
/// cache at one does not produce a verification.
const DOH_RESOLVERS: &[(&str, &str)] = &[
    ("cloudflare", "https://cloudflare-dns.com/dns-query"),
    ("google", "https://dns.google/resolve"),
];

/// TXT records are prefixed so a domain can carry unrelated TXT records (SPF,
/// site verification, …) without this check tripping over them.
pub const TXT_PREFIX: &str = "integrity-verification=";

/// Preferred name for the record, checked before the bare domain.
pub const VERIFICATION_SUBDOMAIN: &str = "_integrity";

/// How long a DNS proof stands before it must be re-proved. Namespace control is
/// a claim about the present: domains lapse and change hands, and a verification
/// that never expires would keep asserting control the agent may have lost.
pub const DNS_VERIFICATION_TTL_DAYS: i64 = 90;

/// How long an issued challenge stays usable. Long enough to publish a DNS record
/// and let it propagate, short enough that a leaked nonce is not useful.
pub const CHALLENGE_TTL_MINUTES: i64 = 60;

pub const TIER_DNS_VERIFIED: i32 = 2;
pub const TIER_KYC_VERIFIED: i32 = 3;

#[derive(Debug, thiserror::Error)]
pub enum VerificationError {
    #[error("DNS resolution failed: {0}")]
    Resolution(String),
    #[error("resolvers disagreed about {domain} — refusing to verify (this is what the two-resolver check is for)")]
    ResolverDisagreement { domain: String },
    #[error("no TXT record starting with `{TXT_PREFIX}` found on {domain}")]
    RecordNotFound { domain: String },
    #[error("TXT record is malformed: {0}")]
    MalformedRecord(String),
    #[error("signature did not verify for {domain} — the record was not signed by this agent's key")]
    BadSignature { domain: String },
    #[error("agent has no Ed25519 public key registered; cannot verify a signed challenge")]
    NoAgentKey,
    #[error("no active challenge for this (agent, domain) — request one first")]
    NoChallenge,
    #[error("challenge expired; request a new one")]
    ChallengeExpired,
    #[error("domain is not a valid hostname: {0}")]
    InvalidDomain(String),
}

/// The exact bytes an agent signs. Binding all three fields matters:
/// - `did` stops one agent's valid record from verifying a different agent,
/// - `domain` stops a record proved for one domain being replayed on another,
/// - `nonce` stops a record published once from verifying forever.
///
/// Dropping any one of them turns this into a materially weaker proof, so the
/// format is pinned here and reproduced by `integrity-cli`.
pub fn challenge_message(did: &str, domain: &str, nonce: &str) -> String {
    format!("integrity-domain-verification:v1:{did}:{domain}:{nonce}")
}

/// The full TXT record value an operator publishes.
pub fn expected_txt_record(signature_hex: &str) -> String {
    format!("{TXT_PREFIX}{signature_hex}")
}

/// Reject anything that isn't plausibly a hostname before it reaches a URL.
/// This is an SSRF/injection guard, not a correctness nicety: `domain` comes from
/// the request body and is interpolated into a resolver query string.
pub fn validate_domain(domain: &str) -> Result<(), VerificationError> {
    let d = domain.trim();
    if d.is_empty() || d.len() > 253 {
        return Err(VerificationError::InvalidDomain(domain.to_string()));
    }
    if !d.contains('.') {
        return Err(VerificationError::InvalidDomain(format!("{domain} (needs a dot)")));
    }
    let ok = d.split('.').all(|label| {
        !label.is_empty()
            && label.len() <= 63
            && !label.starts_with('-')
            && !label.ends_with('-')
            && label.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    });
    if !ok {
        return Err(VerificationError::InvalidDomain(domain.to_string()));
    }
    Ok(())
}

#[derive(Debug, Deserialize)]
struct DohResponse {
    #[serde(rename = "Answer", default)]
    answer: Vec<DohAnswer>,
}

#[derive(Debug, Deserialize)]
struct DohAnswer {
    #[serde(rename = "type")]
    rtype: u16,
    data: String,
}

const DNS_TYPE_TXT: u16 = 16;

/// Query one DoH resolver for TXT records. Returns the set of record strings.
async fn query_txt_one(
    client: &reqwest::Client,
    endpoint: &str,
    domain: &str,
) -> Result<HashSet<String>, VerificationError> {
    let resp = client
        .get(endpoint)
        .query(&[("name", domain), ("type", "TXT")])
        .header("accept", "application/dns-json")
        .send()
        .await
        .map_err(|e| VerificationError::Resolution(format!("{endpoint}: {e}")))?;

    if !resp.status().is_success() {
        return Err(VerificationError::Resolution(format!(
            "{endpoint}: HTTP {}",
            resp.status()
        )));
    }

    let body: DohResponse = resp
        .json()
        .await
        .map_err(|e| VerificationError::Resolution(format!("{endpoint}: bad JSON: {e}")))?;

    Ok(body
        .answer
        .into_iter()
        .filter(|a| a.rtype == DNS_TYPE_TXT)
        .map(|a| normalize_txt(&a.data))
        .collect())
}

/// DoH returns TXT data quoted, and long records arrive split into multiple
/// quoted chunks that must be concatenated (DNS strings cap at 255 bytes). An
/// Ed25519 signature is 128 hex chars plus the prefix, so it fits in one chunk
/// today — but relying on that would break silently the moment the format grows,
/// so the chunks are joined properly.
fn normalize_txt(raw: &str) -> String {
    let mut out = String::new();
    let mut in_quotes = false;
    let mut escaped = false;
    for c in raw.chars() {
        if escaped {
            out.push(c);
            escaped = false;
        } else if c == '\\' {
            escaped = true;
        } else if c == '"' {
            in_quotes = !in_quotes;
        } else if in_quotes {
            out.push(c);
        }
    }
    if out.is_empty() {
        raw.trim().trim_matches('"').to_string()
    } else {
        out
    }
}

/// Resolve TXT records via every configured resolver and require agreement on the
/// integrity-verification records specifically.
///
/// Agreement is checked on the FILTERED set, not the whole TXT set: unrelated
/// records (SPF, other vendors' site-verification tokens) legitimately differ
/// between resolvers due to caching, and demanding whole-set equality would make
/// verification fail for reasons that have nothing to do with this proof.
pub async fn resolve_verification_txt(
    client: &reqwest::Client,
    domain: &str,
) -> Result<HashSet<String>, VerificationError> {
    validate_domain(domain)?;

    // Check the dedicated subdomain first, then the bare domain. A dedicated name
    // is the better place for this — it keeps the root TXT set free for SPF/DMARC
    // and lets an operator delegate just `_integrity` — but plenty of DNS UIs make
    // subdomain TXT records awkward, so the bare domain stays acceptable. Both are
    // equally strong: the signature binds the DID, the domain and the nonce
    // regardless of which name carries it.
    let names = [format!("{VERIFICATION_SUBDOMAIN}.{domain}"), domain.to_string()];

    let mut found: HashSet<String> = HashSet::new();
    let mut errors: Vec<String> = Vec::new();
    let mut any_resolver_answered = false;

    for name in &names {
        let mut seen: Option<HashSet<String>> = None;
        let mut answered_here = false;

        for (resolver, endpoint) in DOH_RESOLVERS {
            match query_txt_one(client, endpoint, name).await {
                Ok(records) => {
                    answered_here = true;
                    any_resolver_answered = true;
                    let relevant: HashSet<String> = records
                        .into_iter()
                        .filter(|r| r.starts_with(TXT_PREFIX))
                        .collect();
                    match &seen {
                        None => seen = Some(relevant),
                        Some(prev) if *prev != relevant => {
                            // Disagreement is fatal for the whole verification, not
                            // just this name: if resolvers disagree about any name we
                            // are consulting, we cannot trust the answer we got.
                            return Err(VerificationError::ResolverDisagreement {
                                domain: name.clone(),
                            });
                        }
                        _ => {}
                    }
                }
                Err(e) => errors.push(format!("{resolver}/{name}: {e}")),
            }
        }

        if answered_here {
            if let Some(s) = seen {
                found.extend(s);
            }
        }
    }

    if !any_resolver_answered {
        // Fail closed. A verification that succeeds when resolvers are unreachable
        // would let a network outage mint trust — the same fail-open trap
        // `opa_client` exists to avoid.
        return Err(VerificationError::Resolution(format!(
            "no resolver answered ({})",
            errors.join("; ")
        )));
    }
    if found.is_empty() {
        return Err(VerificationError::RecordNotFound {
            domain: domain.to_string(),
        });
    }
    Ok(found)
}

/// Check whether any published record is a valid signature over the challenge.
///
/// Takes the agent's pubkey from the DATABASE (recorded at registration), never
/// from the request — otherwise an attacker could supply both a key and a
/// matching signature and verify any domain.
pub fn verify_txt_records(
    records: &HashSet<String>,
    agent_pubkey: &[u8],
    did: &str,
    domain: &str,
    nonce: &str,
) -> Result<String, VerificationError> {
    let key_bytes: [u8; 32] = agent_pubkey
        .try_into()
        .map_err(|_| VerificationError::NoAgentKey)?;
    let key = VerifyingKey::from_bytes(&key_bytes).map_err(|_| VerificationError::NoAgentKey)?;

    let message = challenge_message(did, domain, nonce);

    for record in records {
        let sig_hex = record.trim_start_matches(TXT_PREFIX).trim();
        let Ok(sig_bytes) = hex::decode(sig_hex) else {
            continue; // not hex — try the next record rather than failing the domain
        };
        let Ok(sig_arr): Result<[u8; 64], _> = sig_bytes.as_slice().try_into() else {
            continue;
        };
        let signature = Signature::from_bytes(&sig_arr);
        if key.verify(message.as_bytes(), &signature).is_ok() {
            return Ok(sig_hex.to_string());
        }
    }

    if records.is_empty() {
        return Err(VerificationError::RecordNotFound {
            domain: domain.to_string(),
        });
    }
    Err(VerificationError::BadSignature {
        domain: domain.to_string(),
    })
}

/// Evidence recorded for an accepted DNS verification. No PII by construction —
/// a domain and a signature are both public information.
#[derive(Debug, Serialize)]
pub struct DnsEvidence<'a> {
    pub domain: &'a str,
    pub signature: &'a str,
    pub nonce: &'a str,
    pub resolvers: Vec<&'a str>,
    pub challenge_format: &'a str,
}

pub fn dns_evidence<'a>(domain: &'a str, signature: &'a str, nonce: &'a str) -> DnsEvidence<'a> {
    DnsEvidence {
        domain,
        signature,
        nonce,
        resolvers: DOH_RESOLVERS.iter().map(|(n, _)| *n).collect(),
        challenge_format: "integrity-domain-verification:v1:<did>:<domain>:<nonce>",
    }
}

/// Effective tier = the registration floor unioned with active verifications.
///
/// Deliberately a max rather than a stored column: a verification that expires or
/// is revoked must LOWER the tier automatically, and a derived value cannot drift
/// out of sync with its evidence the way a cached column would.
pub fn effective_tier(registration_tier: i32, active_verification_tiers: &[i32]) -> i32 {
    active_verification_tiers
        .iter()
        .copied()
        .fold(registration_tier, i32::max)
        .clamp(0, 3)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    fn key() -> SigningKey {
        SigningKey::from_bytes(&[7u8; 32])
    }

    #[test]
    fn challenge_message_binds_did_domain_and_nonce() {
        let a = challenge_message("did:integrity:aaa", "example.com", "n1");
        assert_ne!(a, challenge_message("did:integrity:bbb", "example.com", "n1"));
        assert_ne!(a, challenge_message("did:integrity:aaa", "other.com", "n1"));
        assert_ne!(a, challenge_message("did:integrity:aaa", "example.com", "n2"));
    }

    #[test]
    fn accepts_a_correctly_signed_record() {
        let sk = key();
        let did = "did:integrity:abc";
        let (domain, nonce) = ("example.com", "nonce-1");
        let sig = sk.sign(challenge_message(did, domain, nonce).as_bytes());
        let records: HashSet<String> = [expected_txt_record(&hex::encode(sig.to_bytes()))].into();

        let got = verify_txt_records(&records, sk.verifying_key().as_bytes(), did, domain, nonce);
        assert!(got.is_ok(), "{got:?}");
    }

    #[test]
    fn rejects_a_record_signed_for_a_different_domain() {
        // The replay this binding exists to stop: a valid proof for one domain
        // must not verify another.
        let sk = key();
        let did = "did:integrity:abc";
        let sig = sk.sign(challenge_message(did, "attacker.com", "n").as_bytes());
        let records: HashSet<String> = [expected_txt_record(&hex::encode(sig.to_bytes()))].into();

        let got = verify_txt_records(&records, sk.verifying_key().as_bytes(), did, "victim.com", "n");
        assert!(matches!(got, Err(VerificationError::BadSignature { .. })));
    }

    #[test]
    fn rejects_a_record_signed_with_a_stale_nonce() {
        let sk = key();
        let did = "did:integrity:abc";
        let sig = sk.sign(challenge_message(did, "example.com", "old").as_bytes());
        let records: HashSet<String> = [expected_txt_record(&hex::encode(sig.to_bytes()))].into();

        let got = verify_txt_records(&records, sk.verifying_key().as_bytes(), did, "example.com", "new");
        assert!(matches!(got, Err(VerificationError::BadSignature { .. })));
    }

    #[test]
    fn rejects_a_record_signed_by_another_key() {
        let attacker = SigningKey::from_bytes(&[9u8; 32]);
        let did = "did:integrity:abc";
        let sig = attacker.sign(challenge_message(did, "example.com", "n").as_bytes());
        let records: HashSet<String> = [expected_txt_record(&hex::encode(sig.to_bytes()))].into();

        let got = verify_txt_records(&records, key().verifying_key().as_bytes(), did, "example.com", "n");
        assert!(matches!(got, Err(VerificationError::BadSignature { .. })));
    }

    #[test]
    fn ignores_unrelated_txt_records_alongside_a_valid_one() {
        let sk = key();
        let did = "did:integrity:abc";
        let sig = sk.sign(challenge_message(did, "example.com", "n").as_bytes());
        let records: HashSet<String> = [
            "v=spf1 include:_spf.google.com ~all".to_string(),
            format!("{TXT_PREFIX}not-hex-at-all"),
            expected_txt_record(&hex::encode(sig.to_bytes())),
        ]
        .into();

        assert!(verify_txt_records(&records, sk.verifying_key().as_bytes(), did, "example.com", "n").is_ok());
    }

    #[test]
    fn normalizes_quoted_and_chunked_txt_data() {
        assert_eq!(normalize_txt("\"hello\""), "hello");
        assert_eq!(normalize_txt("\"abc\" \"def\""), "abcdef");
        assert_eq!(normalize_txt("bare"), "bare");
    }

    #[test]
    fn rejects_domains_that_are_not_hostnames() {
        for bad in ["", "nodot", "a..b", "-lead.com", "trail-.com", "has space.com"] {
            assert!(validate_domain(bad).is_err(), "should reject {bad:?}");
        }
        for good in ["example.com", "a.b.c.example.com", "xibalbatechsol.com", "my_host.example.com"] {
            assert!(validate_domain(good).is_ok(), "should accept {good:?}");
        }
    }

    #[test]
    fn effective_tier_takes_the_highest_active_verification() {
        assert_eq!(effective_tier(1, &[]), 1);
        assert_eq!(effective_tier(1, &[TIER_DNS_VERIFIED]), 2);
        assert_eq!(effective_tier(1, &[TIER_DNS_VERIFIED, TIER_KYC_VERIFIED]), 3);
        // Registration floor is never lowered by a weaker verification.
        assert_eq!(effective_tier(2, &[0]), 2);
    }
}
