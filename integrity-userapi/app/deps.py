"""FastAPI dependency wiring: DB pool access, JWT bearer auth, and developer
API key auth.

Two credential types authenticate a request here, both resolving to the same
thing (a `user_id`): a JWT bearer token (`get_current_token` /
`get_current_user_id`, short-lived, issued at login/register, revocable via
`jti`) and a developer API key (`X-API-Key` header, long-lived, issued via
`POST /api-keys`, revocable via `api_keys.revoked_at`). `get_current_user_id`
is the single dependency nearly every route uses; it accepts either
credential so callers don't need two code paths per route.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, settings as default_settings
from app.security import DecodedToken, TokenError, decode_access_token, hash_api_key

_bearer_scheme = HTTPBearer(auto_error=False)


def get_settings() -> Settings:
    return default_settings


async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool


async def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(get_settings),
    pool: asyncpg.Pool = Depends(get_pool),
) -> DecodedToken:
    """Decodes + validates the bearer JWT: signature, expiry, not-revoked,
    and that the user it names still exists. Used directly by routes (like
    logout) that need the token's own `jti`, not just the user it names."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        decoded = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {exc}") from exc

    revoked = await pool.fetchrow("SELECT 1 FROM revoked_tokens WHERE jti = $1", UUID(decoded.jti))
    if revoked is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token has been revoked")

    row = await pool.fetchrow("SELECT id FROM users WHERE id = $1", decoded.user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user no longer exists")
    return decoded


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
    pool: asyncpg.Pool = Depends(get_pool),
) -> str:
    if credentials is not None:
        decoded = await get_current_token(credentials, settings, pool)
        return decoded.user_id

    if api_key is not None:
        row = await pool.fetchrow(
            "SELECT user_id FROM api_keys WHERE key_hash = $1 AND revoked_at IS NULL",
            hash_api_key(api_key),
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or revoked api key")
        return str(row["user_id"])

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token or api key")
