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
use serde::Serialize;
use sqlx::postgres::PgPoolOptions;
use sqlx::PgPool;
use utoipa::ToSchema;
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
        -- EFFECTIVE tier, computed in one pass rather than N+1 round trips.
        -- `a.verification_tier` is only the registration floor; rungs 2/3 live in
        -- `identity_verifications`, and expiry/revocation are applied here so a
        -- lapsed proof lowers the reported tier automatically. Returning the raw
        -- column made the fleet list show every climbed agent at tier 1.
        SELECT a.id,
               GREATEST(
                   a.verification_tier,
                   COALESCE((
                       SELECT MAX(v.tier_granted)
                       FROM identity_verifications v
                       WHERE v.agent_id = a.id
                         AND v.revoked_at IS NULL
                         AND (v.expires_at IS NULL OR v.expires_at > now())
                   ), 0)
               ) AS verification_tier,
               a.created_at, a.did_document,
               p.sovereign_agent_address
        FROM agents a
        LEFT JOIN agent_primitives p ON p.agent_id = a.id
        ORDER BY a.created_at DESC
        "#,
    )
    .fetch_all(pool)
    .await
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct UnregisteredAgentRow {
    pub agent_id: String,
    pub source: String,
    pub first_seen: DateTime<Utc>,
}

/// Real "shadow AI" detection: `otel_spans` and `audit_log` both store `agent_id` as a
/// bare TEXT column with no foreign key to `agents` (see each table's own migration) --
/// the oracle already durably records telemetry/policy-decision evidence for DIDs that
/// were never registered via `POST /v1/agent/register`. This surfaces exactly that set,
/// using data that already exists rather than any new scanning infra (see
/// bcc_middleware/spec/xibalba-shield-v1.md's [PLANNED] kernel-sensor design for the
/// separate, out-of-scope-here vision this deliberately does not attempt).
pub async fn list_unregistered_agents(pool: &PgPool) -> Result<Vec<UnregisteredAgentRow>, sqlx::Error> {
    sqlx::query_as::<_, UnregisteredAgentRow>(
        r#"
        SELECT agent_id, 'otel' AS source, MIN(start_time) AS first_seen
        FROM otel_spans
        WHERE agent_id NOT IN (SELECT id FROM agents)
        GROUP BY agent_id
        UNION ALL
        SELECT agent_id, 'audit_log' AS source, MIN(created_at) AS first_seen
        FROM audit_log
        WHERE agent_id IS NOT NULL
          AND agent_id NOT IN (SELECT id FROM agents)
        GROUP BY agent_id
        ORDER BY first_seen ASC
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
    /// EVM chain id this row was resolved against. `NULL` for rows written before this
    /// column existed — the caller must treat that the same as a chain mismatch (E11),
    /// never as "assume it's the current chain".
    pub chain_id: Option<i64>,
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
    chain_id: i64,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO agent_primitives
            (agent_id, sovereign_agent_address, state_anchor_address, reputation_registry_address,
             slasher_address, verifier_registry_address, compliance_gate_address, agent_profile_address,
             controller_address, domain_id, chain_id, resolved_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, now())
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
            chain_id = EXCLUDED.chain_id,
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
    .bind(chain_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn get_agent_primitives(pool: &PgPool, agent_id: &str) -> Result<Option<AgentPrimitivesRow>, sqlx::Error> {
    sqlx::query_as::<_, AgentPrimitivesRow>(
        r#"
        SELECT agent_id, sovereign_agent_address, state_anchor_address, reputation_registry_address,
               slasher_address, verifier_registry_address, compliance_gate_address, agent_profile_address,
               controller_address, domain_id, resolved_at, chain_id
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
    phi_flags: Option<&[String]>,
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
            (id, agent_id, nonce, performance_variance, hgi_raw, gpu_hours_verified, flagged, zk_verified, leaf_hash, payload, phi_flags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
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
    .bind(phi_flags)
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

/// BCC intent-vs-effect join (~/.claude/plans/velvet-giggling-quill.md): both the original
/// ALLOW row (written with `intended_state_hash` in its metadata, see /v1/audit/ingest) and
/// any `posttool_effect` row(s) reporting an actual effect hash against it (see
/// `submit_audit_effect`) share the same `intended_state_hash` value inside their JSONB
/// `metadata` -- there's no dedicated column for it (see this session's own earlier
/// investigation: it lives only in the blob), so this queries the JSONB field directly
/// (`metadata->>'intended_state_hash' = $1`) rather than requiring a migration. `AuditLogRow`
/// doesn't carry `metadata` (it's a read DTO shaped for the dashboard's audit panel), so this
/// returns a lighter-weight row that does, since inspecting the metadata IS the point here.
#[derive(Debug, Clone, sqlx::FromRow, Serialize, ToSchema)]
pub struct AuditEffectJoinRow {
    pub id: Uuid,
    pub agent_id: Option<String>,
    pub event_type: String,
    pub decision: String,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
}

pub async fn get_audit_log_by_intended_state_hash(
    pool: &PgPool,
    intended_state_hash: &str,
) -> Result<Vec<AuditEffectJoinRow>, sqlx::Error> {
    sqlx::query_as::<_, AuditEffectJoinRow>(
        r#"
        SELECT id, agent_id, event_type, decision, metadata, created_at
        FROM audit_log
        WHERE metadata->>'intended_state_hash' = $1
        ORDER BY created_at ASC
        "#,
    )
    .bind(intended_state_hash)
    .fetch_all(pool)
    .await
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
    phi_flags: Option<&[String]>,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO otel_spans
            (id, agent_id, trace_id, span_id, parent_span_id, name, kind, start_time, end_time, status_code, attributes, phi_flags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
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
    .bind(phi_flags)
    .execute(pool)
    .await?;
    Ok(())
}

/// Token totals for an agent, grouped by the emitter's token `type` attribute
/// (input / output / cacheRead / cacheCreation for Claude Code).
///
/// Selects on **unit**, not metric name: `unit = 'tokens'` is emitter-neutral, so a runtime
/// other than Claude Code that follows the same OTel convention rolls up here too, rather
/// than the query being welded to one vendor's metric names.
pub async fn agent_token_usage(
    pool: &PgPool,
    agent_id: &str,
    since: DateTime<Utc>,
) -> Result<Vec<(String, f64)>, sqlx::Error> {
    sqlx::query_as::<_, (String, f64)>(
        r#"
        -- Reduce per series, then sum across series. Only DELTA points are increments that
        -- may be summed; everything else (cumulative counters, gauges, and legacy rows
        -- written before migration 0009 recorded temporality at all) must take the LATEST
        -- reading for the series. Latest, not MAX: it is correct for a cumulative counter
        -- (monotonic, so latest is the running total) AND for a gauge (a point-in-time
        -- reading, where MAX would report a past peak). See migration 0009.
        SELECT token_type, SUM(v) AS total FROM (
            SELECT COALESCE(attributes->>'type', 'unspecified') AS token_type, SUM(value) AS v
            FROM otel_metrics
            WHERE agent_id = $1 AND unit = 'tokens' AND time >= $2 AND temporality = 'delta'
            GROUP BY 1, attributes
            UNION ALL
            SELECT token_type, v FROM (
                SELECT DISTINCT ON (attributes)
                       COALESCE(attributes->>'type', 'unspecified') AS token_type, value AS v
                FROM otel_metrics
                WHERE agent_id = $1 AND unit = 'tokens' AND time >= $2 AND temporality <> 'delta'
                ORDER BY attributes, time DESC
            ) latest_per_series
        ) reduced
        GROUP BY 1
        ORDER BY 1
        "#,
    )
    .bind(agent_id)
    .bind(since)
    .fetch_all(pool)
    .await
}

/// Reported cost for an agent over the window, grouped by model. `unit = 'USD'` for the
/// same emitter-neutral reason as `agent_token_usage`.
pub async fn agent_cost_usage(
    pool: &PgPool,
    agent_id: &str,
    since: DateTime<Utc>,
) -> Result<Vec<(String, f64)>, sqlx::Error> {
    sqlx::query_as::<_, (String, f64)>(
        r#"
        -- Same delta-vs-latest reduction as agent_token_usage.
        SELECT model, SUM(v) AS total FROM (
            SELECT COALESCE(attributes->>'model', 'unspecified') AS model, SUM(value) AS v
            FROM otel_metrics
            WHERE agent_id = $1 AND unit = 'USD' AND time >= $2 AND temporality = 'delta'
            GROUP BY 1, attributes
            UNION ALL
            SELECT model, v FROM (
                SELECT DISTINCT ON (attributes)
                       COALESCE(attributes->>'model', 'unspecified') AS model, value AS v
                FROM otel_metrics
                WHERE agent_id = $1 AND unit = 'USD' AND time >= $2 AND temporality <> 'delta'
                ORDER BY attributes, time DESC
            ) latest_per_series
        ) reduced
        GROUP BY 1
        ORDER BY 2 DESC
        "#,
    )
    .bind(agent_id)
    .bind(since)
    .fetch_all(pool)
    .await
}

#[derive(Debug, Clone, sqlx::FromRow)]
pub struct OtelLogRow {
    pub event_name: Option<String>,
    pub severity_text: Option<String>,
    pub body: Option<String>,
    pub attributes: serde_json::Value,
    pub trace_id: Option<String>,
    pub span_id: Option<String>,
    pub time: DateTime<Utc>,
}

/// Most recent structured events for an agent, newest first.
pub async fn recent_otel_logs(
    pool: &PgPool,
    agent_id: &str,
    limit: i64,
) -> Result<Vec<OtelLogRow>, sqlx::Error> {
    sqlx::query_as::<_, OtelLogRow>(
        r#"
        SELECT event_name, severity_text, body, attributes, trace_id, span_id, time
        FROM otel_logs
        WHERE agent_id = $1
        ORDER BY time DESC
        LIMIT $2
        "#,
    )
    .bind(agent_id)
    .bind(limit)
    .fetch_all(pool)
    .await
}

/// One OTLP metric data point. Written by `OtlpMetricsService::export`.
///
/// `evidence_tier` is passed explicitly rather than defaulted in SQL so every caller has to
/// state what it is inserting: rows arriving over the unauthenticated OTLP port are vendor
/// telemetry, not agent-signed evidence, and must never reach AIS (migration 0008's header).
#[allow(clippy::too_many_arguments)]
pub async fn insert_otel_metric(
    pool: &PgPool,
    id: Uuid,
    agent_id: &str,
    name: &str,
    description: Option<&str>,
    unit: Option<&str>,
    data_type: &str,
    temporality: &str,
    value: f64,
    attributes: &serde_json::Value,
    start_time: Option<DateTime<Utc>>,
    time: DateTime<Utc>,
    evidence_tier: &str,
    phi_flags: Option<&[String]>,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO otel_metrics
            (id, agent_id, name, description, unit, data_type, temporality, value, attributes, start_time, time, evidence_tier, phi_flags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        "#,
    )
    .bind(id)
    .bind(agent_id)
    .bind(name)
    .bind(description)
    .bind(unit)
    .bind(data_type)
    .bind(temporality)
    .bind(value)
    .bind(attributes)
    .bind(start_time)
    .bind(time)
    .bind(evidence_tier)
    .bind(phi_flags)
    .execute(pool)
    .await?;
    Ok(())
}

/// One OTLP log record / structured event. Written by `OtlpLogsService::export`.
/// Same evidence-tier caveat as `insert_otel_metric`.
#[allow(clippy::too_many_arguments)]
pub async fn insert_otel_log(
    pool: &PgPool,
    id: Uuid,
    agent_id: &str,
    event_name: Option<&str>,
    severity_text: Option<&str>,
    severity_number: Option<i32>,
    body: Option<&str>,
    attributes: &serde_json::Value,
    trace_id: Option<&str>,
    span_id: Option<&str>,
    time: DateTime<Utc>,
    evidence_tier: &str,
    phi_flags: Option<&[String]>,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        r#"
        INSERT INTO otel_logs
            (id, agent_id, event_name, severity_text, severity_number, body, attributes, trace_id, span_id, time, evidence_tier, phi_flags)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        "#,
    )
    .bind(id)
    .bind(agent_id)
    .bind(event_name)
    .bind(severity_text)
    .bind(severity_number)
    .bind(body)
    .bind(attributes)
    .bind(trace_id)
    .bind(span_id)
    .bind(time)
    .bind(evidence_tier)
    .bind(phi_flags)
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


// ---------------------------------------------------------------------------
// Verification Ladder (rungs 2 and 3) — see verification.rs and migration 0011.
// ---------------------------------------------------------------------------

#[derive(Debug, serde::Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct IdentityVerificationRow {
    pub id: i64,
    pub agent_id: String,
    pub method: String,
    pub tier_granted: i32,
    pub subject: String,
    pub evidence: serde_json::Value,
    pub verified_at: chrono::DateTime<chrono::Utc>,
    pub expires_at: Option<chrono::DateTime<chrono::Utc>>,
    pub revoked_at: Option<chrono::DateTime<chrono::Utc>>,
    pub revoked_reason: Option<String>,
}

/// Issue (or replace) a DNS challenge nonce for one (agent, domain).
///
/// Replacing rather than accumulating: an operator who asks twice should get a
/// usable nonce, not a collision, and leaving old nonces valid would widen the
/// replay window the nonce exists to close.
pub async fn issue_dns_challenge(
    pool: &PgPool,
    agent_id: &str,
    domain: &str,
    nonce: &str,
    ttl_minutes: i64,
) -> Result<chrono::DateTime<chrono::Utc>, sqlx::Error> {
    let expires_at = chrono::Utc::now() + chrono::Duration::minutes(ttl_minutes);
    sqlx::query(
        r#"
        INSERT INTO dns_verification_challenges (agent_id, domain, nonce, expires_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (agent_id, domain) DO UPDATE
          SET nonce = EXCLUDED.nonce,
              issued_at = now(),
              expires_at = EXCLUDED.expires_at,
              consumed_at = NULL
        "#,
    )
    .bind(agent_id)
    .bind(domain)
    .bind(nonce)
    .bind(expires_at)
    .execute(pool)
    .await?;
    Ok(expires_at)
}

/// Fetch an UNEXPIRED, UNCONSUMED challenge. Expiry is enforced in SQL rather than
/// in the caller so there is no window where application code forgets to check it.
pub async fn get_active_dns_challenge(
    pool: &PgPool,
    agent_id: &str,
    domain: &str,
) -> Result<Option<String>, sqlx::Error> {
    sqlx::query_scalar::<_, String>(
        r#"
        SELECT nonce FROM dns_verification_challenges
        WHERE agent_id = $1 AND domain = $2
          AND consumed_at IS NULL
          AND expires_at > now()
        "#,
    )
    .bind(agent_id)
    .bind(domain)
    .fetch_optional(pool)
    .await
}

pub async fn consume_dns_challenge(
    pool: &PgPool,
    agent_id: &str,
    domain: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE dns_verification_challenges SET consumed_at = now() WHERE agent_id = $1 AND domain = $2",
    )
    .bind(agent_id)
    .bind(domain)
    .execute(pool)
    .await?;
    Ok(())
}

/// Record a successful verification. Re-proving the same (agent, method, subject)
/// refreshes it in place rather than adding a row, matching the partial unique
/// index in migration 0011.
pub async fn record_identity_verification(
    pool: &PgPool,
    agent_id: &str,
    method: &str,
    tier_granted: i32,
    subject: &str,
    evidence: serde_json::Value,
    expires_at: Option<chrono::DateTime<chrono::Utc>>,
) -> Result<IdentityVerificationRow, sqlx::Error> {
    sqlx::query_as::<_, IdentityVerificationRow>(
        r#"
        INSERT INTO identity_verifications
            (agent_id, method, tier_granted, subject, evidence, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (agent_id, method, subject) WHERE revoked_at IS NULL
        DO UPDATE SET tier_granted = EXCLUDED.tier_granted,
                      evidence     = EXCLUDED.evidence,
                      verified_at  = now(),
                      expires_at   = EXCLUDED.expires_at
        RETURNING id, agent_id, method, tier_granted, subject, evidence,
                  verified_at, expires_at, revoked_at, revoked_reason
        "#,
    )
    .bind(agent_id)
    .bind(method)
    .bind(tier_granted)
    .bind(subject)
    .bind(evidence)
    .bind(expires_at)
    .fetch_one(pool)
    .await
}

/// Tiers from verifications that are active RIGHT NOW — not revoked, not expired.
///
/// Expiry is applied here, in the query, which is what makes a lapsed domain
/// automatically lower an agent's tier instead of requiring a sweep job. A cached
/// `verification_tier` column could not do that without drifting from its evidence.
pub async fn active_verification_tiers(
    pool: &PgPool,
    agent_id: &str,
) -> Result<Vec<i32>, sqlx::Error> {
    sqlx::query_scalar::<_, i32>(
        r#"
        SELECT tier_granted FROM identity_verifications
        WHERE agent_id = $1
          AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())
        "#,
    )
    .bind(agent_id)
    .fetch_all(pool)
    .await
}

pub async fn list_identity_verifications(
    pool: &PgPool,
    agent_id: &str,
) -> Result<Vec<IdentityVerificationRow>, sqlx::Error> {
    sqlx::query_as::<_, IdentityVerificationRow>(
        r#"
        SELECT id, agent_id, method, tier_granted, subject, evidence,
               verified_at, expires_at, revoked_at, revoked_reason
        FROM identity_verifications
        WHERE agent_id = $1
        ORDER BY verified_at DESC
        "#,
    )
    .bind(agent_id)
    .fetch_all(pool)
    .await
}

/// Return an unrevoked verification owned by this agent. Expired evidence is
/// still revocable so its audit record can explicitly say the agent withdrew it.
pub async fn get_revocable_identity_verification(
    pool: &PgPool,
    agent_id: &str,
    verification_id: i64,
) -> Result<Option<IdentityVerificationRow>, sqlx::Error> {
    sqlx::query_as::<_, IdentityVerificationRow>(
        r#"
        SELECT id, agent_id, method, tier_granted, subject, evidence,
               verified_at, expires_at, revoked_at, revoked_reason
        FROM identity_verifications
        WHERE id = $1 AND agent_id = $2 AND revoked_at IS NULL
        "#,
    )
    .bind(verification_id)
    .bind(agent_id)
    .fetch_optional(pool)
    .await
}

/// Revoke without deleting: tier derivation stops considering the row
/// immediately, while the evidence and reason remain available for audit.
pub async fn revoke_identity_verification(
    pool: &PgPool,
    agent_id: &str,
    verification_id: i64,
    reason: &str,
    challenge_subject: &str,
) -> Result<Option<IdentityVerificationRow>, sqlx::Error> {
    let mut tx = pool.begin().await?;
    let row = sqlx::query_as::<_, IdentityVerificationRow>(
        r#"
        UPDATE identity_verifications
        SET revoked_at = now(), revoked_reason = $3
        WHERE id = $1 AND agent_id = $2 AND revoked_at IS NULL
        RETURNING id, agent_id, method, tier_granted, subject, evidence,
                  verified_at, expires_at, revoked_at, revoked_reason
        "#,
    )
    .bind(verification_id)
    .bind(agent_id)
    .bind(reason)
    .fetch_optional(&mut *tx)
    .await?;

    if row.is_none() {
        tx.rollback().await?;
        return Ok(None);
    }

    let consumed = sqlx::query(
        r#"
        UPDATE dns_verification_challenges
        SET consumed_at = now()
        WHERE agent_id = $1 AND domain = $2
          AND consumed_at IS NULL AND expires_at > now()
        "#,
    )
    .bind(agent_id)
    .bind(challenge_subject)
    .execute(&mut *tx)
    .await?;

    if consumed.rows_affected() != 1 {
        tx.rollback().await?;
        return Ok(None);
    }

    tx.commit().await?;
    Ok(row)
}

/// The tier the rest of the system should use: registration floor ∪ active verifications.
pub async fn effective_verification_tier(
    pool: &PgPool,
    agent_id: &str,
    registration_tier: i32,
) -> Result<i32, sqlx::Error> {
    Ok(effective_tier_with_source(pool, agent_id, registration_tier).await?.0)
}

/// Effective tier plus WHERE IT CAME FROM.
///
/// The source is not cosmetic: a development override produces a tier that is
/// asserted rather than proven, and every surface that reports the tier must be
/// able to say which it is. Returning them together makes it impossible to
/// report the number without having the provenance in hand.
pub async fn effective_tier_with_source(
    pool: &PgPool,
    agent_id: &str,
    registration_tier: i32,
) -> Result<(i32, crate::verification::TierSource), sqlx::Error> {
    let tiers = active_verification_tiers(pool, agent_id).await?;
    let verified = crate::verification::effective_tier(registration_tier, &tiers);
    Ok(crate::verification::apply_dev_override(agent_id, verified))
}
