//! Verification Ladder rungs 2 and 3: proving an identity claim stronger than
//! registration alone can establish.
//!
//! # Why this exists
//!
//! Registration deliberately establishes only a tier-1 floor. Without stronger
//! evidence, `scoring_core::score_with_tier` clamps AIS to
//! 600 at tier 1, so once an agent's raw score passed 600 nothing it did could
//! move its reported score — and the ZK boost (`x1.15`), the protocol's flagship
//! cryptographic feature, was absorbed entirely by the clamp. Measured on the
//! `xibalba` agent: raw 704, boosted 810, reported 600. See PRODUCTION_GAPS §23.
//!
//! # The rungs establish different kinds of claim
//!
//! - **DNS TXT (tier 2, "Linked")** — proves *control of a namespace*. Anyone can
//!   re-check it, it needs no third party, and it carries no PII. It is a claim
//!   about the present, so it expires and must be re-proved.
//! - **GitHub (tier 2, "Linked")** — proves control of a public GitHub namespace
//!   by checking a signed challenge in a repository owned by that login.
//! - **AWS Nitro (tier 3, "Institutional")** — proves a live enclave produced a
//!   nonce-bound attestation chaining to AWS's Nitro root. See `attestation.rs`.
//! - **KYC (tier 3)** accepts only nonce-bound receipts signed by an operator-configured
//!   provider trust root. The provider can be a self-hosted open-source stack; raw PII
//!   never enters the Oracle. See `kyc.rs`.
//!
//! Evidence expires or can be agent-revoked; the effective tier is derived from
//! active rows on every read, so removing the strongest evidence immediately
//! lowers the ceiling.
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
    #[error("verification-revocation signature is malformed or does not match the registered agent key")]
    BadRevocationSignature,
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

/// Exact bytes signed to revoke one evidence row. Hex-encoding the UTF-8 reason
/// removes delimiter ambiguity while keeping the signed representation portable
/// across SDK/CLI implementations.
pub fn revocation_message(
    did: &str,
    verification_id: i64,
    nonce: &str,
    reason: &str,
) -> String {
    format!(
        "integrity-verification-revoke:v1:{did}:{verification_id}:{nonce}:{}",
        hex::encode(reason.as_bytes())
    )
}

/// Verify an agent-authorized revocation against the Ed25519 key stored at
/// registration. The key is never accepted from the request.
pub fn verify_revocation_signature(
    agent_pubkey: &[u8],
    did: &str,
    verification_id: i64,
    nonce: &str,
    reason: &str,
    signature_hex: &str,
) -> Result<(), VerificationError> {
    let key_bytes: [u8; 32] = agent_pubkey
        .try_into()
        .map_err(|_| VerificationError::NoAgentKey)?;
    let key = VerifyingKey::from_bytes(&key_bytes).map_err(|_| VerificationError::NoAgentKey)?;
    let sig_bytes = hex::decode(signature_hex.trim_start_matches("0x"))
        .map_err(|_| VerificationError::BadRevocationSignature)?;
    let sig_arr: [u8; 64] = sig_bytes
        .as_slice()
        .try_into()
        .map_err(|_| VerificationError::BadRevocationSignature)?;
    let signature = Signature::from_bytes(&sig_arr);
    key.verify(
        revocation_message(did, verification_id, nonce, reason).as_bytes(),
        &signature,
    )
    .map_err(|_| VerificationError::BadRevocationSignature)
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
    fn revocation_signature_binds_agent_row_nonce_and_reason() {
        let signing_key = key();
        let did = "did:integrity:aaa";
        let message = revocation_message(did, 42, "nonce-1", "key rotated");
        let signature = signing_key.sign(message.as_bytes());
        let signature_hex = hex::encode(signature.to_bytes());
        let pubkey = signing_key.verifying_key().to_bytes();

        verify_revocation_signature(&pubkey, did, 42, "nonce-1", "key rotated", &signature_hex)
            .expect("valid revocation signature");
        assert!(verify_revocation_signature(&pubkey, did, 43, "nonce-1", "key rotated", &signature_hex).is_err());
        assert!(verify_revocation_signature(&pubkey, did, 42, "nonce-2", "key rotated", &signature_hex).is_err());
        assert!(verify_revocation_signature(&pubkey, did, 42, "nonce-1", "different", &signature_hex).is_err());
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

// ---------------------------------------------------------------------------
// Rung 2, automated variant: control of a GitHub identity
// ---------------------------------------------------------------------------
// Same claim as DNS TXT — "I control this namespace" — proved against a namespace
// the agent can WRITE TO PROGRAMMATICALLY. That difference is the whole point:
// publishing a DNS TXT record is a human editing a zone file, so the ladder could
// never be climbed unattended. Creating a public gist is one authenticated API
// call, so an agent can prove control of its own identity with no operator in the
// loop.
//
// WHY NOT WHOIS (asked for, and deliberately not built):
// WHOIS is a PUBLIC RECORD LOOKUP. Anyone can read the WHOIS of any domain, so
// "the WHOIS record exists" is not evidence that *this agent* controls it — this
// oracle could 'verify' google.com from a laptop. Verification requires the agent
// to do something only the controller could do; reading public data never
// qualifies, no matter how authoritative the source. WHOIS is also widely
// redacted post-GDPR, so it often cannot even identify a registrant. It could at
// best corroborate an already-proven claim, never establish one.
//
// The proof here is the same shape as DNS: the oracle issues a nonce, the agent
// signs it, and the oracle independently reads the result from a place only the
// account holder can write to. Ownership is established by GitHub's own API
// reporting who owns the gist — not by anything the client tells us.

/// Filename the signed challenge must be published under, so a gist listing can
/// be scanned without fetching every gist body.
pub const GITHUB_MARKER_FILENAME: &str = "integrity-verification.txt";

/// Path inside a repository where the challenge is published. `.well-known/` is
/// the established convention for machine-readable proofs (RFC 8615), and using
/// it means a GitHub Pages repo serves the same artefact over HTTPS at a stable
/// URL as a side effect.
pub const GITHUB_REPO_MARKER_PATH: &str = ".well-known/integrity-verification.txt";

/// Fetch the challenge from a file in a PUBLIC repository the claimed login owns.
///
/// Preferred over gists in practice: creating a gist needs a token scope that
/// fine-grained PATs frequently cannot grant at all (observed here as
/// `403 Resource not accessible by personal access token`), whereas writing a
/// file to a repo the account already owns is the ordinary case. The proof is
/// identical in strength — both are namespaces only the account holder can write
/// to, and in both cases GitHub's API, not the client, is the authority on who
/// owns the artefact.
pub async fn fetch_github_repo_payload(
    client: &reqwest::Client,
    login: &str,
    repo: &str,
) -> Result<String, VerificationError> {
    validate_github_login(login)?;
    validate_github_login(repo_label(repo))?;

    // Confirm the repo is public AND owned by the claimed login before reading
    // anything out of it. Without the ownership re-check a client could name
    // someone else's repo that happens to contain a marker file.
    let meta_url = format!("https://api.github.com/repos/{login}/{repo}");
    let meta = client
        .get(&meta_url)
        .header("accept", "application/vnd.github+json")
        .send()
        .await
        .map_err(|e| VerificationError::Resolution(format!("github repo: {e}")))?;

    if meta.status() == reqwest::StatusCode::NOT_FOUND {
        return Err(VerificationError::RecordNotFound {
            domain: format!("github {login}/{repo} (not found or not public)"),
        });
    }
    if meta.status() == reqwest::StatusCode::FORBIDDEN {
        return Err(VerificationError::Resolution(
            "github API rate limit or access denied (unauthenticated limit is 60/hr)".to_string(),
        ));
    }
    if !meta.status().is_success() {
        return Err(VerificationError::Resolution(format!(
            "github repo: HTTP {}",
            meta.status()
        )));
    }

    #[derive(Deserialize)]
    struct RepoMeta {
        private: bool,
        owner: GistOwner,
    }
    let meta: RepoMeta = meta
        .json()
        .await
        .map_err(|e| VerificationError::Resolution(format!("github repo: bad JSON: {e}")))?;

    if meta.private {
        // A private artefact cannot be re-checked by anyone else, which defeats
        // the point of a claim third parties are meant to be able to audit.
        return Err(VerificationError::MalformedRecord(format!(
            "{login}/{repo} is private; the proof must be publicly verifiable"
        )));
    }
    if meta.owner.login.to_lowercase() != login.to_lowercase() {
        return Err(VerificationError::MalformedRecord(format!(
            "{repo} is owned by {}, not {login}",
            meta.owner.login
        )));
    }

    let raw_url =
        format!("https://raw.githubusercontent.com/{login}/{repo}/HEAD/{GITHUB_REPO_MARKER_PATH}");
    let body = client
        .get(&raw_url)
        .send()
        .await
        .map_err(|e| VerificationError::Resolution(format!("github raw: {e}")))?;
    if !body.status().is_success() {
        return Err(VerificationError::RecordNotFound {
            domain: format!("github {login}/{repo}:{GITHUB_REPO_MARKER_PATH}"),
        });
    }
    body.text()
        .await
        .map(|t| t.trim().to_string())
        .map_err(|e| VerificationError::Resolution(format!("github raw: {e}")))
}

/// Repo names allow `.` and `_` which logins do not, so strip the parts that a
/// login validator would reject before reusing it as a cheap syntax guard.
fn repo_label(repo: &str) -> &str {
    repo.split(['.', '_']).next().unwrap_or(repo)
}

/// GitHub logins: alphanumeric and hyphens, max 39 chars, no leading/trailing or
/// doubled hyphen. Validated before interpolation into an API path.
pub fn validate_github_login(login: &str) -> Result<(), VerificationError> {
    let l = login.trim();
    if l.is_empty() || l.len() > 39 {
        return Err(VerificationError::InvalidDomain(format!("github login {login:?}")));
    }
    let ok = l.chars().all(|c| c.is_ascii_alphanumeric() || c == '-')
        && !l.starts_with('-')
        && !l.ends_with('-')
        && !l.contains("--");
    if !ok {
        return Err(VerificationError::InvalidDomain(format!("github login {login:?}")));
    }
    Ok(())
}

/// The subject string a GitHub verification is recorded under, and the value bound
/// into the signed message. Namespaced so a github login can never collide with a
/// domain in the `identity_verifications` unique index.
pub fn github_subject(login: &str) -> String {
    format!("github:{}", login.to_lowercase())
}

#[derive(Debug, Deserialize)]
struct GistListEntry {
    id: String,
    public: bool,
    files: std::collections::HashMap<String, GistFile>,
    owner: Option<GistOwner>,
}

#[derive(Debug, Deserialize)]
struct GistFile {
    raw_url: Option<String>,
}

#[derive(Debug, Deserialize)]
struct GistOwner {
    login: String,
}

/// Fetch the signed challenge from the claimed account's PUBLIC gists.
///
/// Server-verified end to end: we ask GitHub for *that login's* gists rather than
/// letting the client hand us a gist id, and we re-check `owner.login` on the
/// entry we use. A client cannot point us at someone else's gist, and cannot
/// claim a login it does not own — GitHub's API is the authority on who owns what.
///
/// Only PUBLIC gists count. A private one would make the proof unverifiable by
/// anyone but us, which defeats the purpose of a claim others are meant to be
/// able to re-check.
pub async fn fetch_github_challenge_payloads(
    client: &reqwest::Client,
    login: &str,
) -> Result<Vec<String>, VerificationError> {
    validate_github_login(login)?;

    let list_url = format!("https://api.github.com/users/{login}/gists?per_page=100");
    let resp = client
        .get(&list_url)
        .header("accept", "application/vnd.github+json")
        .send()
        .await
        .map_err(|e| VerificationError::Resolution(format!("github list: {e}")))?;

    if resp.status() == reqwest::StatusCode::NOT_FOUND {
        return Err(VerificationError::RecordNotFound {
            domain: format!("github user {login}"),
        });
    }
    if resp.status() == reqwest::StatusCode::FORBIDDEN {
        // Unauthenticated GitHub API is 60 req/hr per IP. Say so plainly instead
        // of surfacing a bare 403 that reads like a permissions problem.
        return Err(VerificationError::Resolution(
            "github API rate limit or access denied (unauthenticated limit is 60/hr) — retry later"
                .to_string(),
        ));
    }
    if !resp.status().is_success() {
        return Err(VerificationError::Resolution(format!(
            "github list: HTTP {}",
            resp.status()
        )));
    }

    let gists: Vec<GistListEntry> = resp
        .json()
        .await
        .map_err(|e| VerificationError::Resolution(format!("github list: bad JSON: {e}")))?;

    let want = login.to_lowercase();
    let mut payloads = Vec::new();

    for gist in gists {
        if !gist.public {
            continue;
        }
        // Re-check ownership on the entry itself rather than trusting that the
        // listing endpoint only ever returns this user's gists.
        match &gist.owner {
            Some(o) if o.login.to_lowercase() == want => {}
            _ => continue,
        }
        let Some(file) = gist.files.get(GITHUB_MARKER_FILENAME) else {
            continue;
        };
        let Some(raw_url) = file.raw_url.as_deref() else {
            continue;
        };
        // Only follow gist raw URLs on GitHub's own host — `raw_url` comes from an
        // API response, and blindly fetching a URL from a response body is an SSRF
        // primitive.
        if !raw_url.starts_with("https://gist.githubusercontent.com/") {
            continue;
        }
        if let Ok(body_resp) = client.get(raw_url).send().await {
            if body_resp.status().is_success() {
                if let Ok(text) = body_resp.text().await {
                    payloads.push(text.trim().to_string());
                }
            }
        }
        let _ = &gist.id; // id is not trusted for anything; ownership is what matters
    }

    if payloads.is_empty() {
        return Err(VerificationError::RecordNotFound {
            domain: format!("github user {login} (no public gist named {GITHUB_MARKER_FILENAME})"),
        });
    }
    Ok(payloads)
}

/// Verify one of the fetched payloads is a valid signature over the challenge.
/// Payloads may carry the same `integrity-verification=` prefix as a TXT record
/// (so the published artefact looks identical in both methods) or be a bare hex
/// signature.
pub fn verify_github_payloads(
    payloads: &[String],
    agent_pubkey: &[u8],
    did: &str,
    subject: &str,
    nonce: &str,
) -> Result<String, VerificationError> {
    let records: HashSet<String> = payloads
        .iter()
        .map(|p| {
            let t = p.trim();
            if t.starts_with(TXT_PREFIX) {
                t.to_string()
            } else {
                expected_txt_record(t)
            }
        })
        .collect();
    verify_txt_records(&records, agent_pubkey, did, subject, nonce)
}

#[cfg(test)]
mod github_tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};

    fn sk() -> SigningKey {
        SigningKey::from_bytes(&[11u8; 32])
    }

    #[test]
    fn accepts_a_correctly_signed_gist_payload() {
        let k = sk();
        let did = "did:integrity:abc";
        let subject = github_subject("XibalbaTechSol");
        let nonce = "n1";
        let sig = k.sign(challenge_message(did, &subject, nonce).as_bytes());

        // Bare hex, as an agent would write it into the gist.
        let payloads = vec![hex::encode(sig.to_bytes())];
        assert!(verify_github_payloads(&payloads, k.verifying_key().as_bytes(), did, &subject, nonce).is_ok());

        // Prefixed form is accepted too, so the published artefact can look
        // identical to the DNS TXT value.
        let prefixed = vec![expected_txt_record(&hex::encode(sig.to_bytes()))];
        assert!(verify_github_payloads(&prefixed, k.verifying_key().as_bytes(), did, &subject, nonce).is_ok());
    }

    #[test]
    fn github_subject_is_namespaced_and_case_insensitive() {
        assert_eq!(github_subject("XibalbaTechSol"), "github:xibalbatechsol");
        // Namespacing is what stops a login colliding with a domain in the
        // (agent, method, subject) unique index.
        assert!(github_subject("example.com").starts_with("github:"));
    }

    #[test]
    fn rejects_a_signature_bound_to_a_different_github_account() {
        let k = sk();
        let did = "did:integrity:abc";
        let sig = k.sign(challenge_message(did, &github_subject("attacker"), "n").as_bytes());
        let payloads = vec![hex::encode(sig.to_bytes())];
        let got = verify_github_payloads(
            &payloads,
            k.verifying_key().as_bytes(),
            did,
            &github_subject("victim"),
            "n",
        );
        assert!(matches!(got, Err(VerificationError::BadSignature { .. })));
    }

    #[test]
    fn rejects_a_github_proof_replayed_from_a_domain_proof() {
        // A signature proving control of `example.com` must not verify the
        // GitHub account `example.com`-shaped subject, and vice versa.
        let k = sk();
        let did = "did:integrity:abc";
        let sig = k.sign(challenge_message(did, "example.com", "n").as_bytes());
        let payloads = vec![hex::encode(sig.to_bytes())];
        let got = verify_github_payloads(
            &payloads,
            k.verifying_key().as_bytes(),
            did,
            &github_subject("example.com"),
            "n",
        );
        assert!(matches!(got, Err(VerificationError::BadSignature { .. })));
    }

    #[test]
    fn validates_github_logins() {
        for bad in ["", "-lead", "trail-", "has--double", "has space", &"x".repeat(40)] {
            assert!(validate_github_login(bad).is_err(), "should reject {bad:?}");
        }
        for good in ["XibalbaTechSol", "a", "my-org-1", "a1-b2"] {
            assert!(validate_github_login(good).is_ok(), "should accept {good:?}");
        }
    }
}

#[cfg(test)]
mod ladder_tests {
    //! End-to-end validation of the WHOLE Verification Ladder, not one rung.
    //!
    //! The ladder's failure mode is not "a rung is broken" — it's "the rungs
    //! don't compose". Before this suite existed the ceiling silently bound at
    //! tier 1 for every agent, the ZK boost was entirely absorbed by the clamp,
    //! and nothing in the test suite noticed any of it. These tests assert the
    //! ladder's behaviour as a system: each rung's ceiling, how tiers combine,
    //! and that losing a verification lowers the tier again.

    use super::*;
    use scoring_core::{AisComponentInputs, AisEngine, AisWeights};

    const TIER_REGISTRATION: i32 = 1;

    fn engine() -> AisEngine {
        AisEngine::new(AisWeights::default()).unwrap()
    }

    /// A deliberately strong agent: every component near max, so the CEILING is
    /// the only thing that can hold the score down. If a tier's cap is wrong,
    /// this input is what exposes it.
    fn excellent_agent() -> AisComponentInputs {
        AisComponentInputs {
            performance_variance: 0.0,
            hgi_raw: 1.0,
            gpu_hours_verified: 10_000.0,
            penalty_ratio: 0.0,
            zk_verified_this_period: false,
        }
    }

    #[test]
    fn every_tier_enforces_its_documented_ceiling() {
        let e = engine();
        let inputs = excellent_agent();
        // identity-ceiling.md: 0 -> 300, 1 -> 600, 2 -> 850, 3 -> uncapped(1000).
        for (tier, expected) in [(0, 300.0), (1, 600.0), (2, 850.0), (3, 1000.0)] {
            let got = e.score_with_tier(&inputs, tier).ais;
            assert!(
                (got - expected).abs() < 1.0,
                "tier {tier} should cap at {expected}, got {got}"
            );
        }
    }

    #[test]
    fn climbing_a_rung_actually_raises_the_reported_score() {
        // The bug this whole subsystem exists to fix: an agent whose raw score
        // exceeds its ceiling gains NOTHING from behaving better, only from
        // climbing. Each step must strictly increase the reported score.
        let e = engine();
        let inputs = excellent_agent();
        let mut previous = 0.0;
        for tier in 0..=3 {
            let got = e.score_with_tier(&inputs, tier).ais;
            assert!(
                got > previous,
                "tier {tier} ({got}) must score strictly higher than tier {} ({previous})",
                tier - 1
            );
            previous = got;
        }
    }

    #[test]
    fn the_zk_boost_is_wasted_below_tier_3_for_a_strong_agent() {
        // Documents a REAL, measured property rather than asserting it is fine:
        // the boost is applied before the clamp, so for an agent already above
        // its ceiling the boost buys literally nothing. This is why the xibalba
        // agent's Barretenberg proof was worth 0 points at tier 1.
        let e = engine();
        let mut boosted = excellent_agent();
        boosted.zk_verified_this_period = true;

        for tier in [0, 1, 2] {
            let plain = e.score_with_tier(&excellent_agent(), tier).ais;
            let with_zk = e.score_with_tier(&boosted, tier).ais;
            assert_eq!(
                plain, with_zk,
                "at tier {tier} a strong agent's ZK boost is absorbed by the ceiling — \
                 if this ever changes, the ladder's incentive design changed with it"
            );
        }
        // At tier 3 there is no clamp, so the boost is finally worth something.
        let plain = e.score_with_tier(&excellent_agent(), 3).ais;
        let with_zk = e.score_with_tier(&boosted, 3).ais;
        assert!(with_zk > plain, "tier 3 must let the ZK boost through");
    }

    #[test]
    fn a_weak_agent_is_limited_by_conduct_not_by_tier() {
        // The ceiling must only ever be a CAP, never a floor. An agent behaving
        // badly at tier 3 must not out-score a good agent at tier 1.
        let e = engine();
        let weak = AisComponentInputs {
            performance_variance: 100.0,
            hgi_raw: 0.05,
            gpu_hours_verified: 0.1,
            penalty_ratio: 0.9,
            zk_verified_this_period: false,
        };
        let weak_at_3 = e.score_with_tier(&weak, 3).ais;
        let strong_at_1 = e.score_with_tier(&excellent_agent(), 1).ais;
        assert!(
            weak_at_3 < strong_at_1,
            "a badly-behaved tier-3 agent ({weak_at_3}) must not out-score a good tier-1 one ({strong_at_1})"
        );
    }

    #[test]
    fn effective_tier_composes_rungs_and_never_drops_below_registration() {
        // Rung 2 can be reached by either namespace method; rung 3 by TEE.
        assert_eq!(effective_tier(TIER_REGISTRATION, &[]), 1, "no proofs -> registration floor");
        assert_eq!(effective_tier(TIER_REGISTRATION, &[TIER_DNS_VERIFIED]), 2, "DNS -> 2");
        assert_eq!(effective_tier(TIER_REGISTRATION, &[TIER_KYC_VERIFIED]), 3, "TEE/KYC -> 3");
        assert_eq!(
            effective_tier(TIER_REGISTRATION, &[TIER_DNS_VERIFIED, TIER_KYC_VERIFIED]),
            3,
            "holding both -> the highest, not the sum"
        );
        // A weaker proof must never pull an agent DOWN.
        assert_eq!(effective_tier(2, &[0]), 2);
        assert_eq!(effective_tier(3, &[TIER_DNS_VERIFIED]), 3);
    }

    #[test]
    fn losing_every_verification_returns_the_agent_to_the_registration_floor() {
        // Expiry and revocation are applied by excluding rows from the tier list,
        // so "all proofs gone" must collapse to the floor -- and the ceiling with
        // it. A cached tier column could not do this.
        let after_expiry = effective_tier(TIER_REGISTRATION, &[]);
        assert_eq!(after_expiry, TIER_REGISTRATION);
        assert!(
            (AisEngine::ceiling_for_tier(after_expiry) - 600.0).abs() < f64::EPSILON,
            "ceiling must fall back to 600 when proofs lapse"
        );
    }

    #[test]
    fn tier_ceilings_are_strictly_increasing() {
        // A non-monotonic ladder would make climbing pointless or harmful.
        let ceilings: Vec<f64> = (0..=3).map(AisEngine::ceiling_for_tier).collect();
        for w in ceilings.windows(2) {
            assert!(w[1] > w[0], "ceilings must strictly increase, got {ceilings:?}");
        }
    }

    #[test]
    fn an_unknown_tier_is_treated_as_the_top_not_as_a_bypass() {
        // Defensive: `ceiling_for_tier` matches `_ => 1000.0`. Confirm a garbage
        // tier cannot be used to exceed the documented maximum, and that
        // effective_tier clamps rather than propagating nonsense.
        assert_eq!(AisEngine::ceiling_for_tier(99), 1000.0);
        assert_eq!(effective_tier(0, &[99]), 3, "out-of-range tiers clamp to 3");
        assert_eq!(effective_tier(0, &[-5]), 0, "negative tiers cannot go below 0");
    }
}

// ---------------------------------------------------------------------------
// Development tier override
// ---------------------------------------------------------------------------
// An explicit, loud escape hatch for local development, where climbing rung 3
// legitimately cannot be done: generating a Nitro attestation needs real enclave
// hardware, and no amount of engineering removes that on a laptop.
//
// This is the single most dangerous thing in this module, so it is built to be
// impossible to use by accident and impossible to mistake for a real proof:
//
//   1. **Opt-in twice.** It requires BOTH `INTEGRITY_ALLOW_DEV_TIER_OVERRIDE=1`
//      and an explicit per-DID entry. Neither alone does anything.
//   2. **Never persisted.** It is applied at READ time and never written to
//      `identity_verifications`. A dev tier leaves no row that could later be
//      mistaken for evidence, and removing the env var removes the tier
//      instantly and completely.
//   3. **Always disclosed.** Every response that carries an overridden tier also
//      carries `tier_source: "dev_override"`, and the server logs a warning at
//      startup and on every application. A tier that is asserted rather than
//      proven must SAY so — a trust protocol that quietly fabricates its own
//      trust level has no product left.
//
// The honest framing: this does not make the agent tier 3. It makes the agent
// *behave as if* tier 3 in a development environment, which is a different
// claim, and the API says which one it is.

pub const DEV_OVERRIDE_ENABLE_VAR: &str = "INTEGRITY_ALLOW_DEV_TIER_OVERRIDE";
pub const DEV_OVERRIDE_MAP_VAR: &str = "INTEGRITY_DEV_TIER_OVERRIDES";

/// Where a reported tier came from. Surfaced in API responses so a consumer can
/// distinguish an earned tier from an asserted one without reading the docs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TierSource {
    /// Registration floor plus verified, unexpired evidence.
    Verified,
    /// Asserted by local configuration. NOT a proof.
    DevOverride,
}

/// Parse `INTEGRITY_DEV_TIER_OVERRIDES` — `did=tier` pairs, comma separated.
/// Malformed entries are skipped rather than defaulting to a tier: a typo must
/// never silently grant something.
pub fn parse_dev_overrides(raw: &str) -> Vec<(String, i32)> {
    raw.split(',')
        .filter_map(|entry| {
            let (did, tier) = entry.trim().split_once('=')?;
            let tier: i32 = tier.trim().parse().ok()?;
            if !(0..=3).contains(&tier) {
                return None;
            }
            Some((did.trim().to_string(), tier))
        })
        .collect()
}

/// Returns the overridden tier for this agent, if one is configured AND the
/// master switch is on.
pub fn dev_tier_override(agent_id: &str) -> Option<i32> {
    if std::env::var(DEV_OVERRIDE_ENABLE_VAR).unwrap_or_default() != "1" {
        return None;
    }
    let raw = std::env::var(DEV_OVERRIDE_MAP_VAR).unwrap_or_default();
    parse_dev_overrides(&raw)
        .into_iter()
        .find(|(did, _)| did == agent_id)
        .map(|(_, tier)| tier)
}

/// Apply the override on top of a verified tier, reporting which one won.
///
/// The override is a MAX, not a replacement: it can raise a tier for development
/// but must never silently lower a genuinely earned one, or a stale env var could
/// mask real verification state.
pub fn apply_dev_override(agent_id: &str, verified_tier: i32) -> (i32, TierSource) {
    match dev_tier_override(agent_id) {
        Some(dev) if dev > verified_tier => {
            tracing::warn!(
                agent_id, verified_tier, dev_tier = dev,
                "DEV TIER OVERRIDE APPLIED — this tier is asserted by configuration, \
                 NOT proven. Never enable {} in production.",
                DEV_OVERRIDE_ENABLE_VAR
            );
            (dev, TierSource::DevOverride)
        }
        _ => (verified_tier, TierSource::Verified),
    }
}

/// Log configured overrides once at startup, so an operator cannot be unaware
/// that their oracle is asserting tiers.
pub fn warn_about_dev_overrides_at_startup() {
    if std::env::var(DEV_OVERRIDE_ENABLE_VAR).unwrap_or_default() != "1" {
        return;
    }
    let raw = std::env::var(DEV_OVERRIDE_MAP_VAR).unwrap_or_default();
    let overrides = parse_dev_overrides(&raw);
    if overrides.is_empty() {
        tracing::warn!(
            "{} is set but {} configures no agents — no overrides are active",
            DEV_OVERRIDE_ENABLE_VAR, DEV_OVERRIDE_MAP_VAR
        );
        return;
    }
    tracing::warn!(
        "DEV TIER OVERRIDES ACTIVE for {} agent(s): {:?}. Verification tiers for these \
         agents are ASSERTED, not proven. This must never be enabled in production.",
        overrides.len(),
        overrides
    );
}

#[cfg(test)]
mod dev_override_tests {
    use super::*;

    #[test]
    fn parses_well_formed_entries_and_skips_junk() {
        let got = parse_dev_overrides("did:integrity:aaa=3, did:integrity:bbb=2");
        assert_eq!(got, vec![
            ("did:integrity:aaa".to_string(), 3),
            ("did:integrity:bbb".to_string(), 2),
        ]);
        // A typo must never grant a tier by defaulting.
        assert!(parse_dev_overrides("did:integrity:aaa").is_empty());
        assert!(parse_dev_overrides("did:integrity:aaa=notanumber").is_empty());
        assert!(parse_dev_overrides("did:integrity:aaa=9").is_empty(), "out of range");
        assert!(parse_dev_overrides("did:integrity:aaa=-1").is_empty());
        assert!(parse_dev_overrides("").is_empty());
    }

    #[test]
    fn override_never_lowers_a_genuinely_earned_tier() {
        // A stale env var must not mask real verification state.
        let (tier, source) = apply_dev_override("did:integrity:nobody", 3);
        assert_eq!(tier, 3);
        assert_eq!(source, TierSource::Verified);
    }

    #[test]
    fn an_unconfigured_agent_is_untouched() {
        let (tier, source) = apply_dev_override("did:integrity:nobody", 1);
        assert_eq!(tier, 1);
        assert_eq!(source, TierSource::Verified, "must report Verified when no override applies");
    }
}
