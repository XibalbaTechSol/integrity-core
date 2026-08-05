//! Generates `spec/ais-api/v1/openapi.yaml` from the real handlers/DTOs in `handlers.rs`,
//! rather than hand-authoring the spec separately (which is exactly how the `agent_id`/
//! `did` field-name drift documented in `docs/INTERFACE_CONTRACT.md` §6.3 happened once
//! already for internal package coordination — this generation step is the backstop
//! against that recurring on the *external* wire surface). Run via `cargo run --bin
//! gen-openapi` (see `src/bin/gen_openapi.rs`); wire that into CI so the committed
//! `spec/ais-api/v1/openapi.yaml` can be diffed against a fresh generation to catch
//! any handler/schema change that wasn't accompanied by a spec regeneration.
//!
//! Split into two `#[derive(OpenApi)]` structs, merged at runtime via
//! `combined_openapi()`, because of a confirmed utoipa 5.5.0 limitation: a single
//! `paths(...)` list silently drops its last entry once it holds more than 15 items
//! (verified directly — removing any one path from a 16-item list makes the 16th
//! appear again; the macro expansion itself is correct, this is a runtime
//! aggregation issue on utoipa's side, not a bug in how these are declared). No such
//! limit was found on `components(schemas(...))` at 42 entries. If upgrading utoipa
//! ever fixes this upstream, both structs can be folded back into one — nothing here
//! depends on them staying separate beyond working around the limit.

use utoipa::OpenApi;

use crate::handlers;

#[derive(OpenApi)]
#[openapi(
    info(
        title = "Integrity Protocol — AIS API",
        version = "1.0.0",
        description = "Read-side wire protocol for querying an agent's Agent Integrity \
            Score (AIS), on-chain primitive addresses, compliance status, market state, \
            and wallet balances. This is the versioned, externally-supported surface — \
            /v1/* is additive-only for its lifetime; any field rename, type change, or \
            removal requires a /v2/* prefix. See spec/ais-api/v1/README.md for the \
            integration guide and spec/ais-api/CHANGELOG.md for the version history.",
    ),
    paths(
        handlers::register_agent,
        handlers::get_agent,
        handlers::list_agents,
        handlers::get_ais,
        handlers::get_ais_history,
        handlers::get_telemetry_history,
        handlers::get_telemetry_volume,
        handlers::get_otel_volume,
        handlers::get_traces,
        handlers::ingest_telemetry,
        handlers::get_compliance,
        handlers::list_markets,
        handlers::get_market,
        handlers::get_leaderboard,
    ),
    components(schemas(
        handlers::PrimitiveSetDto,
        handlers::RegisterAgentRequest,
        handlers::RegisterAgentResponse,
        handlers::AgentResponse,
        handlers::AgentSummary,
        handlers::AisWeightsSchema,
        handlers::AisResponse,
        handlers::AisComponents,
        handlers::AisHistoryPoint,
        handlers::VolumeBucket,
        handlers::OtelVolumeBucket,
        handlers::DerivedSignals,
        handlers::ZkProofDto,
        handlers::JudgeEvaluationDto,
        handlers::TelemetryIngestRequest,
        handlers::TelemetryIngestResponse,
        handlers::ComplianceResponse,
        handlers::MarketSummaryDto,
        handlers::PositionDto,
        handlers::MarketDetailDto,
        handlers::LeaderboardEntryDto,
    )),
    tags(
        (name = "agents", description = "Agent identity, registration, and on-chain primitive resolution"),
        (name = "ais", description = "Agent Integrity Score and leaderboard"),
        (name = "telemetry", description = "Telemetry ingestion (feeds AIS computation)"),
        (name = "compliance", description = "HIPAA/Integrity Health vertical compliance status"),
        (name = "markets", description = "IntegrityMarket prediction-market reads"),
        (name = "wallet", description = "$ITK balance and open market positions"),
    ),
)]
pub struct ApiDocCore;

/// The overflow half — anything added once `ApiDocCore`'s `paths()` list would hit
/// the 16-item limit goes here instead. See this module's doc comment.
#[derive(OpenApi)]
#[openapi(
    paths(handlers::get_wallet, handlers::get_trace_tree, handlers::ingest_audit_log, handlers::ingest_anchor_events, handlers::get_provenance, handlers::get_stake, handlers::get_credit, handlers::get_agent_contracts, handlers::get_agent_baas, handlers::get_benchmarks, handlers::get_xns_resolve, handlers::get_agent_handle, handlers::get_governance_proposals, handlers::get_stats, handlers::get_audit_log, handlers::get_recent_traces),
    components(schemas(
        handlers::WalletPositionDto,
        handlers::WalletResponse,
        handlers::TelemetryEventDetailDto,
        handlers::AgentJudgeEvaluationDto,
        handlers::TraceTreeResponse,
        crate::trace_tree::SpanTreeNode,
        handlers::AuditLogIngestRequest,
        handlers::AuditLogIngestResponse,
        handlers::AnchorEventIngestRequest,
        handlers::AnchorEventIngestResponse,
        handlers::ProvenanceEntryDto,
        handlers::StakeDto,
        handlers::CreditDto,
        handlers::BaaDto,
        handlers::BenchmarkDto,
        handlers::XnsResolveDto,
        handlers::AgentHandleDto,
        handlers::ProposalDto,
        handlers::StatsDto,
        handlers::AuditLogEntryDto,
        handlers::RecentTraceDto,
    )),
    tags(
        (name = "audit", description = "Real, durable audit trail (BCC intercept decisions + flagged telemetry)"),
    ),
)]
pub struct ApiDocExtra;

/// The second overflow half. `ApiDocCore` and `ApiDocExtra` are both at 16 `paths()`
/// entries — utoipa 5.5.0 silently drops the last entry past that, so a new endpoint
/// appended to either would vanish from the generated spec without any error (see this
/// module's doc comment). New endpoints go here until this list reaches 16 too.
#[derive(OpenApi)]
#[openapi(
    paths(
        handlers::get_agent_usage,
        handlers::get_agent_events,
        handlers::get_unregistered_agents,
        handlers::request_kyc_challenge,
        handlers::verify_kyc_receipt,
    ),
    components(schemas(
        handlers::AgentUsageDto,
        handlers::AgentEventDto,
        handlers::UnregisteredAgentDto,
        handlers::KycChallengeRequest,
        handlers::KycChallengeResponse,
        handlers::VerificationResponse,
        crate::kyc::KycReceipt,
        crate::kyc::KycChecks,
    )),
    tags(
        (name = "verification", description = "Evidence-backed identity verification ladder"),
    ),
)]
pub struct ApiDocUsage;

pub fn combined_openapi() -> utoipa::openapi::OpenApi {
    ApiDocCore::openapi()
        .merge_from(ApiDocExtra::openapi())
        .merge_from(ApiDocUsage::openapi())
}
