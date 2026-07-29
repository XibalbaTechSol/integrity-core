//! Axum handlers. Business logic lives here; `routes.rs` only wires paths to these
//! functions. Every handler returns `Result<_, AppError>` (see `error.rs`) so status-code
//! mapping stays centralized.

use std::str::FromStr;

use alloy::primitives::Address;
use axum::extract::{Path, Query, State};
use axum::Json;
use chrono::Utc;
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::chain::{MarketDetail, PrimitiveSet as ChainPrimitiveSet};
use crate::crypto::{self, AgentVerificationMethods};
use crate::db;
use crate::derive;
use crate::error::AppError;
use crate::merkle;
use crate::phi;
use crate::AppState;

// ---------------------------------------------------------------------------------
// Shared wire types
// ---------------------------------------------------------------------------------

/// Wire shape for the 7-address PrimitiveSet (§6.1), matching
/// `integrity-dashboard/src/lib/api/types.ts`'s `PrimitiveSet` field-for-field (camelCase)
/// so the dashboard can deserialize this oracle's responses without a translation layer.
#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
pub struct PrimitiveSetDto {
    pub sovereign_agent: String,
    pub state_anchor: String,
    pub reputation_registry: String,
    pub slasher: String,
    pub verifier_registry: String,
    pub compliance_gate: String,
    pub agent_profile: String,
}

impl PrimitiveSetDto {
    fn parse_addresses(&self) -> Result<ChainPrimitiveSet, AppError> {
        let parse = |label: &str, s: &str| -> Result<Address, AppError> {
            Address::from_str(s).map_err(|e| AppError::BadRequest(format!("invalid {label} address '{s}': {e}")))
        };
        Ok(ChainPrimitiveSet {
            sovereign_agent: parse("sovereignAgent", &self.sovereign_agent)?,
            state_anchor: parse("stateAnchor", &self.state_anchor)?,
            reputation_registry: parse("reputationRegistry", &self.reputation_registry)?,
            slasher: parse("slasher", &self.slasher)?,
            verifier_registry: parse("verifierRegistry", &self.verifier_registry)?,
            compliance_gate: parse("complianceGate", &self.compliance_gate)?,
            agent_profile: parse("agentProfile", &self.agent_profile)?,
        })
    }
}

impl From<ChainPrimitiveSet> for PrimitiveSetDto {
    fn from(p: ChainPrimitiveSet) -> Self {
        Self {
            sovereign_agent: p.sovereign_agent.to_checksum(None),
            state_anchor: p.state_anchor.to_checksum(None),
            reputation_registry: p.reputation_registry.to_checksum(None),
            slasher: p.slasher.to_checksum(None),
            verifier_registry: p.verifier_registry.to_checksum(None),
            compliance_gate: p.compliance_gate.to_checksum(None),
            agent_profile: p.agent_profile.to_checksum(None),
        }
    }
}

// ---------------------------------------------------------------------------------
// POST /v1/agent/register
// ---------------------------------------------------------------------------------

#[derive(Debug, Deserialize, ToSchema)]
pub struct RegisterAgentRequest {
    /// `did:integrity:<fingerprint>` — the agent's canonical off-chain identifier and
    /// the primary key of the `agents` table.
    pub did: String,
    /// §4.1 DID Document. Stored verbatim in the response for now (no dedicated column —
    /// see README/gaps note); its `verificationMethod` is where `ed25519_pubkey_hex`
    /// below is expected to have come from, but this handler trusts the explicit field,
    /// not a parse of the document, to avoid a second, redundant multibase-decode path.
    pub did_document: serde_json::Value,
    /// The 7 on-chain primitive addresses the client claims it registered via
    /// `AgentPrimitivesFactory`. Independently re-verified against
    /// `XibalbaAgentRegistry.resolveDID` below — never trusted as-is (see chain.rs's
    /// module doc comment for why).
    pub primitives: PrimitiveSetDto,
    pub ed25519_pubkey_hex: Option<String>,
    pub eth_address_hex: Option<String>,
    /// ADVISORY ONLY — never trusted. A previous version of this handler stored this
    /// client-supplied value directly, which meant any client could self-assert
    /// `verification_tier: 3` at registration with nothing server-side checking the
    /// claim, defeating the entire point of a verification ladder (see
    /// docs/wiki/concepts/identity-ceiling.md). `register_agent` now always computes
    /// the real, server-verified tier itself (see that function) and ignores this
    /// field; it's kept on the wire only for backward request-shape compatibility.
    #[serde(default)]
    pub verification_tier: i32,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct RegisterAgentResponse {
    pub id: String,
    pub verification_tier: i32,
    pub primitives: PrimitiveSetDto,
    pub controller: String,
    pub domain_id: String,
}

/// The only verification tier `register_agent` can legitimately assign today. Per
/// docs/wiki/concepts/identity-ceiling.md's ladder, Tier 1 ("Sovereign") requires only
/// proof-of-possession of a software key — which is exactly what that handler's checks
/// (a supplied key + an independently-confirmed on-chain primitive match) establish.
/// Tiers 2 ("Linked" — DNS TXT/social attestation) and 3 ("Institutional" — real TEE
/// attestation) have no verification path implemented anywhere in this codebase yet, so
/// there is no legitimate way to assign them server-side. When that verification exists,
/// this becomes a real tier computation instead of a constant.
const SERVER_VERIFIED_TIER: i32 = 1;

/// Registers an agent, but only after independently confirming on-chain that the
/// primitives it claims actually belong to its DID. This is the crux of the
/// self-sovereign model being honest end-to-end: without this check, `/v1/agent/register`
/// would just be recording whatever the client says, and the entire "the chain is the
/// source of truth" premise (§6) would be decorative.
#[utoipa::path(
    post,
    path = "/v1/agent/register",
    request_body = RegisterAgentRequest,
    responses(
        (status = 200, description = "Agent registered", body = RegisterAgentResponse),
        (status = 400, description = "Bad request"),
        (status = 409, description = "Agent already registered"),
    ),
    tag = "agents",
)]
pub async fn register_agent(
    State(state): State<AppState>,
    Json(req): Json<RegisterAgentRequest>,
) -> Result<Json<RegisterAgentResponse>, AppError> {
    if req.ed25519_pubkey_hex.is_none() && req.eth_address_hex.is_none() {
        return Err(AppError::BadRequest(
            "agent must supply at least one of ed25519_pubkey_hex / eth_address_hex".to_string(),
        ));
    }

    let claimed = req.primitives.parse_addresses()?;

    // The independent on-chain check: ask XibalbaAgentRegistry what it actually recorded
    // for this DID, and reject if the client's claim doesn't match byte-for-byte.
    let record = state.chain.resolve_primitives_by_did(&req.did).await?;
    if record.primitives != claimed {
        return Err(AppError::ChainMismatch(format!(
            "claimed primitives for DID '{}' do not match on-chain XibalbaAgentRegistry record \
             (claimed sovereignAgent={:#x}, on-chain sovereignAgent={:#x})",
            req.did, claimed.sovereign_agent, record.primitives.sovereign_agent
        )));
    }

    // Spec v0.3 §7.1 — the persistent-memory gate, checked immediately after the
    // PrimitiveSet match and with the same posture: read the agent's own StateAnchor
    // directly from chain rather than trusting anything the client sent. A zero
    // `latestRoot` means no genesis memory root was ever anchored, so per §4.1/§6 the
    // agent is not a continuing economic subject and registration is refused outright —
    // "no half-registered agents". The agent fixes this by anchoring its genesis root
    // (§7.2: controller or `SovereignAgent.execute`, at epoch 0) and retrying.
    let (latest_root, latest_epoch) = state.chain.memory_state(record.primitives.state_anchor).await?;
    if latest_root.is_zero() {
        return Err(AppError::MemoryNotInitialized(format!(
            "agent '{}' has no anchored genesis memory root — StateAnchor {:#x} reports \
             latestRoot=0x0 at epoch {}. Anchor a genesis Trust Vault root through the \
             agent's own controller (spec v0.3 §7.2) before registering.",
            req.did, record.primitives.state_anchor, latest_epoch
        )));
    }

    let ed25519_pubkey = req
        .ed25519_pubkey_hex
        .as_deref()
        .map(|h| hex::decode(h.strip_prefix("0x").unwrap_or(h)))
        .transpose()
        .map_err(|e| AppError::BadRequest(format!("invalid ed25519_pubkey_hex: {e}")))?;

    let row = db::register_agent(
        &state.pool,
        &req.did,
        ed25519_pubkey,
        req.eth_address_hex.clone(),
        SERVER_VERIFIED_TIER,
        Some(req.did_document.clone()),
    )
    .await
    .map_err(|e| match e {
        db::RegisterAgentError::AlreadyExists => AppError::AgentAlreadyExists(req.did.clone()),
        db::RegisterAgentError::Db(e) => AppError::Database(e),
    })?;

    db::upsert_agent_primitives(
        &state.pool,
        &req.did,
        &format!("{:#x}", claimed.sovereign_agent),
        &format!("{:#x}", claimed.state_anchor),
        &format!("{:#x}", claimed.reputation_registry),
        &format!("{:#x}", claimed.slasher),
        &format!("{:#x}", claimed.verifier_registry),
        &format!("{:#x}", claimed.compliance_gate),
        &format!("{:#x}", claimed.agent_profile),
        &format!("{:#x}", record.controller),
        &record.domain_id.to_string(),
    )
    .await?;

    Ok(Json(RegisterAgentResponse {
        id: row.id,
        verification_tier: row.verification_tier,
        primitives: req.primitives,
        controller: format!("{:#x}", record.controller),
        domain_id: record.domain_id.to_string(),
    }))
}

// ---------------------------------------------------------------------------------
// GET /v1/agent/{id}
// ---------------------------------------------------------------------------------

#[derive(Debug, Serialize, ToSchema)]
pub struct AgentResponse {
    pub id: String,
    /// RESERVED (partially enforced) — server-verified as of this version (`register_agent`
    /// computes it independently; a client can no longer self-assert a value), but only
    /// Tier 1 is currently achievable (no Tier 2/3 verification path is built), and only
    /// `bcc_middleware`'s policy gate consults it, and only for a subset of intent_types —
    /// see `spec/bcc/v1/README.md` once that surface exists. Most integrations should
    /// still treat this as informational rather than build authorization logic on top of
    /// it directly.
    pub verification_tier: i32,
    pub last_nonce: i64,
    pub created_at: chrono::DateTime<Utc>,
    pub has_ed25519_key: bool,
    pub has_eth_address: bool,
    pub primitives: Option<PrimitiveSetDto>,
    /// True when this response's `primitives` came from a live chain read performed just
    /// now (cache miss / no local `agents` row), rather than the Postgres cache.
    pub primitives_source: &'static str,
    /// §4.1 DID Document, as supplied on `POST /v1/agent/register`. `None` for agents that
    /// registered before this field existed, or that were only ever seen via a chain
    /// backfill (see the "chain-backfill"/"unavailable" `primitives_source` cases below,
    /// which synthesize a response with no local `agents` row at all).
    pub did_document: Option<serde_json::Value>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}",
    params(("id" = String, Path, description = "Agent DID (`did:integrity:<fingerprint>`)")),
    responses(
        (status = 200, description = "Agent found", body = AgentResponse),
        (status = 404, description = "Unknown DID"),
    ),
    tag = "agents",
)]
pub async fn get_agent(State(state): State<AppState>, Path(id): Path<String>) -> Result<Json<AgentResponse>, AppError> {
    let agent_row = db::get_agent(&state.pool, &id).await?;

    // Prefer the Postgres cache; fall back to a live chain resolution ("backfilled from
    // chain on miss") and persist it so the next lookup is cheap again. This also covers
    // an agent that registered on-chain directly via integrity-sdk/cli without ever
    // calling this oracle's POST /v1/agent/register.
    let cached = db::get_agent_primitives(&state.pool, &id).await?;
    let (primitives, source) = match cached {
        Some(row) => (Some(row_to_dto(&row)?), "cache"),
        None => match state.chain.resolve_primitives_by_did(&id).await {
            Ok(record) => {
                db::upsert_agent_primitives(
                    &state.pool,
                    &id,
                    &format!("{:#x}", record.primitives.sovereign_agent),
                    &format!("{:#x}", record.primitives.state_anchor),
                    &format!("{:#x}", record.primitives.reputation_registry),
                    &format!("{:#x}", record.primitives.slasher),
                    &format!("{:#x}", record.primitives.verifier_registry),
                    &format!("{:#x}", record.primitives.compliance_gate),
                    &format!("{:#x}", record.primitives.agent_profile),
                    &format!("{:#x}", record.controller),
                    &record.domain_id.to_string(),
                )
                .await?;
                (Some(record.primitives.into()), "chain-backfill")
            }
            // No agents row AND nothing on-chain either: genuinely unknown DID.
            Err(_) if agent_row.is_none() => return Err(AppError::AgentNotFound(id)),
            // Chain lookup failed but we do have a local row — still return what we know
            // rather than failing the whole request over an on-chain read hiccup.
            Err(_) => (None, "unavailable"),
        },
    };

    let agent_row = match agent_row {
        Some(r) => r,
        None => {
            // Chain-only agent (see above): synthesize a response without off-chain
            // verification material rather than fabricating placeholder values.
            return Ok(Json(AgentResponse {
                id: id.clone(),
                verification_tier: 0,
                last_nonce: 0,
                created_at: Utc::now(),
                has_ed25519_key: false,
                has_eth_address: false,
                primitives,
                primitives_source: source,
                did_document: None,
            }));
        }
    };

    Ok(Json(AgentResponse {
        id: agent_row.id,
        verification_tier: agent_row.verification_tier,
        last_nonce: agent_row.last_nonce,
        created_at: agent_row.created_at,
        has_ed25519_key: agent_row.ed25519_pubkey.is_some(),
        has_eth_address: agent_row.eth_address.is_some(),
        primitives,
        primitives_source: source,
        did_document: agent_row.did_document,
    }))
}

fn row_to_dto(row: &db::AgentPrimitivesRow) -> Result<PrimitiveSetDto, AppError> {
    Ok(PrimitiveSetDto {
        sovereign_agent: row.sovereign_agent_address.clone(),
        state_anchor: row.state_anchor_address.clone(),
        reputation_registry: row.reputation_registry_address.clone(),
        slasher: row.slasher_address.clone(),
        verifier_registry: row.verifier_registry_address.clone(),
        compliance_gate: row.compliance_gate_address.clone(),
        agent_profile: row.agent_profile_address.clone(),
    })
}

// ---------------------------------------------------------------------------------
// GET /v1/agents
// ---------------------------------------------------------------------------------

#[derive(Debug, Serialize, ToSchema)]
pub struct AgentSummary {
    pub id: String,
    /// The agent's primary XNS handle (e.g. `"xibalba.integrity"`), read live from
    /// `XibalbaNameService.primaryHandle(sovereignAgent)`. This is the protocol's own
    /// naming authority — self-service and on-chain (see XibalbaNameService.sol's NatSpec
    /// on why there is deliberately no privileged off-chain registrar) — so consumers
    /// should prefer it over `name` when displaying an agent.
    ///
    /// `None` is a normal, expected outcome, never an error: the agent hasn't claimed a
    /// handle, XNS isn't deployed on this chain, or the on-chain read failed. See
    /// `list_agents` on why a chain hiccup must not take the whole fleet list down.
    pub handle: Option<String>,
    /// Legacy secondary display name, if the agent's DID document carries an `alsoKnownAs`
    /// entry. Kept as a last-resort fallback below `handle` — most agents have none, and
    /// nothing in this system can write it (`register_agent` is an insert with no update
    /// path), so new naming should go through XNS.
    pub name: Option<String>,
    pub verification_tier: i32,
    pub created_at: chrono::DateTime<Utc>,
}

#[utoipa::path(
    get,
    path = "/v1/agents",
    responses((status = 200, description = "All registered agents", body = Vec<AgentSummary>)),
    tag = "agents",
)]
pub async fn list_agents(State(state): State<AppState>) -> Result<Json<Vec<AgentSummary>>, AppError> {
    let rows = db::list_agents(&state.pool).await?;
    let handles = resolve_primary_handles(&state, &rows).await;
    Ok(Json(
        rows.into_iter()
            .enumerate()
            .map(|(i, r)| AgentSummary {
                handle: handles.get(i).cloned().flatten(),
                name: r.did_document.as_ref()
                    .and_then(|d| d.get("alsoKnownAs"))
                    .and_then(|a| a.get(0))
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string()),
                id: r.id,
                verification_tier: r.verification_tier,
                created_at: r.created_at,
            })
            .collect(),
    ))
}

/// Best-effort XNS lookup for a whole agent list, returned positionally (one entry per
/// input row, in the same order).
///
/// **Every failure degrades to `None` rather than propagating.** Unlike `get_agent_handle`
/// — where the handle *is* the response, so a missing XNS singleton rightly surfaces as a
/// 400 — here the handle is one cosmetic field on the route the entire dashboard fleet list
/// depends on. Letting a `MissingSingleton` (any chain without XNS deployed, e.g. a local
/// anvil genesis) or a transient RPC error bubble up would turn "no handles" into "no
/// agents", which is a far worse failure than an unnamed agent. The reads run concurrently,
/// same `join_all` pattern as `refresh_leaderboard_if_stale`.
async fn resolve_primary_handles(state: &AppState, rows: &[db::AgentListRow]) -> Vec<Option<String>> {
    let Some(xns) = state.chain.xibalba_name_service() else {
        // XNS not deployed on this chain — skip the chain reads entirely, don't error.
        return vec![None; rows.len()];
    };
    let reads = rows.iter().map(|row| async move {
        let sovereign_agent = Address::from_str(row.sovereign_agent_address.as_deref()?).ok()?;
        let handle = state.chain.primary_handle(xns, sovereign_agent).await.ok()?;
        if handle.is_empty() {
            None
        } else {
            Some(handle)
        }
    });
    futures::future::join_all(reads).await
}

// ---------------------------------------------------------------------------------
// GET /v1/agent/{id}/ais
// ---------------------------------------------------------------------------------

/// Schema-only mirror of `scoring_core::AisWeights` for OpenAPI generation.
/// `scoring-core` is deliberately dependency-free beyond `serde` (see its Cargo.toml —
/// it's the single source of truth for the AIS formula and must stay trivially
/// auditable), so it doesn't derive `utoipa::ToSchema` itself. This struct's fields
/// must stay in sync with `scoring_core::AisWeights` by hand; a `scoring_core` unit
/// test pinning its `Serialize` output's field names is the backstop against drift
/// (see scoring-core's existing `default_weights_sum_to_one` test module).
#[derive(Debug, Serialize, ToSchema)]
pub struct AisWeightsSchema {
    pub w_entropy: f64,
    pub w_grounding: f64,
    pub w_sacrifice: f64,
    pub w_compliance: f64,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AisResponse {
    pub agent_id: String,
    pub ais: f64,
    pub components: AisComponents,
    #[schema(value_type = AisWeightsSchema)]
    pub weights: scoring_core::AisWeights,
    pub zk_boost: f64,
    pub zk_proof_verified: bool,
    pub period_start: chrono::DateTime<Utc>,
    pub period_end: chrono::DateTime<Utc>,
    pub event_count: i64,
    /// Present only when a cached on-chain ReputationRegistry address is known for this
    /// agent — a nice-to-have cross-check (per the task's "not required" note) that the
    /// oracle's off-chain `zk_verified_this_period` telemetry flag agrees with the
    /// contract's own independently-earned `isZkBoosted` state. A mismatch here doesn't
    /// fail the request (the two are allowed to be transiently out of sync — e.g. a proof
    /// submitted directly to the contract that hasn't shown up in telemetry yet) but is
    /// worth surfacing to an operator.
    pub onchain_zk_boost_consistent: Option<bool>,
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AisComponents {
    pub entropy: f64,
    pub grounding: f64,
    pub sacrifice: f64,
    pub compliance: f64,
}

/// Computes the current AIS breakdown for an agent. The single call site both
/// `GET /v1/agent/{id}/ais` and the SSE stream's `AisUpdate` push (see `stream.rs`) go
/// through — per `docs/INTERFACE_CONTRACT.md` §4.3, AIS is computed in exactly one place
/// (`scoring-core`), and this function is that place's one caller inside `backend`, so a
/// live-pushed score can never drift from what a direct REST read would return.
///
/// Callers are responsible for the existence check (`db::get_agent(...).is_none()` ->
/// `AppError::AgentNotFound`) before calling this, since a stream context may already have
/// resolved that the agent exists.
pub(crate) async fn compute_ais_for_agent(state: &AppState, id: &str) -> Result<AisResponse, AppError> {
    let period_end = Utc::now();
    let period_start = period_end - chrono::Duration::days(state.config.reporting_period_days);

    let aggregate = db::aggregate_for_ais(&state.pool, id, period_start).await?;

    let inputs = scoring_core::AisComponentInputs {
        performance_variance: aggregate.avg_variance,
        hgi_raw: aggregate.avg_hgi,
        gpu_hours_verified: aggregate.sum_gpu_hours,
        penalty_ratio: aggregate.penalty_ratio,
        zk_verified_this_period: aggregate.zk_verified_this_period,
    };

    let engine = scoring_core::AisEngine::new(state.config.ais_weights).map_err(|e| AppError::Internal(anyhow::anyhow!(e)))?;
    let breakdown = engine.score(&inputs);

    let onchain_zk_boost_consistent = match db::get_agent_primitives(&state.pool, id).await? {
        Some(row) => {
            let rep_addr = Address::from_str(&row.reputation_registry_address).ok();
            let sov_addr = Address::from_str(&row.sovereign_agent_address).ok();
            match (rep_addr, sov_addr) {
                (Some(rep), Some(sov)) => state.chain.is_zk_boosted(rep, sov).await.ok().map(|onchain| onchain == aggregate.zk_verified_this_period),
                _ => None,
            }
        }
        None => None,
    };

    Ok(AisResponse {
        agent_id: id.to_string(),
        ais: breakdown.ais,
        components: AisComponents {
            entropy: breakdown.s_entropy,
            grounding: breakdown.s_grounding,
            sacrifice: breakdown.s_sacrifice,
            compliance: breakdown.s_compliance,
        },
        weights: state.config.ais_weights,
        zk_boost: breakdown.zk_boost,
        zk_proof_verified: aggregate.zk_verified_this_period,
        period_start,
        period_end,
        event_count: aggregate.event_count,
        onchain_zk_boost_consistent,
    })
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/ais",
    params(("id" = String, Path, description = "Agent DID")),
    responses(
        (status = 200, description = "Current AIS (Agent Integrity Score) breakdown", body = AisResponse),
        (status = 404, description = "Unknown DID"),
    ),
    tag = "ais",
)]
pub async fn get_ais(State(state): State<AppState>, Path(id): Path<String>) -> Result<Json<AisResponse>, AppError> {
    // Existence check: an AIS read for a totally unknown agent should 404, not silently
    // return a zeroed-out score for an id nobody registered.
    if db::get_agent(&state.pool, &id).await?.is_none() {
        return Err(AppError::AgentNotFound(id));
    }

    Ok(Json(compute_ais_for_agent(&state, &id).await?))
}

// ---------------------------------------------------------------------------------
// POST /v1/telemetry/ingest
// ---------------------------------------------------------------------------------

#[derive(Debug, Deserialize, Serialize, ToSchema)]
pub struct DerivedSignals {
    /// Maps to `telemetry_events.performance_variance` (S_entropy's raw input, §4.3) —
    /// higher means less stable/more erratic behavior for this event.
    pub entropy: f64,
    /// Maps to `telemetry_events.hgi_raw`, in `[0.0, 1.0]`.
    pub grounding: f64,
    /// Maps to `telemetry_events.gpu_hours_verified` for this event.
    pub sacrifice: f64,
    /// Whether the BCC/OPA pipeline (bcc_middleware) flagged this specific event's intent.
    /// This oracle treats it as a straightforward boolean-ish signal (>0.5 => flagged);
    /// see the field's doc in `aggregate_for_ais`/scoring-core for how per-event flags
    /// become the period's `penalty_ratio`.
    pub compliance: f64,
}

#[derive(Debug, Deserialize, Serialize, ToSchema)]
pub struct ZkProofDto {
    pub circuit_id: String,
    /// Base64-encoded raw bytes of `bb prove`'s `proof` output file.
    pub proof: String,
    /// Base64-encoded raw bytes of `bb prove`'s `public_inputs` output file.
    pub public_inputs: String,
}

/// A judge (LLM-as-judge) evaluation, optionally carried alongside a telemetry
/// ingestion — storage + ingestion plumbing only (task write-up item 6). No judge/
/// rubric implementation exists in this codebase; this is purely "if some other
/// component produces one of these, the oracle can persist it." Deliberately NOT part
/// of `ingest_telemetry`'s signed payload (see that handler's `signable` JSON
/// construction below, which does not reference this field) — adding it there would
/// retroactively invalidate every telemetry signature a client produced before this
/// field existed. It rides along as an unauthenticated sidecar on an otherwise-
/// authenticated request (the rest of the payload still requires a valid agent
/// signature); this is an accepted, documented scope limit for now.
#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
pub struct JudgeEvaluationDto {
    pub run_id: String,
    pub judge_model: String,
    pub verdict: String,
    #[serde(default)]
    pub score: Option<f64>,
    #[serde(default)]
    pub rationale_summary: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, ToSchema)]
pub struct TelemetryIngestRequest {
    pub agent_id: String,
    pub nonce: i64,
    #[serde(default)]
    pub otel_spans: Vec<serde_json::Value>,
    pub derived_signals: DerivedSignals,
    #[serde(default)]
    pub zk_proof: Option<ZkProofDto>,
    /// Hex signature over the canonical JSON (see `crypto::canonical_json_bytes`) of every
    /// field above EXCEPT this one and `judge_evaluation` — i.e. the client constructs the
    /// object without `signature`, canonicalizes+signs that, then adds this field before
    /// POSTing. This mirrors the §4.2 BCC Commitment convention (sign the payload minus the
    /// signature field itself) rather than inventing a different scheme for telemetry.
    pub signature: String,
    /// See `JudgeEvaluationDto`'s doc comment: optional, unauthenticated sidecar, not part
    /// of the signed envelope.
    #[serde(default)]
    pub judge_evaluation: Option<JudgeEvaluationDto>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct TelemetryIngestResponse {
    pub event_id: Uuid,
    pub leaf_hash: String,
    pub zk_verified: bool,
    pub flagged: bool,
}

/// Fixed-window rate limiter over Redis: `INCR` a per-agent, per-minute counter (key
/// includes the current unix-minute bucket, so an old counter can never leak into a new
/// window) and set it to expire in 60s the first time it's created in that window. This
/// is the "concrete, real use of Redis" `config.rs`'s doc comment on
/// `telemetry_rate_limit_per_minute` describes — protecting Postgres and the `bb verify`
/// subprocess from a misbehaving/compromised agent hammering ingestion, not a token
/// bucket (a fixed window is simpler and sufficient for this purpose: the worst case is
/// bursting up to 2x the limit at a window boundary, which is an acceptable trade for not
/// needing a token-bucket's extra state).
async fn check_telemetry_rate_limit(state: &AppState, agent_id: &str) -> Result<(), AppError> {
    use redis::AsyncCommands;

    let window = Utc::now().timestamp() / 60;
    let key = format!("ratelimit:telemetry:{agent_id}:{window}");

    let mut conn = state.redis.clone();
    let count: i64 = conn.incr(&key, 1).await?;
    if count == 1 {
        let _: () = conn.expire(&key, 60).await?;
    }

    if count > state.config.telemetry_rate_limit_per_minute as i64 {
        return Err(AppError::RateLimited);
    }
    Ok(())
}

/// Oracle-side compliance derivation, mirroring `integrity_sdk/telemetry/derive.py`'s
/// `derive_compliance` — "on-chain wins" over the self-reported flagged-ratio — but run
/// unconditionally here rather than as an SDK-side opt-in a caller could forget to pass.
/// `covered_entity_address` is read from `req.otel_spans`' `metadata` (see
/// `derive::entry_covered_entity_address`'s doc comment for why, not a new signed field)
/// rather than a request parameter. Falls back to the self-reported signal — never
/// errors — whenever the agent isn't cached, isn't in a regulated vertical, no
/// `covered_entity_address` was supplied, or the chain read fails; this function
/// computes an AIS input, not a security gate (`EHRGate.sol` remains the real,
/// fail-closed enforcement point for actual PHI access).
async fn oracle_compliance(state: &AppState, req: &TelemetryIngestRequest) -> f64 {
    let self_reported = derive::self_reported_compliance(&req.otel_spans);

    let Some(primitives) = db::get_agent_primitives(&state.pool, &req.agent_id).await.ok().flatten() else {
        return self_reported;
    };
    let Some(covered_entity) = derive::entry_covered_entity_address(&req.otel_spans) else {
        return self_reported;
    };
    let Some(gate) = Address::from_str(&primitives.compliance_gate_address).ok() else {
        return self_reported;
    };
    let Some(entity) = Address::from_str(&covered_entity).ok() else {
        return self_reported;
    };

    match state.chain.compliance_vertical(gate).await {
        Ok(1) => match state.chain.is_healthcare_compliant(gate, entity).await {
            // On-chain wins: a live "not compliant" read overrides a clean self-report
            // (an agent can't talk its way out of a lapsed BAA), but a live "compliant"
            // read still can't push the score above what self-reporting already earned.
            Ok(true) => self_reported.min(1.0),
            Ok(false) => 0.0,
            Err(_) => self_reported,
        },
        _ => self_reported,
    }
}

#[utoipa::path(
    post,
    path = "/v1/telemetry/ingest",
    request_body = TelemetryIngestRequest,
    responses(
        (status = 200, description = "Event ingested and Merkle-leafed", body = TelemetryIngestResponse),
        (status = 400, description = "Bad request / PHI detected in payload"),
        (status = 401, description = "Signature verification failed"),
        (status = 404, description = "Unknown agent"),
        (status = 409, description = "Nonce replay"),
        (status = 429, description = "Rate limited"),
    ),
    tag = "telemetry",
)]
pub async fn ingest_telemetry(
    State(state): State<AppState>,
    Json(req): Json<TelemetryIngestRequest>,
) -> Result<Json<TelemetryIngestResponse>, AppError> {
    // Defense-in-depth PHI/PII/secret backstop (see crate::phi's doc comment): scan the
    // free-text-bearing parts of the payload for a raw pattern integrity-sdk's
    // client-side Redactor should already have masked. A hit here means that
    // redaction was buggy or bypassed — reject loudly before this ever touches
    // Postgres or gets folded into a Merkle leaf, rather than silently storing it.
    // Runs first, before any DB/RPC work, so a malformed payload fails fast.
    let mut phi_hits: Vec<&'static str> = Vec::new();
    for span in &req.otel_spans {
        phi::scan_json_value(span, &mut phi_hits);
    }
    if let Some(judge) = &req.judge_evaluation {
        if let Ok(judge_value) = serde_json::to_value(judge) {
            phi::scan_json_value(&judge_value, &mut phi_hits);
        }
    }
    if !phi_hits.is_empty() {
        phi_hits.sort_unstable();
        phi_hits.dedup();
        return Err(AppError::PhiDetected(phi_hits.into_iter().map(str::to_string).collect()));
    }

    let agent = db::get_agent(&state.pool, &req.agent_id)
        .await?
        .ok_or_else(|| AppError::AgentNotFound(req.agent_id.clone()))?;

    check_telemetry_rate_limit(&state, &req.agent_id).await?;

    // Rebuild exactly the JSON object the client should have signed: every field of the
    // request except `signature` itself. Re-serializing the typed struct with a
    // `#[serde(skip_serializing)]`-free copy keeps this in one place rather than hand-
    // building a parallel `serde_json::Map`.
    let signable = serde_json::json!({
        "agent_id": req.agent_id,
        "nonce": req.nonce,
        "otel_spans": req.otel_spans,
        "derived_signals": req.derived_signals,
        "zk_proof": req.zk_proof,
    });
    let message = crypto::canonical_json_bytes(&signable);

    // `ed25519_pubkey` is stored as raw bytes (BYTEA), but the verification method needs a
    // hex string — hex-encode once here rather than changing the crypto module's signature
    // to accept raw bytes just for this one caller.
    let ed25519_hex = agent.ed25519_pubkey.as_ref().map(hex::encode);
    let methods = AgentVerificationMethods {
        ed25519_pubkey_hex: ed25519_hex.as_deref(),
        eth_address_hex: agent.eth_address.as_deref(),
    };

    let verified = crypto::verify_agent_signature(&message, &req.signature, &methods)?;
    if !verified {
        return Err(AppError::Unauthorized);
    }

    // The oracle independently recomputes entropy/grounding/sacrifice from the raw
    // content already inside this signed request (`otel_spans`' `metadata.text_output`/
    // token usage) rather than trusting `req.derived_signals` — see `derive.rs`'s module
    // doc comment for why. Placed after signature verification (so an unauthenticated
    // request never triggers this work) and before the ZK check.
    let recomputed = derive::recompute(&req.otel_spans);

    let zk_verified = match &req.zk_proof {
        Some(proof) => {
            use base64::Engine;
            let proof_bytes = base64::engine::general_purpose::STANDARD
                .decode(&proof.proof)
                .map_err(|e| AppError::BadRequest(format!("invalid base64 zk_proof.proof: {e}")))?;
            let inputs_bytes = base64::engine::general_purpose::STANDARD
                .decode(&proof.public_inputs)
                .map_err(|e| AppError::BadRequest(format!("invalid base64 zk_proof.public_inputs: {e}")))?;
            state.zk.verify(&proof.circuit_id, &proof_bytes, &inputs_bytes).await?
        }
        None => false,
    };

    let compliance = oracle_compliance(&state, &req).await;
    // `compliance` is high-is-good (1.0 = clean, matching derive::self_reported_compliance
    // and oracle_compliance's on-chain `Ok(false) => 0.0` branch) — NOT the same polarity
    // as the old client-submitted DerivedSignals.compliance field this comparator was
    // originally written for (that field was high-is-bad, "flag likelihood"). Using `> 0.5`
    // here inverted the compliance axis of AIS for every agent: a clean batch scored
    // flagged=true (penalized) and an all-violation batch scored flagged=false (not
    // penalized). See PRODUCTION_GAPS.md §2 for the full incident writeup.
    let flagged = compliance < 0.5;

    // Leaf hash per merkle.rs's telemetry_leaf_data convention: keccak256 of the payload
    // (everything the client signed, so the leaf is bound to the same bytes the signature
    // covers), then packed with agent_id/nonce per §4.4.
    let payload_hash = merkle::keccak256(&message);
    let leaf_data = merkle::telemetry_leaf_data(&req.agent_id, req.nonce as u64, payload_hash);
    let leaf_hash = merkle::keccak256(&leaf_data);

    let event_id = Uuid::new_v4();
    let payload_json = serde_json::json!({
        "otel_spans": req.otel_spans,
        // Client's claimed values — advisory/audit-trail only, no longer what gets scored.
        "derived_signals": req.derived_signals,
        // The oracle's own independently-recomputed values — these are what
        // actually feed telemetry_events/AIS. Comparing the two after the fact
        // (e.g. via a SQL query over this JSONB column) is how a systematically
        // lying client would be detected, without ever having rejected a
        // legitimate one over float-precision/heuristic-version drift.
        "oracle_recomputed_signals": {
            "entropy": recomputed.entropy,
            "grounding": recomputed.grounding,
            "sacrifice": recomputed.sacrifice,
            "compliance": compliance,
        },
        "zk_proof": req.zk_proof.as_ref().map(|p| &p.circuit_id),
    });

    db::insert_telemetry_event(
        &state.pool,
        event_id,
        &req.agent_id,
        req.nonce,
        // `performance_variance` (scoring-core: 0.0 = best, a true variance) is fed the
        // POLARITY-CORRECTED inverse of the oracle's stability score (1.0 = best) — see
        // derive.rs's module doc comment: storing the raw stability score here was
        // backwards for every agent prior to this fix.
        1.0 - recomputed.entropy,
        recomputed.grounding,
        // `gpu_hours_verified` now receives an hours-equivalent proxy (see derive.rs),
        // not a pre-normalized [0,1] index — scoring-core's own log10 is the only
        // normalization step now, removing the prior double-compression.
        recomputed.sacrifice,
        flagged,
        zk_verified,
        &leaf_hash,
        &payload_json,
    )
    .await
    .map_err(|e| match e {
        db::InsertTelemetryError::NonceReplay { submitted, last_seen } => AppError::NonceReplay {
            agent_id: req.agent_id.clone(),
            submitted,
            last_seen,
        },
        db::InsertTelemetryError::Db(e) => AppError::Database(e),
    })?;

    // Storage + ingestion plumbing only (see JudgeEvaluationDto's doc comment) — no
    // judge/rubric implementation lives here. Persisted only after the telemetry event
    // itself is safely committed, and linked to it via telemetry_event_id.
    if let Some(judge) = &req.judge_evaluation {
        db::insert_judge_evaluation(
            &state.pool,
            Uuid::new_v4(),
            &req.agent_id,
            &judge.run_id,
            &judge.judge_model,
            &judge.verdict,
            judge.score,
            judge.rationale_summary.as_deref(),
            Some(event_id),
        )
        .await?;
    }

    // Push a live update to any SSE subscriber (`stream.rs`) — best effort (a `send`
    // error just means zero current subscribers, not a failure to report to the
    // client), and the AIS recompute is skipped entirely when nobody's listening so a
    // quiet oracle doesn't pay for a computation no client will ever see.
    if state.telemetry_tx.receiver_count() > 0 {
        let _ = state.telemetry_tx.send(crate::stream::StreamEvent::TelemetryEvent {
            agent_id: req.agent_id.clone(),
            event_id,
            flagged,
            created_at: Utc::now(),
        });
        if let Ok(ais) = compute_ais_for_agent(&state, &req.agent_id).await {
            let _ = state.telemetry_tx.send(crate::stream::StreamEvent::AisUpdate(ais));
        }
    }

    Ok(Json(TelemetryIngestResponse {
        event_id,
        leaf_hash: format!("0x{}", hex::encode(leaf_hash)),
        zk_verified,
        flagged,
    }))
}

// ---------------------------------------------------------------------------------
// GET /v1/agent/{id}/compliance
// ---------------------------------------------------------------------------------

#[derive(Debug, Deserialize, ToSchema)]
pub struct ComplianceQuery {
    /// Which covered-entity address to check `isHealthcareCompliant` against.
    /// `ComplianceGate.isHealthcareCompliant` takes a covered-entity argument (there's no
    /// single "the" covered entity for an agent) — the dashboard's `ComplianceStatus`
    /// type carries an optional `coveredEntity` for exactly this reason. Omitting this
    /// query param still reports the declared `vertical`, just without a live compliance
    /// verdict.
    pub covered_entity: Option<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct ComplianceResponse {
    pub agent_id: String,
    pub vertical: &'static str,
    pub is_compliant: bool,
    pub covered_entity: Option<String>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/compliance",
    params(
        ("id" = String, Path, description = "Agent DID"),
        ("covered_entity" = Option<String>, Query, description = "Covered-entity address to check isHealthcareCompliant against"),
    ),
    responses((status = 200, description = "Declared vertical + live compliance verdict", body = ComplianceResponse)),
    tag = "compliance",
)]
pub async fn get_compliance(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<ComplianceQuery>,
) -> Result<Json<ComplianceResponse>, AppError> {
    let cached = db::get_agent_primitives(&state.pool, &id).await?;
    let compliance_gate_addr = match cached {
        Some(row) => Address::from_str(&row.compliance_gate_address)
            .map_err(|e| AppError::Internal(anyhow::anyhow!("cached compliance_gate_address is not a valid address: {e}")))?,
        None => {
            let record = state.chain.resolve_primitives_by_did(&id).await?;
            record.primitives.compliance_gate
        }
    };

    let vertical_code = state.chain.compliance_vertical(compliance_gate_addr).await?;
    let vertical = match vertical_code {
        1 => "healthcare",
        _ => "none",
    };

    if vertical == "none" {
        return Ok(Json(ComplianceResponse {
            agent_id: id,
            vertical,
            is_compliant: false,
            covered_entity: None,
        }));
    }

    let is_compliant = match &query.covered_entity {
        Some(addr_str) => {
            let covered_entity = Address::from_str(addr_str)
                .map_err(|e| AppError::BadRequest(format!("invalid covered_entity address: {e}")))?;
            state.chain.is_healthcare_compliant(compliance_gate_addr, covered_entity).await?
        }
        None => false,
    };

    Ok(Json(ComplianceResponse {
        agent_id: id,
        vertical,
        is_compliant,
        covered_entity: query.covered_entity,
    }))
}

// ---------------------------------------------------------------------------------
// GET /v1/markets, GET /v1/markets/{id} (§6.9)
// ---------------------------------------------------------------------------------

/// How long a `markets_cache`/`markets_index_sync` row is trusted before a handler
/// re-reads live chain state. A documented tradeoff, not silent staleness: real-money
/// (well, real-$ITK) state that changes on every `enterPosition`/`resolve` could in
/// principle always be read live, but that would mean every `GET /v1/markets` call
/// fans out N+1 RPC calls (one per market) — 30s keeps the common case (repeated
/// dashboard polling) cheap while keeping the worst-case staleness small and stated.
const MARKETS_CACHE_STALENESS_SECS: i64 = 30;

#[derive(Debug, Serialize, ToSchema)]
pub struct MarketSummaryDto {
    pub address: String,
    pub creator: String,
    pub question: String,
    pub outcome_count: u8,
    /// Decimal string — see migrations/0002's header note on why uint256 amounts are
    /// never serialized as a JSON number.
    pub min_ais_to_enter: String,
    pub resolve_deadline: chrono::DateTime<Utc>,
    pub resolved: bool,
    pub winning_outcome: Option<u8>,
    pub total_staked: String,
    /// Per-outcome pari-mutuel pool, decimal strings, index = outcome index. Cheap
    /// public-getter reads (`outcomeStaked(i)`), unlike per-holder positions (see
    /// `MarketDetailDto`'s doc comment).
    pub outcome_staked: Vec<String>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct PositionDto {
    pub amount: String,
    pub outcome_index: u8,
    pub bcc_commitment_hash: String,
    pub claimed: bool,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct MarketDetailDto {
    #[serde(flatten)]
    #[schema(inline)]
    pub summary: MarketSummaryDto,
    /// Only populated when the request carries `?agent=0x...` — a single, cheap
    /// `getPosition(agent)` read. Real per-holder enumeration across ALL positions
    /// would require indexing `PositionEntered` events, which this pass does not
    /// build — a documented gap, not a silent omission.
    pub your_position: Option<PositionDto>,
    pub positions_note: &'static str,
}

fn market_cache_row_to_dto(row: db::MarketCacheRow) -> Result<MarketSummaryDto, AppError> {
    let outcome_staked: Vec<String> = serde_json::from_value(row.outcome_staked)
        .map_err(|e| AppError::Internal(anyhow::anyhow!("corrupt outcome_staked cache value: {e}")))?;
    let resolve_deadline = chrono::DateTime::<Utc>::from_timestamp(row.resolve_deadline, 0)
        .ok_or_else(|| AppError::Internal(anyhow::anyhow!("resolve_deadline {} out of range", row.resolve_deadline)))?;
    Ok(MarketSummaryDto {
        address: row.address,
        creator: row.creator_address,
        question: row.question,
        outcome_count: row.outcome_count as u8,
        min_ais_to_enter: row.min_ais_to_enter,
        resolve_deadline,
        resolved: row.resolved,
        winning_outcome: if row.resolved { Some(row.winning_outcome as u8) } else { None },
        total_staked: row.total_staked,
        outcome_staked,
    })
}

async fn upsert_market_detail(state: &AppState, detail: &MarketDetail) -> Result<(), AppError> {
    let outcome_staked: Vec<String> = detail.outcome_staked.iter().map(|v| v.to_string()).collect();
    let outcome_staked_json = serde_json::to_value(&outcome_staked)
        .map_err(|e| AppError::Internal(anyhow::anyhow!("failed to serialize outcome_staked: {e}")))?;
    db::upsert_market_cache(
        &state.pool,
        &format!("{:#x}", detail.address),
        &format!("{:#x}", detail.creator),
        &detail.question,
        detail.outcome_count as i16,
        &detail.min_ais_to_enter.to_string(),
        u64::try_from(detail.resolve_deadline).unwrap_or(u64::MAX) as i64,
        detail.resolved,
        detail.winning_outcome as i16,
        &detail.total_staked.to_string(),
        &outcome_staked_json,
    )
    .await?;
    Ok(())
}

/// Re-enumerates `MarketFactory.allMarkets` and refreshes every market's cached row
/// when the last full sync is older than [`MARKETS_CACHE_STALENESS_SECS`] — see that
/// constant's doc comment. Re-enumerating (not just refreshing already-cached rows) is
/// what lets a market created after the last sync actually show up.
async fn refresh_markets_index_if_stale(state: &AppState) -> Result<(), AppError> {
    let sync = db::get_markets_index_sync(&state.pool).await?;
    let stale = match &sync {
        None => true,
        Some(s) => Utc::now().signed_duration_since(s.synced_at).num_seconds() > MARKETS_CACHE_STALENESS_SECS,
    };
    if !stale {
        return Ok(());
    }

    let addresses = state.chain.all_market_addresses().await?;
    let details = state.chain.read_markets(&addresses).await;
    for detail in &details {
        upsert_market_detail(state, detail).await?;
    }
    db::upsert_markets_index_sync(&state.pool, addresses.len() as i32, Utc::now()).await?;
    Ok(())
}

#[utoipa::path(
    get,
    path = "/v1/markets",
    responses((status = 200, description = "All known IntegrityMarket instances", body = Vec<MarketSummaryDto>)),
    tag = "markets",
)]
pub async fn list_markets(State(state): State<AppState>) -> Result<Json<Vec<MarketSummaryDto>>, AppError> {
    refresh_markets_index_if_stale(&state).await?;
    let rows = db::list_market_cache(&state.pool).await?;
    let dtos: Result<Vec<_>, _> = rows.into_iter().map(market_cache_row_to_dto).collect();
    Ok(Json(dtos?))
}

#[derive(Debug, Deserialize, ToSchema)]
pub struct MarketDetailQuery {
    /// A `SovereignAgent` address to look up a single, real `getPosition` read for —
    /// see `MarketDetailDto::your_position`.
    pub agent: Option<String>,
}

#[utoipa::path(
    get,
    path = "/v1/markets/{id}",
    params(
        ("id" = String, Path, description = "IntegrityMarket contract address"),
        ("agent" = Option<String>, Query, description = "SovereignAgent address to include a your_position read for"),
    ),
    responses(
        (status = 200, description = "Market detail", body = MarketDetailDto),
        (status = 400, description = "Invalid address / no readable IntegrityMarket at that address"),
    ),
    tag = "markets",
)]
pub async fn get_market(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<MarketDetailQuery>,
) -> Result<Json<MarketDetailDto>, AppError> {
    let market_addr = Address::from_str(&id).map_err(|e| AppError::BadRequest(format!("invalid market address '{id}': {e}")))?;
    let addr_key = format!("{:#x}", market_addr);

    let cached = db::get_market_cache(&state.pool, &addr_key).await?;
    let fresh = cached
        .as_ref()
        .map(|r| Utc::now().signed_duration_since(r.refreshed_at).num_seconds() <= MARKETS_CACHE_STALENESS_SECS)
        .unwrap_or(false);

    let row = if fresh {
        cached.expect("fresh implies Some")
    } else {
        let live = state
            .chain
            .read_market(market_addr)
            .await
            .map_err(|e| AppError::BadRequest(format!("no readable IntegrityMarket at {addr_key}: {e}")))?;
        upsert_market_detail(&state, &live).await?;
        db::get_market_cache(&state.pool, &addr_key).await?.expect("just upserted")
    };

    let your_position = match &query.agent {
        Some(agent_str) => {
            let agent_addr = Address::from_str(agent_str).map_err(|e| AppError::BadRequest(format!("invalid agent address: {e}")))?;
            let pos = state.chain.get_position(market_addr, agent_addr).await?;
            if pos.amount.is_zero() {
                None
            } else {
                Some(PositionDto {
                    amount: pos.amount.to_string(),
                    outcome_index: pos.outcome_index,
                    bcc_commitment_hash: format!("0x{}", hex::encode(pos.bcc_commitment_hash)),
                    claimed: pos.claimed,
                })
            }
        }
        None => None,
    };

    Ok(Json(MarketDetailDto {
        summary: market_cache_row_to_dto(row)?,
        your_position,
        positions_note: "Per-holder position enumeration requires indexing PositionEntered \
                          events, which this pass does not build; outcome_staked (the real \
                          pari-mutuel pool per outcome) and your_position (single-address \
                          getPosition read via ?agent=) are the real reads available today.",
    }))
}

// ---------------------------------------------------------------------------------
// GET /v1/leaderboard
// ---------------------------------------------------------------------------------

/// Cache-or-resolve helper for an agent's `AgentPrimitivesRow`, shared by the
/// leaderboard/wallet handlers below. `get_agent`'s own inline version (above) predates
/// this task and has slightly different fallback semantics (it also decides whether the
/// DID exists at all) — left untouched to avoid risking its already-covered behavior;
/// this is a smaller, best-effort variant: `Ok(None)` on any resolution failure rather
/// than a hard error, since callers here (leaderboard) want to skip-and-continue, not
/// fail the whole request over one agent's stale/unresolvable primitives.
async fn resolve_primitives_row(state: &AppState, agent_id: &str) -> Result<Option<db::AgentPrimitivesRow>, AppError> {
    if let Some(row) = db::get_agent_primitives(&state.pool, agent_id).await? {
        return Ok(Some(row));
    }
    match state.chain.resolve_primitives_by_did(agent_id).await {
        Ok(record) => {
            db::upsert_agent_primitives(
                &state.pool,
                agent_id,
                &format!("{:#x}", record.primitives.sovereign_agent),
                &format!("{:#x}", record.primitives.state_anchor),
                &format!("{:#x}", record.primitives.reputation_registry),
                &format!("{:#x}", record.primitives.slasher),
                &format!("{:#x}", record.primitives.verifier_registry),
                &format!("{:#x}", record.primitives.compliance_gate),
                &format!("{:#x}", record.primitives.agent_profile),
                &format!("{:#x}", record.controller),
                &record.domain_id.to_string(),
            )
            .await?;
            Ok(db::get_agent_primitives(&state.pool, agent_id).await?)
        }
        Err(_) => Ok(None),
    }
}

#[derive(Debug, Serialize, ToSchema)]
pub struct LeaderboardEntryDto {
    pub agent_id: String,
    pub sovereign_agent: String,
    /// Real `ReputationRegistry.effectiveScore` read (decimal string — see
    /// migrations/0002's header note on uint256 serialization), NOT the off-chain
    /// `scoring-core` AIS float `GET /v1/agent/{id}/ais` returns — the two are related
    /// but distinct numbers (the on-chain value is the last score this oracle itself
    /// pushed via `ReputationRegistry.updateScore`, possibly zk-boosted).
    pub effective_score: String,
    /// Realized P&L is NOT computed. It would require indexing `IntegrityMarket`
    /// `PositionEntered`/`MarketResolved`/`PayoutClaimed` events across every market —
    /// out of scope for this pass. `null`, always — never a fabricated number. See
    /// `docs/wiki/entities/integrity-oracle.md` for the documented follow-up.
    pub realized_pnl: Option<String>,
}

/// Refreshes every agent's cached leaderboard row when the last full sync is older than
/// [`MARKETS_CACHE_STALENESS_SECS`] (reused, not a separate constant — same tradeoff:
/// bounded worst-case staleness vs. an N-agent RPC fan-out on every unauthenticated hit,
/// see PRODUCTION_GAPS.md §2). Re-enumerates `agents` (not just already-cached rows) so
/// a newly-registered agent actually appears, mirroring
/// `refresh_markets_index_if_stale`'s exact pattern.
async fn refresh_leaderboard_if_stale(state: &AppState) -> Result<(), AppError> {
    let sync = db::get_leaderboard_sync(&state.pool).await?;
    let stale = match &sync {
        None => true,
        Some(s) => Utc::now().signed_duration_since(s.synced_at).num_seconds() > MARKETS_CACHE_STALENESS_SECS,
    };
    if !stale {
        return Ok(());
    }

    let agents = db::list_agents(&state.pool).await?;
    let agent_count = agents.len();

    let reads = agents.into_iter().map(|agent| {
        let state = state.clone();
        async move {
            let row = resolve_primitives_row(&state, &agent.id).await.ok().flatten()?;
            let sovereign_agent = Address::from_str(&row.sovereign_agent_address).ok()?;
            let reputation_registry = Address::from_str(&row.reputation_registry_address).ok()?;
            let score = state.chain.effective_score(reputation_registry, sovereign_agent).await.ok()?;
            Some((agent.id, row.sovereign_agent_address, score))
        }
    });
    let results: Vec<(String, String, alloy::primitives::U256)> = futures::future::join_all(reads).await.into_iter().flatten().collect();
    for (agent_id, sovereign_agent, score) in &results {
        db::upsert_leaderboard_cache(&state.pool, agent_id, sovereign_agent, &score.to_string()).await?;
    }
    db::upsert_leaderboard_sync(&state.pool, agent_count as i32, Utc::now()).await?;
    Ok(())
}

#[utoipa::path(
    get,
    path = "/v1/leaderboard",
    responses((status = 200, description = "Agents ranked by on-chain ReputationRegistry.effectiveScore", body = Vec<LeaderboardEntryDto>)),
    tag = "ais",
)]
pub async fn get_leaderboard(State(state): State<AppState>) -> Result<Json<Vec<LeaderboardEntryDto>>, AppError> {
    refresh_leaderboard_if_stale(&state).await?;
    let mut rows = db::list_leaderboard_cache(&state.pool).await?;
    // effective_score is a decimal-string uint256 — compare numerically via U256, not
    // lexicographically, or "9" would sort above "10".
    rows.sort_by(|a, b| {
        let sa = alloy::primitives::U256::from_str(&a.effective_score).unwrap_or_default();
        let sb = alloy::primitives::U256::from_str(&b.effective_score).unwrap_or_default();
        sb.cmp(&sa)
    });

    Ok(Json(
        rows.into_iter()
            .map(|row| LeaderboardEntryDto {
                agent_id: row.agent_id,
                sovereign_agent: row.sovereign_agent_address,
                effective_score: row.effective_score,
                realized_pnl: None,
            })
            .collect(),
    ))
}

// ---------------------------------------------------------------------------------
// GET /v1/agent/{id}/wallet
// ---------------------------------------------------------------------------------

#[derive(Debug, Serialize, ToSchema)]
pub struct WalletPositionDto {
    pub market_address: String,
    pub question: String,
    pub outcome_index: u8,
    pub amount: String,
    pub market_resolved: bool,
    /// `Some(bool)` only once the market has resolved; `None` while still open.
    pub won: Option<bool>,
}

#[derive(Debug, Serialize, ToSchema, Clone)]
pub struct TransactionDto {
    pub id: String,
    #[serde(rename = "type")]
    pub tx_type: String,
    pub asset: String,
    pub amount: String,
    pub usd: Option<String>,
    pub agent: String,
    pub status: String,
    pub time: String,
}

#[derive(Debug, Serialize, ToSchema, Clone)]
pub struct AllowanceDto {
    pub agent: String,
    pub limit: String,
    pub spent: f64,
    pub status: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct WalletResponse {
    pub agent_id: String,
    pub sovereign_agent: String,
    /// Real `IntegrityToken.balanceOf(sovereignAgent)` read, decimal string.
    pub itk_balance: String,
    /// Unclaimed positions (amount > 0, `claimed == false`) across every market in the
    /// markets cache, cross-referenced via a real `getPosition` read per market. Bounded
    /// by the current market count — fine at this scale, would want indexing if the
    /// market count grows into the hundreds+.
    pub open_positions: Vec<WalletPositionDto>,
    /// Transfer/stake/payout history requires indexing on-chain events (`Transfer`,
    /// `PositionEntered`, `PayoutClaimed`, ...), which this pass does not build. `null`,
    /// never a fabricated transaction list. See `docs/wiki/entities/integrity-oracle.md`.
    pub transaction_history: Option<Vec<TransactionDto>>,
    pub allowances: Option<Vec<AllowanceDto>>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/wallet",
    params(("id" = String, Path, description = "Agent DID")),
    responses(
        (status = 200, description = "$ITK balance + open market positions", body = WalletResponse),
        (status = 404, description = "Unknown DID"),
    ),
    tag = "wallet",
)]
pub async fn get_wallet(State(state): State<AppState>, Path(id): Path<String>) -> Result<Json<WalletResponse>, AppError> {
    let row = resolve_primitives_row(&state, &id).await?.ok_or_else(|| AppError::AgentNotFound(id.clone()))?;
    let sovereign_agent = Address::from_str(&row.sovereign_agent_address)
        .map_err(|e| AppError::Internal(anyhow::anyhow!("cached sovereign_agent_address is not a valid address: {e}")))?;

    let balance = state.chain.itk_balance_of(sovereign_agent).await?;

    refresh_markets_index_if_stale(&state).await?;
    let markets = db::list_market_cache(&state.pool).await?;

    let reads = markets.into_iter().map(|m| {
        let state = state.clone();
        async move {
            let market_addr = Address::from_str(&m.address).ok()?;
            let pos = state.chain.get_position(market_addr, sovereign_agent).await.ok()?;
            if pos.amount.is_zero() || pos.claimed {
                return None;
            }
            let dto = market_cache_row_to_dto(m).ok()?;
            Some(WalletPositionDto {
                market_address: dto.address,
                question: dto.question,
                outcome_index: pos.outcome_index,
                amount: pos.amount.to_string(),
                market_resolved: dto.resolved,
                won: dto.resolved.then_some(dto.winning_outcome == Some(pos.outcome_index)),
            })
        }
    });
    let open_positions: Vec<WalletPositionDto> = futures::future::join_all(reads).await.into_iter().flatten().collect();

    Ok(Json(WalletResponse {
        agent_id: id,
        sovereign_agent: row.sovereign_agent_address,
        itk_balance: balance.to_string(),
        open_positions,
        transaction_history: None,
        allowances: None,
    }))
}

#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
pub struct TelemetryEventDetailDto {
    pub id: Uuid,
    pub agent_id: String,
    pub nonce: i64,
    pub performance_variance: f64,
    pub hgi_raw: f64,
    pub gpu_hours_verified: f64,
    pub flagged: bool,
    pub zk_verified: bool,
    pub leaf_hash: String,
    pub payload: serde_json::Value,
    /// Always `null` today — see `db::fetch_pending_leaves`'s doc comment. Real Merkle
    /// anchoring for this event's leaf happens out-of-band, per-agent, in
    /// `bcc_middleware/app/anchor.py`, not via a root assigned back onto this row.
    pub merkle_root_id: Option<Uuid>,
    /// Always `null` today — see `merkle_root_id`'s doc comment.
    pub leaf_index: Option<i32>,
    pub created_at: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
pub struct AgentJudgeEvaluationDto {
    pub id: Uuid,
    pub agent_id: String,
    pub run_id: String,
    pub judge_model: String,
    pub verdict: String,
    pub score: Option<f64>,
    pub rationale_summary: Option<String>,
    pub telemetry_event_id: Option<Uuid>,
    pub created_at: String,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/telemetry",
    params(("id" = String, Path, description = "Agent DID")),
    responses(
        (status = 200, description = "List of telemetry events", body = Vec<TelemetryEventDetailDto>),
        (status = 404, description = "Agent not found"),
    ),
    tag = "agents",
)]
pub async fn get_telemetry_history(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Vec<TelemetryEventDetailDto>>, AppError> {
    let agent_row = db::get_agent(&state.pool, &id).await?;
    if agent_row.is_none() {
        return Err(AppError::AgentNotFound(id));
    }
    let events = db::get_recent_telemetry(&state.pool, &id, 50).await?;
    let dtos = events
        .into_iter()
        .map(|e| TelemetryEventDetailDto {
            id: e.id,
            agent_id: e.agent_id,
            nonce: e.nonce,
            performance_variance: e.performance_variance,
            hgi_raw: e.hgi_raw,
            gpu_hours_verified: e.gpu_hours_verified,
            flagged: e.flagged,
            zk_verified: e.zk_verified,
            leaf_hash: hex::encode(e.leaf_hash),
            payload: e.payload,
            merkle_root_id: e.merkle_root_id,
            leaf_index: e.leaf_index,
            created_at: e.created_at.to_rfc3339(),
        })
        .collect();
    Ok(Json(dtos))
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/traces",
    params(("id" = String, Path, description = "Agent DID")),
    responses(
        (status = 200, description = "List of judge evaluations/traces", body = Vec<AgentJudgeEvaluationDto>),
        (status = 404, description = "Agent not found"),
    ),
    tag = "agents",
)]
pub async fn get_traces(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Vec<AgentJudgeEvaluationDto>>, AppError> {
    let agent_row = db::get_agent(&state.pool, &id).await?;
    if agent_row.is_none() {
        return Err(AppError::AgentNotFound(id));
    }
    let evaluations = db::get_recent_evaluations(&state.pool, &id, 50).await?;
    let dtos = evaluations
        .into_iter()
        .map(|e| AgentJudgeEvaluationDto {
            id: e.id,
            agent_id: e.agent_id,
            run_id: e.run_id,
            judge_model: e.judge_model,
            verdict: e.verdict,
            score: e.score,
            rationale_summary: e.rationale_summary,
            telemetry_event_id: e.telemetry_event_id,
            created_at: e.created_at.to_rfc3339(),
        })
        .collect();
    Ok(Json(dtos))
}

// ---------------------------------------------------------------------------------
// audit_log: the real, durable event trail behind `/v1/audit-log` (dashboard's Audit
// Logs panel). `POST /v1/audit/ingest` is called by bcc_middleware (see
// `bcc_middleware/app/audit.py`) after every intercept decision — allow AND deny —
// which is what makes this a genuine source of truth rather than a re-hash of data
// that already had its own page (telemetry_events -> SDK Telemetry, otel_spans ->
// Trace Analytics). Deliberately unauthenticated, matching the OTLP receiver's
// existing posture (see otlp.rs) — this is a private-network service-to-service call
// in the current single-operator topology, not a public-facing endpoint; a forged
// entry here is a known, documented limitation (PRODUCTION_GAPS.md), not silently
// claimed to be tamper-proof.
// ---------------------------------------------------------------------------------

#[derive(Debug, Deserialize, ToSchema)]
pub struct AuditLogIngestRequest {
    pub agent_id: Option<String>,
    pub source: String,
    pub event_type: String,
    pub decision: String,
    pub reason_code: Option<String>,
    pub detail: Option<String>,
    pub intent_type: Option<String>,
    #[serde(default)]
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct AuditLogIngestResponse {
    pub id: Uuid,
}

#[utoipa::path(
    post,
    path = "/v1/audit/ingest",
    request_body = AuditLogIngestRequest,
    responses(
        (status = 200, description = "Audit event recorded", body = AuditLogIngestResponse),
    ),
    tag = "audit",
)]
pub async fn ingest_audit_log(
    State(state): State<AppState>,
    Json(req): Json<AuditLogIngestRequest>,
) -> Result<Json<AuditLogIngestResponse>, AppError> {
    let metadata = req.metadata.unwrap_or_else(|| serde_json::json!({}));
    let id = db::insert_audit_log(
        &state.pool,
        req.agent_id.as_deref(),
        &req.source,
        &req.event_type,
        &req.decision,
        req.reason_code.as_deref(),
        req.detail.as_deref(),
        req.intent_type.as_deref(),
        &metadata,
    )
    .await?;
    Ok(Json(AuditLogIngestResponse { id }))
}

// ---------------------------------------------------------------------------------
// Anchor-event ingest (docs/design/evidence-export.md, Lever 4). bcc_middleware
// posts here after it successfully anchors an agent's Merkle sub-tree on-chain, so
// each anchored ALLOW decision can be joined to its StateAnchor transaction at
// export time. Written to its own `anchor_events` table (NOT back-filled onto the
// audit_log row) specifically so it does not depend on the decision row having
// been committed first -- see the migration header for the write-ordering race
// that motivates the JOIN design. Same best-effort, single-operator-trust posture
// as /v1/audit/ingest (see that handler's note + PRODUCTION_GAPS.md).
// ---------------------------------------------------------------------------------

#[derive(Debug, Deserialize, ToSchema)]
pub struct AnchorEventIngestRequest {
    pub agent_id: String,
    /// 0x-prefixed keccak256 Merkle leaves that were committed in this anchor tx.
    pub leaves: Vec<String>,
    /// 0x-prefixed per-agent sub-tree root anchored on-chain.
    pub root: String,
    /// On-chain StateAnchor.anchorRoot transaction hash.
    pub tx_hash: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct AnchorEventIngestResponse {
    /// Rows inserted (leaves already recorded are skipped idempotently).
    pub recorded: u64,
}

#[utoipa::path(
    post,
    path = "/v1/audit/anchor",
    request_body = AnchorEventIngestRequest,
    responses(
        (status = 200, description = "Anchor events recorded", body = AnchorEventIngestResponse),
    ),
    tag = "audit",
)]
pub async fn ingest_anchor_events(
    State(state): State<AppState>,
    Json(req): Json<AnchorEventIngestRequest>,
) -> Result<Json<AnchorEventIngestResponse>, AppError> {
    let recorded =
        db::insert_anchor_events(&state.pool, &req.agent_id, &req.leaves, &req.root, &req.tx_hash)
            .await?;
    Ok(Json(AnchorEventIngestResponse { recorded }))
}

// Provenance: an agent's on-chain-anchored history (Class B, docs/design/
// dashboard-wiring.md). Reuses anchor_events + audit_log -- no chain call.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct ProvenanceEntryDto {
    pub id: String,
    pub agent_id: String,
    /// The committed intent type (the "action"), when the anchored leaf joins to
    /// an audit_log decision row.
    pub intent_type: Option<String>,
    /// 0x keccak Merkle leaf of the committed intent (the provenance input hash).
    pub leaf: String,
    /// 0x per-agent StateAnchor root the leaf was committed under.
    pub root: String,
    /// On-chain StateAnchor.anchorRoot transaction hash.
    pub tx_hash: String,
    /// The policy decision that produced the leaf (allow / shadow_deny / …), if joined.
    pub decision: Option<String>,
    pub anchored_at: String,
    pub created_at: Option<String>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/provenance",
    params(("id" = String, Path, description = "Agent DID")),
    responses(
        (status = 200, description = "The agent's on-chain-anchored provenance chain", body = Vec<ProvenanceEntryDto>),
    ),
    tag = "audit",
)]
pub async fn get_provenance(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Vec<ProvenanceEntryDto>>, AppError> {
    let rows = db::get_agent_provenance(&state.pool, &id, 100).await?;
    let entries = rows
        .into_iter()
        .map(|r| ProvenanceEntryDto {
            id: r.id.to_string(),
            agent_id: r.agent_id,
            intent_type: r.intent_type,
            leaf: r.leaf,
            root: r.root,
            tx_hash: r.tx_hash,
            decision: r.decision,
            anchored_at: r.anchored_at.to_rfc3339(),
            created_at: r.created_at.map(|t| t.to_rfc3339()),
        })
        .collect();
    Ok(Json(entries))
}

// Real on-chain stake (Class B, docs/design/dashboard-wiring.md). Reads the
// agent's own Slasher clone. U256 values are serialized as decimal strings (wei
// of $ITK) -- same convention as the market DTOs -- since they can exceed a
// JSON-safe integer.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct StakeDto {
    pub agent_id: String,
    pub total_stake: String,
    pub locked_stake: String,
    pub available_stake: String,
    /// Count of the agent's currently-open (unresolved) slashing disputes. The
    /// dashboard sums this across its agent loop for a real protocol-wide
    /// `active_disputes` with no extra fan-out (Slashers are per-agent clones with
    /// no singleton dispute index) — see docs/design/dashboard-wiring.md.
    pub open_disputes: u64,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/stake",
    params(("id" = String, Path, description = "Agent DID")),
    responses(
        (status = 200, description = "The agent's on-chain stake accounting", body = StakeDto),
    ),
    tag = "agent",
)]
pub async fn get_stake(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<StakeDto>, AppError> {
    // Resolve the agent's own Slasher clone + staker address live from the
    // registry (never guessed), then read its real stake accounting.
    let record = state.chain.resolve_primitives_by_did(&id).await?;
    let stake = state
        .chain
        .read_stake(record.primitives.slasher, record.primitives.sovereign_agent)
        .await?;
    Ok(Json(StakeDto {
        agent_id: id,
        total_stake: stake.total.to_string(),
        locked_stake: stake.locked.to_string(),
        available_stake: stake.available.to_string(),
        open_disputes: stake.open_disputes,
    }))
}

// Real capital position (Class B) aggregated from the A2ACapitalPool for the
// agent. U256 as decimal strings (wei of $ITK). `escrowed` is the agent's live
// available capital line; `released` has been disbursed.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct CreditDto {
    pub agent_id: String,
    pub total_allocated: String,
    pub escrowed: String,
    pub released: String,
    pub clawed_back: String,
    pub breached: String,
    pub allocation_count: u64,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/credit",
    params(("id" = String, Path, description = "Agent DID")),
    responses(
        (status = 200, description = "The agent's aggregated A2ACapitalPool position", body = CreditDto),
    ),
    tag = "agent",
)]
pub async fn get_credit(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<CreditDto>, AppError> {
    let pool = state
        .chain
        .a2a_capital_pool()
        .ok_or(crate::chain::ChainError::MissingSingleton("A2ACapitalPool"))?;
    let record = state.chain.resolve_primitives_by_did(&id).await?;
    let credit = state
        .chain
        .read_credit(pool, record.primitives.sovereign_agent)
        .await?;
    Ok(Json(CreditDto {
        agent_id: id,
        total_allocated: credit.total_allocated.to_string(),
        escrowed: credit.escrowed.to_string(),
        released: credit.released.to_string(),
        clawed_back: credit.clawed_back.to_string(),
        breached: credit.breached.to_string(),
        allocation_count: credit.allocation_count,
    }))
}

/// `MarketDetail` (live chain read) -> `MarketSummaryDto`, mirroring
/// `market_cache_row_to_dto`'s conventions (lowercase 0x-addresses, decimal-string
/// uint256s, `winning_outcome` only when resolved) so a market looks identical whether
/// it comes from the cache or a direct read.
fn market_detail_to_dto(detail: MarketDetail) -> Result<MarketSummaryDto, AppError> {
    let resolve_deadline = chrono::DateTime::<Utc>::from_timestamp(detail.resolve_deadline.to::<u64>() as i64, 0)
        .ok_or_else(|| AppError::Internal(anyhow::anyhow!("resolve_deadline out of range")))?;
    Ok(MarketSummaryDto {
        address: format!("{:#x}", detail.address),
        creator: format!("{:#x}", detail.creator),
        question: detail.question,
        outcome_count: detail.outcome_count,
        min_ais_to_enter: detail.min_ais_to_enter.to_string(),
        resolve_deadline,
        resolved: detail.resolved,
        winning_outcome: if detail.resolved { Some(detail.winning_outcome) } else { None },
        total_staked: detail.total_staked.to_string(),
        outcome_staked: detail.outcome_staked.iter().map(|v| v.to_string()).collect(),
    })
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/contracts",
    params(("id" = String, Path, description = "Agent DID")),
    responses((status = 200, description = "IntegrityMarket contracts this agent deployed and owns", body = Vec<MarketSummaryDto>)),
    tag = "markets",
)]
pub async fn get_agent_contracts(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Vec<MarketSummaryDto>>, AppError> {
    // Real "contracts an agent owns": the IntegrityMarket clones it deployed via
    // MarketFactory (marketsByCreator, keyed on the agent's SovereignAgent). Read live —
    // there's no per-agent cache table for this, and the set is small per agent.
    let record = state.chain.resolve_primitives_by_did(&id).await?;
    let addresses = state.chain.markets_by_creator(record.primitives.sovereign_agent).await?;
    let details = state.chain.read_markets(&addresses).await;
    let dtos: Result<Vec<_>, _> = details.into_iter().map(market_detail_to_dto).collect();
    Ok(Json(dtos?))
}

#[derive(Debug, Serialize, ToSchema)]
pub struct BaaDto {
    pub address: String,
    pub covered_entity: String,
    pub business_associate: String,
    pub agreement_hash: String,
    /// Decimal string, uint256 wei of $ITK (SmartBAA.requiredCollateral).
    pub required_collateral: String,
    /// SmartBAA.Status: Proposed | Active | Disputed | Terminated.
    pub status: String,
}

/// Issues a signed W3C Verifiable Credential (AgentIntegrityCredential) for the agent's
/// current AIS + verification tier. Real Ed25519 proof via the oracle's issuer key — see
/// `crate::vc`. Returned as a raw JSON-LD credential (no fixed ToSchema, so no utoipa doc).
pub async fn get_agent_vc(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<serde_json::Value>, AppError> {
    let ais = compute_ais_for_agent(&state, &id).await?;
    let tier = db::get_agent(&state.pool, &id)
        .await?
        .map(|a| a.verification_tier)
        .unwrap_or(0);
    Ok(Json(crate::vc::issue_vc(&id, ais.ais.round() as i64, tier)))
}

/// Network-wide model/provider stability benchmark (aggregated telemetry per model).
#[derive(Debug, Serialize, ToSchema)]
pub struct BenchmarkDto {
    pub model_name: String,
    pub provider_name: String,
    /// Simulated AIS on the 0-1000 scale from this model's stability + grounding.
    pub simulated_ais: i64,
    /// Behavioral stability in [0,1] = exp(-1.5 * avg_variance^2) (mirrors the entropy score).
    pub stability_metric: f64,
    /// Average grounding (HGI) in [0,1].
    pub grounding_metric: f64,
    pub sample_count: i64,
}

fn provider_for(model: &str) -> &'static str {
    let m = model.to_lowercase();
    if m.contains("claude") || m.contains("opus") || m.contains("sonnet") || m.contains("haiku") || m.contains("fable") {
        "Anthropic"
    } else if m.contains("gpt") || m.starts_with("o1") || m.starts_with("o3") {
        "OpenAI"
    } else if m.contains("gemini") {
        "Google"
    } else if m.contains("llama") {
        "Meta"
    } else if m.contains("mistral") {
        "Mistral"
    } else {
        "Unknown"
    }
}

#[utoipa::path(
    get,
    path = "/v1/benchmarks",
    responses((status = 200, description = "Model/provider stability benchmarks (network-wide telemetry aggregate)", body = Vec<BenchmarkDto>)),
    tag = "ais",
)]
pub async fn get_benchmarks(State(state): State<AppState>) -> Result<Json<Vec<BenchmarkDto>>, AppError> {
    let rows = db::benchmark_by_model(&state.pool).await?;
    let dtos = rows
        .into_iter()
        .map(|(model, avg_var, avg_ground, n)| {
            let stability = (-1.5 * avg_var * avg_var).exp().clamp(0.0, 1.0);
            let grounding = avg_ground.clamp(0.0, 1.0);
            BenchmarkDto {
                provider_name: provider_for(&model).to_string(),
                model_name: model,
                simulated_ais: ((stability * 500.0) + (grounding * 500.0)) as i64,
                stability_metric: stability,
                grounding_metric: grounding,
                sample_count: n,
            }
        })
        .collect();
    Ok(Json(dtos))
}

fn baa_status_str(s: u8) -> &'static str {
    match s {
        0 => "Proposed",
        1 => "Active",
        2 => "Disputed",
        3 => "Terminated",
        _ => "Unknown",
    }
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/baas",
    params(("id" = String, Path, description = "Agent DID")),
    responses((status = 200, description = "SmartBAA agreements where this agent is the business associate", body = Vec<BaaDto>)),
    tag = "shield",
)]
pub async fn get_agent_baas(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Vec<BaaDto>>, AppError> {
    let factory = state
        .chain
        .smart_baa_factory()
        .ok_or(crate::chain::ChainError::MissingSingleton("SmartBAAFactory"))?;
    let record = state.chain.resolve_primitives_by_did(&id).await?;
    let baas = state
        .chain
        .read_baas_for_agent(factory, record.primitives.sovereign_agent)
        .await?;
    let dtos = baas
        .into_iter()
        .map(|b| BaaDto {
            address: format!("{:#x}", b.address),
            covered_entity: format!("{:#x}", b.covered_entity),
            business_associate: format!("{:#x}", b.business_associate),
            agreement_hash: format!("{:#x}", b.agreement_hash),
            required_collateral: b.required_collateral.to_string(),
            status: baa_status_str(b.status).to_string(),
        })
        .collect();
    Ok(Json(dtos))
}

// ---- XNS (XibalbaNameService) read endpoints -------------------------------------------
// Handle→SovereignAgent and SovereignAgent→primary-handle resolution, read live from the
// deployed XibalbaNameService singleton. Returns 400 (MissingSingleton) until the contract is
// deployed and wired into deployments.*.json — an honest "not yet deployed", not a mock.

#[derive(Debug, Deserialize, utoipa::IntoParams)]
pub struct XnsResolveQuery {
    /// Human-readable handle to resolve (without a leading @), e.g. "atlas".
    pub handle: String,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct XnsResolveDto {
    pub handle: String,
    /// SovereignAgent address the handle points at, or null if unregistered.
    pub sovereign_agent: Option<String>,
    /// DID (did:integrity:<sovereign_agent>) when a reverse mapping exists in the oracle DB.
    pub did: Option<String>,
}

#[utoipa::path(
    get,
    path = "/v1/xns/resolve",
    params(XnsResolveQuery),
    responses((status = 200, description = "Resolve an XNS handle to its SovereignAgent", body = XnsResolveDto)),
    tag = "identity",
)]
pub async fn get_xns_resolve(
    State(state): State<AppState>,
    Query(q): Query<XnsResolveQuery>,
) -> Result<Json<XnsResolveDto>, AppError> {
    let xns = state
        .chain
        .xibalba_name_service()
        .ok_or(crate::chain::ChainError::MissingSingleton("XibalbaNameService"))?;
    let handle = q.handle.trim_start_matches('@').to_string();
    let addr = state.chain.resolve_handle(xns, &handle).await?;
    let sovereign_agent = if addr.is_zero() {
        None
    } else {
        Some(format!("{addr:#x}"))
    };
    // Reverse the SovereignAgent to a known DID via the oracle DB (best-effort).
    let did = match &sovereign_agent {
        Some(sa) => db::did_by_sovereign_agent(&state.pool, sa).await?,
        None => None,
    };
    Ok(Json(XnsResolveDto {
        handle,
        sovereign_agent,
        did,
    }))
}

#[derive(Debug, Serialize, ToSchema)]
pub struct AgentHandleDto {
    pub did: String,
    /// Primary handle registered for this agent's SovereignAgent, or null if none.
    pub handle: Option<String>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/handle",
    params(("id" = String, Path, description = "Agent DID")),
    responses((status = 200, description = "Primary XNS handle for the agent", body = AgentHandleDto)),
    tag = "identity",
)]
pub async fn get_agent_handle(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<AgentHandleDto>, AppError> {
    let xns = state
        .chain
        .xibalba_name_service()
        .ok_or(crate::chain::ChainError::MissingSingleton("XibalbaNameService"))?;
    let record = state.chain.resolve_primitives_by_did(&id).await?;
    let handle = state
        .chain
        .primary_handle(xns, record.primitives.sovereign_agent)
        .await?;
    let handle = if handle.is_empty() { None } else { Some(handle) };
    Ok(Json(AgentHandleDto { did: id, handle }))
}

// ---- Governance read endpoint ----------------------------------------------------------
// Live enumeration of IntegrityGovernance proposals. Returns 400 (MissingSingleton) until the
// contract is deployed and wired into deployments.*.json — an honest "governance not live yet",
// never a fabricated proposal list.

#[derive(Debug, Serialize, ToSchema)]
pub struct ProposalDto {
    pub id: u64,
    pub proposer: String,
    pub target: String,
    /// Decimal string, uint256 wei of native value the action would send (usually "0").
    pub value: String,
    pub start_time: u64,
    pub end_time: u64,
    /// Timelock ETA (unix seconds); 0 until queued.
    pub eta: u64,
    /// Decimal string, wei of ITK locked FOR.
    pub for_votes: String,
    /// Decimal string, wei of ITK locked AGAINST.
    pub against_votes: String,
    /// Active | Defeated | Succeeded | Queued | Executed | Expired | Canceled.
    pub state: String,
    pub description: String,
}

fn proposal_state_str(s: u8) -> &'static str {
    match s {
        0 => "Active",
        1 => "Defeated",
        2 => "Succeeded",
        3 => "Queued",
        4 => "Executed",
        5 => "Expired",
        6 => "Canceled",
        _ => "Unknown",
    }
}

#[utoipa::path(
    get,
    path = "/v1/governance/proposals",
    responses((status = 200, description = "IntegrityGovernance proposals (newest first)", body = Vec<ProposalDto>)),
    tag = "governance",
)]
pub async fn get_governance_proposals(
    State(state): State<AppState>,
) -> Result<Json<Vec<ProposalDto>>, AppError> {
    let gov = state
        .chain
        .integrity_governance()
        .ok_or(crate::chain::ChainError::MissingSingleton("IntegrityGovernance"))?;
    let proposals = state.chain.read_proposals(gov).await?;
    let dtos = proposals
        .into_iter()
        .map(|p| ProposalDto {
            id: p.id,
            proposer: format!("{:#x}", p.proposer),
            target: format!("{:#x}", p.target),
            value: p.value.to_string(),
            start_time: p.start_time,
            end_time: p.end_time,
            eta: p.eta,
            for_votes: p.for_votes.to_string(),
            against_votes: p.against_votes.to_string(),
            state: proposal_state_str(p.state).to_string(),
            description: p.description,
        })
        .collect();
    Ok(Json(dtos))
}

// Protocol-wide aggregates (Class B, docs/design/dashboard-wiring.md). Deliberately
// the *minimal supplement* to what the dashboard already derives client-side from its
// per-agent loop (`active_nodes`, `aggregate_ais`, `protocol_staked_itk`,
// `total_contracts`, and — summing StakeDto.open_disputes — `active_disputes`). This
// endpoint only sources the fields that need a singleton read the dashboard can't cheaply
// derive: marketplace volume (sum of cached market total_staked) and the A2ACapitalPool
// totals (one unfiltered scan of the singleton pool). `tvl` is composed client-side as
// protocol_staked_itk + escrowed_credit + total_marketplace_volume so there is exactly one
// source of truth for stake. All amounts are decimal-string wei of $ITK.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct StatsDto {
    /// Number of prediction markets in the cached index.
    pub market_count: u64,
    /// Sum of `total_staked` across every market (pari-mutuel volume).
    pub total_marketplace_volume: String,
    /// A2ACapitalPool: capital currently escrowed (live available lines) across all agents.
    pub escrowed_credit: String,
    /// A2ACapitalPool: capital disbursed ("borrowed") across all agents — the real
    /// `total_loans_volume`.
    pub released_credit: String,
    /// A2ACapitalPool: number of allocations scanned.
    pub allocation_count: u64,
}

#[utoipa::path(
    get,
    path = "/v1/stats",
    responses((status = 200, description = "Protocol-wide singleton aggregates (marketplace + capital pool)", body = StatsDto)),
    tag = "ais",
)]
pub async fn get_stats(State(state): State<AppState>) -> Result<Json<StatsDto>, AppError> {
    // Marketplace volume from the cached market index (refresh honoring the same
    // staleness window the market/leaderboard reads use — no per-hit fan-out).
    refresh_markets_index_if_stale(&state).await?;
    let markets = db::list_market_cache(&state.pool).await?;
    let market_count = markets.len() as u64;
    let total_marketplace_volume: alloy::primitives::U256 = markets
        .iter()
        .map(|m| alloy::primitives::U256::from_str(&m.total_staked).unwrap_or_default())
        .fold(alloy::primitives::U256::ZERO, |acc, v| acc + v);

    // A2ACapitalPool totals: one unfiltered scan of the singleton pool (not an
    // N-agent fan-out). If the market/capital layer isn't deployed on this network,
    // the pool contributes zeros rather than failing the whole endpoint.
    let pool_totals = match state.chain.a2a_capital_pool() {
        Some(pool) => state.chain.read_pool_totals(pool).await?,
        None => crate::chain::CreditInfo::default(),
    };

    Ok(Json(StatsDto {
        market_count,
        total_marketplace_volume: total_marketplace_volume.to_string(),
        escrowed_credit: pool_totals.escrowed.to_string(),
        released_credit: pool_totals.released.to_string(),
        allocation_count: pool_totals.allocation_count,
    }))
}

#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct AuditLogEntryDto {
    pub id: String,
    pub agent_id: Option<String>,
    pub source: String,
    pub event_type: String,
    pub decision: String,
    pub reason_code: Option<String>,
    pub detail: Option<String>,
    pub created_at: String,
    // Evidence-export linkage (docs/design/evidence-export.md): for an ALLOW
    // decision whose Merkle leaf has been anchored on-chain, these carry the
    // per-agent StateAnchor root + transaction that committed it (LEFT JOINed
    // from `anchor_events` on `metadata->>'leaf'`). Absent for un-anchored or
    // non-BCC rows. Omitted from JSON when null so existing consumers are
    // unaffected.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub anchor_root: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub anchor_tx_hash: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub anchored_at: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct AuditLogQuery {
    #[serde(default)]
    pub agent_id: Option<String>,
    #[serde(default)]
    pub limit: Option<i64>,
}

/// Merges three real event streams into one time-ordered feed -- the genuine
/// "everything logged" table a manual-debugging view needs, not just policy
/// decisions: `audit_log` (BCC intercept decisions -- the only source with an
/// explicit allow/deny verdict), `telemetry_events` (SDK-submitted telemetry,
/// surfaced as "flagged"/"recorded" so a compliance operator sees
/// signature-verified-but-suspicious submissions alongside policy denials),
/// and `otel_spans` (every real span, flat, `decision` repurposed as the
/// span's own real status_code). Merged in Rust rather than a single SQL
/// UNION because the three source tables don't share a column shape and
/// coercing them into one query would obscure more than it saves — see each
/// table's own migration for why they're separate to begin with. The
/// telemetry_events and otel_spans sides only mix in when `agent_id` is
/// given: neither table has an existing "recent across all agents" query
/// (both underlying db:: functions are always agent-scoped), so the global
/// feed (no agent_id) is audit_log only rather than paying for a new
/// unscoped scan just for this one aggregate view.
#[utoipa::path(
    get,
    path = "/v1/audit-log",
    params(
        ("agent_id" = Option<String>, Query, description = "Filter to one agent's DID; omit for the global feed"),
        ("limit" = Option<i64>, Query, description = "Max entries per source table before merging (default 100)"),
    ),
    responses(
        (status = 200, description = "Real, time-ordered log merging BCC decisions, SDK telemetry, and OTel spans", body = Vec<AuditLogEntryDto>),
    ),
    tag = "audit",
)]
pub async fn get_audit_log(
    State(state): State<AppState>,
    Query(query): Query<AuditLogQuery>,
) -> Result<Json<Vec<AuditLogEntryDto>>, AppError> {
    let limit = query.limit.unwrap_or(100).clamp(1, 500);
    let agent_id = query.agent_id.as_deref();

    let decisions = db::get_recent_audit_log(&state.pool, agent_id, limit).await?;
    let mut entries: Vec<AuditLogEntryDto> = decisions
        .into_iter()
        .map(|r| AuditLogEntryDto {
            id: r.id.to_string(),
            agent_id: r.agent_id,
            source: r.source,
            event_type: r.event_type,
            decision: r.decision,
            reason_code: r.reason_code,
            detail: r.detail,
            created_at: r.created_at.to_rfc3339(),
            anchor_root: r.anchor_root,
            anchor_tx_hash: r.anchor_tx_hash,
            anchored_at: r.anchored_at.map(|t| t.to_rfc3339()),
        })
        .collect();

    if let Some(aid) = agent_id {
        let telemetry = db::get_recent_telemetry(&state.pool, aid, limit).await?;
        entries.extend(telemetry.into_iter().map(|e| AuditLogEntryDto {
            id: e.id.to_string(),
            agent_id: Some(e.agent_id),
            source: "sdk_telemetry".to_string(),
            event_type: "telemetry_event".to_string(),
            decision: if e.flagged { "flagged".to_string() } else { "recorded".to_string() },
            reason_code: None,
            detail: Some(format!(
                "nonce={} performance_variance={:.3} hgi_raw={:.3} zk_verified={}",
                e.nonce, e.performance_variance, e.hgi_raw, e.zk_verified
            )),
            created_at: e.created_at.to_rfc3339(),
            anchor_root: None,
            anchor_tx_hash: None,
            anchored_at: None,
        }));

        // Third real source: OTel spans, flat (not trace-tree-grouped) --
        // makes this the genuine "everything logged for this agent" feed a
        // manual-debugging table needs, not just policy decisions and
        // telemetry submissions. `decision` here isn't an authorization
        // verdict (spans don't have one) -- it's the span's own real
        // `status_code` (STATUS_CODE_OK/ERROR/UNSET), which is the closest
        // real analog: did this unit of work report success or failure.
        let spans = db::get_recent_spans_flat(&state.pool, aid, limit).await?;
        entries.extend(spans.into_iter().map(|s| {
            let duration_ms = (s.end_time - s.start_time).num_milliseconds();
            AuditLogEntryDto {
                id: s.id.to_string(),
                agent_id: Some(s.agent_id),
                source: "otel_span".to_string(),
                event_type: s.name,
                decision: s.status_code,
                reason_code: s.parent_span_id,
                detail: Some(format!("trace_id={} duration_ms={}", s.trace_id, duration_ms)),
                created_at: s.created_at.to_rfc3339(),
                anchor_root: None,
                anchor_tx_hash: None,
                anchored_at: None,
            }
        }));
    }

    entries.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    entries.truncate(limit as usize);
    Ok(Json(entries))
}

// ---------------------------------------------------------------------------------
// Historical/bucketed endpoints (PRODUCTION_GAPS.md §1 items 2-3): AIS trend,
// telemetry volume, OTLP span volume — the Finance/Intelligence/SdkTelemetry pages'
// chart data source, backed by migration 0004's `time_bucket` queries.
// ---------------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
pub struct HistoryQuery {
    #[serde(default)]
    pub bucket: Option<String>,
    #[serde(default)]
    pub since: Option<chrono::DateTime<Utc>>,
}

/// Restricts the `bucket` query param to a fixed allowlist before it's bound into a
/// `time_bucket($1::interval, ...)` query. Binding (not string-formatting) already
/// rules out SQL injection, but the allowlist keeps the accepted values meaningful for
/// callers and gives a real 400 on typos rather than a confusing Postgres interval
/// parse error surfacing as a 500.
fn parse_bucket_interval(raw: Option<&str>) -> Result<&'static str, AppError> {
    Ok(match raw.unwrap_or("1h") {
        "5m" => "5 minutes",
        "15m" => "15 minutes",
        "1h" => "1 hour",
        "6h" => "6 hours",
        "1d" => "1 day",
        "1w" => "1 week",
        other => return Err(AppError::BadRequest(format!("unsupported bucket '{other}', expected one of: 5m, 15m, 1h, 6h, 1d, 1w"))),
    })
}

/// Default lookback window when `since` isn't given: 7 days, distinct from
/// `compute_ais_for_agent`'s 30-day (`AIS_REPORTING_PERIOD_DAYS`) scoring window — the
/// two are read for different purposes (a chart's default view vs. the score itself)
/// and don't need to share a constant.
// ---------------------------------------------------------------------------------
// GET /v1/agent/{id}/usage  +  /v1/agent/{id}/events  — vendor OTLP telemetry readback
// ---------------------------------------------------------------------------------

/// Token and cost rollup for an agent, from the OTLP metrics receiver (`otel_metrics`).
///
/// `tokens` is keyed by the emitter's token `type` attribute, so Claude Code yields
/// `input` / `output` / `cacheRead` / `cacheCreation` — the breakdown the signed telemetry
/// path cannot supply, since providers report cache and reasoning tokens only in their own
/// usage objects.
#[derive(Debug, Serialize, ToSchema)]
pub struct AgentUsageDto {
    pub agent_id: String,
    /// token type -> summed count over the window.
    pub tokens: std::collections::BTreeMap<String, f64>,
    pub total_tokens: f64,
    /// model -> summed reported cost in USD.
    pub cost_usd_by_model: std::collections::BTreeMap<String, f64>,
    pub total_cost_usd: f64,
    /// Always `"unsigned_vendor"`. This data arrives over the UNAUTHENTICATED OTLP port and
    /// carries no agent signature, so it is deliberately NOT an AIS input — it is reported
    /// here for observability and for cross-checking what an agent signs against what its
    /// runtime reports. Surfaced in the response so a consumer cannot mistake it for
    /// agent-attested evidence.
    pub evidence_tier: String,
    pub since: chrono::DateTime<Utc>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/usage",
    params(("id" = String, Path, description = "Agent DID")),
    responses((status = 200, description = "Token/cost rollup from vendor OTLP metrics", body = AgentUsageDto)),
    tag = "telemetry",
)]
pub async fn get_agent_usage(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<HistoryQuery>,
) -> Result<Json<AgentUsageDto>, AppError> {
    let since = query.since.unwrap_or_else(default_history_since);

    let tokens: std::collections::BTreeMap<String, f64> =
        db::agent_token_usage(&state.pool, &id, since).await?.into_iter().collect();
    let cost_usd_by_model: std::collections::BTreeMap<String, f64> =
        db::agent_cost_usage(&state.pool, &id, since).await?.into_iter().collect();

    Ok(Json(AgentUsageDto {
        agent_id: id,
        total_tokens: tokens.values().sum(),
        total_cost_usd: cost_usd_by_model.values().sum(),
        tokens,
        cost_usd_by_model,
        evidence_tier: crate::otlp::EVIDENCE_TIER_UNSIGNED_VENDOR.to_string(),
        since,
    }))
}

#[derive(Debug, Serialize, ToSchema)]
pub struct AgentEventDto {
    pub event_name: Option<String>,
    pub severity_text: Option<String>,
    pub body: Option<String>,
    pub attributes: serde_json::Value,
    pub trace_id: Option<String>,
    pub span_id: Option<String>,
    pub time: chrono::DateTime<Utc>,
    pub evidence_tier: String,
}

#[derive(Debug, Deserialize, ToSchema, utoipa::IntoParams)]
pub struct EventsQuery {
    #[serde(default)]
    pub limit: Option<i64>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/events",
    params(("id" = String, Path, description = "Agent DID")),
    responses((status = 200, description = "Recent structured events from vendor OTLP logs", body = Vec<AgentEventDto>)),
    tag = "telemetry",
)]
pub async fn get_agent_events(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<EventsQuery>,
) -> Result<Json<Vec<AgentEventDto>>, AppError> {
    // Clamped, not merely defaulted: an unbounded `limit` on a hypertable scan is a trivial
    // way to make this endpoint expensive from outside.
    let limit = query.limit.unwrap_or(100).clamp(1, 500);

    let rows = db::recent_otel_logs(&state.pool, &id, limit).await?;
    Ok(Json(
        rows.into_iter()
            .map(|r| AgentEventDto {
                event_name: r.event_name,
                severity_text: r.severity_text,
                body: r.body,
                attributes: r.attributes,
                trace_id: r.trace_id,
                span_id: r.span_id,
                time: r.time,
                evidence_tier: crate::otlp::EVIDENCE_TIER_UNSIGNED_VENDOR.to_string(),
            })
            .collect(),
    ))
}

fn default_history_since() -> chrono::DateTime<Utc> {
    Utc::now() - chrono::Duration::days(7)
}

#[derive(Debug, Serialize, ToSchema)]
pub struct AisHistoryPoint {
    pub bucket_start: chrono::DateTime<Utc>,
    pub ais: f64,
    pub entropy: f64,
    pub grounding: f64,
    pub sacrifice: f64,
    pub compliance: f64,
    pub zk_boost: f64,
    pub event_count: i64,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/ais/history",
    params(
        ("id" = String, Path, description = "Agent DID"),
        ("bucket" = Option<String>, Query, description = "One of: 5m, 15m, 1h, 6h, 1d, 1w (default 1h)"),
        ("since" = Option<String>, Query, description = "RFC3339 timestamp; default now - 7 days"),
    ),
    responses(
        (status = 200, description = "AIS trend, bucketed", body = Vec<AisHistoryPoint>),
        (status = 400, description = "Unsupported bucket value"),
        (status = 404, description = "Agent not found"),
    ),
    tag = "ais",
)]
pub async fn get_ais_history(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<HistoryQuery>,
) -> Result<Json<Vec<AisHistoryPoint>>, AppError> {
    if db::get_agent(&state.pool, &id).await?.is_none() {
        return Err(AppError::AgentNotFound(id));
    }

    let bucket = parse_bucket_interval(query.bucket.as_deref())?;
    let since = query.since.unwrap_or_else(default_history_since);

    let engine = scoring_core::AisEngine::new(state.config.ais_weights).map_err(|e| AppError::Internal(anyhow::anyhow!(e)))?;

    let buckets = db::ais_history_buckets(&state.pool, &id, bucket, since).await?;
    let points = buckets
        .into_iter()
        .map(|b| {
            let inputs = scoring_core::AisComponentInputs {
                performance_variance: b.avg_variance,
                hgi_raw: b.avg_hgi,
                gpu_hours_verified: b.sum_gpu_hours,
                penalty_ratio: b.penalty_ratio,
                zk_verified_this_period: b.zk_verified_this_period,
            };
            let breakdown = engine.score(&inputs);
            AisHistoryPoint {
                bucket_start: b.bucket_start,
                ais: breakdown.ais,
                entropy: breakdown.s_entropy,
                grounding: breakdown.s_grounding,
                sacrifice: breakdown.s_sacrifice,
                compliance: breakdown.s_compliance,
                zk_boost: breakdown.zk_boost,
                event_count: b.event_count,
            }
        })
        .collect();

    Ok(Json(points))
}

#[derive(Debug, Serialize, ToSchema)]
pub struct VolumeBucket {
    pub bucket_start: chrono::DateTime<Utc>,
    pub count: i64,
    pub flagged_count: i64,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/telemetry/volume",
    params(
        ("id" = String, Path, description = "Agent DID"),
        ("bucket" = Option<String>, Query, description = "One of: 5m, 15m, 1h, 6h, 1d, 1w (default 1h)"),
        ("since" = Option<String>, Query, description = "RFC3339 timestamp; default now - 7 days"),
    ),
    responses(
        (status = 200, description = "Signed telemetry ingest volume, bucketed", body = Vec<VolumeBucket>),
        (status = 400, description = "Unsupported bucket value"),
        (status = 404, description = "Agent not found"),
    ),
    tag = "telemetry",
)]
pub async fn get_telemetry_volume(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<HistoryQuery>,
) -> Result<Json<Vec<VolumeBucket>>, AppError> {
    if db::get_agent(&state.pool, &id).await?.is_none() {
        return Err(AppError::AgentNotFound(id));
    }

    let bucket = parse_bucket_interval(query.bucket.as_deref())?;
    let since = query.since.unwrap_or_else(default_history_since);

    let rows = db::telemetry_volume_buckets(&state.pool, &id, bucket, since).await?;
    let buckets = rows
        .into_iter()
        .map(|(bucket_start, count, flagged_count)| VolumeBucket {
            bucket_start,
            count,
            flagged_count,
        })
        .collect();

    Ok(Json(buckets))
}

#[derive(Debug, Serialize, ToSchema)]
pub struct OtelVolumeBucket {
    pub bucket_start: chrono::DateTime<Utc>,
    pub span_count: i64,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/otel/volume",
    params(
        ("id" = String, Path, description = "Agent DID"),
        ("bucket" = Option<String>, Query, description = "One of: 5m, 15m, 1h, 6h, 1d, 1w (default 1h)"),
        ("since" = Option<String>, Query, description = "RFC3339 timestamp; default now - 7 days"),
    ),
    responses(
        (status = 200, description = "Real OTLP span volume, bucketed. Unauthenticated data source (see otlp.rs) — no 404 on an unknown agent_id, since one was never required to exist.", body = Vec<OtelVolumeBucket>),
    ),
    tag = "telemetry",
)]
pub async fn get_otel_volume(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<HistoryQuery>,
) -> Result<Json<Vec<OtelVolumeBucket>>, AppError> {
    let bucket = parse_bucket_interval(query.bucket.as_deref())?;
    let since = query.since.unwrap_or_else(default_history_since);

    let rows = db::otel_volume_buckets(&state.pool, &id, bucket, since).await?;
    let buckets = rows.into_iter().map(|(bucket_start, span_count)| OtelVolumeBucket { bucket_start, span_count }).collect();

    Ok(Json(buckets))
}

#[derive(Debug, Serialize, ToSchema)]
pub struct RecentTraceDto {
    pub trace_id: String,
    pub name: String,
    pub start_time: String,
}

#[derive(Debug, Deserialize)]
pub struct LimitQuery {
    #[serde(default)]
    pub limit: Option<i64>,
}

#[utoipa::path(
    get,
    path = "/v1/agent/{id}/otel/traces",
    params(
        ("id" = String, Path, description = "Agent DID"),
        ("limit" = Option<i64>, Query, description = "Max traces to return (default 20)"),
    ),
    responses(
        (status = 200, description = "Recent trace_ids for this agent (one row per root span, most recent first) — the list-discovery endpoint `GET /v1/traces/{trace_id}` itself never provided.", body = Vec<RecentTraceDto>),
    ),
    tag = "telemetry",
)]
pub async fn get_recent_traces(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Query(query): Query<LimitQuery>,
) -> Result<Json<Vec<RecentTraceDto>>, AppError> {
    let limit = query.limit.unwrap_or(20).clamp(1, 200);
    let rows = db::get_recent_root_spans(&state.pool, &id, limit).await?;
    let dtos = rows
        .into_iter()
        .map(|r| RecentTraceDto {
            trace_id: r.trace_id,
            name: r.name,
            start_time: r.start_time.to_rfc3339(),
        })
        .collect();
    Ok(Json(dtos))
}

// ---------------------------------------------------------------------------------
// GET /v1/traces/{trace_id} — LangSmith-style nested run-tree view over the real
// OTLP spans in `otel_spans` (see `trace_tree.rs` for the tree-building logic).
// Top-level (not under /agent/{id}/) because a trace_id is a global identifier —
// matches real OTel/LangSmith semantics, not scoped to a single agent's routes.
// ---------------------------------------------------------------------------------

#[derive(Debug, Serialize, ToSchema)]
pub struct TraceTreeResponse {
    pub trace_id: String,
    pub span_count: usize,
    /// True if the deepest branch was cut off (see `trace_tree::MAX_TREE_DEPTH`) —
    /// an honest signal that this isn't the complete tree, never silently dropped.
    pub truncated: bool,
    pub roots: Vec<crate::trace_tree::SpanTreeNode>,
}

#[utoipa::path(
    get,
    path = "/v1/traces/{trace_id}",
    params(("trace_id" = String, Path, description = "OTLP trace ID (hex)")),
    responses(
        (status = 200, description = "Nested span tree for this trace", body = TraceTreeResponse),
        (status = 404, description = "No spans found for this trace_id — unauthenticated data source (see otlp.rs), so this just means nothing was ever ingested under that ID, not that access was denied"),
    ),
    tag = "telemetry",
)]
pub async fn get_trace_tree(State(state): State<AppState>, Path(trace_id): Path<String>) -> Result<Json<TraceTreeResponse>, AppError> {
    let spans = db::get_otel_spans_for_trace(&state.pool, &trace_id).await?;
    if spans.is_empty() {
        return Err(AppError::TraceNotFound(trace_id));
    }
    let span_count = spans.len();
    let result = crate::trace_tree::build_tree(spans);

    Ok(Json(TraceTreeResponse {
        trace_id,
        span_count,
        truncated: result.truncated,
        roots: result.roots,
    }))
}

