//! Route table. Kept separate from `handlers.rs` (pure path -> handler wiring, no logic)
//! so the shape of the API surface is readable in one place.

use axum::routing::{get, post};
use axum::Router;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

use crate::handlers;
use crate::stream;
use crate::AppState;

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/v1/stream", get(stream::stream_events))
        .route("/v1/agent/{id}/stream", get(stream::stream_agent))
        .route("/v1/agent/register", post(handlers::register_agent))
        .route("/v1/agent/{id}", get(handlers::get_agent))
        .route("/v1/agents", get(handlers::list_agents))
        .route("/v1/agent/{id}/ais", get(handlers::get_ais))
        .route("/v1/agent/{id}/ais/history", get(handlers::get_ais_history))
        .route("/v1/agent/{id}/compliance", get(handlers::get_compliance))
        .route("/v1/agent/{id}/wallet", get(handlers::get_wallet))
        .route("/v1/agent/{id}/telemetry", get(handlers::get_telemetry_history))
        .route("/v1/agent/{id}/telemetry/volume", get(handlers::get_telemetry_volume))
        .route("/v1/agent/{id}/otel/volume", get(handlers::get_otel_volume))
        .route("/v1/agent/{id}/otel/traces", get(handlers::get_recent_traces))
        .route("/v1/agent/{id}/traces", get(handlers::get_traces))
        .route("/v1/traces/{trace_id}", get(handlers::get_trace_tree))
        .route("/v1/telemetry/ingest", post(handlers::ingest_telemetry))
        .route("/v1/audit/ingest", post(handlers::ingest_audit_log))
        .route("/v1/audit/anchor", post(handlers::ingest_anchor_events))
        .route("/v1/agent/{id}/provenance", get(handlers::get_provenance))
        .route("/v1/agent/{id}/stake", get(handlers::get_stake))
        .route("/v1/agent/{id}/credit", get(handlers::get_credit))
        .route("/v1/stats", get(handlers::get_stats))
        .route("/v1/audit-log", get(handlers::get_audit_log))
        .route("/v1/markets", get(handlers::list_markets))
        .route("/v1/markets/{id}", get(handlers::get_market))
        .route("/v1/leaderboard", get(handlers::get_leaderboard))
        .route("/healthz", get(|| async { "ok" }))
        .layer(TraceLayer::new_for_http())
        .layer(CorsLayer::permissive())
        .with_state(state)
}
