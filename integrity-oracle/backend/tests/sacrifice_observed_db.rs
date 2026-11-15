//! Real-Postgres tests for the unobserved-sacrifice aggregates (migration 0026).
//!
//! Opt in with `COMPLIANCE_DB_TEST=1` and `TEST_DATABASE_URL` (the same switch as the
//! migration 0025 tests, so one Postgres run covers both proxy axes).

use backend::db;
use chrono::{Duration, Utc};
use uuid::Uuid;

fn random32() -> [u8; 32] {
    let mut out = [0u8; 32];
    out[..16].copy_from_slice(Uuid::new_v4().as_bytes());
    out[16..].copy_from_slice(Uuid::new_v4().as_bytes());
    out
}

#[tokio::test]
async fn sum_gpu_hours_counts_only_attested_rows() {
    if std::env::var("COMPLIANCE_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP sacrifice DB test (set COMPLIANCE_DB_TEST=1)");
        return;
    }
    let db_url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&db_url).await.expect("Postgres must be reachable");
    db::run_migrations(&pool).await.expect("Oracle migrations must apply");

    let agent_id = format!("did:integrity:sobs-{}", Uuid::new_v4().simple());
    sqlx::query("INSERT INTO agents (id, ed25519_pubkey) VALUES ($1, $2)")
        .bind(&agent_id)
        .bind(vec![2u8; 32])
        .execute(&pool)
        .await
        .expect("agent insert");

    let now = Utc::now();
    // (sacrifice_observed, gpu_hours): the unobserved rows carry legacy self-reported
    // proxy hours, which must not reach the sum.
    let rows = [(true, 2.0), (false, 40.0), (false, 7.0)];
    for (i, (observed, hours)) in rows.iter().enumerate() {
        let nonce = i as i64 + 1;
        db::insert_telemetry_event(
            &pool, Uuid::new_v4(), &agent_id, nonce, 0.1, 0.9, *hours, false, false, *observed, false,
            &random32(), &random32(), now, &serde_json::json!({"i": nonce}), None,
        )
        .await
        .expect("telemetry insert");
    }

    let since = now - Duration::hours(1);
    let agg = db::aggregate_for_ais(&pool, &agent_id, since).await.unwrap();
    assert_eq!(agg.event_count, 3);
    assert_eq!(agg.sacrifice_observed_count, 1);
    assert!((agg.sum_gpu_hours - 2.0).abs() < 1e-9, "got {}", agg.sum_gpu_hours);

    let buckets = db::ais_history_buckets(&pool, &agent_id, "1 day", since).await.unwrap();
    assert_eq!(buckets.iter().map(|b| b.sacrifice_observed_count).sum::<i64>(), 1);
    assert!((buckets.iter().map(|b| b.sum_gpu_hours).sum::<f64>() - 2.0).abs() < 1e-9);

    // A legacy row written before migration 0026 takes the column default: unobserved.
    let agent2 = format!("did:integrity:sobs-{}", Uuid::new_v4().simple());
    sqlx::query("INSERT INTO agents (id, ed25519_pubkey) VALUES ($1, $2)")
        .bind(&agent2)
        .bind(vec![3u8; 32])
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query(
        "INSERT INTO telemetry_events (id, agent_id, nonce, performance_variance, hgi_raw, gpu_hours_verified, flagged, zk_verified, leaf_hash, content_hash, event_time, payload)
         VALUES ($1, $2, 1, 0.1, 0.9, 99.0, false, false, $3, $4, $5, '{}'::jsonb)",
    )
    .bind(Uuid::new_v4())
    .bind(&agent2)
    .bind(random32().to_vec())
    .bind(random32().to_vec())
    .bind(now)
    .execute(&pool)
    .await
    .unwrap();
    let agg2 = db::aggregate_for_ais(&pool, &agent2, since).await.unwrap();
    assert_eq!(agg2.event_count, 1);
    assert_eq!(agg2.sacrifice_observed_count, 0);
    assert_eq!(agg2.sum_gpu_hours, 0.0);
}
