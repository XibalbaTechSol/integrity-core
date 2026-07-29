//! Real end-to-end test of the oracle's HTTP layer against real infrastructure:
//! a real anvil chain running the real `contracts/script/Deploy.s.sol`, a real agent
//! registered on-chain through integrity-sdk's real registration flow, a real Postgres,
//! a real Redis, and the real Axum server (hit over real HTTP via reqwest). No mocked
//! dependency anywhere — this is the "no silent mocks" ground rule applied to the
//! oracle's own tests.
//!
//! Opt-in: this test only runs when `ORACLE_E2E=1` is set, because it needs a Postgres
//! and Redis reachable (defaults: `TEST_DATABASE_URL`, `TEST_REDIS_URL`), plus `anvil`,
//! `forge`, and the integrity-sdk venv python on the machine. A bare `cargo test` in an
//! infra-less CI skips it rather than failing spuriously — the skip is logged, not
//! silent.
//!
//! **Must run with `--test-threads=1` when `ORACLE_E2E=1`.** Every test in this file
//! shares one `TEST_DATABASE_URL`, and `build_state`'s setup does a destructive
//! `DROP TABLE ... CASCADE` + re-migrate — running tests in parallel means one test's
//! setup can wipe another's mid-flight, a real (verified, not theoretical) flake, not a
//! hypothetical one. `cargo test --test e2e -- --test-threads=1` is correct; the
//! default parallel `cargo test` is not. (CI itself never hits this: no `ORACLE_E2E` is
//! set there, so these tests only ever print SKIP.)

use std::net::SocketAddr;
use std::path::PathBuf;
use std::process::Command;
use std::sync::Arc;
use std::time::Duration;

use backend::chain::ChainClient;
use futures::StreamExt;
use backend::config::Config;
use backend::zk::ZkVerifier;
use backend::{db, AppState};

fn repo_root() -> PathBuf {
    // backend/ -> integrity-oracle/ -> repo root
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().parent().unwrap().to_path_buf()
}

fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port()
}

/// Anvil's well-known dev account #0 — always pre-funded on a fresh anvil, used as the
/// deploy/funder wallet exactly as `contracts/script/Deploy.s.sol` and the SDK expect.
const ANVIL_KEY: &str = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";

struct AnvilGuard(std::process::Child);
impl Drop for AnvilGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
    }
}

fn start_anvil(port: u16) -> AnvilGuard {
    let child = Command::new("anvil")
        .args(["--port", &port.to_string(), "--silent"])
        .spawn()
        .expect("anvil must be on PATH");
    // Wait for the RPC to accept connections.
    let addr = format!("127.0.0.1:{port}");
    for _ in 0..50 {
        if std::net::TcpStream::connect(&addr).is_ok() {
            return AnvilGuard(child);
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    panic!("anvil did not become reachable on {addr}");
}

fn run_deploy(rpc_url: &str) {
    let status = Command::new("forge")
        .current_dir(repo_root().join("contracts"))
        .args(["script", "script/Deploy.s.sol", "--rpc-url", rpc_url, "--broadcast"])
        .env("FUNDER_PRIVATE_KEY", ANVIL_KEY)
        .status()
        .expect("forge must be on PATH");
    assert!(status.success(), "Deploy.s.sol failed");
}

#[derive(serde::Deserialize)]
struct SdkRegistration {
    did: String,
    evm_address: String,
    sovereign_agent: String,
    state_anchor: String,
    reputation_registry: String,
    slasher: String,
    verifier_registry: String,
    compliance_gate: String,
    agent_profile: String,
}

/// Registers a real agent on-chain via the SDK's real flow (subprocess into the SDK
/// venv), returning the addresses it actually produced.
fn register_agent_onchain(rpc_url: &str, deployments_file: &str, vertical: &str, agent_id: &str, wallet_home: &str) -> SdkRegistration {
    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let script = repo_root().join("integrity-oracle/backend/tests/support/register_agent.py");
    let output = Command::new(sdk_python)
        .args([script.to_str().unwrap(), rpc_url, deployments_file, vertical, agent_id])
        .env("FUNDER_PRIVATE_KEY", ANVIL_KEY)
        .env("INTEGRITY_WALLET_PASSWORD", "oracle-e2e-test-pw")
        .env("INTEGRITY_WALLET_HOME", format!("{wallet_home}/wallet"))
        .env("INTEGRITY_DID_HOME", format!("{wallet_home}/did"))
        .output()
        .expect("integrity-sdk venv python must exist (run `uv pip install -e .` in integrity-sdk)");
    assert!(
        output.status.success(),
        "on-chain registration failed:\nstdout: {}\nstderr: {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let last_line = String::from_utf8_lossy(&output.stdout).lines().last().unwrap().to_string();
    serde_json::from_str(&last_line).expect("SDK helper must print registration JSON on its last stdout line")
}

async fn build_state(rpc_url: &str, deployments_file: &PathBuf, db_url: &str, redis_url: &str) -> AppState {
    let pool = db::create_pool(db_url).await.expect("Postgres must be reachable");
    // Fresh schema each run so tests are independent. `TEST_DATABASE_URL` must run the
    // `timescale/timescaledb` image (not plain `postgres`) for migration 0004's
    // `CREATE EXTENSION timescaledb` to succeed — a real environment requirement, not
    // something `cargo test --workspace --lib` needs (that path never touches a live DB).
    sqlx::query(
        "DROP TABLE IF EXISTS telemetry_events, agent_primitives, merkle_roots, agents, markets_cache, markets_index_sync, judge_evaluations, otel_spans, _sqlx_migrations CASCADE",
    )
    .execute(&pool)
    .await
    .unwrap();
    db::run_migrations(&pool).await.expect("migrations apply");

    let redis_client = redis::Client::open(redis_url).unwrap();
    let redis = redis::aio::ConnectionManager::new(redis_client).await.expect("Redis must be reachable");

    let chain = ChainClient::connect(rpc_url, deployments_file).await.expect("chain client connects");

    let config = Config::from_env_for_test(rpc_url.to_string(), db_url.to_string(), redis_url.to_string());
    let zk = ZkVerifier::new(config.zk_vk_paths.clone(), config.zk_verifier_target.clone(), config.bb_binary.clone(), config.zk_scratch_dir.clone());

    let (telemetry_tx, _) = tokio::sync::broadcast::channel(backend::stream::CHANNEL_CAPACITY);

    AppState { pool, redis, chain, zk, config: Arc::new(config), telemetry_tx }
}

#[tokio::test]
async fn oracle_e2e_register_verify_ais_compliance() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e (set ORACLE_E2E=1 with Postgres+Redis+anvil+forge+sdk-venv to run)");
        return;
    }
    // Surface the server's own tracing::error!(...) lines (masked in the HTTP body) so a
    // 500 in a handler is diagnosable from the test output.
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());

    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    run_deploy(&rpc_url);

    let deployments_file = repo_root().join("deployments.local.json");
    let wallet_home = std::env::temp_dir().join(format!("oracle-e2e-{anvil_port}"));

    // Register a healthcare-vertical agent on-chain the real way.
    let reg = register_agent_onchain(
        &rpc_url,
        deployments_file.to_str().unwrap(),
        "healthcare",
        "oracle-e2e-agent",
        wallet_home.to_str().unwrap(),
    );

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;
    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let base = format!("http://127.0.0.1:{server_port}");
    let http = reqwest::Client::new();

    // 1. Register with the REAL on-chain primitives -> accepted.
    let correct_primitives = serde_json::json!({
        "sovereign_agent": reg.sovereign_agent,
        "state_anchor": reg.state_anchor,
        "reputation_registry": reg.reputation_registry,
        "slasher": reg.slasher,
        "verifier_registry": reg.verifier_registry,
        "compliance_gate": reg.compliance_gate,
        "agent_profile": reg.agent_profile,
    });
    let resp = http
        .post(format!("{base}/v1/agent/register"))
        .json(&serde_json::json!({
            "did": reg.did,
            "did_document": {"id": reg.did},
            "primitives": correct_primitives,
            "eth_address_hex": reg.evm_address,
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 200, "correct registration must be accepted: {}", resp.text().await.unwrap());

    // 2. Register with a FABRICATED sovereign_agent -> rejected (the honesty guarantee).
    let mut fake = correct_primitives.clone();
    fake["sovereign_agent"] = serde_json::json!("0x000000000000000000000000000000000000dEaD");
    let resp = http
        .post(format!("{base}/v1/agent/register"))
        .json(&serde_json::json!({
            "did": "did:integrity:fabricated-claimant",
            "did_document": {"id": "did:integrity:fabricated-claimant"},
            "primitives": fake,
            "eth_address_hex": reg.evm_address,
        }))
        .send()
        .await
        .unwrap();
    // Either ChainMismatch (400) if the DID resolves to different addrs, or NotFound (404)
    // for a DID never registered on-chain — both are correct rejections, neither is a 200.
    assert!(resp.status().is_client_error(), "fabricated claim must be rejected, got {}", resp.status());

    // 3. AIS for the real agent (no telemetry yet -> a real baseline score, not an error).
    let resp = http.get(format!("{base}/v1/agent/{}/ais", reg.did)).send().await.unwrap();
    let status = resp.status();
    let body = resp.text().await.unwrap();
    assert_eq!(status, 200, "ais endpoint must return a score, body: {body}");
    let resp = http.get(format!("{base}/v1/agent/{}/ais", reg.did)).send().await.unwrap();
    let ais: serde_json::Value = resp.json().await.unwrap();
    assert!(ais["ais"].is_number(), "ais response must carry a numeric score");

    // 4. Live compliance read against the agent's real ComplianceGate clone.
    let resp = http.get(format!("{base}/v1/agent/{}/compliance", reg.did)).send().await.unwrap();
    assert_eq!(resp.status(), 200, "compliance endpoint must return a status");
    let compliance: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(compliance["vertical"], "healthcare", "agent registered as healthcare vertical");

    // 5. GET /v1/markets against the REAL, live-deployed MarketFactory (Deploy.s.sol
    // deploys the market layer as part of genesis now, so this is exercising a real
    // binding/parse/handler round-trip, not a mock) — no market has been created on this
    // fresh anvil, so a real, honest empty list is the correct response, not an error.
    let resp = http.get(format!("{base}/v1/markets")).send().await.unwrap();
    assert_eq!(resp.status(), 200, "markets endpoint must return a status: {}", resp.text().await.unwrap());
    let resp = http.get(format!("{base}/v1/markets")).send().await.unwrap();
    let markets: serde_json::Value = resp.json().await.unwrap();
    assert!(markets.is_array(), "markets response must be a JSON array");
    assert_eq!(markets.as_array().unwrap().len(), 0, "no markets created yet on this fresh anvil");

    // 6. GET /v1/leaderboard: a real ReputationRegistry.effectiveScore read for the one
    // real registered agent, ranked (trivially, with one entry) — no fabricated P&L.
    let resp = http.get(format!("{base}/v1/leaderboard")).send().await.unwrap();
    assert_eq!(resp.status(), 200, "leaderboard endpoint must return a status");
    let leaderboard: serde_json::Value = resp.json().await.unwrap();
    let entries = leaderboard.as_array().expect("leaderboard must be a JSON array");
    assert_eq!(entries.len(), 1, "exactly the one real registered agent should appear");
    assert_eq!(entries[0]["agent_id"], reg.did);
    assert!(entries[0]["effective_score"].is_string(), "on-chain score is serialized as a decimal string, not a lossy JSON number");
    assert!(entries[0]["realized_pnl"].is_null(), "realized P&L must be an honest null, never a fabricated number");

    // 7. GET /v1/agent/{id}/wallet: a real IntegrityToken.balanceOf read for the agent's
    // real SovereignAgent contract address, plus (empty, since no markets exist) open
    // positions and an honestly-null transaction history.
    let resp = http.get(format!("{base}/v1/agent/{}/wallet", reg.did)).send().await.unwrap();
    assert_eq!(resp.status(), 200, "wallet endpoint must return a status: {}", resp.text().await.unwrap());
    let resp = http.get(format!("{base}/v1/agent/{}/wallet", reg.did)).send().await.unwrap();
    let wallet: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(wallet["sovereign_agent"].as_str().unwrap().to_lowercase(), reg.sovereign_agent.to_lowercase(), "wallet balance must be read for the agent's real SovereignAgent address");
    assert!(wallet["itk_balance"].is_string(), "uint256 balance is serialized as a decimal string");
    assert_eq!(wallet["open_positions"].as_array().unwrap().len(), 0);
    assert!(wallet["transaction_history"].is_null(), "tx history must be an honest null, never fabricated");

    // 8. POST /v1/telemetry/ingest PHI backstop: the check runs before signature
    // verification (see handlers::ingest_telemetry), so this exercises the real
    // HTTP-wired rejection path without needing a validly-signed payload. A raw,
    // unredacted SSN embedded in an otel span must be rejected with 400, never stored.
    let resp = http
        .post(format!("{base}/v1/telemetry/ingest"))
        .json(&serde_json::json!({
            "agent_id": reg.did,
            "nonce": 1,
            "otel_spans": [{"name": "llm_call", "attributes": {"prompt": "patient ssn is 123-45-6789"}}],
            "derived_signals": {"entropy": 0.1, "grounding": 0.9, "sacrifice": 0.0, "compliance": 0.0},
            "signature": "0xnotarealsignature",
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(resp.status(), 400, "raw unredacted SSN in telemetry must be rejected, not silently stored");
    let body: serde_json::Value = resp.json().await.unwrap();
    assert!(body["error"].as_str().unwrap().contains("PHI"), "rejection reason must be surfaced: {body}");

    // 9. Telemetry history and traces retrieval verification (real database insert -> HTTP read)
    let event_id = uuid::Uuid::new_v4();
    let payload = serde_json::json!({"test": "data"});
    let leaf_hash = vec![0u8; 32];
    db::insert_telemetry_event(
        &state.pool,
        event_id,
        &reg.did,
        1, // nonce
        0.5, // performance_variance
        0.8, // hgi_raw
        10.0, // gpu_hours_verified
        false, // flagged
        true, // zk_verified
        &leaf_hash,
        &payload,
    )
    .await
    .unwrap();

    let eval_id = uuid::Uuid::new_v4();
    db::insert_judge_evaluation(
        &state.pool,
        eval_id,
        &reg.did,
        "run-123",
        "gpt-4o",
        "PASS",
        Some(1.0),
        Some("Nominal behavior"),
        Some(event_id),
    )
    .await
    .unwrap();

    // Fetch telemetry history via HTTP
    let resp = http.get(format!("{base}/v1/agent/{}/telemetry", reg.did)).send().await.unwrap();
    assert_eq!(resp.status(), 200);
    let history: serde_json::Value = resp.json().await.unwrap();
    let events = history.as_array().unwrap();
    assert_eq!(events.len(), 1);
    assert_eq!(events[0]["nonce"], 1);
    assert_eq!(events[0]["gpu_hours_verified"], 10.0);

    // Fetch traces history via HTTP
    let resp = http.get(format!("{base}/v1/agent/{}/traces", reg.did)).send().await.unwrap();
    assert_eq!(resp.status(), 200);
    let traces: serde_json::Value = resp.json().await.unwrap();
    let evals = traces.as_array().unwrap();
    assert_eq!(evals.len(), 1);
    assert_eq!(evals[0]["run_id"], "run-123");
    assert_eq!(evals[0]["judge_model"], "gpt-4o");
}

/// Signs a real `POST /v1/telemetry/ingest` payload via the SDK venv's Python
/// (`tests/support/sign_telemetry.py`), using integrity-sdk's own canonical-JSON
/// implementation — the exact bytes `crypto::verify_agent_signature` must agree with —
/// rather than approximating the wire format in Rust.
#[allow(clippy::too_many_arguments)]
#[allow(clippy::too_many_arguments)]
fn sign_telemetry_with_spans(
    private_key: &str,
    agent_id: &str,
    nonce: u64,
    entropy: f64,
    grounding: f64,
    sacrifice: f64,
    compliance: f64,
    otel_spans: &serde_json::Value,
) -> serde_json::Value {
    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let script = repo_root().join("integrity-oracle/backend/tests/support/sign_telemetry.py");
    let output = Command::new(sdk_python)
        .args([
            script.to_str().unwrap(),
            private_key,
            agent_id,
            &nonce.to_string(),
            &entropy.to_string(),
            &grounding.to_string(),
            &sacrifice.to_string(),
            &compliance.to_string(),
            &otel_spans.to_string(),
        ])
        .output()
        .expect("integrity-sdk venv python must exist (run `uv pip install -e .` in integrity-sdk)");
    assert!(
        output.status.success(),
        "telemetry signing failed:\nstdout: {}\nstderr: {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("sign_telemetry.py must print a JSON payload")
}

fn sign_telemetry(private_key: &str, agent_id: &str, nonce: u64, entropy: f64, grounding: f64, sacrifice: f64, compliance: f64) -> serde_json::Value {
    sign_telemetry_with_spans(private_key, agent_id, nonce, entropy, grounding, sacrifice, compliance, &serde_json::json!([]))
}

/// Real OTLP/gRPC ingestion (PRODUCTION_GAPS.md §1 item 2), exercised with the SDK's
/// actual, unmodified `OTLPSpanExporter`/`init_telemetry` — not a hand-rolled tonic
/// client — since the whole point is proving the receiver's resource-attribute
/// extraction (`otlp::AGENT_ID_ATTRIBUTE_KEY`) agrees with what the real SDK sends
/// (`integrity_sdk/telemetry/core.py`'s `Resource.create({"integrity.agent.id": ...})`).
/// A mismatch here would make every real span the SDK sends get rejected while the Rust
/// side still compiles and unit-tests clean — this is the check that catches that class
/// of bug (and did, once, during this feature's development).
#[tokio::test]
async fn oracle_e2e_otlp_ingestion() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_otlp_ingestion (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    let otlp_port = free_port();
    let otlp_addr: SocketAddr = format!("127.0.0.1:{otlp_port}").parse().unwrap();
    let otlp_state = state.clone();
    tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(backend::otlp::TraceServiceServer::new(backend::otlp::OtlpTraceService::new(otlp_state.clone())))
            .add_service(backend::otlp::MetricsServiceServer::new(backend::otlp::OtlpMetricsService::new(otlp_state)))
            .serve(otlp_addr)
            .await
            .unwrap();
    });
    // Wait for the gRPC port to accept connections before the SDK tries to export to it.
    // `tokio::net`, not `std::net`, so this actually yields to the runtime between
    // attempts rather than risking starving the just-spawned server task.
    let mut otlp_ready = false;
    for _ in 0..50 {
        if tokio::net::TcpStream::connect(otlp_addr).await.is_ok() {
            otlp_ready = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(otlp_ready, "in-process OTLP grpc server never became reachable on {otlp_addr}");

    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let script = repo_root().join("integrity-oracle/backend/tests/support/otlp_send_span.py");
    // `tokio::process::Command`, NOT `std::process::Command`: this test runs on the
    // default single-threaded `#[tokio::test]` runtime, and the in-process OTLP server
    // above is a spawned task on that SAME runtime. A blocking `std::process::Command`
    // wait here would starve that task of any chance to run while this subprocess is
    // alive, so the exporter would hang until its own client-side deadline and this
    // assertion would fail even though the receiver is implemented correctly — a real
    // bug in this test's own concurrency, caught by running it for real rather than
    // trusting that it compiles.
    let output = tokio::process::Command::new(&sdk_python)
        .args([script.to_str().unwrap(), &format!("127.0.0.1:{otlp_port}"), "did:integrity:otlp-e2e-agent", "real"])
        .output()
        .await
        .expect("integrity-sdk venv python must exist");
    assert!(output.status.success(), "real span export failed:\nstdout: {}\nstderr: {}", String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr));

    let row: (String, String) = sqlx::query_as("SELECT agent_id, name FROM otel_spans WHERE agent_id = $1")
        .bind("did:integrity:otlp-e2e-agent")
        .fetch_one(&state.pool)
        .await
        .expect("a real span sent via the SDK's real OTLPSpanExporter must land in otel_spans");
    assert_eq!(row.0, "did:integrity:otlp-e2e-agent");
    assert_eq!(row.1, "verify-span");

    // A span carrying unredacted PHI must be rejected (INVALID_ARGUMENT) and never
    // persisted — same PHI backstop posture as POST /v1/telemetry/ingest, applied here.
    let output = tokio::process::Command::new(&sdk_python)
        .args([script.to_str().unwrap(), &format!("127.0.0.1:{otlp_port}"), "did:integrity:otlp-phi-e2e-agent", "phi"])
        .output()
        .await
        .expect("integrity-sdk venv python must exist");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("INVALID_ARGUMENT") || stderr.contains("PHI"), "PHI span must be rejected by the receiver, got: {stderr}");

    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM otel_spans WHERE agent_id = $1")
        .bind("did:integrity:otlp-phi-e2e-agent")
        .fetch_one(&state.pool)
        .await
        .unwrap();
    assert_eq!(count, 0, "a PHI-flagged span must never be persisted");
}

/// Proves the "single AIS computation path" invariant end-to-end, over real HTTP: an
/// SSE subscriber's pushed `AisUpdate` (triggered by a real, EIP-191-signed
/// `POST /v1/telemetry/ingest`) must carry the exact same numbers a direct
/// `GET /v1/agent/{id}/ais` call returns immediately after — proving `stream.rs`'s push
/// and `handlers::get_ais` both go through the same `compute_ais_for_agent` call, never
/// two independently-drifting formula paths.
#[tokio::test]
async fn oracle_e2e_sse_matches_direct_ais() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_sse_matches_direct_ais (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    // A throwaway secp256k1 key, registered directly into `agents` (bypassing on-chain
    // registration, which this test doesn't need — it only exercises the signature
    // verification + telemetry ingest + SSE/AIS paths, not on-chain primitive resolution).
    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let keygen = Command::new(&sdk_python)
        .args(["-c", "from eth_account import Account; a = Account.create(); print(a.address); print(a.key.hex())"])
        .output()
        .expect("integrity-sdk venv python must exist");
    let keygen_out = String::from_utf8_lossy(&keygen.stdout);
    let mut lines = keygen_out.lines();
    let address = lines.next().unwrap().to_string();
    let private_key = lines.next().unwrap().to_string();

    let agent_id = "did:integrity:sse-e2e-agent";
    sqlx::query("INSERT INTO agents (id, eth_address, verification_tier, last_nonce) VALUES ($1, $2, 1, 0)")
        .bind(agent_id)
        .bind(&address)
        .execute(&state.pool)
        .await
        .unwrap();

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let base = format!("http://127.0.0.1:{server_port}");
    let http = reqwest::Client::new();

    // Subscribe to the SSE stream before triggering the event that should appear on it.
    let stream_resp = http.get(format!("{base}/v1/agent/{agent_id}/stream")).send().await.unwrap();
    assert_eq!(stream_resp.status(), 200);
    let mut byte_stream = stream_resp.bytes_stream();

    let payload = sign_telemetry(&private_key, agent_id, 1, 0.2, 0.8, 5.0, 0.0);
    let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
    assert_eq!(resp.status(), 200, "real EIP-191-signed telemetry must be accepted: {}", resp.text().await.unwrap());

    // Read SSE frames until an `ais_update` event arrives (a `telemetry` event may arrive
    // first — both are pushed from the same ingest, per handlers::ingest_telemetry).
    let mut buf = String::new();
    let ais_from_stream: serde_json::Value = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            let chunk = byte_stream.next().await.expect("stream ended before an ais_update event arrived").unwrap();
            buf.push_str(&String::from_utf8_lossy(&chunk));
            if let Some(idx) = buf.find("event: ais_update") {
                let data_line = buf[idx..].lines().find(|l| l.starts_with("data: ")).unwrap();
                return serde_json::from_str(data_line.strip_prefix("data: ").unwrap()).unwrap();
            }
        }
    })
    .await
    .expect("timed out waiting for an ais_update SSE frame");

    let direct: serde_json::Value = http.get(format!("{base}/v1/agent/{agent_id}/ais")).send().await.unwrap().json().await.unwrap();

    assert_eq!(
        ais_from_stream["ais"], direct["ais"],
        "SSE-pushed AIS must exactly match a direct GET /ais read (single computation path)"
    );
    assert_eq!(ais_from_stream["components"], direct["components"]);
}

/// Proves the actual point of the AIS input-signal trust hardening: a client that
/// signs a request CLAIMING an inflated `grounding=0.95` alongside `otel_spans` whose
/// real text content is full of hallucination markers must have the LOW,
/// oracle-recomputed value (~0.40, from `derive::keyword_grounding_score`) land in
/// storage and in the AIS breakdown — never the client's claim. Built on the grounding
/// axis specifically: unlike entropy, grounding's SDK->scoring-core mapping has no
/// pre-existing polarity bug, so this assertion isn't confounded by anything except
/// the one thing it's testing.
#[tokio::test]
async fn oracle_e2e_recomputed_grounding_overrides_inflated_client_claim() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_recomputed_grounding_overrides_inflated_client_claim (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let keygen = Command::new(&sdk_python)
        .args(["-c", "from eth_account import Account; a = Account.create(); print(a.address); print(a.key.hex())"])
        .output()
        .expect("integrity-sdk venv python must exist");
    let keygen_out = String::from_utf8_lossy(&keygen.stdout);
    let mut lines = keygen_out.lines();
    let address = lines.next().unwrap().to_string();
    let private_key = lines.next().unwrap().to_string();

    let agent_id = "did:integrity:grounding-override-e2e-agent";
    sqlx::query("INSERT INTO agents (id, eth_address, verification_tier, last_nonce) VALUES ($1, $2, 1, 0)")
        .bind(agent_id)
        .bind(&address)
        .execute(&state.pool)
        .await
        .unwrap();

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let base = format!("http://127.0.0.1:{server_port}");
    let http = reqwest::Client::new();

    let otel_spans = serde_json::json!([{
        "kind": "telemetry",
        "metadata": { "text_output": "I'm not sure, I think I might hallucinate this answer." }
    }]);

    // Client CLAIMS an inflated grounding=0.95 (as if the text were clean) while the
    // otel_spans it signs alongside that claim actually contain hallucination markers.
    let payload = sign_telemetry_with_spans(&private_key, agent_id, 1, 0.9, 0.95, 0.0, 0.0, &otel_spans);
    let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
    assert_eq!(resp.status(), 200, "well-formed, validly-signed request must be accepted: {}", resp.text().await.unwrap());

    // Read back what was actually stored via the real telemetry-history endpoint — must
    // reflect the ORACLE's recomputation (0.40, hallucination markers detected), never
    // the client's inflated claim (0.95).
    let resp = http.get(format!("{base}/v1/agent/{agent_id}/telemetry")).send().await.unwrap();
    let history: serde_json::Value = resp.json().await.unwrap();
    let stored_hgi_raw = history.as_array().unwrap()[0]["hgi_raw"].as_f64().unwrap();
    assert!(
        (stored_hgi_raw - 0.40).abs() < 1e-6,
        "stored grounding must be the oracle's own recomputation (0.40), not the client's inflated claim (0.95): got {stored_hgi_raw}"
    );

    // And the AIS breakdown must show the LOW S_grounding component, not one that
    // reflects the client's claim-inflated 0.95.
    let resp = http.get(format!("{base}/v1/agent/{agent_id}/ais")).send().await.unwrap();
    let ais: serde_json::Value = resp.json().await.unwrap();
    let s_grounding = ais["components"]["grounding"].as_f64().unwrap();
    assert!(s_grounding < 500.0, "S_grounding must reflect the oracle-recomputed low-grounding signal, got {s_grounding}: {ais}");
}

/// Regression test for the compliance/`flagged` polarity inversion (PRODUCTION_GAPS.md
/// §2): `handlers::ingest_telemetry` used to compute `flagged = compliance > 0.5` against
/// a high-is-GOOD `compliance` value, so a perfectly clean batch was stored as
/// `flagged=true` (penalized) and an all-violation batch as `flagged=false` (not
/// penalized) — inverted for every agent. Asserts polarity end-to-end via the real HTTP
/// ingest + read path for both a clean and an all-violation batch on the same agent, so
/// this can never silently regress again.
#[tokio::test]
async fn oracle_e2e_compliance_flagged_polarity_is_correct() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_compliance_flagged_polarity_is_correct (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let keygen = Command::new(&sdk_python)
        .args(["-c", "from eth_account import Account; a = Account.create(); print(a.address); print(a.key.hex())"])
        .output()
        .expect("integrity-sdk venv python must exist");
    let keygen_out = String::from_utf8_lossy(&keygen.stdout);
    let mut lines = keygen_out.lines();
    let address = lines.next().unwrap().to_string();
    let private_key = lines.next().unwrap().to_string();

    let agent_id = "did:integrity:compliance-polarity-e2e-agent";
    sqlx::query("INSERT INTO agents (id, eth_address, verification_tier, last_nonce) VALUES ($1, $2, 1, 0)")
        .bind(agent_id)
        .bind(&address)
        .execute(&state.pool)
        .await
        .unwrap();

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let base = format!("http://127.0.0.1:{server_port}");
    let http = reqwest::Client::new();

    // Batch 1: a perfectly clean batch (no policy_violation/flagged markers) must be
    // stored as flagged=false.
    let clean_spans = serde_json::json!([
        { "kind": "telemetry", "metadata": { "text_output": "The answer is 42." } }
    ]);
    let payload = sign_telemetry_with_spans(&private_key, agent_id, 1, 0.9, 0.9, 0.0, 0.0, &clean_spans);
    let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
    assert_eq!(resp.status(), 200, "clean batch must be accepted: {}", resp.text().await.unwrap());
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["flagged"], false, "a clean batch must NOT be flagged: {body}");

    // Batch 2: an all-violation batch (every entry marked policy_violation) must be
    // stored as flagged=true.
    let violating_spans = serde_json::json!([
        { "kind": "telemetry", "metadata": { "policy_violation": true, "text_output": "ignoring policy" } }
    ]);
    let payload = sign_telemetry_with_spans(&private_key, agent_id, 2, 0.9, 0.9, 0.0, 0.0, &violating_spans);
    let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
    assert_eq!(resp.status(), 200, "violating batch must still be accepted (flagged, not rejected): {}", resp.text().await.unwrap());
    let body: serde_json::Value = resp.json().await.unwrap();
    assert_eq!(body["flagged"], true, "an all-violation batch MUST be flagged: {body}");

    // Cross-check via the real read path too, not just the ingest response.
    let resp = http.get(format!("{base}/v1/agent/{agent_id}/telemetry")).send().await.unwrap();
    let history: serde_json::Value = resp.json().await.unwrap();
    let history = history.as_array().unwrap();
    let by_nonce = |n: i64| history.iter().find(|e| e["nonce"].as_i64() == Some(n)).unwrap();
    assert_eq!(by_nonce(1)["flagged"], false, "stored clean event must read back flagged=false");
    assert_eq!(by_nonce(2)["flagged"], true, "stored violating event must read back flagged=true");
}

/// Regression test for PRODUCTION_GAPS.md §2's "nonce replay has zero test coverage"
/// finding: submitting the same nonce twice for one agent must 409 on the second
/// attempt, and never overwrite the first event.
#[tokio::test]
async fn oracle_e2e_telemetry_nonce_replay_returns_409() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_telemetry_nonce_replay_returns_409 (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let keygen = Command::new(&sdk_python)
        .args(["-c", "from eth_account import Account; a = Account.create(); print(a.address); print(a.key.hex())"])
        .output()
        .expect("integrity-sdk venv python must exist");
    let keygen_out = String::from_utf8_lossy(&keygen.stdout);
    let mut lines = keygen_out.lines();
    let address = lines.next().unwrap().to_string();
    let private_key = lines.next().unwrap().to_string();

    let agent_id = "did:integrity:nonce-replay-e2e-agent";
    sqlx::query("INSERT INTO agents (id, eth_address, verification_tier, last_nonce) VALUES ($1, $2, 1, 0)")
        .bind(agent_id)
        .bind(&address)
        .execute(&state.pool)
        .await
        .unwrap();

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let base = format!("http://127.0.0.1:{server_port}");
    let http = reqwest::Client::new();

    let payload = sign_telemetry(&private_key, agent_id, 1, 0.9, 0.9, 0.0, 0.0);
    let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
    assert_eq!(resp.status(), 200, "first submission of a fresh nonce must be accepted: {}", resp.text().await.unwrap());

    // Same nonce again (a different, freshly-signed payload — a real replaying agent
    // wouldn't necessarily resend byte-identical bytes, only the same nonce value).
    let payload = sign_telemetry(&private_key, agent_id, 1, 0.5, 0.5, 0.5, 0.5);
    let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
    assert_eq!(resp.status(), 409, "replaying an already-used nonce must be rejected with 409 Conflict");

    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM telemetry_events WHERE agent_id = $1")
        .bind(agent_id)
        .fetch_one(&state.pool)
        .await
        .unwrap();
    assert_eq!(count, 1, "the replayed submission must never overwrite or duplicate the original event");
}

/// Regression test for PRODUCTION_GAPS.md §2's "rate limiting has zero test coverage"
/// finding: exceeding `telemetry_rate_limit_per_minute` must 429, using a deliberately
/// tiny override so this test doesn't need to send 60+ real signed requests.
#[tokio::test]
async fn oracle_e2e_telemetry_rate_limit_returns_429() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_telemetry_rate_limit_returns_429 (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let mut state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;
    let mut cfg = (*state.config).clone();
    cfg.telemetry_rate_limit_per_minute = 2;
    state.config = Arc::new(cfg);

    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let keygen = Command::new(&sdk_python)
        .args(["-c", "from eth_account import Account; a = Account.create(); print(a.address); print(a.key.hex())"])
        .output()
        .expect("integrity-sdk venv python must exist");
    let keygen_out = String::from_utf8_lossy(&keygen.stdout);
    let mut lines = keygen_out.lines();
    let address = lines.next().unwrap().to_string();
    let private_key = lines.next().unwrap().to_string();

    let agent_id = "did:integrity:telemetry-rate-limit-e2e-agent";
    sqlx::query("INSERT INTO agents (id, eth_address, verification_tier, last_nonce) VALUES ($1, $2, 1, 0)")
        .bind(agent_id)
        .bind(&address)
        .execute(&state.pool)
        .await
        .unwrap();

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let base = format!("http://127.0.0.1:{server_port}");
    let http = reqwest::Client::new();

    // Limit is 2/minute: the first two submissions succeed, the third must 429.
    for nonce in 1..=2u64 {
        let payload = sign_telemetry(&private_key, agent_id, nonce, 0.9, 0.9, 0.0, 0.0);
        let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
        assert_eq!(resp.status(), 200, "submission {nonce} within the limit must be accepted: {}", resp.text().await.unwrap());
    }
    let payload = sign_telemetry(&private_key, agent_id, 3, 0.9, 0.9, 0.0, 0.0);
    let resp = http.post(format!("{base}/v1/telemetry/ingest")).json(&payload).send().await.unwrap();
    assert_eq!(resp.status(), 429, "the submission exceeding the per-minute limit must be rejected with 429 Too Many Requests");
}

/// Regression test for the OTLP receiver's rate limiter added this session
/// (PRODUCTION_GAPS.md §2: the OTLP path previously had NO throttle at all, unlike the
/// authenticated `/v1/telemetry/ingest` path). Uses a tiny override for the same reason
/// as the HTTP rate-limit test above.
#[tokio::test]
async fn oracle_e2e_otlp_rate_limit_rejects_excess_spans() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_otlp_rate_limit_rejects_excess_spans (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let mut state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;
    let mut cfg = (*state.config).clone();
    cfg.telemetry_rate_limit_per_minute = 2;
    state.config = Arc::new(cfg);

    let otlp_port = free_port();
    let otlp_addr: SocketAddr = format!("127.0.0.1:{otlp_port}").parse().unwrap();
    let otlp_state = state.clone();
    tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(backend::otlp::TraceServiceServer::new(backend::otlp::OtlpTraceService::new(otlp_state.clone())))
            .add_service(backend::otlp::MetricsServiceServer::new(backend::otlp::OtlpMetricsService::new(otlp_state)))
            .serve(otlp_addr)
            .await
            .unwrap();
    });
    let mut otlp_ready = false;
    for _ in 0..50 {
        if tokio::net::TcpStream::connect(otlp_addr).await.is_ok() {
            otlp_ready = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(otlp_ready, "in-process OTLP grpc server never became reachable on {otlp_addr}");

    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let script = repo_root().join("integrity-oracle/backend/tests/support/otlp_send_span.py");
    let agent_id = "did:integrity:otlp-rate-limit-e2e-agent";

    // Limit is 2/minute: the first two exports succeed.
    for _ in 0..2 {
        let output = tokio::process::Command::new(&sdk_python)
            .args([script.to_str().unwrap(), &format!("127.0.0.1:{otlp_port}"), agent_id, "real"])
            .output()
            .await
            .expect("integrity-sdk venv python must exist");
        assert!(output.status.success(), "span export within the limit must succeed:\nstdout: {}\nstderr: {}", String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr));
    }

    // The third export in the same window must be rejected (RESOURCE_EXHAUSTED).
    let output = tokio::process::Command::new(&sdk_python)
        .args([script.to_str().unwrap(), &format!("127.0.0.1:{otlp_port}"), agent_id, "real"])
        .output()
        .await
        .expect("integrity-sdk venv python must exist");
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("RESOURCE_EXHAUSTED") || stderr.contains("rate limit"), "span export exceeding the OTLP rate limit must be rejected, got: {stderr}");

    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM otel_spans WHERE agent_id = $1")
        .bind(agent_id)
        .fetch_one(&state.pool)
        .await
        .unwrap();
    assert_eq!(count, 2, "only the two spans within the rate limit must have been persisted");
}

/// LangSmith-style nested run-tree view (`GET /v1/traces/{trace_id}`, `trace_tree.rs`):
/// sends a real 3-level parent/child/grandchild span tree via genuine OTel context
/// propagation (not hand-constructed parent_span_id fields — `otlp_send_span.py`'s
/// "nested" mode uses real nested `tracer.start_as_current_span` blocks), then asserts
/// the oracle reconstructs the exact same nesting via the real gRPC receiver + a real
/// HTTP read.
#[tokio::test]
async fn oracle_e2e_trace_tree_reconstructs_real_span_nesting() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_trace_tree_reconstructs_real_span_nesting (set ORACLE_E2E=1 with Postgres+Redis+anvil+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    let otlp_port = free_port();
    let otlp_addr: SocketAddr = format!("127.0.0.1:{otlp_port}").parse().unwrap();
    let otlp_state = state.clone();
    tokio::spawn(async move {
        tonic::transport::Server::builder()
            .add_service(backend::otlp::TraceServiceServer::new(backend::otlp::OtlpTraceService::new(otlp_state.clone())))
            .add_service(backend::otlp::MetricsServiceServer::new(backend::otlp::OtlpMetricsService::new(otlp_state)))
            .serve(otlp_addr)
            .await
            .unwrap();
    });
    let mut otlp_ready = false;
    for _ in 0..50 {
        if tokio::net::TcpStream::connect(otlp_addr).await.is_ok() {
            otlp_ready = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(otlp_ready, "in-process OTLP grpc server never became reachable on {otlp_addr}");

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let base = format!("http://127.0.0.1:{server_port}");
    let http = reqwest::Client::new();

    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let script = repo_root().join("integrity-oracle/backend/tests/support/otlp_send_span.py");
    // tokio::process::Command, not std::process::Command: this test runs on the
    // default single-threaded #[tokio::test] runtime, and the in-process OTLP server
    // above is a spawned task on that same runtime — a blocking wait here would starve
    // it (see oracle_e2e_otlp_ingestion's own comment on this exact pitfall).
    let output = tokio::process::Command::new(&sdk_python)
        .args([script.to_str().unwrap(), &format!("127.0.0.1:{otlp_port}"), "did:integrity:trace-tree-e2e-agent", "nested"])
        .output()
        .await
        .expect("integrity-sdk venv python must exist");
    assert!(output.status.success(), "nested span export failed:\nstdout: {}\nstderr: {}", String::from_utf8_lossy(&output.stdout), String::from_utf8_lossy(&output.stderr));
    let trace_id = String::from_utf8_lossy(&output.stdout).trim().to_string();
    assert_eq!(trace_id.len(), 32, "trace_id must be a 32-char hex string, got: {trace_id:?}");

    let resp = http.get(format!("{base}/v1/traces/{trace_id}")).send().await.unwrap();
    assert_eq!(resp.status(), 200, "trace tree endpoint must find the just-ingested trace: {}", resp.text().await.unwrap());
    let tree: serde_json::Value = resp.json().await.unwrap();

    assert_eq!(tree["trace_id"], trace_id);
    assert_eq!(tree["span_count"], 3);
    assert_eq!(tree["truncated"], false);

    let roots = tree["roots"].as_array().unwrap();
    assert_eq!(roots.len(), 1, "must reconstruct exactly one root span: {tree}");
    assert_eq!(roots[0]["name"], "agent-run");
    let children = roots[0]["children"].as_array().unwrap();
    assert_eq!(children.len(), 1, "root must have exactly one child: {tree}");
    assert_eq!(children[0]["name"], "llm-call");
    let grandchildren = children[0]["children"].as_array().unwrap();
    assert_eq!(grandchildren.len(), 1, "child must have exactly one grandchild: {tree}");
    assert_eq!(grandchildren[0]["name"], "tool-call");
    assert!(grandchildren[0]["children"].as_array().unwrap().is_empty());

    // Unknown trace_id must 404, not silently return an empty tree.
    let resp = http.get(format!("{base}/v1/traces/0000000000000000000000000000dead")).send().await.unwrap();
    assert_eq!(resp.status(), 404, "an unknown trace_id must 404");
}

/// `GET /v1/agents` carries each agent's on-chain XNS handle, and — the part that matters —
/// degrades to `handle: null` instead of failing the whole request when XNS can't be read.
///
/// This is the regression this test exists for: `get_agent_handle` (the single-agent route)
/// deliberately surfaces a missing `XibalbaNameService` singleton as a 400, since there the
/// handle *is* the response. `list_agents` must NOT copy that behavior — it's the route the
/// dashboard's entire fleet list depends on, so a chain without XNS deployed (or a transient
/// RPC error) turning "no handles" into "no agents" would be a hard regression.
///
/// Runs against a real anvil + real `deployments.local.json` with the `XibalbaNameService`
/// key stripped out — a real deployment shape (XNS post-dates the genesis deploy), not a
/// mocked chain client.
#[tokio::test]
async fn oracle_e2e_agents_list_degrades_without_xns() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_agents_list_degrades_without_xns (set ORACLE_E2E=1 with Postgres+Redis+anvil to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);

    // Real deployments file, minus the XNS singleton.
    let mut deployments: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(repo_root().join("deployments.local.json")).unwrap()).unwrap();
    deployments["singletons"].as_object_mut().unwrap().remove("XibalbaNameService");
    let stripped = std::env::temp_dir().join(format!("deployments-no-xns-{anvil_port}.json"));
    std::fs::write(&stripped, serde_json::to_string(&deployments).unwrap()).unwrap();

    let state = build_state(&rpc_url, &stripped, &db_url, &redis_url).await;
    assert!(
        state.chain.xibalba_name_service().is_none(),
        "test setup is wrong if XNS is still configured — it would not exercise the degradation path"
    );

    // Two agents: one with a cached primitive set (the normal case), one without any
    // `agent_primitives` row at all (must still appear — the query LEFT JOINs on purpose).
    let with_primitives = "did:integrity:xns-e2e-with-primitives";
    let without_primitives = "did:integrity:xns-e2e-without-primitives";
    let addr_of = |n: u8| format!("0x{:040x}", n);
    // `eth_address` is required: migration 0001's `agents_has_a_verification_method` check
    // constraint refuses a row with neither an eth_address nor an ed25519_pubkey.
    for (i, id) in [with_primitives, without_primitives].into_iter().enumerate() {
        sqlx::query("INSERT INTO agents (id, eth_address, verification_tier, last_nonce) VALUES ($1, $2, 1, 0)")
            .bind(id)
            .bind(addr_of(100 + i as u8))
            .execute(&state.pool)
            .await
            .unwrap();
    }
    db::upsert_agent_primitives(
        &state.pool,
        with_primitives,
        &addr_of(1), &addr_of(2), &addr_of(3), &addr_of(4), &addr_of(5), &addr_of(6), &addr_of(7),
        &addr_of(8),
        "0",
    )
    .await
    .unwrap();

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let http = reqwest::Client::new();

    let resp = http.get(format!("http://127.0.0.1:{server_port}/v1/agents")).send().await.unwrap();
    assert_eq!(
        resp.status(),
        200,
        "/v1/agents must stay 200 with XNS undeployed, not 400 like the single-agent handle route"
    );
    let agents: Vec<serde_json::Value> = resp.json().await.unwrap();

    for id in [with_primitives, without_primitives] {
        let agent = agents
            .iter()
            .find(|a| a["id"] == id)
            .unwrap_or_else(|| panic!("agent {id} must appear in the fleet list; got {agents:?}"));
        assert!(
            agent["handle"].is_null(),
            "handle must degrade to null when XNS is undeployed, got {:?}",
            agent["handle"]
        );
    }

    let _ = std::fs::remove_file(&stripped);
}

/// Spec v0.3 §7.1: an agent with no anchored genesis memory root MUST be refused at
/// registration with `400 MemoryNotInitialized` — persistent memory (§4.1) is a
/// foundational primitive, and an agent that cannot carry state across sessions is not a
/// continuing economic subject, so it is not registerable.
///
/// The agent under test is deployed through the real on-chain path (real
/// `SovereignAgent`/`StateAnchor` deploys, real `registerPrimitives`) with exactly one
/// transaction omitted: the genesis anchor. So this asserts the gate fires on a genuinely
/// zero-root agent, not on a hand-faked payload — the PrimitiveSet it presents is real and
/// matches `XibalbaAgentRegistry`, meaning the request gets past the primitive
/// re-verification and is rejected *specifically* by the memory gate.
#[tokio::test]
async fn oracle_e2e_register_rejects_missing_genesis_memory_root() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_register_rejects_missing_genesis_memory_root (set ORACLE_E2E=1 with Postgres+Redis+anvil+forge+sdk-venv to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    run_deploy(&rpc_url);
    let deployments_file = repo_root().join("deployments.local.json");

    let wallet_home = std::env::temp_dir().join(format!("integrity-e2e-nogenesis-{anvil_port}"));
    let sdk_python = repo_root().join("integrity-sdk/.venv/bin/python");
    let script = repo_root().join("integrity-oracle/backend/tests/support/register_agent_no_genesis.py");
    let output = Command::new(sdk_python)
        .args([
            script.to_str().unwrap(),
            &rpc_url,
            deployments_file.to_str().unwrap(),
            "oracle-e2e-no-genesis",
        ])
        .env("FUNDER_PRIVATE_KEY", ANVIL_KEY)
        .env("INTEGRITY_WALLET_PASSWORD", "oracle-e2e-test-pw")
        .env("INTEGRITY_WALLET_HOME", format!("{}/wallet", wallet_home.display()))
        .env("INTEGRITY_DID_HOME", format!("{}/did", wallet_home.display()))
        .output()
        .expect("integrity-sdk venv python must exist");
    assert!(
        output.status.success(),
        "no-genesis on-chain registration failed:\nstdout: {}\nstderr: {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let reg: serde_json::Value =
        serde_json::from_str(String::from_utf8_lossy(&output.stdout).lines().last().unwrap())
            .expect("support script must print registration JSON on its last stdout line");

    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    // Precondition, read from chain rather than assumed: this agent really has no root.
    let anchor: alloy::primitives::Address = reg["state_anchor"].as_str().unwrap().parse().unwrap();
    let (root, epoch) = state.chain.memory_state(anchor).await.unwrap();
    assert!(root.is_zero(), "test setup is wrong if the agent already has a genesis root");
    assert_eq!(epoch, alloy::primitives::U256::ZERO, "no root anchored means epoch 0");

    let app = backend::build_router(state.clone());
    let server_port = free_port();
    let addr: SocketAddr = format!("127.0.0.1:{server_port}").parse().unwrap();
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    let http = reqwest::Client::new();

    let resp = http
        .post(format!("http://127.0.0.1:{server_port}/v1/agent/register"))
        .json(&serde_json::json!({
            "did": reg["did"],
            "did_document": {"id": reg["did"]},
            "primitives": {
                "sovereign_agent": reg["sovereign_agent"],
                "state_anchor": reg["state_anchor"],
                "reputation_registry": reg["reputation_registry"],
                "slasher": reg["slasher"],
                "verifier_registry": reg["verifier_registry"],
                "compliance_gate": reg["compliance_gate"],
                "agent_profile": reg["agent_profile"],
            },
            "eth_address_hex": reg["eth_address"],
        }))
        .send()
        .await
        .unwrap();

    assert_eq!(resp.status(), 400, "a zero genesis root must be refused with 400, not accepted");
    let body = resp.text().await.unwrap();
    assert!(
        body.contains("memory not initialized"),
        "rejection must name the memory gate specifically (not a generic chain mismatch): {body}"
    );

    // And the refusal must be total — no half-registered agent left behind (§6).
    let listed = db::list_agents(&state.pool).await.unwrap();
    assert!(
        !listed.iter().any(|a| a.id == reg["did"].as_str().unwrap()),
        "a rejected agent must not be persisted"
    );
}

/// The OTLP metrics + logs receivers persist real agent token/cost data.
///
/// Shaped as an actual Claude Code export (`claude_code.token.usage` with
/// `type=cacheRead`, `claude_code.cost.usage` in USD, and a `claude_code.api_request` log
/// record carrying per-call tokens and `cost_usd`), because that is the emitter this work
/// exists to receive. Before this, `OtlpMetricsService::export` accepted and discarded, and
/// no logs service was registered at all.
///
/// Asserts the rows land with `evidence_tier = 'unsigned_vendor'` — the OTLP port is
/// unauthenticated, so this data must stay distinguishable from agent-signed telemetry.
#[tokio::test]
async fn oracle_e2e_otlp_metrics_and_logs_persist() {
    if std::env::var("ORACLE_E2E").ok().as_deref() != Some("1") {
        eprintln!("SKIP oracle_e2e_otlp_metrics_and_logs_persist (set ORACLE_E2E=1 with Postgres+Redis+anvil to run)");
        return;
    }
    let _ = tracing_subscriber::fmt().with_max_level(tracing::Level::ERROR).try_init();

    use opentelemetry_proto::tonic::collector::logs::v1::logs_service_server::LogsService;
    use opentelemetry_proto::tonic::collector::logs::v1::ExportLogsServiceRequest;
    use opentelemetry_proto::tonic::collector::metrics::v1::metrics_service_server::MetricsService;
    use opentelemetry_proto::tonic::collector::metrics::v1::ExportMetricsServiceRequest;
    use opentelemetry_proto::tonic::common::v1::{any_value::Value as AnyValueKind, AnyValue, KeyValue};
    use opentelemetry_proto::tonic::logs::v1::{LogRecord, ResourceLogs, ScopeLogs};
    use opentelemetry_proto::tonic::metrics::v1::{
        metric::Data as MetricData, number_data_point::Value as NumberValue, Metric, NumberDataPoint,
        ResourceMetrics, ScopeMetrics, Sum,
    };
    use opentelemetry_proto::tonic::resource::v1::Resource;

    let db_url = std::env::var("TEST_DATABASE_URL")
        .unwrap_or_else(|_| "postgres://integrity:integrity_dev_only@127.0.0.1:5434/integrity".to_string());
    let redis_url = std::env::var("TEST_REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1:6379".to_string());
    let anvil_port = free_port();
    let rpc_url = format!("http://127.0.0.1:{anvil_port}");
    let _anvil = start_anvil(anvil_port);
    let deployments_file = repo_root().join("deployments.local.json");
    let state = build_state(&rpc_url, &deployments_file, &db_url, &redis_url).await;

    let agent_id = "did:integrity:otlp-metrics-logs-agent";
    fn str_kv(key: &str, value: &str) -> KeyValue {
        KeyValue {
            key: key.to_string(),
            value: Some(AnyValue { value: Some(AnyValueKind::StringValue(value.to_string())) }),
            key_strindex: 0,
        }
    }
    fn int_kv(key: &str, value: i64) -> KeyValue {
        KeyValue {
            key: key.to_string(),
            value: Some(AnyValue { value: Some(AnyValueKind::IntValue(value)) }),
            key_strindex: 0,
        }
    }
    let resource = |id: &str| Some(Resource { attributes: vec![str_kv("integrity.agent.id", id)], dropped_attributes_count: 0, entity_refs: vec![] });

    let now_nanos = 1_800_000_000_000_000_000u64;
    let sum_metric = |name: &str, unit: &str, value: NumberValue, attrs: Vec<KeyValue>| Metric {
        name: name.to_string(),
        description: String::new(),
        unit: unit.to_string(),
        metadata: vec![],
        data: Some(MetricData::Sum(Sum {
            data_points: vec![NumberDataPoint {
                attributes: attrs,
                start_time_unix_nano: now_nanos,
                time_unix_nano: now_nanos,
                exemplars: vec![],
                flags: 0,
                value: Some(value),
            }],
            aggregation_temporality: 2,
            is_monotonic: true,
        })),
    };

    let metrics_req = ExportMetricsServiceRequest {
        resource_metrics: vec![ResourceMetrics {
            resource: resource(agent_id),
            schema_url: String::new(),
            scope_metrics: vec![ScopeMetrics {
                scope: None,
                schema_url: String::new(),
                metrics: vec![
                    sum_metric(
                        "claude_code.token.usage",
                        "tokens",
                        NumberValue::AsInt(15_000),
                        vec![str_kv("type", "cacheRead"), str_kv("model", "claude-opus-5")],
                    ),
                    sum_metric(
                        "claude_code.cost.usage",
                        "USD",
                        NumberValue::AsDouble(0.42),
                        vec![str_kv("model", "claude-opus-5"), str_kv("query_source", "main")],
                    ),
                ],
            }],
        }],
    };

    backend::otlp::OtlpMetricsService::new(state.clone())
        .export(tonic::Request::new(metrics_req))
        .await
        .expect("metrics export must be accepted");

    let logs_req = ExportLogsServiceRequest {
        resource_logs: vec![ResourceLogs {
            resource: resource(agent_id),
            schema_url: String::new(),
            scope_logs: vec![ScopeLogs {
                scope: None,
                schema_url: String::new(),
                log_records: vec![LogRecord {
                    time_unix_nano: now_nanos,
                    observed_time_unix_nano: now_nanos,
                    severity_number: 9,
                    severity_text: "INFO".to_string(),
                    body: None,
                    attributes: vec![
                        str_kv("event.name", "claude_code.api_request"),
                        str_kv("model", "claude-opus-5"),
                        int_kv("input_tokens", 1200),
                        int_kv("output_tokens", 800),
                        int_kv("cache_read_tokens", 15_000),
                        int_kv("cache_creation_tokens", 300),
                    ],
                    dropped_attributes_count: 0,
                    flags: 0,
                    trace_id: vec![],
                    span_id: vec![],
                    event_name: String::new(),
                }],
            }],
        }],
    };

    backend::otlp::OtlpLogsService::new(state.clone())
        .export(tonic::Request::new(logs_req))
        .await
        .expect("logs export must be accepted");

    // Metrics: the cacheRead token count must be queryable BY its data-point attributes —
    // that is the whole point of storing them, since token type lives there, not in the name.
    let (value, tier): (f64, String) = sqlx::query_as(
        "SELECT value, evidence_tier FROM otel_metrics
         WHERE agent_id = $1 AND name = 'claude_code.token.usage' AND attributes->>'type' = 'cacheRead'",
    )
    .bind(agent_id)
    .fetch_one(&state.pool)
    .await
    .expect("cacheRead token metric must be persisted and queryable by attribute");
    assert_eq!(value, 15_000.0);
    assert_eq!(tier, "unsigned_vendor", "OTLP data is unauthenticated and must be tiered as such");

    let (cost,): (f64,) = sqlx::query_as(
        "SELECT value FROM otel_metrics WHERE agent_id = $1 AND name = 'claude_code.cost.usage'",
    )
    .bind(agent_id)
    .fetch_one(&state.pool)
    .await
    .expect("cost metric must be persisted");
    assert!((cost - 0.42).abs() < 1e-9, "real USD cost must survive the round trip, got {cost}");

    // Logs: event identity resolved from the `event.name` attribute, and the per-call token
    // breakdown preserved.
    let (event_name, attrs, tier): (Option<String>, serde_json::Value, String) = sqlx::query_as(
        "SELECT event_name, attributes, evidence_tier FROM otel_logs WHERE agent_id = $1",
    )
    .bind(agent_id)
    .fetch_one(&state.pool)
    .await
    .expect("log record must be persisted");
    assert_eq!(event_name.as_deref(), Some("claude_code.api_request"));
    assert_eq!(attrs["cache_read_tokens"], serde_json::json!(15_000));
    assert_eq!(attrs["output_tokens"], serde_json::json!(800));
    assert_eq!(tier, "unsigned_vendor");

    // A resource with no integrity.agent.id must be rejected, not stored unattributed —
    // same posture as the trace receiver.
    let orphan = ExportLogsServiceRequest {
        resource_logs: vec![ResourceLogs {
            resource: Some(Resource { attributes: vec![], dropped_attributes_count: 0, entity_refs: vec![] }),
            schema_url: String::new(),
            scope_logs: vec![],
        }],
    };
    let err = backend::otlp::OtlpLogsService::new(state.clone())
        .export(tonic::Request::new(orphan))
        .await
        .expect_err("a log export without integrity.agent.id must be rejected");
    assert_eq!(err.code(), tonic::Code::InvalidArgument);
}
