"""
Developer API key create -> list -> revoke round trip, plus the API key as
an actual authentication credential (`get_current_user_id` in app/deps.py
now accepts an `X-API-Key` header as an alternative to a JWT bearer token,
resolving to the key's owning user -- see that module's docstring).
"""

from __future__ import annotations

import hashlib

import httpx

from app.security import hash_api_key

EMAIL = "keys@example.com"
PASSWORD = "correct-horse-battery-staple"


async def _auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_api_key_returns_raw_key_once(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    resp = await client.post("/api-keys", headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["raw_key"].startswith("uak_")
    assert body["ais_trust_ceiling"] == 300
    # ApiKeyCreateResponse deliberately has no `revoked_at` field -- a
    # freshly created key can't be revoked yet, so the schema doesn't offer
    # a place to lie about it.
    assert "revoked_at" not in body


async def test_created_key_only_hash_is_persisted(client: httpx.AsyncClient, db_pool) -> None:
    headers = await _auth_headers(client)
    resp = await client.post("/api-keys", headers=headers)
    raw_key = resp.json()["raw_key"]
    key_id = resp.json()["id"]

    row = await db_pool.fetchrow("SELECT key_hash FROM api_keys WHERE id = $1", key_id)
    assert row["key_hash"] == hash_api_key(raw_key)
    assert row["key_hash"] == hashlib.sha256(raw_key.encode()).hexdigest()
    # The raw key itself must not appear anywhere in the persisted row's hash column.
    assert raw_key != row["key_hash"]


async def test_list_api_keys_round_trip(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers)
    created_id = created.json()["id"]

    listed = await client.get("/api-keys", headers=headers)
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert created_id in ids
    # The raw key must never be re-returned by the list endpoint.
    assert all("raw_key" not in item for item in listed.json())


async def test_list_api_keys_scoped_to_owner(client: httpx.AsyncClient) -> None:
    headers_a = await _auth_headers(client)
    await client.post("/api-keys", headers=headers_a)

    resp_b = await client.post("/auth/register", json={"email": "other@example.com", "password": PASSWORD})
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    listed_b = await client.get("/api-keys", headers=headers_b)
    assert listed_b.json() == []


async def test_revoke_api_key(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers)
    key_id = created.json()["id"]

    revoke_resp = await client.delete(f"/api-keys/{key_id}", headers=headers)
    assert revoke_resp.status_code == 204

    listed = await client.get("/api-keys", headers=headers)
    revoked_entry = next(item for item in listed.json() if item["id"] == key_id)
    assert revoked_entry["revoked_at"] is not None


async def test_revoke_already_revoked_key_404s(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers)
    key_id = created.json()["id"]

    first = await client.delete(f"/api-keys/{key_id}", headers=headers)
    assert first.status_code == 204

    second = await client.delete(f"/api-keys/{key_id}", headers=headers)
    assert second.status_code == 404


async def test_revoke_unknown_key_404s(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    resp = await client.delete("/api-keys/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404


async def test_cannot_revoke_another_users_key(client: httpx.AsyncClient) -> None:
    headers_a = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers_a)
    key_id = created.json()["id"]

    resp_b = await client.post("/auth/register", json={"email": "other2@example.com", "password": PASSWORD})
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    resp = await client.delete(f"/api-keys/{key_id}", headers=headers_b)
    assert resp.status_code == 404

    # Confirm it's genuinely untouched, not silently revoked under the hood.
    listed_a = await client.get("/api-keys", headers=headers_a)
    entry = next(item for item in listed_a.json() if item["id"] == key_id)
    assert entry["revoked_at"] is None


async def test_api_key_authenticates_a_request(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers)
    raw_key = created.json()["raw_key"]

    resp = await client.get("/me", headers={"X-API-Key": raw_key})
    assert resp.status_code == 200
    assert resp.json()["email"] == EMAIL


async def test_revoked_api_key_no_longer_authenticates(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers)
    raw_key = created.json()["raw_key"]
    key_id = created.json()["id"]

    await client.delete(f"/api-keys/{key_id}", headers=headers)

    resp = await client.get("/me", headers={"X-API-Key": raw_key})
    assert resp.status_code == 401


async def test_api_key_cannot_mint_further_api_keys(client: httpx.AsyncClient) -> None:
    # Minting/revoking a key is JWT-only (see app/main.py's "API keys" section
    # docstring) -- an API key that could mint further keys would let a single
    # leaked long-lived credential perpetuate itself past its own revocation.
    headers = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers)
    raw_key = created.json()["raw_key"]

    resp = await client.post("/api-keys", headers={"X-API-Key": raw_key})
    assert resp.status_code == 401


async def test_api_key_cannot_revoke_api_keys(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers)
    raw_key = created.json()["raw_key"]
    key_id = created.json()["id"]

    resp = await client.delete(f"/api-keys/{key_id}", headers={"X-API-Key": raw_key})
    assert resp.status_code == 401

    # Confirm it's genuinely untouched.
    listed = await client.get("/api-keys", headers=headers)
    entry = next(item for item in listed.json() if item["id"] == key_id)
    assert entry["revoked_at"] is None


async def test_unknown_api_key_401s(client: httpx.AsyncClient) -> None:
    resp = await client.get("/me", headers={"X-API-Key": "uak_totally-not-a-real-key"})
    assert resp.status_code == 401


async def test_api_key_resolves_to_its_own_owner_not_another_users(client: httpx.AsyncClient) -> None:
    headers_a = await _auth_headers(client)
    created = await client.post("/api-keys", headers=headers_a)
    raw_key = created.json()["raw_key"]

    resp_b = await client.post("/auth/register", json={"email": "keyowner2@example.com", "password": PASSWORD})
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    # Authenticating with A's api key must list A's keys, never B's -- even
    # though this request is made "as" whichever user the key resolves to.
    listed = await client.get("/api-keys", headers={"X-API-Key": raw_key})
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert created.json()["id"] in ids

    listed_b = await client.get("/api-keys", headers=headers_b)
    assert listed_b.json() == []
