"""
integrity-userapi -- user accounts, developer API keys, agent ownership
pointers, and per-user demo run history for the Integrity Protocol.

Hard boundary (see README.md): this service NEVER calls a smart contract or
a chain RPC directly. The only outbound integration is `app/oracle_client.py`,
a plain HTTP client that fans out to integrity-oracle for anything
protocol/agent-related. Nothing here imports web3/alloy, and `user_agents`
stores only a DID pointer, never a cache of full agent state.
"""

from __future__ import annotations

import asyncio
import secrets

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
import subprocess
import os

from app import db, oracle_client
from app.config import Settings, settings as default_settings
from app.deps import get_current_token, get_current_user_id, get_pool, get_settings
from app.login_limiter import LoginRateLimiter
from app.schemas import (
    AddAgentRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    DemoRunResponse,
    DemoRunUpdateRequest,
    LoginRequest,
    OwnedAgentResponse,
    RegisterRequest,
    TokenResponse,
    TransferRequest,
    TransferResponse,
    UserResponse,
    WalletResponse,
)
from app.security import (
    DecodedToken,
    create_access_token,
    generate_api_key,
    hash_password,
    verify_password,
)
from app.security import (
    create_access_token,
    generate_api_key,
    hash_password,
    verify_password,
)

app = FastAPI(title="integrity-userapi", version="0.1.0")

# integrity-dashboard (the browser dashboard, task #21) is a cross-origin caller by
# construction -- it's served by Vite on its own port (5173 dev / 5190 e2e),
# never the same origin as this API. To ensure security, CORS origins are explicitly
# restricted to trusted frontend domains instead of using a wildcard '*'.
app.add_middleware(
    CORSMiddleware,
    allow_origins=default_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Process-local state, same accepted single-process tradeoff as
# bcc_middleware's AgentCircuitBreaker (see app/login_limiter.py docstring).
login_rate_limiter = LoginRateLimiter(
    failure_threshold=default_settings.login_failure_threshold,
    lockout_duration_seconds=default_settings.login_lockout_duration_seconds,
)


@app.on_event("startup")
async def _startup() -> None:
    # Skipped when a test harness has already attached a pool to app.state
    # (httpx's ASGITransport does not run lifespan events by default, so
    # tests set app.state.pool themselves before constructing the client --
    # see tests/conftest.py). Real deployments (uvicorn) always hit this.
    if getattr(app.state, "pool", None) is not None:
        return
    app.state.pool = await db.create_pool(default_settings.database_url)
    await db.run_migrations(app.state.pool)


@app.on_event("shutdown")
async def _shutdown() -> None:
    pool = getattr(app.state, "pool", None)
    if pool is not None:
        await pool.close()


@app.get("/health")
async def health() -> dict:
    return {"status": "online", "service": "integrity-userapi"}


# --- Auth -------------------------------------------------------------------


@app.post(
    "/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    body: RegisterRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    existing = await pool.fetchrow("SELECT id FROM users WHERE email = $1", body.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="email already registered"
        )

    hashed = hash_password(body.password)
    row = await pool.fetchrow(
        "INSERT INTO users (email, hashed_password) VALUES ($1, $2) RETURNING id",
        body.email,
        hashed,
    )
    token = create_access_token(user_id=str(row["id"]), settings=settings)
    return TokenResponse(access_token=token)


@app.post("/auth/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    if login_rate_limiter.is_locked_out(body.email):
        remaining = int(login_rate_limiter.lockout_remaining_seconds(body.email))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"too many failed login attempts, try again in {remaining}s",
            headers={"Retry-After": str(remaining)},
        )

    row = await pool.fetchrow(
        "SELECT id, hashed_password FROM users WHERE email = $1", body.email
    )
    if row is None or not verify_password(body.password, row["hashed_password"]):
        login_rate_limiter.record_failure(body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password"
        )

    login_rate_limiter.record_success(body.email)
    token = create_access_token(user_id=str(row["id"]), settings=settings)
    return TokenResponse(access_token=token)


@app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    token: DecodedToken = Depends(get_current_token),
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    """Revokes the presented bearer token immediately -- see
    `revoked_tokens` (migrations/0002_jwt_revocation.sql) and
    `get_current_token`'s revocation check. Opportunistically sweeps
    already-expired revocation rows first, so this table stays bounded by
    "revoked tokens still inside their own exp window" without needing a
    separate cleanup job."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM revoked_tokens WHERE expires_at < now()")
            await conn.execute(
                """
                INSERT INTO revoked_tokens (jti, user_id, expires_at)
                VALUES ($1, $2, $3)
                ON CONFLICT (jti) DO NOTHING
                """,
                UUID(token.jti),
                UUID(token.user_id),
                token.expires_at,
            )


@app.get("/me", response_model=UserResponse)
async def me(
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> UserResponse:
    row = await pool.fetchrow(
        "SELECT id, email, created_at FROM users WHERE id = $1", UUID(user_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="user not found"
        )
    return UserResponse(**dict(row))


# --- Custodial app wallet ------------------------------------------------------
#
# The honest "app-managed" counterpart to the dashboard's self-custodial MetaMask path:
# the userapi custodies a per-user app wallet and keeps an authoritative internal $ITK
# ledger. Transfers are real, transactional debits/credits (SELECT ... FOR UPDATE), not a
# faked number. New wallets get a dev faucet grant so the app-wallet flow is usable locally.

_DEV_FAUCET_WEI = 10_000 * 10**18

@app.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(

@app.get("/me/wallet", response_model=WalletResponse)
async def get_wallet(
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> WalletResponse:
    row = await pool.fetchrow(
        "SELECT app_wallet_address, itk_balance_wei FROM user_wallets WHERE user_id = $1",
        UUID(user_id),
    )
    if row is None:
        address = "0x" + secrets.token_hex(20)
        row = await pool.fetchrow(
            """
            INSERT INTO user_wallets (user_id, app_wallet_address, itk_balance_wei)
            VALUES ($1, $2, $3)
            RETURNING app_wallet_address, itk_balance_wei
            """,
            UUID(user_id),
            address,
            _DEV_FAUCET_WEI,
        )
    return WalletResponse(
        app_wallet_address=row["app_wallet_address"],
        balance=float(int(row["itk_balance_wei"]) / 1e18),
    )


@app.post("/me/wallet/transfer", response_model=TransferResponse)
async def wallet_transfer(
    body: TransferRequest,
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> TransferResponse:
    amount_wei = int(round(body.amount * 1e18))
    async with pool.acquire() as conn:
        async with conn.transaction():
            bal = await conn.fetchval(
                "SELECT itk_balance_wei FROM user_wallets WHERE user_id = $1 FOR UPDATE",
                UUID(user_id),
            )
            if bal is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no app wallet")
            if int(bal) < amount_wei:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="insufficient balance")
            new_bal = await conn.fetchval(
                "UPDATE user_wallets SET itk_balance_wei = itk_balance_wei - $2 WHERE user_id = $1 RETURNING itk_balance_wei",
                UUID(user_id),
                amount_wei,
            )
            # Credit the recipient iff it's another custodial app wallet (internal settlement);
            # an external 0x address is a debit only (funds leave the custodial ledger).
            await conn.execute(
                "UPDATE user_wallets SET itk_balance_wei = itk_balance_wei + $2 WHERE app_wallet_address = $1",
                body.recipient_address,
                amount_wei,
            )
    return TransferResponse(status="ok", new_balance=float(int(new_bal) / 1e18))


# --- API keys -----------------------------------------------------------------
#
# Minting and revoking a key are deliberately JWT-only (`get_current_token`,
# not `get_current_user_id`) even though API keys now authenticate most of
# this service (see app/deps.py). A `uak_...` key is meant for long-lived
# programmatic/agent use, not account-security management -- if it were
# allowed to mint further keys, a single leaked key could perpetuate itself
# past its own revocation. Listing keys stays open to either credential
# (read-only, no privilege-escalation risk).


@app.post(
    "/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    token: DecodedToken = Depends(get_current_token),
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> ApiKeyCreateResponse:
    raw_key, key_hash = generate_api_key()
    row = await pool.fetchrow(
        """
        INSERT INTO api_keys (user_id, key_hash, ais_trust_ceiling)
        VALUES ($1, $2, $3)
        RETURNING id, created_at
        """,
        UUID(token.user_id),
        key_hash,
        settings.default_api_key_trust_ceiling,
    )
    return ApiKeyCreateResponse(
        id=row["id"],
        raw_key=raw_key,
        ais_trust_ceiling=settings.default_api_key_trust_ceiling,
        created_at=row["created_at"],
    )


@app.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[ApiKeyResponse]:
    rows = await pool.fetch(
        """
        SELECT id, ais_trust_ceiling, revoked_at, created_at
        FROM api_keys WHERE user_id = $1 ORDER BY created_at DESC
        """,
        UUID(user_id),
    )
    return [ApiKeyResponse(**dict(row)) for row in rows]


@app.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    token: DecodedToken = Depends(get_current_token),
    pool: asyncpg.Pool = Depends(get_pool),
) -> None:
    result = await pool.execute(
        """
        UPDATE api_keys SET revoked_at = now()
        WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
        """,
        key_id,
        UUID(token.user_id),
    )
    # asyncpg's execute() returns a tag string like "UPDATE 0" / "UPDATE 1".
    if result == "UPDATE 0":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="api key not found"
        )


# --- Agent ownership ----------------------------------------------------------


@app.get("/me/agents", response_model=list[OwnedAgentResponse])
async def list_my_agents(
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> list[OwnedAgentResponse]:
    rows = await pool.fetch(
        "SELECT agent_did, added_at FROM user_agents WHERE user_id = $1 ORDER BY added_at DESC",
        UUID(user_id),
    )
    lookups = await asyncio.gather(
        *(oracle_client.fetch_agent(row["agent_did"], settings) for row in rows)
    )

    results: list[OwnedAgentResponse] = []
    for row, lookup in zip(rows, lookups):
        results.append(
            OwnedAgentResponse(
                agent_did=row["agent_did"],
                added_at=row["added_at"],
                live_data=lookup.live_data,
                error=lookup.error,
            )
        )
    return results


@app.post(
    "/me/agents", response_model=OwnedAgentResponse, status_code=status.HTTP_201_CREATED
)
async def add_my_agent(
    body: AddAgentRequest,
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> OwnedAgentResponse:
    row = await pool.fetchrow(
        """
        INSERT INTO user_agents (user_id, agent_did) VALUES ($1, $2)
        ON CONFLICT (user_id, agent_did) DO UPDATE SET agent_did = EXCLUDED.agent_did
        RETURNING agent_did, added_at
        """,
        UUID(user_id),
        body.agent_did,
    )
    lookup = await oracle_client.fetch_agent(row["agent_did"], settings)
    return OwnedAgentResponse(
        agent_did=row["agent_did"],
        added_at=row["added_at"],
        live_data=lookup.live_data,
        error=lookup.error,
    )


# --- Demo runs ------------------------------------------------------------------


def run_demo_script():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    try:
        subprocess.run(["make", "demo"], cwd=project_root, check=True)
    except Exception as e:
        print(f"Failed to run demo script: {e}")

@app.post(
    "/demo/run", response_model=DemoRunResponse, status_code=status.HTTP_201_CREATED
)
async def start_demo_run(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> DemoRunResponse:
    row = await pool.fetchrow(
        """
        INSERT INTO demo_runs (user_id, status) VALUES ($1, 'pending')
        RETURNING id, status, started_at, finished_at, result_summary
        """,
        UUID(user_id),
    )
    background_tasks.add_task(run_demo_script)
    return DemoRunResponse(**dict(row))


@app.get("/demo/runs", response_model=list[DemoRunResponse])
async def list_demo_runs(
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> list[DemoRunResponse]:
    rows = await pool.fetch(
        """
        SELECT id, status, started_at, finished_at, result_summary
        FROM demo_runs WHERE user_id = $1 ORDER BY started_at DESC
        """,
        UUID(user_id),
    )
    return [DemoRunResponse(**dict(row)) for row in rows]


@app.patch("/demo/runs/{run_id}", response_model=DemoRunResponse)
async def update_demo_run(
    run_id: UUID,
    body: DemoRunUpdateRequest,
    user_id: str = Depends(get_current_user_id),
    pool: asyncpg.Pool = Depends(get_pool),
) -> DemoRunResponse:
    """The completion-callback side of the demo_runs bridge: an actual
    executor (integrity-dashboard/demo's scenario engine, see its `main.py`
    module docstring) reports real status/result transitions back here.
    `finished_at` is stamped only on a terminal status (completed/failed);
    it stays null while transitioning through 'running'. Scoped to the
    owning user's own run, same ownership check as every other /demo/*
    and /api-keys/* mutation in this file -- a 404 (not 403) on mismatch
    or unknown id, so this endpoint doesn't leak which run ids exist for
    other users."""
    finished_at_clause = "now()" if body.status in ("completed", "failed") else "finished_at"
    row = await pool.fetchrow(
        f"""
        UPDATE demo_runs
        SET status = $1, result_summary = $2, finished_at = {finished_at_clause}
        WHERE id = $3 AND user_id = $4
        RETURNING id, status, started_at, finished_at, result_summary
        """,
        body.status,
        body.result_summary,
        run_id,
        UUID(user_id),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="demo run not found")
    return DemoRunResponse(**dict(row))
