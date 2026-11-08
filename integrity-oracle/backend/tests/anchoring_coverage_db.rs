//! Real-Postgres test for `db::agent_anchoring_coverage` — the "are agents anchoring intent?"
//! metric: of the actions an agent executed, what fraction carried a prior signed intent.
//!
//! Opt in with `INVOCATION_DB_TEST=1` and `TEST_DATABASE_URL`, matching invocation_id_db.rs.

use backend::db;
use chrono::{Duration, Utc};
use uuid::Uuid;

#[tokio::test]
async fn anchoring_coverage_counts_anchored_vs_unanchored_executions() {
    if std::env::var("INVOCATION_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP anchoring coverage DB test (set INVOCATION_DB_TEST=1)");
        return;
    }
    let db_url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&db_url).await.expect("Postgres reachable");
    db::run_migrations(&pool).await.expect("migrations apply");

    // A fresh agent id per run so the per-agent aggregate is isolated.
    let agent = format!("did:integrity:anchoring-cov-{}", Uuid::new_v4().simple());
    db::register_agent(&pool, &agent, None, Some("0x".to_owned() + &"a".repeat(40)), 1, None)
        .await
        .expect("register agent");

    let hash = |n: &str| format!("0x{}", n.repeat(64));

    // (1) An ANCHORED execution: a signed ALLOW intent, then a matching outcome.
    let anchored_inv = Uuid::new_v4();
    db::insert_audit_log(
        &pool, Some(&agent), "bcc", "pretool_gate", "allow", None, None, Some("read_file"),
        &serde_json::json!({"invocation_id": anchored_inv, "intended_state_hash": hash("1")}),
    ).await.expect("intent insert");
    db::insert_audit_effect_idempotent(
        &pool, &agent, "matched",
        &serde_json::json!({"invocation_id": anchored_inv, "intended_state_hash": hash("1"), "matches": true}),
    ).await.expect("matching outcome insert");

    // (2) An UNANCHORED execution: an outcome with NO prior intent.
    let orphan_inv = Uuid::new_v4();
    db::insert_audit_effect_idempotent(
        &pool, &agent, "matched",
        &serde_json::json!({"invocation_id": orphan_inv, "intended_state_hash": hash("2"), "matches": true}),
    ).await.expect("orphan outcome insert");

    // (3) An authorized intent that never executed (surfaced, not counted against coverage).
    let dangling_inv = Uuid::new_v4();
    db::insert_audit_log(
        &pool, Some(&agent), "bcc", "pretool_gate", "allow", None, None, Some("run_command"),
        &serde_json::json!({"invocation_id": dangling_inv, "intended_state_hash": hash("3")}),
    ).await.expect("dangling intent insert");

    let cov = db::agent_anchoring_coverage(&pool, &agent, 500, 50).await.expect("coverage");

    assert_eq!(cov.executions_observed, 2, "two outcomes were reported");
    assert_eq!(cov.executions_anchored, 1, "one had a prior signed intent");
    assert_eq!(cov.executions_unanchored, 1, "one ran without any intent");
    assert_eq!(cov.intents_without_outcome, 1, "one authorized intent never ran");
    assert_eq!(cov.coverage_ratio, Some(0.5));
    assert_eq!(cov.findings.len(), 1, "the one unanchored execution is a finding");
    assert_eq!(cov.findings[0].status, "outcome_without_intent");
    assert_eq!(
        cov.findings[0].invocation_id.as_deref(),
        Some(orphan_inv.to_string().as_str()),
        "the finding names the orphan execution",
    );
}

#[tokio::test]
async fn anchoring_coverage_is_none_for_an_agent_with_no_executions() {
    if std::env::var("INVOCATION_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP anchoring coverage DB test (set INVOCATION_DB_TEST=1)");
        return;
    }
    let db_url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&db_url).await.expect("Postgres reachable");
    db::run_migrations(&pool).await.expect("migrations apply");

    let agent = format!("did:integrity:anchoring-empty-{}", Uuid::new_v4().simple());
    db::register_agent(&pool, &agent, None, Some("0x".to_owned() + &"b".repeat(40)), 1, None)
        .await
        .expect("register agent");

    let cov = db::agent_anchoring_coverage(&pool, &agent, 500, 50).await.expect("coverage");
    assert_eq!(cov.executions_observed, 0);
    assert_eq!(cov.coverage_ratio, None, "no observed executions -> ratio undefined, not 0");
    assert!(cov.findings.is_empty());
}

/// Reconciliation Phase 1: Shield's independent witness becomes the coverage denominator, and — the
/// §6.10 case this exists for — a FULL-BYPASS agent (zero self-reported reconcile rows) is still
/// witnessed via the lookback fallback, reading as a low ratio rather than "no data" / 1.0.
#[tokio::test]
async fn shield_witness_covers_a_full_bypass_agent_with_no_self_reported_rows() {
    if std::env::var("INVOCATION_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP shield witness DB test (set INVOCATION_DB_TEST=1)");
        return;
    }
    let db_url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&db_url).await.expect("Postgres reachable");
    db::run_migrations(&pool).await.expect("migrations apply");

    // A bypassing agent: it never reported an intent OR an outcome, so there are zero reconcile rows.
    let agent = format!("did:integrity:bypass-{}", Uuid::new_v4().simple());
    let device = format!("did:integrity:shield-dev-{}", Uuid::new_v4().simple());
    db::register_agent(&pool, &agent, None, Some("0x".to_owned() + &"c".repeat(40)), 1, None)
        .await
        .expect("register agent");

    // Shield witnessed it anyway: a contiguous, fresh two-record chain (seq 0,1) for this agent.
    // 8 gate-attributed trees total, 3 with no gate receipt (the full-bypass count).
    let now = Utc::now();
    let h0 = format!("0x{}", "a".repeat(64));
    let h1 = format!("0x{}", "b".repeat(64));

    let obs0 = db::ShieldObservationInsert {
        device_id: &device,
        sequence: 0,
        agent_id: &agent,
        window_start: now - Duration::seconds(120),
        window_end: now - Duration::seconds(90),
        executions_witnessed: 5,
        executions_suppressed: 2,
        attribution_confidence: 0.95,
        tree_fingerprint: "sha256:treefp",
        gate_receipt_ref: None,
        record_hash: &h0,
        prev_hash: None,
        device_signature: "sig-placeholder",
    };
    let obs1 = db::ShieldObservationInsert {
        sequence: 1,
        window_end: now - Duration::seconds(30),
        executions_witnessed: 3,
        executions_suppressed: 1,
        record_hash: &h1,
        prev_hash: Some(&h0),
        ..obs0
    };
    assert!(db::insert_shield_observation(&pool, &obs0).await.expect("insert seq 0"), "seq 0 is a fresh insert");
    assert!(db::insert_shield_observation(&pool, &obs1).await.expect("insert seq 1"), "seq 1 is a fresh insert");
    // Idempotent replay of seq 0 (same record_hash) is a no-op, not a second row.
    assert!(
        !db::insert_shield_observation(&pool, &obs0).await.expect("replay seq 0"),
        "byte-identical replay does not insert again"
    );

    let cov = db::agent_anchoring_coverage(&pool, &agent, 500, 50).await.expect("coverage");
    assert_eq!(cov.executions_observed, 0, "the bypasser self-reported nothing");
    assert_eq!(cov.coverage_basis, "shield_witness", "a complete witness replaces the self-reported denominator");
    assert_eq!(cov.executions_witnessed, Some(8), "witnessed trees are summed across the chain");
    assert_eq!(cov.executions_suppressed, Some(3), "full-bypass (no-receipt) trees are summed");
    assert_eq!(cov.witness_complete, Some(true), "a contiguous, fresh, chain-start witness is complete");
    // 0 anchored / 8 witnessed = 0.0 — the bypasser reads as 0% anchored, NOT None and NOT 1.0.
    assert_eq!(cov.coverage_ratio, Some(0.0));
}

/// A gap in the witness chain must flip `witness_complete` to false and the denominator back to the
/// self-reported side (here `None`, since nothing was self-reported) — never a falsely-high ratio.
#[tokio::test]
async fn shield_witness_sequence_gap_reads_as_incomplete() {
    if std::env::var("INVOCATION_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP shield witness DB test (set INVOCATION_DB_TEST=1)");
        return;
    }
    let db_url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&db_url).await.expect("Postgres reachable");
    db::run_migrations(&pool).await.expect("migrations apply");

    let agent = format!("did:integrity:gap-{}", Uuid::new_v4().simple());
    let device = format!("did:integrity:shield-dev-{}", Uuid::new_v4().simple());
    db::register_agent(&pool, &agent, None, Some("0x".to_owned() + &"d".repeat(40)), 1, None)
        .await
        .expect("register agent");

    let now = Utc::now();
    let h0 = format!("0x{}", "0".repeat(64));
    let h2 = format!("0x{}", "2".repeat(64));
    // Insert seq 0 and seq 2 — sequence 1 is missing (lost/suppressed witness).
    for (seq, rhash, prev) in [(0i64, &h0, None), (2, &h2, Some(h0.as_str()))] {
        db::insert_shield_observation(
            &pool,
            &db::ShieldObservationInsert {
                device_id: &device,
                sequence: seq,
                agent_id: &agent,
                window_start: now - Duration::seconds(120),
                window_end: now - Duration::seconds(30),
                executions_witnessed: 4,
                executions_suppressed: 0,
                attribution_confidence: 0.9,
                tree_fingerprint: "sha256:treefp",
                gate_receipt_ref: None,
                record_hash: rhash,
                prev_hash: prev,
                device_signature: "sig-placeholder",
            },
        )
        .await
        .expect("insert observation");
    }

    let cov = db::agent_anchoring_coverage(&pool, &agent, 500, 50).await.expect("coverage");
    assert_eq!(cov.witness_complete, Some(false), "a missing sequence makes the witness incomplete");
    assert_eq!(cov.executions_suppressed, None, "suppressed is only trusted when the witness is complete");
    assert_eq!(cov.coverage_ratio, None, "incomplete witness + nothing self-reported -> None, not a high ratio");
    assert_eq!(cov.coverage_basis, "self_reported", "falls back to (and labels) the self-reported basis");
}
