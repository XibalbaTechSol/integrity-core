"""
Fail-closed OPA behavior -- the single most security-critical property of
this service (docs/INTERFACE_CONTRACT.md §7): "if OPA is unreachable, the
request must fail closed (deny), not silently approve."

`test_opa_never_started_denies_without_mocking` is the literal version of
what the task asked for: it points at a real TCP port with NOTHING
listening (OPA is never started for that test) and confirms the real
`httpx` call fails and the request is denied -- no mocking of the failure
mode at all.
"""

from __future__ import annotations

import pytest
import respx
from httpx import ConnectError, Response

from app.config import Settings
from app.opa_client import OPAUnavailableError, evaluate
from app.main import run_intercept
from tests.helpers import make_commitment_model, new_agent, sign_commitment


def _free_unused_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --- 1. Real OPA, genuinely never started (no mocking) -----------------------


@pytest.mark.asyncio
async def test_opa_client_raises_when_nothing_is_listening():
    dead_port = _free_unused_port()  # bound-then-released; nothing is listening on it
    settings = Settings(opa_url=f"http://127.0.0.1:{dead_port}")
    with pytest.raises(OPAUnavailableError):
        await evaluate(settings, {"agent_id": "did:integrity:x", "intent_type": "payment", "nonce": 1, "timestamp": 1})


@pytest.mark.asyncio
async def test_intercept_denies_when_opa_was_never_started():
    dead_port = _free_unused_port()
    settings = Settings(opa_url=f"http://127.0.0.1:{dead_port}", merkle_batch_size=999)
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
    commitment = make_commitment_model(**payload)

    response = await run_intercept(commitment, settings)

    assert response.authorized is False
    assert "BCC_POLICY_ENGINE_UNAVAILABLE" in response.reason


@pytest.mark.asyncio
async def test_opa_outage_does_not_trip_the_circuit_breaker():
    """
    An OPA outage is OUR infra failing, not the agent misbehaving -- it must
    deny the request but must NOT count against the agent's circuit
    breaker, or an OPA outage would lock out every well-behaved agent in
    the fleet for the lockout window (see circuit_breaker.py docstring).
    """
    import app.main as main_module

    dead_port = _free_unused_port()
    settings = Settings(opa_url=f"http://127.0.0.1:{dead_port}")
    agent_id, private_key = new_agent()

    main_module.circuit_breaker.reset(agent_id)
    for nonce in range(1, main_module.circuit_breaker.violation_threshold + 2):
        payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=nonce)
        commitment = make_commitment_model(**payload)
        response = await run_intercept(commitment, settings)
        assert response.authorized is False

    assert not main_module.circuit_breaker.is_locked_out(agent_id)


# --- 2. Real OPA, running, evaluating our real policies -----------------------


@pytest.mark.asyncio
async def test_real_opa_allows_ordinary_payment(real_opa_server):
    settings = Settings(opa_url=real_opa_server)
    decision = await evaluate(settings, {"agent_id": "did:integrity:x", "intent_type": "payment", "nonce": 1, "timestamp": 1})
    assert decision.allow is True
    assert decision.requires_baa is False


@pytest.mark.asyncio
async def test_real_opa_denies_unauthorized_clinical_agent(real_opa_server):
    settings = Settings(opa_url=real_opa_server)
    decision = await evaluate(
        settings,
        {"agent_id": "did:integrity:random_agent", "intent_type": "EMR_WRITE", "nonce": 1, "timestamp": 1},
    )
    assert decision.allow is False
    assert decision.requires_baa is True
    assert any("HIPAA_ACCESS_CONTROL_VIOLATION" in v for v in decision.violations)


@pytest.mark.asyncio
async def test_full_intercept_flow_denies_via_real_opa(real_opa_server):
    """End-to-end: real signature verification + real running OPA denying a clinical action."""
    settings = Settings(opa_url=real_opa_server, merkle_batch_size=999)
    agent_id, private_key = new_agent()
    payload = sign_commitment(private_key, agent_id=agent_id, intent_type="EMR_WRITE", nonce=1)
    commitment = make_commitment_model(**payload)

    response = await run_intercept(commitment, settings)

    assert response.authorized is False
    assert "OPA_REJECTION" in response.reason
    assert "HIPAA_ACCESS_CONTROL_VIOLATION" in response.reason


# --- 3. Malformed / erroring OPA responses (still fail closed) ---------------


@pytest.mark.asyncio
async def test_opa_non_200_response_fails_closed():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://opa.invalid/v1/data/integrity/bcc").mock(return_value=Response(500, text="boom"))
        settings = Settings(opa_url="http://opa.invalid")
        with pytest.raises(OPAUnavailableError):
            await evaluate(settings, {"agent_id": "did:integrity:x", "intent_type": "payment", "nonce": 1, "timestamp": 1})


@pytest.mark.asyncio
async def test_opa_malformed_json_fails_closed():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://opa.invalid/v1/data/integrity/bcc").mock(return_value=Response(200, text="not json"))
        settings = Settings(opa_url="http://opa.invalid")
        with pytest.raises(OPAUnavailableError):
            await evaluate(settings, {"agent_id": "did:integrity:x", "intent_type": "payment", "nonce": 1, "timestamp": 1})


@pytest.mark.asyncio
async def test_opa_missing_result_key_fails_closed():
    """A wrong/typo'd policy path returns `{}` -- must not be silently read as allow=False forever."""
    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://opa.invalid/v1/data/integrity/bcc").mock(return_value=Response(200, json={}))
        settings = Settings(opa_url="http://opa.invalid")
        with pytest.raises(OPAUnavailableError):
            await evaluate(settings, {"agent_id": "did:integrity:x", "intent_type": "payment", "nonce": 1, "timestamp": 1})


@pytest.mark.asyncio
async def test_intercept_denies_malformed_opa_decision_with_safe_diagnostic():
    """An indeterminate OPA result must become an explicit denial, not an exception or implicit allow."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get(url__regex=r"http://oracle\.invalid/v1/agent/.+").mock(
            return_value=Response(404, json={"detail": "agent not indexed"})
        )
        mock.post("http://opa.invalid/v1/data/integrity/bcc").mock(
            return_value=Response(200, json={"result": {"allow": "yes"}})
        )
        settings = Settings(
            opa_url="http://opa.invalid",
            oracle_url="http://oracle.invalid",
            merkle_batch_size=999,
        )
        agent_id, private_key = new_agent()
        payload = sign_commitment(private_key, agent_id=agent_id, intent_type="payment", nonce=1)
        commitment = make_commitment_model(**payload)

        response = await run_intercept(commitment, settings)

    assert response.authorized is False
    assert response.reason is not None
    assert response.reason.startswith("BCC_POLICY_ENGINE_UNAVAILABLE:")
    assert "missing boolean 'allow' field" in response.reason


@pytest.mark.asyncio
async def test_opa_connection_error_fails_closed():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("http://opa.invalid/v1/data/integrity/bcc").mock(side_effect=ConnectError("refused"))
        settings = Settings(opa_url="http://opa.invalid")
        with pytest.raises(OPAUnavailableError):
            await evaluate(settings, {"agent_id": "did:integrity:x", "intent_type": "payment", "nonce": 1, "timestamp": 1})
