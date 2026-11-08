//! Real-Postgres test for `db::agent_anchoring_coverage` — the "are agents anchoring intent?"
//! metric: of the actions an agent executed, what fraction carried a prior signed intent.
//!
//! Opt in with `INVOCATION_DB_TEST=1` and `TEST_DATABASE_URL`, matching invocation_id_db.rs.

use backend::db;
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
