"""Authentication on the /v1/admin/* routes (app/main.py::require_admin).

`PUT /v1/admin/clinical-allowlist` decides which agents may commit clinical (PHI-adjacent) intents. It had no
authentication at all and CORS is `*`, so anyone who could reach the port could authorize any agent. These
tests pin the fix: the admin API is DISABLED when no token is configured (never open), anything but the exact
bearer token is a 401, and a future /v1/admin/* route cannot be added without the dependency.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import MIN_ADMIN_TOKEN_LENGTH, Settings

TOKEN = "t" * 40
ALLOWLIST = "/v1/admin/clinical-allowlist"


@pytest.fixture()
def opa_data_cleanup(real_opa_server):
    yield
    httpx.put(f"{real_opa_server}/v1/data/clinical_allowlist/agents", json=[])


def _client(monkeypatch, real_opa_server, *, token: str | None = TOKEN) -> TestClient:
    monkeypatch.setattr(main_module, "default_settings", Settings(opa_url=real_opa_server, admin_token=token))
    return TestClient(main_module.app)


def _opa_allowlist(real_opa_server) -> list[str]:
    return httpx.get(f"{real_opa_server}/v1/data/clinical_allowlist/agents").json().get("result", [])


# -------------------------------------------------------------------------- fail closed


def test_with_no_token_configured_the_admin_api_is_disabled_not_open(monkeypatch, real_opa_server, opa_data_cleanup):
    client = _client(monkeypatch, real_opa_server, token=None)
    for response in (
        client.get(ALLOWLIST),
        client.put(ALLOWLIST, json={"agents": ["did:integrity:attacker"]}),
        client.put(ALLOWLIST, json={"agents": ["did:integrity:attacker"]}, headers={"Authorization": f"Bearer {TOKEN}"}),
    ):
        assert response.status_code == 503 and "BCC_ADMIN_TOKEN" in response.json()["detail"]
    assert "did:integrity:attacker" not in _opa_allowlist(real_opa_server), "a refused write must not reach OPA"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer wrong-token-wrong-token-wrong-token-wrong"},
        {"Authorization": f"Bearer {TOKEN}x"},
        {"Authorization": f"Bearer {TOKEN[:-1]}"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": TOKEN},
        {"X-Admin-Token": TOKEN},
    ],
    ids=lambda h: ",".join(f"{k}={v[:12]}" for k, v in h.items()) or "no-header",
)
def test_anything_but_the_exact_bearer_token_is_rejected(monkeypatch, real_opa_server, opa_data_cleanup, headers):
    client = _client(monkeypatch, real_opa_server)
    for response in (client.get(ALLOWLIST, headers=headers), client.put(ALLOWLIST, json={"agents": ["did:integrity:attacker"]}, headers=headers)):
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
    assert "did:integrity:attacker" not in _opa_allowlist(real_opa_server)


def test_the_correct_token_works_for_read_and_write(monkeypatch, real_opa_server, opa_data_cleanup):
    client = _client(monkeypatch, real_opa_server)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    written = client.put(ALLOWLIST, json={"agents": ["did:integrity:granted"]}, headers=headers)
    assert written.status_code == 200 and written.json()["agents"] == ["did:integrity:granted"]
    assert _opa_allowlist(real_opa_server) == ["did:integrity:granted"]
    assert client.get(ALLOWLIST, headers=headers).json()["agents"] == ["did:integrity:granted"]


def test_the_bearer_scheme_is_case_insensitive(monkeypatch, real_opa_server):
    client = _client(monkeypatch, real_opa_server)
    assert client.get(ALLOWLIST, headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


def test_a_rejected_request_is_logged_without_the_credential(monkeypatch, real_opa_server, caplog):
    client = _client(monkeypatch, real_opa_server)
    with caplog.at_level("WARNING", logger="bcc_middleware"):
        client.get(ALLOWLIST, headers={"Authorization": "Bearer super-secret-attempt-super-secret-attempt"})
    assert "rejected GET /v1/admin/clinical-allowlist" in caplog.text
    assert "super-secret-attempt" not in caplog.text and TOKEN not in caplog.text


# -------------------------------------------------------------------------- the token itself


def test_a_short_token_is_a_startup_error_not_a_weak_secret():
    with pytest.raises(ValueError, match=str(MIN_ADMIN_TOKEN_LENGTH)):
        Settings(admin_token="hunter2")
    Settings(admin_token="a" * MIN_ADMIN_TOKEN_LENGTH)
    Settings(admin_token=None)


def test_an_empty_environment_variable_means_unset(monkeypatch):
    monkeypatch.setenv("BCC_ADMIN_TOKEN", "")
    assert Settings().admin_token is None


# ---------------------------------------------------------------------- nothing else changed


def test_the_token_is_compared_in_constant_time(monkeypatch, real_opa_server):
    """Observe the call itself. (A first version searched the function's source for the string, which its own
    docstring satisfied, so replacing the comparison with `==` survived mutation testing.)"""
    calls: list[tuple[bytes, bytes]] = []
    real = main_module.hmac.compare_digest

    def spy(left, right):
        calls.append((left, right))
        return real(left, right)

    monkeypatch.setattr(main_module.hmac, "compare_digest", spy)
    client = _client(monkeypatch, real_opa_server)
    assert client.get(ALLOWLIST, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200
    assert client.get(ALLOWLIST, headers={"Authorization": "Bearer " + "x" * 40}).status_code == 401
    assert calls == [(TOKEN.encode(), TOKEN.encode()), (b"x" * 40, TOKEN.encode())]


def test_every_admin_route_requires_authentication():
    """Structural, so a future /v1/admin/* route added without the dependency fails the build instead of
    shipping open."""
    admin_routes = [r for r in main_module.app.routes if isinstance(r, APIRoute) and r.path.startswith("/v1/admin")]
    assert admin_routes, "no /v1/admin routes found: has the prefix changed?"
    for route in admin_routes:
        calls = [dependency.call for dependency in route.dependant.dependencies]
        assert main_module.require_admin in calls, f"{sorted(route.methods)} {route.path} has no admin authentication"


def test_non_admin_routes_are_unaffected(monkeypatch, real_opa_server):
    client = _client(monkeypatch, real_opa_server, token=None)
    assert client.get("/health").status_code == 200
    assert client.post("/v1/bcc/intercept", json={"agent_id": "not-a-did"}).status_code == 422
