//! Real-Postgres proofs for off-chain registration semantics (`db::register_agent_offchain`).
//!
//! Opt in with `OFFCHAIN_REGISTRATION_DB_TEST=1` and `TEST_DATABASE_URL`.

use backend::db::{self, RegistrationConflict, RegistrationOutcome};
use sha2::{Digest, Sha256};
use sqlx::PgPool;
use uuid::Uuid;

/// `None` when the test is not opted in; otherwise a migrated pool.
async fn pool() -> Option<PgPool> {
    if std::env::var("OFFCHAIN_REGISTRATION_DB_TEST").ok().as_deref() != Some("1") {
        eprintln!("SKIP offchain registration DB test (set OFFCHAIN_REGISTRATION_DB_TEST=1)");
        return None;
    }
    let url = std::env::var("TEST_DATABASE_URL").expect("TEST_DATABASE_URL is required");
    let pool = db::create_pool(&url).await.expect("Postgres must be reachable");
    db::run_migrations(&pool).await.expect("Oracle migrations must apply");
    Some(pool)
}

fn random_key() -> [u8; 32] {
    let mut k = [0u8; 32];
    k[..16].copy_from_slice(Uuid::new_v4().as_bytes());
    k[16..].copy_from_slice(Uuid::new_v4().as_bytes());
    k
}

fn did_for(key: &[u8]) -> String {
    format!("did:integrity:{}", hex::encode(Sha256::digest(key)))
}

fn handle() -> String {
    format!("h{}", &Uuid::new_v4().simple().to_string()[..8])
}

async fn handle_of(pool: &PgPool, id: &str) -> Option<String> {
    sqlx::query_scalar("SELECT handle FROM xns_handles WHERE agent_id = $1")
        .bind(id)
        .fetch_optional(pool)
        .await
        .unwrap()
}

#[tokio::test]
async fn fresh_did_is_created_at_tier_one() {
    let Some(pool) = pool().await else { return };
    let key = random_key();
    let did = did_for(&key);
    let (row, outcome) = db::register_agent_offchain(&pool, &did, &key, None, None)
        .await
        .expect("register");
    assert_eq!(outcome, RegistrationOutcome::Created);
    assert_eq!(row.verification_tier, 1);
    assert_eq!(row.ed25519_pubkey.as_deref(), Some(&key[..]));
    let stored = db::get_agent(&pool, &did).await.unwrap().expect("row exists");
    assert_eq!(stored.verification_tier, 1);
    assert_eq!(stored.ed25519_pubkey.as_deref(), Some(&key[..]));
}

#[tokio::test]
async fn same_key_is_idempotent() {
    let Some(pool) = pool().await else { return };
    let key = random_key();
    let did = did_for(&key);
    let (_, first) = db::register_agent_offchain(&pool, &did, &key, None, None).await.unwrap();
    let (_, second) = db::register_agent_offchain(&pool, &did, &key, None, None).await.unwrap();
    assert_eq!(first, RegistrationOutcome::Created);
    assert_eq!(second, RegistrationOutcome::AlreadyRegistered);
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM agents WHERE id = $1")
        .bind(&did)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(n, 1);
}

#[tokio::test]
async fn different_key_is_rejected_and_not_overwritten() {
    let Some(pool) = pool().await else { return };
    let key = random_key();
    let did = did_for(&key);
    db::register_agent_offchain(&pool, &did, &key, None, None).await.unwrap();
    let other = random_key();
    let err = db::register_agent_offchain(&pool, &did, &other, None, None)
        .await
        .expect_err("a different key must be rejected");
    assert!(matches!(err, RegistrationConflict::KeyMismatch), "got {err:?}");
    let stored = db::get_agent(&pool, &did).await.unwrap().unwrap();
    assert_eq!(stored.ed25519_pubkey.as_deref(), Some(&key[..]));
}

#[tokio::test]
async fn legacy_keyless_row_gets_key_and_tier_one() {
    let Some(pool) = pool().await else { return };
    let key = random_key();
    let did = did_for(&key);
    let eth = format!("0x{}", hex::encode(&random_key()[..20]));
    db::register_agent(&pool, &did, None, Some(eth.clone()), 0, None)
        .await
        .expect("legacy insert");
    let before = db::get_agent(&pool, &did).await.unwrap().unwrap();
    assert!(before.ed25519_pubkey.is_none());
    assert_eq!(before.verification_tier, 0);

    let (row, outcome) = db::register_agent_offchain(&pool, &did, &key, None, None).await.unwrap();
    assert_eq!(outcome, RegistrationOutcome::KeyAttached);
    assert_eq!(row.verification_tier, 1);
    assert_eq!(row.ed25519_pubkey.as_deref(), Some(&key[..]));
    assert_eq!(row.eth_address.as_deref(), Some(eth.as_str()));
    let stored = db::get_agent(&pool, &did).await.unwrap().unwrap();
    assert_eq!(stored.verification_tier, 1);
    assert_eq!(stored.eth_address.as_deref(), Some(eth.as_str()));
}

#[tokio::test]
async fn higher_tier_is_never_lowered() {
    let Some(pool) = pool().await else { return };
    let key = random_key();
    let did = did_for(&key);
    db::register_agent_offchain(&pool, &did, &key, None, None).await.unwrap();
    sqlx::query("UPDATE agents SET verification_tier = 2 WHERE id = $1")
        .bind(&did)
        .execute(&pool)
        .await
        .unwrap();
    let (row, outcome) = db::register_agent_offchain(&pool, &did, &key, None, None).await.unwrap();
    assert_eq!(outcome, RegistrationOutcome::AlreadyRegistered);
    assert_eq!(row.verification_tier, 2);
    assert_eq!(db::get_agent(&pool, &did).await.unwrap().unwrap().verification_tier, 2);
}

#[tokio::test]
async fn handle_mismatch_rolls_back_key_attach() {
    let Some(pool) = pool().await else { return };
    let key = random_key();
    let did = did_for(&key);
    let (a, b) = (handle(), handle());
    // The `agents_has_a_verification_method` check needs a key or an eth address.
    let eth = format!("0x{}", hex::encode(&random_key()[..20]));
    db::register_agent(&pool, &did, None, Some(eth), 0, None).await.unwrap();
    sqlx::query("INSERT INTO xns_handles (agent_id, handle) VALUES ($1, $2)")
        .bind(&did)
        .bind(&a)
        .execute(&pool)
        .await
        .unwrap();

    let err = db::register_agent_offchain(&pool, &did, &key, None, Some(&b))
        .await
        .expect_err("a different handle must be rejected");
    assert!(matches!(err, RegistrationConflict::HandleMismatch), "got {err:?}");

    let stored = db::get_agent(&pool, &did).await.unwrap().unwrap();
    assert!(stored.ed25519_pubkey.is_none(), "key attach must roll back");
    assert_eq!(stored.verification_tier, 0);
    assert_eq!(handle_of(&pool, &did).await.as_deref(), Some(a.as_str()));
}

#[tokio::test]
async fn concurrent_registration_of_one_did_creates_one_row() {
    let Some(pool) = pool().await else { return };
    let key = random_key();
    let did = did_for(&key);
    let calls = (0..8).map(|_| db::register_agent_offchain(&pool, &did, &key, None, None));
    let results = futures::future::join_all(calls).await;
    let mut created = 0;
    let mut already = 0;
    for r in results {
        match r.expect("no call may error") {
            (_, RegistrationOutcome::Created) => created += 1,
            (_, RegistrationOutcome::AlreadyRegistered) => already += 1,
            (_, other) => panic!("unexpected outcome {other:?}"),
        }
    }
    assert_eq!((created, already), (1, 7));
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM agents WHERE id = $1")
        .bind(&did)
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(n, 1);
}
