"""POST /demo/run creates a row with status='pending'; GET /demo/runs lists it.
This service only records that a run was requested -- it never orchestrates
or fabricates a 'completed' state (see app/main.py's docstring on
start_demo_run), so the pending status itself is the behavior under test.
"""

from __future__ import annotations

import httpx

EMAIL = "demo@example.com"
PASSWORD = "correct-horse-battery-staple"


async def _auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_start_demo_run_creates_pending_row(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    resp = await client.post("/demo/run", headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["finished_at"] is None
    assert body["result_summary"] is None


async def test_list_demo_runs_round_trip(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/demo/run", headers=headers)
    created_id = created.json()["id"]

    listed = await client.get("/demo/runs", headers=headers)
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert created_id in ids
    assert all(item["status"] == "pending" for item in listed.json())


async def test_demo_runs_ordered_most_recent_first(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    first = await client.post("/demo/run", headers=headers)
    second = await client.post("/demo/run", headers=headers)

    listed = await client.get("/demo/runs", headers=headers)
    ids = [item["id"] for item in listed.json()]
    assert ids.index(second.json()["id"]) < ids.index(first.json()["id"])


async def test_demo_runs_scoped_to_owner(client: httpx.AsyncClient) -> None:
    headers_a = await _auth_headers(client)
    await client.post("/demo/run", headers=headers_a)

    resp_b = await client.post("/auth/register", json={"email": "other@example.com", "password": PASSWORD})
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    listed_b = await client.get("/demo/runs", headers=headers_b)
    assert listed_b.json() == []


async def test_start_demo_run_requires_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post("/demo/run")
    assert resp.status_code == 401


async def test_patch_demo_run_transitions_to_running(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/demo/run", headers=headers)
    run_id = created.json()["id"]

    resp = await client.patch(f"/demo/runs/{run_id}", json={"status": "running"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    # Not a terminal status -- finished_at must stay unset.
    assert body["finished_at"] is None


async def test_patch_demo_run_completion_sets_finished_at_and_result(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/demo/run", headers=headers)
    run_id = created.json()["id"]

    resp = await client.patch(
        f"/demo/runs/{run_id}",
        json={"status": "completed", "result_summary": {"agents_registered": 4, "tx_count": 7}},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["finished_at"] is not None
    assert body["result_summary"] == {"agents_registered": 4, "tx_count": 7}


async def test_patch_demo_run_failed_sets_finished_at(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/demo/run", headers=headers)
    run_id = created.json()["id"]

    resp = await client.patch(
        f"/demo/runs/{run_id}", json={"status": "failed", "result_summary": {"error": "rpc timeout"}}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["finished_at"] is not None


async def test_patch_demo_run_rejects_invalid_status(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post("/demo/run", headers=headers)
    run_id = created.json()["id"]

    resp = await client.patch(f"/demo/runs/{run_id}", json={"status": "pending"}, headers=headers)
    assert resp.status_code == 422

    resp2 = await client.patch(f"/demo/runs/{run_id}", json={"status": "made-up-status"}, headers=headers)
    assert resp2.status_code == 422


async def test_patch_demo_run_unknown_id_404s(client: httpx.AsyncClient) -> None:
    headers = await _auth_headers(client)
    resp = await client.patch(
        "/demo/runs/00000000-0000-0000-0000-000000000000", json={"status": "running"}, headers=headers
    )
    assert resp.status_code == 404


async def test_patch_demo_run_cannot_update_another_users_run(client: httpx.AsyncClient) -> None:
    headers_a = await _auth_headers(client)
    created = await client.post("/demo/run", headers=headers_a)
    run_id = created.json()["id"]

    resp_b = await client.post("/auth/register", json={"email": "otherdemo@example.com", "password": PASSWORD})
    headers_b = {"Authorization": f"Bearer {resp_b.json()['access_token']}"}

    resp = await client.patch(f"/demo/runs/{run_id}", json={"status": "running"}, headers=headers_b)
    assert resp.status_code == 404

    # Confirm it's genuinely untouched.
    listed_a = await client.get("/demo/runs", headers=headers_a)
    entry = next(item for item in listed_a.json() if item["id"] == run_id)
    assert entry["status"] == "pending"
