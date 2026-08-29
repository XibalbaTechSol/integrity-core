"""
Auth flow: register -> token issued, login rejects wrong password, /me
requires a valid token and returns the right user. All against the real
FastAPI app + real Postgres via the `client` fixture (conftest.py).
"""

from __future__ import annotations

import httpx

EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery-staple"


async def _register(client: httpx.AsyncClient, email: str = EMAIL, password: str = PASSWORD) -> httpx.Response:
    return await client.post("/auth/register", json={"email": email, "password": password})


async def test_register_issues_token(client: httpx.AsyncClient) -> None:
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


async def test_register_duplicate_email_conflicts(client: httpx.AsyncClient) -> None:
    first = await _register(client)
    assert first.status_code == 201

    second = await _register(client)
    assert second.status_code == 409


async def test_register_rejects_short_password(client: httpx.AsyncClient) -> None:
    resp = await client.post("/auth/register", json={"email": "short@example.com", "password": "short"})
    assert resp.status_code == 422


async def test_login_succeeds_with_correct_password(client: httpx.AsyncClient) -> None:
    await _register(client)
    resp = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_rejects_wrong_password(client: httpx.AsyncClient) -> None:
    await _register(client)
    resp = await client.post("/auth/login", json={"email": EMAIL, "password": "totally-wrong-password"})
    assert resp.status_code == 401


async def test_login_rejects_unknown_email(client: httpx.AsyncClient) -> None:
    resp = await client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert resp.status_code == 401


async def test_me_requires_bearer_token(client: httpx.AsyncClient) -> None:
    resp = await client.get("/me")
    assert resp.status_code == 401


async def test_me_rejects_garbage_token(client: httpx.AsyncClient) -> None:
    resp = await client.get("/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert resp.status_code == 401


async def test_me_returns_the_right_user(client: httpx.AsyncClient) -> None:
    register_resp = await _register(client)
    token = register_resp.json()["access_token"]

    resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == EMAIL
    assert "id" in body and "created_at" in body


async def test_me_rejects_token_for_deleted_user(client: httpx.AsyncClient, db_pool) -> None:
    register_resp = await _register(client)
    token = register_resp.json()["access_token"]

    me_resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me_resp.json()["id"]

    await db_pool.execute("DELETE FROM users WHERE id = $1", user_id)

    resp = await client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_logout_revokes_the_token_immediately(client: httpx.AsyncClient) -> None:
    register_resp = await _register(client)
    token = register_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    still_valid = await client.get("/me", headers=headers)
    assert still_valid.status_code == 200

    logout_resp = await client.post("/auth/logout", headers=headers)
    assert logout_resp.status_code == 204

    after_logout = await client.get("/me", headers=headers)
    assert after_logout.status_code == 401


async def test_logout_only_revokes_the_presented_token_not_others(client: httpx.AsyncClient) -> None:
    await _register(client)
    login_a = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    login_b = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    token_a, token_b = login_a.json()["access_token"], login_b.json()["access_token"]
    assert token_a != token_b  # distinct jti per issuance, even for the same user

    await client.post("/auth/logout", headers={"Authorization": f"Bearer {token_a}"})

    resp_a = await client.get("/me", headers={"Authorization": f"Bearer {token_a}"})
    assert resp_a.status_code == 401

    resp_b = await client.get("/me", headers={"Authorization": f"Bearer {token_b}"})
    assert resp_b.status_code == 200


async def test_logout_requires_a_valid_token(client: httpx.AsyncClient) -> None:
    resp = await client.post("/auth/logout")
    assert resp.status_code == 401


async def test_login_locks_out_after_repeated_failures(client: httpx.AsyncClient) -> None:
    from app.main import login_rate_limiter

    login_rate_limiter.reset()
    await _register(client, email="lockout@example.com")

    for _ in range(login_rate_limiter.failure_threshold):
        resp = await client.post(
            "/auth/login", json={"email": "lockout@example.com", "password": "wrong-password"}
        )
        assert resp.status_code == 401

    # One more attempt -- even with the CORRECT password -- must be locked out.
    locked_resp = await client.post(
        "/auth/login", json={"email": "lockout@example.com", "password": PASSWORD}
    )
    assert locked_resp.status_code == 429
    assert "Retry-After" in locked_resp.headers

    login_rate_limiter.reset()


async def test_login_lockout_is_scoped_to_one_email(client: httpx.AsyncClient) -> None:
    from app.main import login_rate_limiter

    login_rate_limiter.reset()
    await _register(client, email="victim@example.com")
    await _register(client, email="bystander@example.com")

    for _ in range(login_rate_limiter.failure_threshold):
        await client.post("/auth/login", json={"email": "victim@example.com", "password": "wrong"})

    bystander_resp = await client.post(
        "/auth/login", json={"email": "bystander@example.com", "password": PASSWORD}
    )
    assert bystander_resp.status_code == 200

    login_rate_limiter.reset()


async def test_login_success_resets_the_failure_count(client: httpx.AsyncClient) -> None:
    from app.main import login_rate_limiter

    login_rate_limiter.reset()
    await _register(client, email="resets@example.com")

    for _ in range(login_rate_limiter.failure_threshold - 1):
        await client.post("/auth/login", json={"email": "resets@example.com", "password": "wrong"})

    good_login = await client.post(
        "/auth/login", json={"email": "resets@example.com", "password": PASSWORD}
    )
    assert good_login.status_code == 200

    # A fresh run of near-threshold failures after a success must NOT still
    # be counted against the pre-success failures.
    for _ in range(login_rate_limiter.failure_threshold - 1):
        resp = await client.post(
            "/auth/login", json={"email": "resets@example.com", "password": "wrong"}
        )
        assert resp.status_code == 401

    still_ok = await client.post(
        "/auth/login", json={"email": "resets@example.com", "password": PASSWORD}
    )
    assert still_ok.status_code == 200

    login_rate_limiter.reset()
