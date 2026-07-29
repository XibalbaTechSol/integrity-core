//! Binary entrypoint (`oracle-backend`, per `Cargo.toml`'s `[[bin]]`). Boots real
//! infrastructure connections (Postgres, Redis, an on-chain RPC client) and starts the
//! real Axum server — no mocked dependency has a code path here.

use std::sync::Arc;

use backend::chain::ChainClient;
use backend::config::Config;
use backend::otlp::{
    LogsServiceServer, MetricsServiceServer, OtlpLogsService, OtlpMetricsService, OtlpTraceService,
    TraceServiceServer,
};
use backend::stream::CHANNEL_CAPACITY;
use backend::zk::ZkVerifier;
use backend::{db, AppState};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();

    let config = Config::from_env().map_err(|e| anyhow::anyhow!(e))?;
    tracing::info!(bind_addr = %config.bind_addr, rpc_url = %config.rpc_url, "starting oracle-backend");

    let pool = db::create_pool(&config.database_url).await?;
    db::run_migrations(&pool).await?;
    tracing::info!("database migrations applied");

    let redis_client = redis::Client::open(config.redis_url.clone())?;
    let redis = redis::aio::ConnectionManager::new(redis_client).await?;
    tracing::info!("redis connected");

    let chain = ChainClient::connect(&config.rpc_url, &config.deployments_file).await?;
    tracing::info!(deployments_file = %config.deployments_file.display(), "chain client connected");

    let zk = ZkVerifier::new(
        config.zk_vk_paths.clone(),
        config.zk_verifier_target.clone(),
        config.bb_binary.clone(),
        config.zk_scratch_dir.clone(),
    );

    let bind_addr = config.bind_addr.clone();
    let otlp_grpc_addr = config.otlp_grpc_addr.clone();
    let (telemetry_tx, _) = tokio::sync::broadcast::channel(CHANNEL_CAPACITY);
    let state = AppState {
        pool,
        redis,
        chain,
        zk,
        config: Arc::new(config),
        telemetry_tx,
    };

    let app = backend::build_router(state.clone());

    let listener = tokio::net::TcpListener::bind(&bind_addr).await?;
    tracing::info!(bind_addr = %bind_addr, "listening");

    let otlp_addr: std::net::SocketAddr = otlp_grpc_addr.parse()?;
    tracing::info!(otlp_grpc_addr = %otlp_addr, "otlp grpc receiver listening");
    let otlp_server = tonic::transport::Server::builder()
        .add_service(TraceServiceServer::new(OtlpTraceService::new(state.clone())))
        .add_service(MetricsServiceServer::new(OtlpMetricsService::new(state.clone())))
        .add_service(LogsServiceServer::new(OtlpLogsService::new(state)))
        .serve_with_shutdown(otlp_addr, shutdown_signal());

    tokio::try_join!(
        async { axum::serve(listener, app).with_graceful_shutdown(shutdown_signal()).await.map_err(anyhow::Error::from) },
        async { otlp_server.await.map_err(anyhow::Error::from) },
    )?;

    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c().await.expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
    tracing::info!("shutdown signal received");
}
