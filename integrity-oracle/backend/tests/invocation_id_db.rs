//! Real-Postgres tests for the invocation outcome concurrency boundary.
//!
//! Opt in with `INVOCATION_DB_TEST=1` and `TEST_DATABASE_URL`. The default test suite
//! remains infrastructure-free, while the production-readiness run records this test
//! against the same Timescale/Postgres engine used by the Oracle.

use backend::db;
use futures::future::join_all;
use uuid::Uuid;

#[tokio::test]
async fn invocation_outcome_is_idempotent_unique_and_conflict_safe() {
    if std::env::var("INVOCATION_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP invocation DB test (set INVOCATION_DB_TEST=1)");
        return;
    }

    let db_url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&db_url)
        .await
        .expect("Postgres must be reachable");
    db::run_migrations(&pool)
        .await
        .expect("Oracle migrations must apply");

    let invocation_id = Uuid::new_v4();
    let metadata = serde_json::json!({
        "invocation_id": invocation_id,
        "intended_state_hash": format!("0x{}", "1".repeat(64)),
        "effect_hash": format!("0x{}", "2".repeat(64)),
        "matches": true,
    });

    let (first_id, first_matches) = db::insert_audit_effect_idempotent(
        &pool,
        "did:integrity:invocation-db-test",
        "matched",
        &metadata,
    )
    .await
    .expect("first outcome insert succeeds");
    assert!(first_matches);

    let retries = (0..16).map(|_| {
        let pool = pool.clone();
        let metadata = metadata.clone();
        async move {
            db::insert_audit_effect_idempotent(
                &pool,
                "did:integrity:invocation-db-test",
                "matched",
                &metadata,
            )
            .await
            .expect("concurrent retry succeeds")
        }
    });
    let retry_results = join_all(retries).await;
    assert!(
        retry_results
            .iter()
            .all(|(id, matches)| *id == first_id && *matches)
    );

    let stored_count: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM audit_log WHERE event_type = 'posttool_effect' AND metadata->>'invocation_id' = $1",
    )
    .bind(invocation_id.to_string())
    .fetch_one(&pool)
    .await
    .unwrap();
    assert_eq!(
        stored_count, 1,
        "concurrent retries must create exactly one row"
    );

    let conflicting = serde_json::json!({
        "invocation_id": invocation_id,
        "intended_state_hash": format!("0x{}", "1".repeat(64)),
        "effect_hash": format!("0x{}", "3".repeat(64)),
        "matches": false,
    });
    let (conflict_id, payload_matches) = db::insert_audit_effect_idempotent(
        &pool,
        "did:integrity:invocation-db-test",
        "diverged",
        &conflicting,
    )
    .await
    .expect("uniqueness conflict returns the existing row");
    assert_eq!(conflict_id, first_id);
    assert!(
        !payload_matches,
        "reusing an invocation for a different outcome must be rejected by the handler"
    );

    let stored_effect: String =
        sqlx::query_scalar("SELECT metadata->>'effect_hash' FROM audit_log WHERE id = $1")
            .bind(first_id)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(
        stored_effect,
        format!("0x{}", "2".repeat(64)),
        "a conflict must not overwrite evidence"
    );
}
