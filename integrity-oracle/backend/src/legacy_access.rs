//! Caller evidence for routes scheduled for removal.
//!
//! Registration v3 PR 4.6 deletes the legacy `POST /v1/agent/register`. The owner's rule is
//! to WAIT until a traffic window shows no unknown callers. The Oracle had no usable access
//! log: `TraceLayer::new_for_http()` emits at DEBUG and the server filter defaults to `info`,
//! and Render keeps no request logs for this service. So this middleware writes one WARN line
//! per hit under the `legacy_route` target, BEFORE the body is parsed. A caller whose body
//! fails to deserialize never reaches the handler, but it is still a caller and would break
//! differently once the route is gone.
//!
//! Logged: method, path, final status, latency, `User-Agent`, and the first `X-Forwarded-For`
//! hop (Render's proxy sets it). The body is never logged here; the handler adds the DID and
//! handle once they've parsed.

use std::time::Instant;

use axum::extract::Request;
use axum::http::header::USER_AGENT;
use axum::middleware::Next;
use axum::response::Response;

/// Log target to search for in Render (`text: legacy_route`).
pub const TARGET: &str = "legacy_route";

/// Cap on logged header values, so a hostile client can't push oversized lines into the log.
const MAX_HEADER_LEN: usize = 200;

fn header_str(req: &Request, name: &str) -> String {
    req.headers()
        .get(name)
        .and_then(|v| v.to_str().ok())
        .map(|v| v.chars().take(MAX_HEADER_LEN).collect())
        .unwrap_or_else(|| "-".to_string())
}

pub async fn log_legacy_hit(req: Request, next: Next) -> Response {
    let started = Instant::now();
    let method = req.method().clone();
    let path = req.uri().path().to_string();
    let user_agent = header_str(&req, USER_AGENT.as_str());
    let client = header_str(&req, "x-forwarded-for").split(',').next().unwrap_or("-").trim().to_string();

    let response = next.run(req).await;

    tracing::warn!(
        target: TARGET,
        %method,
        path = %path,
        status = response.status().as_u16(),
        latency_ms = started.elapsed().as_millis() as u64,
        user_agent = %user_agent,
        client = %client,
        "legacy route hit"
    );
    response
}

#[cfg(test)]
mod tests {
    use std::io::Write;
    use std::sync::{Arc, Mutex};

    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use axum::routing::post;
    use axum::{Json, Router};
    use tower::ServiceExt;

    use super::*;

    #[derive(Clone, Default)]
    struct Buf(Arc<Mutex<Vec<u8>>>);
    impl Write for Buf {
        fn write(&mut self, b: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(b);
            Ok(b.len())
        }
        fn flush(&mut self) -> std::io::Result<()> {
            Ok(())
        }
    }

    #[derive(serde::Deserialize)]
    struct Body_ {
        #[allow(dead_code)]
        did: String,
    }

    fn app() -> Router {
        Router::new().route(
            "/v1/agent/register",
            post(|Json(_b): Json<Body_>| async { "ok" }).layer(axum::middleware::from_fn(log_legacy_hit)),
        )
    }

    async fn hit(body: &'static str) -> (StatusCode, String) {
        let buf = Buf::default();
        let writer = buf.clone();
        let subscriber = tracing_subscriber::fmt()
            .with_env_filter("info")
            .with_ansi(false)
            .with_writer(move || writer.clone())
            .finish();
        let _guard = tracing::subscriber::set_default(subscriber);
        let req = Request::post("/v1/agent/register")
            .header("content-type", "application/json")
            .header("user-agent", "legacy-probe/1.0")
            .header("x-forwarded-for", "203.0.113.7, 10.0.0.1")
            .body(Body::from(body))
            .unwrap();
        let status = app().oneshot(req).await.unwrap().status();
        let out = String::from_utf8(buf.0.lock().unwrap().clone()).unwrap();
        (status, out)
    }

    #[tokio::test(flavor = "current_thread")]
    async fn logs_a_successful_hit_at_the_default_info_filter() {
        let (status, out) = hit(r#"{"did":"did:integrity:x"}"#).await;
        assert_eq!(status, StatusCode::OK);
        assert!(out.contains("legacy_route"), "{out}");
        assert!(out.contains("status=200"), "{out}");
        assert!(out.contains("legacy-probe/1.0"), "{out}");
        assert!(out.contains("client=203.0.113.7"), "{out}");
        assert!(!out.contains("10.0.0.1"), "only the first forwarded hop is logged: {out}");
    }

    #[tokio::test(flavor = "current_thread")]
    async fn logs_a_caller_whose_body_never_reaches_the_handler() {
        let (status, out) = hit("not json").await;
        assert!(status.is_client_error(), "{status}");
        assert!(out.contains("legacy_route"), "a rejected caller is still a caller: {out}");
        assert!(out.contains(&format!("status={}", status.as_u16())), "{out}");
    }
}
