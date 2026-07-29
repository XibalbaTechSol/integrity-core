//! Crate root for the `backend` (a.k.a. `oracle-backend`) binary — the integrity-oracle's
//! HTTP/indexing layer (`docs/INTERFACE_CONTRACT.md` §6.6's "not yet built" note, now
//! built). This file's only job is module wiring + the `build_router`/`AppState`
//! plumbing shared between `main.rs` (real server) and `tests/` (in-process integration
//! tests against a real Postgres + real anvil) — no business logic lives here.

pub mod chain;
pub mod config;
pub mod crypto;
pub mod db;
pub mod derive;
pub mod error;
pub mod handlers;
pub mod merkle;
pub mod openapi;
pub mod vc;
pub mod otlp;
pub mod phi;
pub mod routes;
pub mod stream;
pub mod trace_tree;
pub mod zk;

use std::sync::Arc;

use redis::aio::ConnectionManager;
use sqlx::PgPool;
use tokio::sync::broadcast;

use crate::chain::ChainClient;
use crate::config::Config;
use crate::stream::StreamEvent;
use crate::zk::ZkVerifier;

/// Shared application state, handed to every handler via Axum's `State` extractor.
/// Everything here is cheap to clone (`Arc`/connection-pool internals), matching the
/// existing crate's convention (`ZkVerifier` is already `Clone` for the same reason).
/// `telemetry_tx` is a `broadcast::Sender`, itself cheap to clone (an `Arc` internally) —
/// see `stream.rs`'s doc comment for why an in-process channel, not Redis/Postgres pub-sub.
#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub redis: ConnectionManager,
    pub chain: ChainClient,
    pub zk: ZkVerifier,
    pub config: Arc<Config>,
    pub telemetry_tx: broadcast::Sender<StreamEvent>,
}

pub fn build_router(state: AppState) -> axum::Router {
    routes::router(state)
}
