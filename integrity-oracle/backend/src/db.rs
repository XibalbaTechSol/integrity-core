//! Postgres persistence via sqlx. Deliberately uses runtime-checked
//! `query`/`query_as` calls rather than the `query!`/`query_as!` compile-time
//! macros: the macros require a live, migrated database reachable at
//! `cargo build` time (or a checked-in `.sqlx` offline query cache), which would
//! make this crate's build depend on Postgres being up. Given this package is
//! being built and iterated on in parallel with the rest of the monorepo (no
//! guarantee Postgres is always running), runtime checking is the pragmatic
//! choice — correctness is instead covered by the integration tests in
//! `tests/`, which run the real migrations against a real Postgres.

use chrono::{DateTime, Utc};
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use uuid::Uuid;

pub async fn create_pool(database_url: &str) -> Result<PgPool, sqlx::Error> {
    PgPoolOptions::new()
        .max_connections(10)
        .connect(database_url)
        .await
}

pub async fn run_migrations(pool: &PgPool) -> Result<(), sqlx::migrate::MigrateError> {
    sqlx::migrate!("./migrations").run(pool).await
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct AgentRow {
    pub id: String,
    pub ed25519_pubkey: Option<Vec<u8>>,
    pub eth_address: Option<String>,
    pub verification_tier: i32,
    pub last_nonce: i64,
    pub created_at: DateTime<Utc>,
    pub did_document: Option<serde_json::Value>,
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct TelemetryEventRow {
    pub id: Uuid,
    pub agent_id: String,
    pub nonce: i64,
    pub leaf_hash: Vec<u8>,
    pub merkle_root_id: Option<Uuid>,
    pub leaf_index: Option<i32>,
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct MerkleRootRow {
    pub id: Uuid,
    pub root_hash: Vec<u8>,
    pub leaf_count: i32,
    pub tx_hash: Option<String>,
    pub created_at: DateTime<Utc>,
}

/// Aggregate telemetry inputs to the AIS formula, computed over the reporting
/// window. A `None` return from `aggregate_for_ais` (rather than zeros) means
/// "no telemetry at all in the window" — callers should treat that as a
/// distinct case (e.g. an agent that just registered) rather than a real
/// worst-case score.
#[derive(Debug, Clone, Copy)]
pub struct AisAggregate {
    pub avg_variance: f64,
    pub avg_hgi: f64,
    pub sum_gpu_hours: f64,
    pub penalty_ratio: f64,
    pub zk_verified_this_period: bool,
    pub event_count: i64,
}

#[derive(Debug, thiserror::Error)]
pub enum RegisterAgentError {
    #[error("agent already registered")]
    AlreadyExists,
    #[error(transparent)]
    Db(#[from] sqlx::Error),
}

pub async fn register_agent(
    pool: &PgPool,
    id: &str,
    ed25519_pubkey: Option<Vec<u8>>,
    eth_address: Option<String>,
    verification_tier: i32,
    did_document: Option<serde_json::Value>,
) -> Result<AgentRow, RegisterAgentError> {
    let result = sqlx::query_as::<_, AgentRow>(
        r#"
        INSERT INTO agents (id, ed25519_pubkey, eth_address, verification_tier, did_document)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, ed25519_pubkey, eth_address, verification_tier, last_nonce, created_at, did_document
        "#,
    )
    .bind(id)
    .bind(ed25519_pubkey)
    .bind(eth_address)
    .bind(verification_tier)
    .bind(did_document)
    .fetch_one(pool)
    .await;

    match result {
        Ok(row) => Ok(row),
        // Postgres unique_violation
        Err(sqlx::Error::Database(db_err)) if db_err.code().as_deref() == Some("23505") => {
            Err(RegisterAgentError::AlreadyExists)
        }
        Err(e) => Err(RegisterAgentError::Db(e)),
    }
}

pub async fn get_agent(pool: &PgPool, id: &str) -> Result<Option<AgentRow>, sqlx::Error> {
    sqlx::query_as::<_, AgentRow>(
        r#"
        SELECT id, ed25519_pubkey, eth_address, verification_tier, last_nonce, created_at, did_document
        FROM agents WHERE id = $1
        "#,
    )
    .bind(id)
    .fetch_optional(pool)
    .await
}

/// Reverse a SovereignAgent address to its owning agent DID via the cached primitive set.
/// Case-insensitive on the hex address. Best-effort: returns None when the agent's primitives
/// have never been resolved into the oracle DB.
pub async fn did_by_sovereign_agent(
    pool: &PgPool,
    sovereign_agent: &str,
) -> Result<Option<String>, sqlx::Error> {
    let row: Option<(String,)> = sqlx::query_as(
        r#"
        SELECT agent_id FROM agent_primitives
        WHERE lower(sovereign_agent_address) = lower($1)
        LIMIT 1
        "#,
    )
    .bind(sovereign_agent)
    .fetch_optional(pool)
    .await?;
    Ok(row.map(|(id,)| id))
}

/// One row of the agent list, carrying the cached `SovereignAgent` address alongside the
/// `agents` columns. The join is a `LEFT` one on purpose: an agent registered in this DB
/// whose `agent_primitives` row hasn't been resolved yet (or that predates primitive
/// caching) must still appear in the list with `sovereign_agent_address: None`, not vanish
/// from the fleet. Callers that only need the DID (e.g. the leaderboard refresh) read `id`
/// and ignore the rest.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct AgentListRow {
    pub id: String,
    pub verification_tier: i32,
    pub created_at: DateTime<Utc>,
    pub did_document: Option<serde_json::Value>,
    pub sovereign_agent_address: Option<String>,
}

pub async fn list_agents(pool: &PgPool) -> Result<Vec<AgentListRow>, sqlx::Error> {
    sqlx::query_as::<_, AgentListRow>(
        r#"
        SELECT a.id, a.verification_tier, a.created_at, a.did_document,
               p.sovereign_agent_address
        FROM agents a
        LEFT JOIN agent_primitives p ON p.agent_id = a.id
        ORDER BY a.created_at DESC
        "#,
    )
    .fetch_all(pool)
    .await
}

/// Cached on-chain `PrimitiveSet` (§6.1) for one agent, as last resolved from
/// `XibalbaAgentRegistry`. Deliberately a separate table/row type from `AgentRow` (see
/// migrations/0001_init.sql's header note) rather than extending it, since `register_agent`
/// predates this task's primitive-resolution work and its signature/return shape is
/// reused as-is.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct AgentPrimitivesRow {
    pub agent_id: String,
    pub sovereign_agent_address: String,
    pub state_anchor_address: String,
    pub reputation_registry_address: String,
    pub slasher_address: String,
    pub verifier_registry_address: String,
    pub compliance_gate_address: String,
    pub agent_profile_address: String,
    pub controller_address: String,
    pub domain_id: String,
    pub resolved_at: DateTime<Utc>,
}

/// Upserts the cached primitive resolution for an agent. Called after a fresh, successful
/// on-chain `resolve_primitives` read (at registration, or on a cache-miss backfill) — this
/// table is always safe to overwrite/rebuild from chain, since `XibalbaAgentRegistry`
/// remains the source of truth and this row is just a read-through cache of it.
#[allow(clippy::too_many_arguments)]
pub async fn upsert_agent_primitives(
    pool: &PgPool,
    agent_id: &str,
    sovereign_agent_address: &str,
    state_anchor_address: &str,
    reputation_registry_address: &str,
    slasher_address: &str,
    verifier_registry_address: &str,
    compliance_gate_address: &str,
    agent_profile_address: &str,
    controller_address: &str,
    domain_id: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO agent_primitives
            (agent_id, sovereign_agent_address, state_anchor_address, reputation_registry_address,
             slasher_address, verifier_registry_address, compliance_gate_address, agent_profile_address,
             controller_address, domain_id, resolved_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
        ON CONFLICT (agent_id) DO UPDATE SET
            sovereign_agent_address = EXCLUDED.sovereign_agent_address,
            state_anchor_address = EXCLUDED.state_anchor_address,
            reputation_registry_address = EXCLUDED.reputation_registry_address,
            slasher_address = EXCLUDED.slasher_address,
            verifier_registry_address = EXCLUDED.verifier_registry_address,
            compliance_gate_address = EXCLUDED.compliance_gate_address,
            agent_profile_address = EXCLUDED.agent_profile_address,
            controller_address = EXCLUDED.controller_address,
            domain_id = EXCLUDED.domain_id,
            resolved_at = now()
        "#,
    )
    .bind(agent_id)
    .bind(sovereign_agent_address)
    .bind(state_anchor_address)
    .bind(reputation_registry_address)
    .bind(slasher_address)
    .bind(verifier_registry_address)
    .bind(compliance_gate_address)
    .bind(agent_profile_address)
    .bind(controller_address)
    .bind(domain_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn get_agent_primitives(pool: &PgPool, agent_id: &str) -> Result<Option<AgentPrimitivesRow>, sqlx::Error> {
    sqlx::query_as::<_, AgentPrimitivesRow>(
        r#"
        SELECT agent_id, sovereign_agent_address, state_anchor_address, reputation_registry_address,
               slasher_address, verifier_registry_address, compliance_gate_address, agent_profile_address,
               controller_address, domain_id, resolved_at
        FROM agent_primitives WHERE agent_id = $1
        "#,
    )
    .bind(agent_id)
    .fetch_optional(pool)
    .await
}

#[derive(Debug, thiserror::Error)]
pub enum InsertTelemetryError {
    #[error("nonce {submitted} is not greater than last seen nonce {last_seen}")]
    NonceReplay { submitted: i64, last_seen: i64 },
    #[error(transparent)]
    Db(#[from] sqlx::Error),
}

/// Inserts a telemetry event and advances the agent's `last_nonce`, atomically.
/// The nonce check happens inside the same transaction as a `SELECT ... FOR
/// UPDATE` row lock on the agent, so two concurrent submissions for the same
/// agent can't both pass the nonce check against a stale `last_nonce` — without
/// this, replay protection would have a TOCTOU race under concurrent requests.
#[allow(clippy::too_many_arguments)]
pub async fn insert_telemetry_event(
    pool: &PgPool,
    event_id: Uuid,
    agent_id: &str,
    nonce: i64,
    performance_variance: f64,
    hgi_raw: f64,
    gpu_hours_verified: f64,
    flagged: bool,
    zk_verified: bool,
    leaf_hash: &[u8],
    payload: &serde_json::Value,
) -> Result<(), InsertTelemetryError> {
    let mut tx = pool.begin().await?;

    let last_nonce: i64 = sqlx::query_scalar("SELECT last_nonce FROM agents WHERE id = $1 FOR UPDATE")
        .bind(agent_id)
        .fetch_one(&mut *tx)
        .await?;

    if nonce <= last_nonce {
        return Err(InsertTelemetryError::NonceReplay {
            submitted: nonce,
            last_seen: last_nonce,
        });
    }

    sqlx::query(
        r#"
        INSERT INTO telemetry_events
            (id, agent_id, nonce, performance_variance, hgi_raw, gpu_hours_verified, flagged, zk_verified, leaf_hash, payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        "#,
    )
    .bind(event_id)
    .bind(agent_id)
    .bind(nonce)
    .bind(performance_variance)
    .bind(hgi_raw)
    .bind(gpu_hours_verified)
    .bind(flagged)
    .bind(zk_verified)
    .bind(leaf_hash)
    .bind(payload)
    .execute(&mut *tx)
    .await?;

    sqlx::query("UPDATE agents SET last_nonce = $1 WHERE id = $2")
        .bind(nonce)
        .bind(agent_id)
        .execute(&mut *tx)
        .await?;

    tx.commit().await?;
    Ok(())
}

pub async fn aggregate_for_ais(
    pool: &PgPool,
    agent_id: &str,
    since: DateTime<Utc>,
) -> Result<AisAggregate, sqlx::Error> {
    let row: (f64, f64, f64, f64, bool, i64) = sqlx::query_as(
        r#"
        SELECT
            -- Each aggregate is explicitly cast to `double precision`: the `1.0`/`0.0`
            -- literals in the CASE expression are Postgres `numeric`, so
            -- `AVG(CASE ...)` returns `numeric`, which sqlx will NOT decode into a Rust
            -- `f64` (it errors with "SQL type NUMERIC is not compatible"). Casting keeps
            -- every returned column FLOAT8 so the `(f64, f64, f64, f64, bool, i64)` row
            -- tuple below decodes cleanly regardless of each source column's type.
            COALESCE(AVG(performance_variance), 0.0)::double precision AS avg_variance,
            COALESCE(AVG(hgi_raw), 0.0)::double precision AS avg_hgi,
            COALESCE(SUM(gpu_hours_verified), 0.0)::double precision AS sum_gpu_hours,
            COALESCE(AVG(CASE WHEN flagged THEN 1.0 ELSE 0.0 END), 0.0)::double precision AS penalty_ratio,
            COALESCE(BOOL_OR(zk_verified), false) AS zk_verified_this_period,
            COUNT(*) AS event_count
        FROM telemetry_events
        WHERE agent_id = $1 AND created_at >= $2
        "#,
    )
    .bind(agent_id)
    .bind(since)
    .fetch_one(pool)
    .await?;

    Ok(AisAggregate {
        avg_variance: row.0,
        avg_hgi: row.1,
        sum_gpu_hours: row.2,
        penalty_ratio: row.3,
        zk_verified_this_period: row.4,
        event_count: row.5,
    })
}

/// Provider/model stability benchmarks: aggregate telemetry across ALL agents grouped by the
/// `model` recorded in each event's payload. Backs `GET /v1/benchmarks` — a real network-wide
/// view of how each underlying model performs (behavioral variance + grounding), independent of
/// which agent used it. Returns (model, avg_variance, avg_grounding, sample_count).
pub async fn benchmark_by_model(pool: &PgPool) -> Result<Vec<(String, f64, f64, i64)>, sqlx::Error> {
    sqlx::query_as(
        r#"
        SELECT
            payload->>'model' AS model,
            COALESCE(AVG(performance_variance), 0.0)::double precision AS avg_variance,
            COALESCE(AVG(hgi_raw), 0.0)::double precision AS avg_grounding,
            COUNT(*) AS sample_count
        FROM telemetry_events
        WHERE payload->>'model' IS NOT NULL
        GROUP BY payload->>'model'
        HAVING COUNT(*) >= 3
        ORDER BY AVG(hgi_raw) DESC
        "#,
    )
    .fetch_all(pool)
    .await
}

/// Telemetry events not yet folded into any anchored Merkle root, oldest first.
/// Ordering matters: it fixes the leaf order the tree gets built with, which
/// must be reproducible later (from `leaf_index`) to regenerate inclusion proofs.
///
/// **Currently dead code (PRODUCTION_GAPS.md §2).** Neither this function nor
/// [`create_merkle_root_and_assign`] has any caller anywhere in this crate — no route,
/// handler, or background task ever builds an oracle-side global Merkle tree from
/// pending `telemetry_events`. Real Merkle anchoring happens entirely through
/// `bcc_middleware/app/anchor.py`'s independent, per-agent batching (one sub-root per
/// agent, anchored to that agent's own `StateAnchor` clone) — a different, incompatible
/// design from this pair's single-global-root-across-all-agents model. This code, its
/// unit tests, and the `merkle_root_id`/`leaf_index` columns it would populate
/// (exposed, currently always `null`, via `GET /v1/agent/{id}/telemetry`'s
/// `TelemetryEventDetailDto`) are left in place — real, working, and tested in
/// isolation — as the oracle-side alternative if a future design ever needs the oracle
/// itself (rather than bcc_middleware) to anchor a cross-agent root, rather than
/// deleted outright, since deleting would also mean dropping the exposed API fields.
pub async fn fetch_pending_leaves(pool: &PgPool) -> Result<Vec<(Uuid, [u8; 32])>, sqlx::Error> {
    let rows: Vec<(Uuid, Vec<u8>)> = sqlx::query_as(
        r#"
        SELECT id, leaf_hash FROM telemetry_events
        WHERE merkle_root_id IS NULL
        ORDER BY created_at ASC, id ASC
        "#,
    )
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|(id, hash)| (id, hash.try_into().expect("leaf_hash column is always 32 bytes")))
        .collect())
}

/// Creates a `merkle_roots` row and assigns `leaf_index`/`merkle_root_id` to each
/// event in `ordered_event_ids`, whose order MUST match the order the tree was
/// built with (see `fetch_pending_leaves`). Runs in one transaction so a crash
/// mid-assignment can't leave some events anchored to a root and others not.
pub async fn create_merkle_root_and_assign(
    pool: &PgPool,
    root_id: Uuid,
    root_hash: [u8; 32],
    ordered_event_ids: &[Uuid],
) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;

    sqlx::query("INSERT INTO merkle_roots (id, root_hash, leaf_count) VALUES ($1, $2, $3)")
        .bind(root_id)
        .bind(root_hash.as_slice())
        .bind(ordered_event_ids.len() as i32)
        .execute(&mut *tx)
        .await?;

    for (index, event_id) in ordered_event_ids.iter().enumerate() {
        sqlx::query("UPDATE telemetry_events SET merkle_root_id = $1, leaf_index = $2 WHERE id = $3")
            .bind(root_id)
            .bind(index as i32)
            .bind(event_id)
            .execute(&mut *tx)
            .await?;
    }

    tx.commit().await?;
    Ok(())
}

pub async fn fetch_event(pool: &PgPool, event_id: Uuid) -> Result<Option<TelemetryEventRow>, sqlx::Error> {
    sqlx::query_as::<_, TelemetryEventRow>(
        "SELECT id, agent_id, nonce, leaf_hash, merkle_root_id, leaf_index FROM telemetry_events WHERE id = $1",
    )
    .bind(event_id)
    .fetch_optional(pool)
    .await
}

pub async fn fetch_root(pool: &PgPool, root_id: Uuid) -> Result<Option<MerkleRootRow>, sqlx::Error> {
    sqlx::query_as::<_, MerkleRootRow>(
        "SELECT id, root_hash, leaf_count, tx_hash, created_at FROM merkle_roots WHERE id = $1",
    )
    .bind(root_id)
    .fetch_optional(pool)
    .await
}

// ---------------------------------------------------------------------------------
// Markets cache (§6.9) — GET /v1/markets, GET /v1/markets/{id}
// ---------------------------------------------------------------------------------

/// Cached `IntegrityMarket` view state, as last read live by `chain::ChainClient::read_market`.
/// Token amounts are TEXT (exact decimal strings of a `uint256`) — see
/// `migrations/0002_markets_and_judge.sql`'s header note on why.
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct MarketCacheRow {
    pub address: String,
    pub creator_address: String,
    pub question: String,
    pub outcome_count: i16,
    pub min_ais_to_enter: String,
    pub resolve_deadline: i64,
    pub resolved: bool,
    pub winning_outcome: i16,
    pub total_staked: String,
    pub outcome_staked: serde_json::Value,
    pub refreshed_at: DateTime<Utc>,
}

#[allow(clippy::too_many_arguments)]
pub async fn upsert_market_cache(
    pool: &PgPool,
    address: &str,
    creator_address: &str,
    question: &str,
    outcome_count: i16,
    min_ais_to_enter: &str,
    resolve_deadline: i64,
    resolved: bool,
    winning_outcome: i16,
    total_staked: &str,
    outcome_staked: &serde_json::Value,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO markets_cache
            (address, creator_address, question, outcome_count, min_ais_to_enter, resolve_deadline,
             resolved, winning_outcome, total_staked, outcome_staked, refreshed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
        ON CONFLICT (address) DO UPDATE SET
            creator_address = EXCLUDED.creator_address,
            question = EXCLUDED.question,
            outcome_count = EXCLUDED.outcome_count,
            min_ais_to_enter = EXCLUDED.min_ais_to_enter,
            resolve_deadline = EXCLUDED.resolve_deadline,
            resolved = EXCLUDED.resolved,
            winning_outcome = EXCLUDED.winning_outcome,
            total_staked = EXCLUDED.total_staked,
            outcome_staked = EXCLUDED.outcome_staked,
            refreshed_at = now()
        "#,
    )
    .bind(address)
    .bind(creator_address)
    .bind(question)
    .bind(outcome_count)
    .bind(min_ais_to_enter)
    .bind(resolve_deadline)
    .bind(resolved)
    .bind(winning_outcome)
    .bind(total_staked)
    .bind(outcome_staked)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn get_market_cache(pool: &PgPool, address: &str) -> Result<Option<MarketCacheRow>, sqlx::Error> {
    sqlx::query_as::<_, MarketCacheRow>(
        r#"
        SELECT address, creator_address, question, outcome_count, min_ais_to_enter, resolve_deadline,
               resolved, winning_outcome, total_staked, outcome_staked, refreshed_at
        FROM markets_cache WHERE address = $1
        "#,
    )
    .bind(address)
    .fetch_optional(pool)
    .await
}

pub async fn list_market_cache(pool: &PgPool) -> Result<Vec<MarketCacheRow>, sqlx::Error> {
    sqlx::query_as::<_, MarketCacheRow>(
        r#"
        SELECT address, creator_address, question, outcome_count, min_ais_to_enter, resolve_deadline,
               resolved, winning_outcome, total_staked, outcome_staked, refreshed_at
        FROM markets_cache ORDER BY resolve_deadline ASC
        "#,
    )
    .fetch_all(pool)
    .await
}

/// Single-row marker of when the full market membership was last re-enumerated from
/// `MarketFactory` (see `migrations/0002_markets_and_judge.sql`'s header note).
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct MarketsIndexSyncRow {
    pub market_count: i32,
    pub synced_at: DateTime<Utc>,
}

pub async fn get_markets_index_sync(pool: &PgPool) -> Result<Option<MarketsIndexSyncRow>, sqlx::Error> {
    sqlx::query_as::<_, MarketsIndexSyncRow>("SELECT market_count, synced_at FROM markets_index_sync WHERE id = TRUE")
        .fetch_optional(pool)
        .await
}

pub async fn upsert_markets_index_sync(pool: &PgPool, market_count: i32, synced_at: DateTime<Utc>) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO markets_index_sync (id, market_count, synced_at) VALUES (TRUE, $1, $2)
        ON CONFLICT (id) DO UPDATE SET market_count = EXCLUDED.market_count, synced_at = EXCLUDED.synced_at
        "#,
    )
    .bind(market_count)
    .bind(synced_at)
    .execute(pool)
    .await?;
    Ok(())
}

// ---------------------------------------------------------------------------------
// Leaderboard cache (GET /v1/leaderboard) — mirrors markets_cache/markets_index_sync
// ---------------------------------------------------------------------------------

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct LeaderboardCacheRow {
    pub agent_id: String,
    pub sovereign_agent_address: String,
    pub effective_score: String,
    pub refreshed_at: DateTime<Utc>,
}

pub async fn upsert_leaderboard_cache(
    pool: &PgPool,
    agent_id: &str,
    sovereign_agent_address: &str,
    effective_score: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO leaderboard_cache (agent_id, sovereign_agent_address, effective_score, refreshed_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (agent_id) DO UPDATE SET
            sovereign_agent_address = EXCLUDED.sovereign_agent_address,
            effective_score = EXCLUDED.effective_score,
            refreshed_at = now()
        "#,
    )
    .bind(agent_id)
    .bind(sovereign_agent_address)
    .bind(effective_score)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn list_leaderboard_cache(pool: &PgPool) -> Result<Vec<LeaderboardCacheRow>, sqlx::Error> {
    sqlx::query_as::<_, LeaderboardCacheRow>(
        "SELECT agent_id, sovereign_agent_address, effective_score, refreshed_at FROM leaderboard_cache",
    )
    .fetch_all(pool)
    .await
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct LeaderboardSyncRow {
    pub agent_count: i32,
    pub synced_at: DateTime<Utc>,
}

pub async fn get_leaderboard_sync(pool: &PgPool) -> Result<Option<LeaderboardSyncRow>, sqlx::Error> {
    sqlx::query_as::<_, LeaderboardSyncRow>("SELECT agent_count, synced_at FROM leaderboard_sync WHERE id = TRUE")
        .fetch_optional(pool)
        .await
}

pub async fn upsert_leaderboard_sync(pool: &PgPool, agent_count: i32, synced_at: DateTime<Utc>) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO leaderboard_sync (id, agent_count, synced_at) VALUES (TRUE, $1, $2)
        ON CONFLICT (id) DO UPDATE SET agent_count = EXCLUDED.agent_count, synced_at = EXCLUDED.synced_at
        "#,
    )
    .bind(agent_count)
    .bind(synced_at)
    .execute(pool)
    .await?;
    Ok(())
}

// ---------------------------------------------------------------------------------
// Judge evaluations (storage + ingestion plumbing only — task write-up item 6)
// ---------------------------------------------------------------------------------

#[allow(clippy::too_many_arguments)]
pub async fn insert_judge_evaluation(
    pool: &PgPool,
    id: Uuid,
    agent_id: &str,
    run_id: &str,
    judge_model: &str,
    verdict: &str,
    score: Option<f64>,
    rationale_summary: Option<&str>,
    telemetry_event_id: Option<Uuid>,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO judge_evaluations
            (id, agent_id, run_id, judge_model, verdict, score, rationale_summary, telemetry_event_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        "#,
    )
    .bind(id)
    .bind(agent_id)
    .bind(run_id)
    .bind(judge_model)
    .bind(verdict)
    .bind(score)
    .bind(rationale_summary)
    .bind(telemetry_event_id)
    .execute(pool)
    .await?;
    Ok(())
}

/// Leaves belonging to an already-anchored root, in the exact order the tree was
/// originally built with (by `leaf_index`) — required to rebuild the same tree
/// shape and regenerate a matching inclusion proof.
pub async fn fetch_leaves_for_root(pool: &PgPool, root_id: Uuid) -> Result<Vec<(i32, [u8; 32])>, sqlx::Error> {
    let rows: Vec<(i32, Vec<u8>)> = sqlx::query_as(
        r#"
        SELECT leaf_index, leaf_hash FROM telemetry_events
        WHERE merkle_root_id = $1
        ORDER BY leaf_index ASC
        "#,
    )
    .bind(root_id)
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|(idx, hash)| (idx, hash.try_into().expect("leaf_hash column is always 32 bytes")))
        .collect())
}

#[derive(Debug, Clone, sqlx::FromRow, serde::Serialize, serde::Deserialize)]
pub struct TelemetryEventDetail {
    pub id: Uuid,
    pub agent_id: String,
    pub nonce: i64,
    pub performance_variance: f64,
    pub hgi_raw: f64,
    pub gpu_hours_verified: f64,
    pub flagged: bool,
    pub zk_verified: bool,
    pub leaf_hash: Vec<u8>,
    pub payload: serde_json::Value,
    pub merkle_root_id: Option<Uuid>,
    pub leaf_index: Option<i32>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, sqlx::FromRow, serde::Serialize, serde::Deserialize)]
pub struct JudgeEvaluationRow {
    pub id: Uuid,
    pub agent_id: String,
    pub run_id: String,
    pub judge_model: String,
    pub verdict: String,
    pub score: Option<f64>,
    pub rationale_summary: Option<String>,
    pub telemetry_event_id: Option<Uuid>,
    pub created_at: DateTime<Utc>,
}

pub async fn get_recent_telemetry(
    pool: &PgPool,
    agent_id: &str,
    limit: i64,
) -> Result<Vec<TelemetryEventDetail>, sqlx::Error> {
    sqlx::query_as::<_, TelemetryEventDetail>(
        r#"
        SELECT id, agent_id, nonce, performance_variance, hgi_raw, gpu_hours_verified,
               flagged, zk_verified, leaf_hash, payload, merkle_root_id, leaf_index, created_at
        FROM telemetry_events
        WHERE agent_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        "#,
    )
    .bind(agent_id)
    .bind(limit)
    .fetch_all(pool)
    .await
}

pub async fn get_recent_evaluations(
    pool: &PgPool,
    agent_id: &str,
    limit: i64,
) -> Result<Vec<JudgeEvaluationRow>, sqlx::Error> {
    sqlx::query_as::<_, JudgeEvaluationRow>(
        r#"
        SELECT id, agent_id, run_id, judge_model, verdict, score, rationale_summary, telemetry_event_id, created_at
        FROM judge_evaluations
        WHERE agent_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        "#,
    )
    .bind(agent_id)
    .bind(limit)
    .fetch_all(pool)
    .await
}

// ---------------------------------------------------------------------------------
// audit_log (real durable BCC-middleware ALLOW/DENY decision trail, see migration
// 0006's header comment for why this table exists — no other component had durable
// storage for the protocol's most audit-worthy event type before this).
// ---------------------------------------------------------------------------------

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct AuditLogRow {
    pub id: Uuid,
    pub agent_id: Option<String>,
    pub source: String,
    pub event_type: String,
    pub decision: String,
    pub reason_code: Option<String>,
    pub detail: Option<String>,
    pub created_at: DateTime<Utc>,
    // Evidence-export linkage (migration 0007): LEFT JOINed from `anchor_events`
    // on `metadata->>'leaf'`. Populated only for ALLOW rows whose Merkle leaf has
    // been anchored on-chain; None otherwise.
    pub anchor_root: Option<String>,
    pub anchor_tx_hash: Option<String>,
    pub anchored_at: Option<DateTime<Utc>>,
}

#[allow(clippy::too_many_arguments)]
pub async fn insert_audit_log(
    pool: &PgPool,
    agent_id: Option<&str>,
    source: &str,
    event_type: &str,
    decision: &str,
    reason_code: Option<&str>,
    detail: Option<&str>,
    intent_type: Option<&str>,
    metadata: &serde_json::Value,
) -> Result<Uuid, sqlx::Error> {
    let id = Uuid::new_v4();
    sqlx::query(
        r#"
        INSERT INTO audit_log (id, agent_id, source, event_type, decision, reason_code, detail, intent_type, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        "#,
    )
    .bind(id)
    .bind(agent_id)
    .bind(source)
    .bind(event_type)
    .bind(decision)
    .bind(reason_code)
    .bind(detail)
    .bind(intent_type)
    .bind(metadata)
    .execute(pool)
    .await?;
    Ok(id)
}

pub async fn get_recent_audit_log(
    pool: &PgPool,
    agent_id: Option<&str>,
    limit: i64,
) -> Result<Vec<AuditLogRow>, sqlx::Error> {
    // LEFT JOIN anchor_events on the ALLOW row's Merkle leaf (audit_log.metadata
    // ->>'leaf', written at decision time) so an anchored decision carries its
    // on-chain StateAnchor root + tx. LEFT (not INNER) so un-anchored and non-BCC
    // rows still appear with null anchor fields. anchor_events.leaf is UNIQUE, so
    // the join never fans a row out.
    match agent_id {
        Some(aid) => {
            sqlx::query_as::<_, AuditLogRow>(
                r#"
                SELECT a.id, a.agent_id, a.source, a.event_type, a.decision, a.reason_code, a.detail, a.created_at,
                       ae.root AS anchor_root, ae.tx_hash AS anchor_tx_hash, ae.anchored_at
                FROM audit_log a
                LEFT JOIN anchor_events ae ON ae.leaf = a.metadata->>'leaf'
                WHERE a.agent_id = $1
                ORDER BY a.created_at DESC
                LIMIT $2
                "#,
            )
            .bind(aid)
            .bind(limit)
            .fetch_all(pool)
            .await
        }
        None => {
            sqlx::query_as::<_, AuditLogRow>(
                r#"
                SELECT a.id, a.agent_id, a.source, a.event_type, a.decision, a.reason_code, a.detail, a.created_at,
                       ae.root AS anchor_root, ae.tx_hash AS anchor_tx_hash, ae.anchored_at
                FROM audit_log a
                LEFT JOIN anchor_events ae ON ae.leaf = a.metadata->>'leaf'
                ORDER BY a.created_at DESC
                LIMIT $1
                "#,
            )
            .bind(limit)
            .fetch_all(pool)
            .await
        }
    }
}

/// Records the anchor events for one agent's just-anchored Merkle sub-tree:
/// every `leaf` committed in the on-chain `tx_hash` under `root`. Idempotent —
/// a leaf already recorded (a retried anchor report) is skipped via the UNIQUE
/// (leaf) constraint rather than duplicated. Returns the number of new rows.
/// See migration 0007 for why this is a separate table joined at read time
/// rather than a back-fill onto audit_log.
pub async fn insert_anchor_events(
    pool: &PgPool,
    agent_id: &str,
    leaves: &[String],
    root: &str,
    tx_hash: &str,
) -> Result<u64, sqlx::Error> {
    let result = sqlx::query(
        r#"
        INSERT INTO anchor_events (agent_id, leaf, root, tx_hash)
        SELECT $1, leaf, $3, $4
        FROM unnest($2::text[]) AS leaf
        ON CONFLICT (leaf) DO NOTHING
        "#,
    )
    .bind(agent_id)
    .bind(leaves)
    .bind(root)
    .bind(tx_hash)
    .execute(pool)
    .await?;
    Ok(result.rows_affected())
}

// Provenance: an agent's real, on-chain-anchored history -- each Merkle leaf it
// committed, the StateAnchor root+tx that anchored it, and (via the same
// metadata->>'leaf' join the audit-log uses) the policy decision that produced
// it. Pure read over anchor_events + audit_log, no chain call. See
// docs/design/evidence-export.md / dashboard-wiring.md (Class B).
#[derive(Debug, Clone, sqlx::FromRow)]
pub struct ProvenanceRow {
    pub id: Uuid,
    pub agent_id: String,
    pub leaf: String,
    pub root: String,
    pub tx_hash: String,
    pub anchored_at: DateTime<Utc>,
    pub decision: Option<String>,
    pub reason_code: Option<String>,
    pub intent_type: Option<String>,
    pub created_at: Option<DateTime<Utc>>,
}

pub async fn get_agent_provenance(
    pool: &PgPool,
    agent_id: &str,
    limit: i64,
) -> Result<Vec<ProvenanceRow>, sqlx::Error> {
    sqlx::query_as::<_, ProvenanceRow>(
        r#"
        SELECT ae.id, ae.agent_id, ae.leaf, ae.root, ae.tx_hash, ae.anchored_at,
               a.decision, a.reason_code, a.intent_type, a.created_at
        FROM anchor_events ae
        LEFT JOIN audit_log a ON a.metadata->>'leaf' = ae.leaf
        WHERE ae.agent_id = $1
        ORDER BY ae.anchored_at DESC
        LIMIT $2
        "#,
    )
    .bind(agent_id)
    .bind(limit)
    .fetch_all(pool)
    .await
}

// ---------------------------------------------------------------------------------
// otel_spans (real OTLP receiver storage, see otlp.rs) + time-bucketed history
// (PRODUCTION_GAPS.md §1 items 2-3) — see migration 0004's header comment for why
// this table exists separately from telemetry_events and is never an AIS input.
// ---------------------------------------------------------------------------------

#[derive(Debug, Clone, sqlx::FromRow, serde::Serialize, serde::Deserialize)]
pub struct OtelSpanRow {
    pub id: Uuid,
    pub agent_id: String,
    pub trace_id: String,
    pub span_id: String,
    pub parent_span_id: Option<String>,
    pub name: String,
    pub kind: String,
    pub start_time: DateTime<Utc>,
    pub end_time: DateTime<Utc>,
    pub status_code: String,
    pub attributes: serde_json::Value,
    pub created_at: DateTime<Utc>,
}

#[allow(clippy::too_many_arguments)]
pub async fn insert_otel_span(
    pool: &PgPool,
    id: Uuid,
    agent_id: &str,
    trace_id: &str,
    span_id: &str,
    parent_span_id: Option<&str>,
    name: &str,
    kind: &str,
    start_time: DateTime<Utc>,
    end_time: DateTime<Utc>,
    status_code: &str,
    attributes: &serde_json::Value,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO otel_spans
            (id, agent_id, trace_id, span_id, parent_span_id, name, kind, start_time, end_time, status_code, attributes)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        "#,
    )
    .bind(id)
    .bind(agent_id)
    .bind(trace_id)
    .bind(span_id)
    .bind(parent_span_id)
    .bind(name)
    .bind(kind)
    .bind(start_time)
    .bind(end_time)
    .bind(status_code)
    .bind(attributes)
    .execute(pool)
    .await?;
    Ok(())
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct RecentTraceRow {
    pub trace_id: String,
    pub name: String,
    pub start_time: DateTime<Utc>,
}

/// One row per trace's root span (`parent_span_id IS NULL`), most recent
/// first -- backs `GET /v1/agent/{id}/otel/traces`, the "list recent traces"
/// endpoint that never existed until now (frontend previously could only
/// discover trace_ids by watching the live SSE stream while a tab was open,
/// so any trace generated before that tab was open was permanently
/// invisible to `GET /v1/traces/{trace_id}` despite being real, queryable
/// data). A trace with multiple genuine roots (see trace_tree.rs's handling
/// of that case) surfaces once per root here, which is an acceptable
/// simplification for a "recent traces" picker, not a correctness issue for
/// `get_trace_tree` itself (which still reconstructs every root).
pub async fn get_recent_root_spans(pool: &PgPool, agent_id: &str, limit: i64) -> Result<Vec<RecentTraceRow>, sqlx::Error> {
    sqlx::query_as::<_, RecentTraceRow>(
        r#"
        SELECT trace_id, name, start_time
        FROM otel_spans
        WHERE agent_id = $1 AND parent_span_id IS NULL
        ORDER BY start_time DESC
        LIMIT $2
        "#,
    )
    .bind(agent_id)
    .bind(limit)
    .fetch_all(pool)
    .await
}

/// Every real span for one agent, most recent first, flat (not grouped into
/// trace trees) -- backs the unified "everything logged" audit-log merge in
/// `get_audit_log` (see that handler's doc comment). Deliberately not
/// restricted to root spans like `get_recent_root_spans`: a manual-debugging
/// log view needs the child spans (`tool_call.*`, `llm_call.*`) too, not
/// just each trace's top-level name.
pub async fn get_recent_spans_flat(pool: &PgPool, agent_id: &str, limit: i64) -> Result<Vec<OtelSpanRow>, sqlx::Error> {
    sqlx::query_as::<_, OtelSpanRow>(
        r#"
        SELECT id, agent_id, trace_id, span_id, parent_span_id, name, kind, start_time, end_time, status_code, attributes, created_at
        FROM otel_spans
        WHERE agent_id = $1
        ORDER BY start_time DESC
        LIMIT $2
        "#,
    )
    .bind(agent_id)
    .bind(limit)
    .fetch_all(pool)
    .await
}

/// Every span belonging to one trace, in start-time order — the shape
/// `ChainOfThoughtPage`'s DAG view walks (parent_span_id links form the tree).
pub async fn get_otel_spans_for_trace(pool: &PgPool, trace_id: &str) -> Result<Vec<OtelSpanRow>, sqlx::Error> {
    sqlx::query_as::<_, OtelSpanRow>(
        r#"
        SELECT id, agent_id, trace_id, span_id, parent_span_id, name, kind, start_time, end_time, status_code, attributes, created_at
        FROM otel_spans
        WHERE trace_id = $1
        ORDER BY start_time ASC
        "#,
    )
    .bind(trace_id)
    .fetch_all(pool)
    .await
}

/// One time bucket's worth of the same raw aggregates `aggregate_for_ais` computes over
/// the whole reporting window — callers feed each bucket through the identical
/// `scoring_core::AisEngine::score` call `compute_ais_for_agent` uses, so a historical
/// point is never computed by a second, drifted formula path.
#[derive(Debug, Clone, Copy)]
pub struct AisBucketAggregate {
    pub bucket_start: DateTime<Utc>,
    pub avg_variance: f64,
    pub avg_hgi: f64,
    pub sum_gpu_hours: f64,
    pub penalty_ratio: f64,
    pub zk_verified_this_period: bool,
    pub event_count: i64,
}

/// `bucket_interval` must be a Postgres-interval-parseable literal (e.g. `"1 hour"`) —
/// callers should route it through `handlers::parse_bucket_interval` first, which
/// restricts input to a fixed allowlist before it ever reaches this bind parameter.
/// `time_bucket` is a TimescaleDB function, available once the extension is installed
/// (migration 0004) against ANY table, not only hypertables — `telemetry_events` is
/// deliberately not a hypertable itself (see that migration's notes), so this still
/// works against it unmodified.
pub async fn ais_history_buckets(
    pool: &PgPool,
    agent_id: &str,
    bucket_interval: &str,
    since: DateTime<Utc>,
) -> Result<Vec<AisBucketAggregate>, sqlx::Error> {
    let rows: Vec<(DateTime<Utc>, f64, f64, f64, f64, bool, i64)> = sqlx::query_as(
        r#"
        SELECT
            time_bucket($1::interval, created_at) AS bucket_start,
            COALESCE(AVG(performance_variance), 0.0)::double precision AS avg_variance,
            COALESCE(AVG(hgi_raw), 0.0)::double precision AS avg_hgi,
            COALESCE(SUM(gpu_hours_verified), 0.0)::double precision AS sum_gpu_hours,
            COALESCE(AVG(CASE WHEN flagged THEN 1.0 ELSE 0.0 END), 0.0)::double precision AS penalty_ratio,
            COALESCE(BOOL_OR(zk_verified), false) AS zk_verified_this_period,
            COUNT(*) AS event_count
        FROM telemetry_events
        WHERE agent_id = $2 AND created_at >= $3
        GROUP BY bucket_start
        ORDER BY bucket_start ASC
        "#,
    )
    .bind(bucket_interval)
    .bind(agent_id)
    .bind(since)
    .fetch_all(pool)
    .await?;

    Ok(rows
        .into_iter()
        .map(|(bucket_start, avg_variance, avg_hgi, sum_gpu_hours, penalty_ratio, zk_verified_this_period, event_count)| {
            AisBucketAggregate {
                bucket_start,
                avg_variance,
                avg_hgi,
                sum_gpu_hours,
                penalty_ratio,
                zk_verified_this_period,
                event_count,
            }
        })
        .collect())
}

/// Telemetry ingestion volume (`telemetry_events`) bucketed by time, for
/// `FinancePage`/`IntelligencePage` volume charts.
pub async fn telemetry_volume_buckets(
    pool: &PgPool,
    agent_id: &str,
    bucket_interval: &str,
    since: DateTime<Utc>,
) -> Result<Vec<(DateTime<Utc>, i64, i64)>, sqlx::Error> {
    sqlx::query_as(
        r#"
        SELECT
            time_bucket($1::interval, created_at) AS bucket_start,
            COUNT(*) AS count,
            COUNT(*) FILTER (WHERE flagged) AS flagged_count
        FROM telemetry_events
        WHERE agent_id = $2 AND created_at >= $3
        GROUP BY bucket_start
        ORDER BY bucket_start ASC
        "#,
    )
    .bind(bucket_interval)
    .bind(agent_id)
    .bind(since)
    .fetch_all(pool)
    .await
}

/// Real OTLP span volume (`otel_spans`) bucketed by time, for `SdkTelemetryPage`.
pub async fn otel_volume_buckets(
    pool: &PgPool,
    agent_id: &str,
    bucket_interval: &str,
    since: DateTime<Utc>,
) -> Result<Vec<(DateTime<Utc>, i64)>, sqlx::Error> {
    sqlx::query_as(
        r#"
        SELECT
            time_bucket($1::interval, created_at) AS bucket_start,
            COUNT(*) AS span_count
        FROM otel_spans
        WHERE agent_id = $2 AND created_at >= $3
        GROUP BY bucket_start
        ORDER BY bucket_start ASC
        "#,
    )
    .bind(bucket_interval)
    .bind(agent_id)
    .bind(since)
    .fetch_all(pool)
    .await
}

