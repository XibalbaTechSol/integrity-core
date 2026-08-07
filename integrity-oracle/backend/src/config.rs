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

    /// circuit_id -> path to that circuit's trusted verification key. Populated
    /// from `ZK_VK_PATHS` as `id1=/path/to/vk,id2=/path/to/vk2`. This is
    /// intentionally the *only* source of VKs the ZK verifier trusts — see
    /// `crate::zk` for why accepting a caller-supplied VK would defeat the point
    /// of verification.
    pub zk_vk_paths: HashMap<String, PathBuf>,
    pub zk_verifier_target: String,
    pub bb_binary: PathBuf,
    pub zk_scratch_dir: PathBuf,

    pub deployments_file: PathBuf,

    pub ais_weights: AisWeights,
    pub reporting_period_days: i64,

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

        let zk_vk_paths = parse_vk_paths(&env_or("ZK_VK_PATHS", ""))?;
        let zk_verifier_target = env_or("ZK_VERIFIER_TARGET", "evm");
        let bb_binary = PathBuf::from(env_or("BB_BINARY", "bb"));
        let zk_scratch_dir =
            PathBuf::from(env_or("ZK_SCRATCH_DIR", std::env::temp_dir().join("integrity-oracle-zk").to_string_lossy().as_ref()));

        // Repo-root-relative default per §6 of the interface contract; every
        // package that needs deployed addresses defaults to the same file.
        let deployments_file = PathBuf::from(env_or("DEPLOYMENTS_FILE", "../deployments.local.json"));

        let ais_weights = parse_ais_weights(std::env::var("AIS_WEIGHTS").ok())?;
        let reporting_period_days: i64 = env_or("AIS_REPORTING_PERIOD_DAYS", "30")
            .parse()
            .map_err(|_| "AIS_REPORTING_PERIOD_DAYS must be a valid integer".to_string())?;
        let phi_backstop_mode = PhiBackstopMode::parse(&env_or("PHI_BACKSTOP_MODE", "reject"))?;
        let telemetry_rate_limit_per_minute: u32 = env_or("TELEMETRY_RATE_LIMIT_PER_MINUTE", "60")
            .parse()
            .map_err(|_| "TELEMETRY_RATE_LIMIT_PER_MINUTE must be a valid integer".to_string())?;
        let kyc_provider_keys = parse_kyc_provider_keys(&env_or("KYC_PROVIDER_KEYS", ""))?;

        Ok(Self {
            database_url,
            redis_url,
            rpc_url,
            chain_id,
            bind_addr,
            otlp_grpc_addr,
            zk_vk_paths,
            zk_verifier_target,
            bb_binary,
            zk_scratch_dir,
            deployments_file,
            ais_weights,
            reporting_period_days,
            telemetry_rate_limit_per_minute,
            phi_backstop_mode,
            kyc_provider_keys,
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
            zk_vk_paths: HashMap::new(),
            zk_verifier_target: "evm".to_string(),
            bb_binary: PathBuf::from("bb"),
            zk_scratch_dir: std::env::temp_dir().join("integrity-oracle-zk-test"),
            deployments_file: PathBuf::from("../deployments.local.json"),
            ais_weights: AisWeights::default(),
            reporting_period_days: 30,
            telemetry_rate_limit_per_minute: 60,
            // Tests get the strict default; a test that needs Flag/Off sets it explicitly, so a
            // relaxed backstop can never be inherited silently.
            phi_backstop_mode: PhiBackstopMode::Reject,
            kyc_provider_keys: HashMap::new(),
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

/// Parses `"circuit_id=path,circuit_id2=path2"` into a map. Empty string yields
/// an empty map (valid: an oracle with no telemetry containing ZK proofs yet,
/// e.g. immediately after a fresh deploy, legitimately has nothing to register).
fn parse_vk_paths(raw: &str) -> Result<HashMap<String, PathBuf>, String> {
    let mut map = HashMap::new();
    if raw.trim().is_empty() {
        return Ok(map);
    }
    for entry in raw.split(',') {
        let entry = entry.trim();
        if entry.is_empty() {
            continue;
        }
        let (id, path) = entry
            .split_once('=')
            .ok_or_else(|| format!("malformed ZK_VK_PATHS entry '{entry}', expected circuit_id=path"))?;
        map.insert(id.trim().to_string(), PathBuf::from(path.trim()));
    }
    Ok(map)
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_multiple_vk_path_entries() {
        let map = parse_vk_paths("attestation-v1=/vks/a.vk, other=/vks/b.vk").unwrap();
        assert_eq!(map.get("attestation-v1").unwrap(), &PathBuf::from("/vks/a.vk"));
        assert_eq!(map.get("other").unwrap(), &PathBuf::from("/vks/b.vk"));
    }

    #[test]
    fn empty_vk_paths_is_valid() {
        assert!(parse_vk_paths("").unwrap().is_empty());
    }

    #[test]
    fn rejects_malformed_vk_path_entry() {
        assert!(parse_vk_paths("no-equals-sign").is_err());
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
