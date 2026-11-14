//! Real-Postgres tests for the unobserved-compliance aggregates (migration 0025).
//!
//! Opt in with `COMPLIANCE_DB_TEST=1` and `TEST_DATABASE_URL`.

use backend::db;
use chrono::{Duration, Utc};
use uuid::Uuid;

/// Fresh random 32 bytes per call, so no fixture reuses a fixed value where the
/// schema expects a hash or signature (and CodeQL sees no hard-coded nonce).
fn random32() -> [u8; 32] {
    let mut out = [0u8; 32];
    out[..16].copy_from_slice(Uuid::new_v4().as_bytes());
    out[16..].copy_from_slice(Uuid::new_v4().as_bytes());
    out
}

#[tokio::test]
async fn aggregates_ignore_unobserved_rows() {
    if std::env::var("COMPLIANCE_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP compliance DB test (set COMPLIANCE_DB_TEST=1)");
        return;
    }
    let db_url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&db_url).await.expect("Postgres must be reachable");
    db::run_migrations(&pool).await.expect("Oracle migrations must apply");

    let agent_id = format!("did:integrity:cobs-{}", Uuid::new_v4().simple());
    sqlx::query("INSERT INTO agents (id, ed25519_pubkey) VALUES ($1, $2)")
        .bind(&agent_id)
        .bind(vec![0u8; 32])
        .execute(&pool)
        .await
        .expect("agent insert");

    // No primitives row: the decision behind `oracle_compliance` returning None.
    assert!(db::get_agent_primitives_on_chain(&pool, &agent_id, 31337)
        .await
        .unwrap()
        .is_none());

    let now = Utc::now();
    // (observed, flagged): the two unobserved rows are flagged=true and must be ignored.
    let rows = [(true, false), (true, true), (false, true), (false, true)];
    for (i, (observed, flagged)) in rows.iter().enumerate() {
        let nonce = i as i64 + 1;
        db::insert_telemetry_event(
            &pool,
            Uuid::new_v4(),
            &agent_id,
            nonce,
            0.1,
            0.9,
            1.0,
            *flagged,
            *observed,
            false,
            &random32(),
            &random32(),
            now,
            &serde_json::json!({"i": nonce}),
            None,
        )
        .await
        .expect("telemetry insert");
    }

    let since = now - Duration::hours(1);
    let agg = db::aggregate_for_ais(&pool, &agent_id, since).await.unwrap();
    assert_eq!(agg.event_count, 4);
    assert_eq!(agg.compliance_observed_count, 2);
    assert!((agg.penalty_ratio - 0.5).abs() < 1e-9, "got {}", agg.penalty_ratio);

    let buckets = db::ais_history_buckets(&pool, &agent_id, "1 day", since).await.unwrap();
    let total: i64 = buckets.iter().map(|b| b.event_count).sum();
    let observed: i64 = buckets.iter().map(|b| b.compliance_observed_count).sum();
    assert_eq!(total, 4);
    assert_eq!(observed, 2);
    // Every bucket's ratio is over observed rows only (0.5 if it holds both observed rows).
    let with_obs: Vec<_> = buckets.iter().filter(|b| b.compliance_observed_count > 0).collect();
    assert_eq!(with_obs.len(), 1);
    assert!((with_obs[0].penalty_ratio - 0.5).abs() < 1e-9);

    // An all-unobserved window: ratio 0.0 and observed count 0.
    let agent2 = format!("did:integrity:cobs-{}", Uuid::new_v4().simple());
    sqlx::query("INSERT INTO agents (id, ed25519_pubkey) VALUES ($1, $2)")
        .bind(&agent2)
        .bind(vec![1u8; 32])
        .execute(&pool)
        .await
        .unwrap();
    db::insert_telemetry_event(
        &pool, Uuid::new_v4(), &agent2, 1, 0.1, 0.9, 1.0, true, false, false,
        &random32(), &random32(), now, &serde_json::json!({}), None,
    )
    .await
    .unwrap();
    let agg2 = db::aggregate_for_ais(&pool, &agent2, since).await.unwrap();
    assert_eq!(agg2.event_count, 1);
    assert_eq!(agg2.compliance_observed_count, 0);
    assert_eq!(agg2.penalty_ratio, 0.0);
}
