//! Central error type for the HTTP layer. Every handler returns `Result<_, AppError>`
//! so error-to-status-code mapping happens in exactly one place, and so that
//! internal error detail (SQL errors, subprocess stderr, etc.) is logged
//! server-side but never leaked to the client — only the old prototype's mocks
//! had the luxury of never producing real errors to worry about.

use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("agent not found: {0}")]
    AgentNotFound(String),
    #[error("no spans found for trace_id: {0}")]
    TraceNotFound(String),
    #[error("agent already registered: {0}")]
    AgentAlreadyExists(String),
    #[error("invalid request: {0}")]
    BadRequest(String),
    #[error("signature verification failed")]
    Unauthorized,
    #[error("nonce {submitted} is not greater than last seen nonce {last_seen} for agent {agent_id} (possible replay)")]
    NonceReplay {
        agent_id: String,
        submitted: i64,
        last_seen: i64,
    },
    #[error("rate limit exceeded, try again shortly")]
    RateLimited,
    #[error(transparent)]
    Verify(#[from] crate::crypto::VerifyError),
    #[error(transparent)]
    Zk(#[from] crate::zk::ZkVerifyError),
    #[error(transparent)]
    Database(#[from] sqlx::Error),
    #[error(transparent)]
    Redis(#[from] redis::RedisError),
    #[error("on-chain claim mismatch: {0}")]
    ChainMismatch(String),
    /// Spec v0.3 §7.1: registration requires the agent's own `StateAnchor.latestRoot` to be
    /// non-zero — an agent with no anchored genesis memory root is not a continuing
    /// economic subject (§4.1), so it is not registerable. A client-fixable precondition
    /// (anchor a genesis root, then retry), hence 400 — the same class as `ChainMismatch`
    /// and `MissingSingleton`, not a server or chain failure.
    #[error("memory not initialized: {0}")]
    MemoryNotInitialized(String),
    #[error(transparent)]
    Chain(#[from] crate::chain::ChainError),
    /// Defense-in-depth PHI/PII/secret backstop rejection on `POST /v1/telemetry/ingest`
    /// (see `crate::phi`) — the categories found are surfaced (not the raw matched
    /// content, which would defeat the point) so the caller can tell what tripped it.
    #[error("payload rejected: possible unredacted PHI/PII/secret detected (categories: {0:?})")]
    PhiDetected(Vec<String>),
    /// `otel_spans` failed schema_version >= 3 structural validation
    /// (`crate::span_schema::validate_batch`) — a client-fixable shape problem,
    /// same class as `BadRequest`, kept distinct so callers can distinguish "your
    /// JSON doesn't parse" from "your JSON parses but violates the v3 span schema".
    #[error("otel_spans schema violation: {0}")]
    SpanSchemaViolation(#[from] crate::span_schema::SchemaViolation),
    #[error(transparent)]
    Internal(#[from] anyhow::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, public_message) = match &self {
            AppError::AgentNotFound(_) => (StatusCode::NOT_FOUND, self.to_string()),
            AppError::TraceNotFound(_) => (StatusCode::NOT_FOUND, self.to_string()),
            AppError::AgentAlreadyExists(_) => (StatusCode::CONFLICT, self.to_string()),
            AppError::BadRequest(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, self.to_string()),
            AppError::NonceReplay { .. } => (StatusCode::CONFLICT, self.to_string()),
            AppError::RateLimited => (StatusCode::TOO_MANY_REQUESTS, self.to_string()),
            AppError::Verify(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::Zk(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::ChainMismatch(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::MemoryNotInitialized(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::PhiDetected(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::SpanSchemaViolation(_) => (StatusCode::BAD_REQUEST, self.to_string()),
            // An on-chain lookup that legitimately found nothing (unregistered DID/address)
            // is a 404, not a 502 — the chain answered fine, there's just no record.
            AppError::Chain(crate::chain::ChainError::UnknownDid(_))
            | AppError::Chain(crate::chain::ChainError::UnknownAgent(_)) => {
                (StatusCode::NOT_FOUND, self.to_string())
            }
            // Missing MarketFactory/IntegrityToken singleton is a deployment-shape fact,
            // not a transient RPC failure — 400, not 502.
            AppError::Chain(crate::chain::ChainError::MissingSingleton(_)) => (StatusCode::BAD_REQUEST, self.to_string()),
            AppError::Chain(_) => (StatusCode::BAD_GATEWAY, "on-chain read failed".to_string()),
            // DB/Redis/internal errors: never echo internals (connection strings,
            // query text, subprocess paths) to the client.
            AppError::Database(_) | AppError::Redis(_) | AppError::Internal(_) => {
                (StatusCode::INTERNAL_SERVER_ERROR, "internal server error".to_string())
            }
        };

        // Log at a severity that matches the status code: a 4xx is the client's
        // fault (bad input, unknown DID, rate limit) and expected in normal
        // operation, so ERROR is reserved for what the status itself already
        // says is a server-side fault (5xx) — a routine 404 should not read
        // like an outage in the logs (E12).
        if status.is_server_error() {
            tracing::error!(error = %self, "request failed");
        } else {
            tracing::warn!(error = %self, "request failed");
        }

        (status, Json(json!({ "error": public_message }))).into_response()
    }
}
