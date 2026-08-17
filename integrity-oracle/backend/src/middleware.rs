use axum::{
    extract::{Request, State},
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use crate::AppState;

pub async fn auth_middleware(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    if let Some(expected_key) = &state.config.oracle_api_key {
        let auth_header = req.headers().get("Authorization");
        let is_valid = match auth_header {
            Some(header_value) => {
                if let Ok(value_str) = header_value.to_str() {
                    value_str == expected_key || value_str == format!("Bearer {}", expected_key)
                } else {
                    false
                }
            }
            None => false,
        };

        if !is_valid {
            return Err(StatusCode::UNAUTHORIZED);
        }
    }
    Ok(next.run(req).await)
}

pub async fn global_rate_limit(
    State(state): State<AppState>,
    req: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    // For global rate limit we can use IP or a generic bucket
    // ...
    Ok(next.run(req).await)
}
