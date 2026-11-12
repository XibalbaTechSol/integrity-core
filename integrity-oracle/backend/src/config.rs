//! Runtime configuration, loaded entirely from environment variables using the
//! exact names pinned by `docs/INTERFACE_CONTRACT.md` §3 — other packages
//! (docker-compose, the sdk, the cli) construct these same names, so renaming
//! any of them here would silently break cross-package wiring.

use std::collections::HashMap;
use std::path::PathBuf;

use scoring_core::AisWeights;

/// What the PHI/PII backstop does when it finds a match.
///
/// The backstop is defense-in-depth: `integrity-sdk`'s collection profiles decide what an
/// agent *sends*, and this decides what the oracle *accepts*. They are separate on purpose —
/// the oracle has no way to know whether a client's redaction actually ran.
///
/// Default is `Reject`, so a deployment that never configures this keeps the strict behavior.
/// A development deployment that wants unredacted content sets `Flag`, which stores the
/// payload **and** records which categories matched, so the data is usable while the risk
/// stays visible in the row itself. `Off` skips the scan entirely and is the only mode that
/// loses the signal — it exists because pretending a disabled control is still a control is
/// worse than naming it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PhiBackstopMode {
    Reject,
    Flag,
    Off,
}

impl PhiBackstopMode {
    fn parse(raw: &str) -> Result<Self, String> {
        match raw.trim().to_ascii_lowercase().as_str() {
            "reject" => Ok(Self::Reject),
            "flag" => Ok(Self::Flag),
            "off" => Ok(Self::Off),
            other => Err(format!(
                "PHI_BACKSTOP_MODE must be one of reject|flag|off (got {other:?})"
            )),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Config {
    pub database_url: String,
    pub redis_url: String,
    pub rpc_url: String,
    pub chain_id: u64,
    pub bind_addr: String,

    /// Bind address for the real OTLP/gRPC receiver (`otlp.rs`) — a second listener,
    /// separate from `bind_addr`'s Axum HTTP server. Default `0.0.0.0:4317` matches the
    /// standard OTLP/gRPC port `integrity-sdk`'s `OTLPSpanExporter`/`OTLPMetricExporter`
    /// already target by default (`telemetry/core.py`'s `endpoint="localhost:4317"`).
    pub otlp_grpc_addr: String,

    pub deployments_file: PathBuf,

    pub ais_weights: AisWeights,
    /// How an AIS becomes a control zone: `AIS_ZONE_POLICY` (`per_tier`, the default, `relative`
    /// or `absolute`), with `AIS_ZONE_PER_TIER_THRESHOLDS`, `AIS_ZONE_RELATIVE_FRACTIONS` and
    /// `AIS_ZONE_ABSOLUTE_THRESHOLDS` overriding the numbers. See `scoring_core::ZonePolicy`.
    pub ais_zone_policy: scoring_core::ZonePolicy,
    pub reporting_period_days: i64,
    /// Optional post-score penalty for active agents with stale anchor coverage.
    /// Defaults to zero: coverage remains informational until an operator opts in.
    pub anchor_stale_penalty_bps: u16,

    /// Telemetry submissions per agent per minute before `429 Too Many Requests`.
    /// A concrete, real use of Redis (fixed-window counter) rather than a token
    /// vault — protects Postgres and the ZK verifier subprocess from a
    /// misbehaving/compromised agent hammering the ingestion endpoint.
    pub telemetry_rate_limit_per_minute: u32,
    pub phi_backstop_mode: PhiBackstopMode,

    /// provider id -> trusted Ed25519 receipt-verification key. A KYC receipt is
    /// authoritative only when signed by one of these independently configured roots.
    /// Parsed from `KYC_PROVIDER_KEYS` as `provider=hex-public-key,...`.
    pub kyc_provider_keys: HashMap<String, [u8; 32]>,
    
    /// Optional shared API key to authenticate internal-only endpoints 
    /// (e.g. /v1/audit/ingest, /v1/audit/anchor, and OTLP receivers).
    pub oracle_api_key: Option<String>,
    /// Operators set this only after the directory refresh has reached the configured
    /// chain-finality policy. It is surfaced in the snapshot envelope; default is false.
    pub agent_directory_finalized: bool,

    /// Device DIDs authorized to submit Shield observation witness records
    /// (`POST /v1/shield/observation`). Parsed from `SHIELD_WITNESS_DIDS`, comma-separated.
    /// EMPTY => the ingest is fail-closed (every submitter rejected): an unauthorized witness
    /// could forge suppression against any agent, so a device must be explicitly allowlisted.
    pub shield_witness_dids: std::collections::HashSet<String>,
}

impl Config {
    pub fn from_env() -> Result<Self, String> {
        let database_url = require_env("DATABASE_URL")?;
        let redis_url = require_env("REDIS_URL")?;
        let rpc_url = env_or("RPC_URL", "http://localhost:8545");
        let chain_id: u64 = env_or("CHAIN_ID", "31337")
            .parse()
            .map_err(|_| "CHAIN_ID must be a valid integer".to_string())?;
        let bind_addr = env_or("BIND_ADDR", "0.0.0.0:8080");
        let otlp_grpc_addr = env_or("OTLP_GRPC_ADDR", "0.0.0.0:4317");


        // Repo-root-relative default per §6 of the interface contract; every
        // package that needs deployed addresses defaults to the same file.
        let deployments_file = PathBuf::from(env_or("DEPLOYMENTS_FILE", "../deployments.local.json"));

        let ais_weights = parse_ais_weights(std::env::var("AIS_WEIGHTS").ok())?;
        let ais_zone_policy = parse_ais_zone_policy(
            std::env::var("AIS_ZONE_POLICY").ok(),
            std::env::var("AIS_ZONE_PER_TIER_THRESHOLDS").ok(),
            std::env::var("AIS_ZONE_RELATIVE_FRACTIONS").ok(),
            std::env::var("AIS_ZONE_ABSOLUTE_THRESHOLDS").ok(),
        )?;
        let reporting_period_days: i64 = env_or("AIS_REPORTING_PERIOD_DAYS", "30")
            .parse()
            .map_err(|_| "AIS_REPORTING_PERIOD_DAYS must be a valid integer".to_string())?;
        if reporting_period_days <= 0 {
            return Err("AIS_REPORTING_PERIOD_DAYS must be greater than zero".to_string());
        }
        let anchor_stale_penalty_bps: u16 = env_or("AIS_ANCHOR_STALE_PENALTY_BPS", "0")
            .parse()
            .map_err(|_| "AIS_ANCHOR_STALE_PENALTY_BPS must be an integer between 0 and 10000".to_string())?;
        if anchor_stale_penalty_bps > 10_000 {
            return Err("AIS_ANCHOR_STALE_PENALTY_BPS must be between 0 and 10000".to_string());
        }
        let phi_backstop_mode = PhiBackstopMode::parse(&env_or("PHI_BACKSTOP_MODE", "reject"))?;
        let telemetry_rate_limit_per_minute: u32 = env_or("TELEMETRY_RATE_LIMIT_PER_MINUTE", "60")
            .parse()
            .map_err(|_| "TELEMETRY_RATE_LIMIT_PER_MINUTE must be a valid integer".to_string())?;
        let kyc_provider_keys = parse_kyc_provider_keys(&env_or("KYC_PROVIDER_KEYS", ""))?;
        let shield_witness_dids = env_or("SHIELD_WITNESS_DIDS", "")
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
            .collect();

        Ok(Self {
            database_url,
            redis_url,
            rpc_url,
            chain_id,
            bind_addr,
            otlp_grpc_addr,
            deployments_file,
            ais_weights,
            ais_zone_policy,
            reporting_period_days,
            anchor_stale_penalty_bps,
            telemetry_rate_limit_per_minute,
            phi_backstop_mode,
            kyc_provider_keys,
            oracle_api_key: parse_optional_api_key(std::env::var("ORACLE_API_KEY").ok()),
            agent_directory_finalized: env_or("AGENT_DIRECTORY_FINALIZED", "false").parse().map_err(|_| "AGENT_DIRECTORY_FINALIZED must be true or false" )?,
            shield_witness_dids,
        })
    }

    /// Builds a Config for integration tests from explicit connection strings +
    /// otherwise-default values, so a test can point at a test Postgres/Redis/anvil
    /// without mutating process-global env vars (which would race across concurrently
    /// running tests). Test-only — the real server always goes through `from_env`.
    pub fn from_env_for_test(rpc_url: String, database_url: String, redis_url: String) -> Self {
        Self {
            database_url,
            redis_url,
            rpc_url,
            chain_id: 31337,
            bind_addr: "127.0.0.1:0".to_string(),
            otlp_grpc_addr: "127.0.0.1:0".to_string(),
            deployments_file: PathBuf::from("../deployments.local.json"),
            ais_weights: AisWeights::default(),
            ais_zone_policy: scoring_core::ZonePolicy::default(),
            reporting_period_days: 30,
            anchor_stale_penalty_bps: 0,
            telemetry_rate_limit_per_minute: 60,
            // Tests get the strict default; a test that needs Flag/Off sets it explicitly, so a
            // relaxed backstop can never be inherited silently.
            phi_backstop_mode: PhiBackstopMode::Reject,
            kyc_provider_keys: HashMap::new(),
            oracle_api_key: None,
            agent_directory_finalized: false,
            shield_witness_dids: std::collections::HashSet::new(),
        }
    }
}

fn parse_kyc_provider_keys(raw: &str) -> Result<HashMap<String, [u8; 32]>, String> {
    let mut keys = HashMap::new();
    if raw.trim().is_empty() {
        return Ok(keys);
    }
    for entry in raw.split(',') {
        let (provider, key_hex) = entry
            .trim()
            .split_once('=')
            .ok_or_else(|| format!("malformed KYC_PROVIDER_KEYS entry {entry:?}, expected provider=hex-key"))?;
        let provider = provider.trim().to_ascii_lowercase();
        if provider.is_empty()
            || !provider
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-' || b == b'_')
        {
            return Err(format!("invalid KYC provider id {provider:?}"));
        }
        let decoded = hex::decode(key_hex.trim().trim_start_matches("0x"))
            .map_err(|_| format!("KYC provider {provider:?} has a non-hex public key"))?;
        let key: [u8; 32] = decoded
            .try_into()
            .map_err(|_| format!("KYC provider {provider:?} key must be exactly 32 bytes"))?;
        if keys.insert(provider.clone(), key).is_some() {
            return Err(format!("duplicate KYC provider id {provider:?}"));
        }
    }
    Ok(keys)
}

fn require_env(key: &str) -> Result<String, String> {
    std::env::var(key).map_err(|_| format!("required environment variable {key} is not set"))
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

/// An unset *or blank* `ORACLE_API_KEY` means "no internal API key configured".
/// docker-compose passes `${ORACLE_API_KEY:-}` through as an empty string when the
/// host has no key; treating that as `Some("")` enabled key checking with an empty
/// key, so every internal caller that sends no Authorization header (BCC audit
/// reports) was rejected with 401.
fn parse_optional_api_key(raw: Option<String>) -> Option<String> {
    raw.map(|k| k.trim().to_string()).filter(|k| !k.is_empty())
}

/// Parses `"wE,wG,wS,wC"` (four comma-separated floats) into `AisWeights`, or
/// falls back to the interface-contract default if unset. Always validated
/// (must sum to 1.0) before being accepted.
fn parse_ais_weights(raw: Option<String>) -> Result<AisWeights, String> {
    let weights = match raw {
        None => AisWeights::default(),
        Some(s) => {
            let parts: Vec<&str> = s.split(',').map(str::trim).collect();
            if parts.len() != 4 {
                return Err("AIS_WEIGHTS must be exactly 4 comma-separated floats: wE,wG,wS,wC".to_string());
            }
            let parsed: Result<Vec<f64>, _> = parts.iter().map(|p| p.parse::<f64>()).collect();
            let parsed = parsed.map_err(|_| "AIS_WEIGHTS must contain valid floats".to_string())?;
            AisWeights {
                w_entropy: parsed[0],
                w_grounding: parsed[1],
                w_sacrifice: parsed[2],
                w_compliance: parsed[3],
            }
        }
    };
    weights.validate()?;
    Ok(weights)
}

fn parse_floats(name: &str, raw: &str, expected: usize) -> Result<Vec<f64>, String> {
    let parsed: Result<Vec<f64>, _> = raw.split(',').map(|p| p.trim().parse::<f64>()).collect();
    match parsed {
        Ok(values) if values.len() == expected => Ok(values),
        _ => Err(format!("{name} must be exactly {expected} comma-separated floats")),
    }
}

fn thresholds_from(values: &[f64]) -> scoring_core::ZoneThresholds {
    scoring_core::ZoneThresholds { yellow: values[0], green: values[1], recovery: values[2] }
}

/// Builds the zone policy from its four optional settings. Unset means the documented default;
/// blank counts as unset. Each numeric setting is `yellow,green,recovery`, and the per-tier one is
/// that triple four times, for tiers 0 to 3. The whole policy is validated, so a threshold a tier
/// cannot reach stops the oracle starting instead of leaving that tier's agents permanently red.
fn parse_ais_zone_policy(
    mode: Option<String>,
    per_tier: Option<String>,
    relative: Option<String>,
    absolute: Option<String>,
) -> Result<scoring_core::ZonePolicy, String> {
    let set = |raw: Option<String>| raw.map(|s| s.trim().to_string()).filter(|s| !s.is_empty());
    let mut policy = scoring_core::ZonePolicy::default();
    if let Some(name) = set(mode) {
        policy.mode = scoring_core::ZonePolicyMode::parse(&name).map_err(|e| format!("AIS_ZONE_POLICY: {e}"))?;
    }
    if let Some(raw) = set(per_tier) {
        let values = parse_floats("AIS_ZONE_PER_TIER_THRESHOLDS", &raw, 12)?;
        for tier in 0..4 {
            policy.per_tier[tier] = thresholds_from(&values[tier * 3..tier * 3 + 3]);
        }
    }
    if let Some(raw) = set(relative) {
        policy.relative = thresholds_from(&parse_floats("AIS_ZONE_RELATIVE_FRACTIONS", &raw, 3)?);
    }
    if let Some(raw) = set(absolute) {
        policy.absolute = thresholds_from(&parse_floats("AIS_ZONE_ABSOLUTE_THRESHOLDS", &raw, 3)?);
    }
    policy.validate().map_err(|e| format!("AIS zone policy is invalid: {e}"))?;
    Ok(policy)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zone_policy_defaults_to_per_tier_and_blank_settings_are_unset() {
        let policy = parse_ais_zone_policy(None, Some("  ".into()), None, Some(String::new())).unwrap();
        assert_eq!(policy, scoring_core::ZonePolicy::default());
        assert_eq!(policy.mode, scoring_core::ZonePolicyMode::PerTier);
    }

    #[test]
    fn zone_policy_mode_and_numbers_are_operator_settable() {
        let policy = parse_ais_zone_policy(
            Some("relative".into()),
            Some("100,200,250, 300,400,500, 500,700,800, 600,800,900".into()),
            Some("0.5,0.8,0.85".into()),
            Some("700,880,900".into()),
        )
        .unwrap();
        assert_eq!(policy.mode, scoring_core::ZonePolicyMode::Relative);
        assert_eq!(policy.per_tier[1].green, 400.0);
        assert_eq!(policy.thresholds_for_tier(1).green, 480.0);
        assert_eq!(policy.absolute.yellow, 700.0);
    }

    #[test]
    fn a_zone_policy_that_cannot_work_stops_startup() {
        let bad = |mode: Option<&str>, per_tier: Option<&str>, relative: Option<&str>| {
            parse_ais_zone_policy(mode.map(String::from), per_tier.map(String::from), relative.map(String::from), None)
        };
        assert!(bad(Some("strict"), None, None).is_err());
        assert!(bad(None, Some("225,270,276"), None).is_err());
        assert!(bad(None, None, Some("0.9,0.8,0.95")).is_err());
        assert!(bad(None, None, Some("0.75,0.9,1.2")).is_err());
        // Tier 0's ceiling is 300: a green threshold of 400 could never be reached. Refused even
        // though the selected mode is `relative`, so a later switch to `per_tier` cannot expose it.
        assert!(bad(Some("relative"), Some("225,400,400, 450,540,552, 637.5,765,782, 750,900,920"), None).is_err());
    }

    #[test]
    fn blank_oracle_api_key_is_treated_as_unset() {
        assert_eq!(parse_optional_api_key(None), None);
        assert_eq!(parse_optional_api_key(Some(String::new())), None);
        assert_eq!(parse_optional_api_key(Some("   ".into())), None);
        assert_eq!(parse_optional_api_key(Some(" k3y ".into())), Some("k3y".to_string()));
    }

    #[test]
    fn default_ais_weights_used_when_unset() {
        let w = parse_ais_weights(None).unwrap();
        assert_eq!(w, AisWeights::default());
    }

    #[test]
    fn custom_ais_weights_must_still_sum_to_one() {
        assert!(parse_ais_weights(Some("0.5,0.5,0.5,0.5".to_string())).is_err());
        let w = parse_ais_weights(Some("0.4,0.3,0.2,0.1".to_string())).unwrap();
        assert_eq!(w.w_entropy, 0.4);
    }

    #[test]
    fn parses_kyc_provider_trust_roots_and_rejects_bad_entries() {
        let key = "11".repeat(32);
        let parsed = parse_kyc_provider_keys(&format!("open-kyc={key}")).unwrap();
        assert_eq!(parsed["open-kyc"], [0x11; 32]);
        assert!(parse_kyc_provider_keys("Open KYC=00").is_err());
        assert!(parse_kyc_provider_keys("open-kyc=abcd").is_err());
    }
}
