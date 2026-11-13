//! Fixed-window rate limiting that never takes the Oracle down with it.
//!
//! Redis was a hard start-up dependency used for exactly one thing: the per-minute
//! counters behind `check_telemetry_rate_limit`, `check_internal_api_rate_limit` and
//! `check_otlp_rate_limit`. When the Render Key Value instance was suspended (2026-11-07)
//! the Oracle could not start at all -- `ConnectionManager::new` retried for minutes,
//! failed, and the service restart-looped, taking every endpoint down to protect a
//! throttle.
//!
//! The throttle still matters: the OTLP receiver is unauthenticated, and each span costs
//! a PHI scan and a Postgres insert. So "no Redis" must not mean "no limit" (fail open)
//! and must not mean "every request 500s" (fail closed). It means an in-process counter
//! with the same key and window shape. On one instance -- the Render deployment -- that
//! is the same limit; with several instances each one enforces it separately, which
//! loosens the global budget by the instance count. A warning is logged once each way.
//!
//! A Redis error at request time also falls back to the local counter for that request.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use redis::aio::ConnectionManager;

/// Local entries above this many trigger a sweep of every stale window.
const LOCAL_SWEEP_THRESHOLD: usize = 10_000;

#[derive(Clone)]
pub struct RateLimiter {
    redis: Option<ConnectionManager>,
    // key -> (window, count). Only the current window per key is kept.
    local: Arc<Mutex<HashMap<String, (i64, i64)>>>,
    warned_fallback: Arc<AtomicBool>,
}

impl RateLimiter {
    /// Per-process counters only (no `REDIS_URL`, or Redis unreachable at start-up).
    pub fn local_only() -> Self {
        Self { redis: None, local: Arc::default(), warned_fallback: Arc::default() }
    }

    /// Shared counters in Redis, with the local counter as the per-request fallback.
    pub fn with_redis(redis: ConnectionManager) -> Self {
        Self { redis: Some(redis), local: Arc::default(), warned_fallback: Arc::default() }
    }

    pub fn is_shared(&self) -> bool {
        self.redis.is_some()
    }

    /// Count one hit against `key` in fixed window `window` and return the window's count,
    /// this hit included. Never fails.
    pub async fn hit(&self, key: &str, window: i64) -> i64 {
        if let Some(redis) = &self.redis {
            match Self::redis_hit(redis.clone(), key, window).await {
                Ok(count) => return count,
                Err(error) => {
                    if !self.warned_fallback.swap(true, Ordering::Relaxed) {
                        tracing::warn!(%error, "redis rate limiter failed; counting in-process until it recovers");
                    }
                }
            }
        }
        self.local_hit(key, window)
    }

    async fn redis_hit(mut conn: ConnectionManager, key: &str, window: i64) -> redis::RedisResult<i64> {
        use redis::AsyncCommands;
        let full_key = format!("{key}:{window}");
        let count: i64 = conn.incr(&full_key, 1).await?;
        if count == 1 {
            let _: () = conn.expire(&full_key, 60).await?;
        }
        Ok(count)
    }

    fn local_hit(&self, key: &str, window: i64) -> i64 {
        // A poisoned lock only means another request panicked mid-update; the counts are
        // still usable, and refusing to count would turn the limiter off.
        let mut map = self.local.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        if map.len() > LOCAL_SWEEP_THRESHOLD {
            map.retain(|_, (stored_window, _)| *stored_window >= window);
        }
        let entry = map.entry(key.to_owned()).or_insert((window, 0));
        if entry.0 != window {
            *entry = (window, 0);
        }
        entry.1 += 1;
        entry.1
    }
}

/// Connect to Redis, bounded by `timeout`. `None` (with a logged reason) when it cannot be
/// reached -- the caller then runs on the local limiter instead of refusing to start.
pub async fn connect_redis(url: &str, timeout: std::time::Duration) -> Option<ConnectionManager> {
    let client = match redis::Client::open(url) {
        Ok(client) => client,
        Err(error) => {
            tracing::warn!(%error, "REDIS_URL is invalid; rate limits are per-process");
            return None;
        }
    };
    match tokio::time::timeout(timeout, ConnectionManager::new(client)).await {
        Ok(Ok(manager)) => Some(manager),
        Ok(Err(error)) => {
            tracing::warn!(%error, "redis unreachable at start-up; rate limits are per-process");
            None
        }
        Err(_) => {
            tracing::warn!(?timeout, "redis did not answer at start-up; rate limits are per-process");
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn local_counts_accumulate_within_a_window() {
        let limiter = RateLimiter::local_only();
        assert_eq!(limiter.hit("ratelimit:telemetry:a", 7).await, 1);
        assert_eq!(limiter.hit("ratelimit:telemetry:a", 7).await, 2);
        assert_eq!(limiter.hit("ratelimit:telemetry:a", 7).await, 3);
    }

    #[tokio::test]
    async fn local_counts_are_per_key() {
        let limiter = RateLimiter::local_only();
        limiter.hit("ratelimit:telemetry:a", 7).await;
        limiter.hit("ratelimit:telemetry:a", 7).await;
        assert_eq!(limiter.hit("ratelimit:telemetry:b", 7).await, 1);
    }

    #[tokio::test]
    async fn a_new_window_starts_from_one() {
        let limiter = RateLimiter::local_only();
        limiter.hit("k", 7).await;
        limiter.hit("k", 7).await;
        assert_eq!(limiter.hit("k", 8).await, 1);
    }

    #[tokio::test]
    async fn clones_share_one_budget() {
        // AppState is cloned per request; a per-clone counter would never limit anything.
        let limiter = RateLimiter::local_only();
        let other = limiter.clone();
        limiter.hit("k", 1).await;
        assert_eq!(other.hit("k", 1).await, 2);
    }

    #[tokio::test]
    async fn stale_windows_are_swept_once_the_map_is_large() {
        let limiter = RateLimiter::local_only();
        for i in 0..=LOCAL_SWEEP_THRESHOLD {
            limiter.hit(&format!("old:{i}"), 1).await;
        }
        limiter.hit("fresh", 2).await;
        let map = limiter.local.lock().unwrap();
        assert_eq!(map.len(), 1, "only the current-window key survives the sweep");
    }

    #[tokio::test]
    async fn unreachable_redis_yields_none_within_the_timeout_instead_of_blocking_start_up() {
        // Port 1 on loopback refuses connections; the call must return, not retry forever.
        let started = std::time::Instant::now();
        let manager = connect_redis("redis://127.0.0.1:1", std::time::Duration::from_secs(3)).await;
        assert!(manager.is_none());
        assert!(started.elapsed() < std::time::Duration::from_secs(10));
    }

    #[tokio::test]
    async fn an_invalid_url_yields_none() {
        assert!(connect_redis("not a url", std::time::Duration::from_secs(1)).await.is_none());
    }
}
