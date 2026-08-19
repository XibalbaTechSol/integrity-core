"""
Tests for app/main.py's deployment-binding check (chain_id + verifying_contract),
docs/plans/2026-08-18-phase1-canonical-intent-encoding-proposal.md.

These call `run_intercept` directly rather than through the TestClient/real-OPA
fixtures the rest of this suite uses for the full gauntlet -- a chain_id or
verifying_contract mismatch is denied BEFORE signature verification, let alone
OPA, so no anvil/OPA infra is needed to exercise this check in isolation. This
mirrors test_opa_fail_closed.py's `test_intercept_denies_when_opa_was_never_started`
pattern: a real (dead) OPA port, `run_intercept` called directly, response
inspected for the specific deny reason.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import run_intercept
from tests.helpers import make_commitment_model, new_agent, sign_commitment


def _dead_opa_settings(**overrides) -> Settings:
    """A Settings pointed at a real, never-started OPA port -- so any test
    below that gets PAST the deployment-binding check still resolves
    deterministically (BCC_POLICY_ENGINE_UNAVAILABLE), same fail-closed
    posture test_opa_fail_closed.py already relies on, rather than hanging
    on a real localhost:8181 that may or may not be running in this
    environment."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        dead_port = s.getsockname()[1]
    return Settings(opa_url=f"http://127.0.0.1:{dead_port}", **overrides)


@pytest.mark.asyncio
async def test_matching_chain_id_and_unconfigured_registry_is_not_denied_here(tmp_path):
    """No XibalbaAgentRegistry configured (the common local/dev/test shape --
    see test_chain_baa_anchor.py's own 'Explicit, nonexistent deployments_file'
    precedent) -- verifying_contract must not be enforced, only chain_id."""
    settings = _dead_opa_settings(chain_id=31337, deployments_file=str(tmp_path / "nonexistent.json"))
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1, chain_id=31337)
    commitment = make_commitment_model(**payload)

    resp = await run_intercept(commitment, settings)

    assert resp.authorized is False
    assert "BCC_CHAIN_MISMATCH" not in resp.reason
    assert "BCC_VERIFYING_CONTRACT_MISMATCH" not in resp.reason
    assert "BCC_POLICY_ENGINE_UNAVAILABLE" in resp.reason  # got past deployment binding + signature + nonce + freshness


@pytest.mark.asyncio
async def test_chain_id_mismatch_is_denied(tmp_path):
    settings = _dead_opa_settings(chain_id=31337, deployments_file=str(tmp_path / "nonexistent.json"))
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1, chain_id=999999)
    commitment = make_commitment_model(**payload)

    resp = await run_intercept(commitment, settings)

    assert resp.authorized is False
    assert resp.reason.startswith("BCC_CHAIN_MISMATCH")


@pytest.mark.asyncio
async def test_verifying_contract_mismatch_is_denied_when_registry_is_configured(tmp_path):
    configured = "0x111111111111111111111111111111111111111a"
    mismatched = "0x222222222222222222222222222222222222222b"
    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.write_text(json.dumps({"singletons": {"XibalbaAgentRegistry": configured}}))
    settings = _dead_opa_settings(chain_id=31337, deployments_file=str(deployments_file))

    agent_id, private_key = new_agent()
    payload = sign_commitment(
        private_key, agent_id=agent_id, intent_type="payment", nonce=1,
        chain_id=31337, verifying_contract=mismatched,
    )
    commitment = make_commitment_model(**payload)

    resp = await run_intercept(commitment, settings)

    assert resp.authorized is False
    assert resp.reason.startswith("BCC_VERIFYING_CONTRACT_MISMATCH")


@pytest.mark.asyncio
async def test_matching_verifying_contract_is_not_denied_here(tmp_path):
    configured = "0x111111111111111111111111111111111111111a"
    deployments_file = tmp_path / "deployments.local.json"
    deployments_file.write_text(json.dumps({"singletons": {"XibalbaAgentRegistry": configured}}))
    settings = _dead_opa_settings(chain_id=31337, deployments_file=str(deployments_file))

    agent_id, private_key = new_agent()
    # Deliberately case-differing but semantically identical -- the check
    # compares case-insensitively, matching how EVM addresses are
    # conventionally compared.
    payload = sign_commitment(
        private_key, agent_id=agent_id, intent_type="payment", nonce=1,
        chain_id=31337, verifying_contract=configured.upper().replace("0X", "0x"),
    )
    commitment = make_commitment_model(**payload)

    resp = await run_intercept(commitment, settings)

    assert resp.authorized is False
    assert "BCC_CHAIN_MISMATCH" not in resp.reason
    assert "BCC_VERIFYING_CONTRACT_MISMATCH" not in resp.reason
    assert "BCC_POLICY_ENGINE_UNAVAILABLE" in resp.reason


def test_commitment_missing_chain_id_fails_schema_validation():
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    del payload["chain_id"]
    with pytest.raises(ValidationError):
        make_commitment_model(**payload)


def test_commitment_missing_verifying_contract_fails_schema_validation():
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    del payload["verifying_contract"]
    with pytest.raises(ValidationError):
        make_commitment_model(**payload)


def test_verifying_contract_bad_shape_fails_schema_validation():
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    payload["verifying_contract"] = "not-an-address"
    with pytest.raises(ValidationError):
        make_commitment_model(**payload)
