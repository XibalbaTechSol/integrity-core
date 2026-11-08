"""BCC with the in-process wasm engine (BCC_POLICY_ENGINE=wasm): the signed pack decides, no OPA server.

Proves the gate behaves like the OPA-server pack engine but needs no BCC_PACK_OPA_URL, and fails closed.
The daemonless path is stage 5 of docs/design/bcc-shared-pack-migration.md.
"""

from __future__ import annotations

import asyncio

import pytest

import app.main as main_module
from app.config import Settings
from app.main import run_intercept
from app.pack_policy import PackPolicy, PackPolicyError
from tests.helpers import make_commitment_model, new_agent, sign_commitment

pytest.importorskip("wasmtime")
RATIONALE = "A sufficiently long declared intent rationale."


def _base(pack_dir: str, signer: str, **over) -> dict:
    return {"policy_engine": "wasm", "policy_pack_dir": pack_dir,
            "trusted_pack_signers": frozenset({signer}), **over}


def _run(settings, policy, agent_id, key, intent_type, monkeypatch, nonce=1):
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "pack_policy", policy)
    monkeypatch.setattr(main_module, "pack_policy_error", None)
    monkeypatch.setattr(main_module, "resolve_verification_tier", lambda agent_id, oracle_url=None: 1)
    main_module.circuit_breaker.reset()
    main_module.token_budget_enforcer.reset()
    payload = sign_commitment(key, agent_id=agent_id, intent_type=intent_type, nonce=nonce, intent_rationale=RATIONALE)
    return asyncio.run(run_intercept(make_commitment_model(**payload), settings))


def test_wasm_engine_needs_no_opa_url_and_permits_a_clean_commitment(make_signed_pack, monkeypatch):
    pack_dir, signer = make_signed_pack(build_wasm=True)
    settings = Settings(**_base(pack_dir, signer))  # note: no pack_opa_url
    policy = PackPolicy.load(settings)  # must not raise about a missing OPA url
    agent_id, key = new_agent()
    resp = _run(settings, policy, agent_id, key, "read_file", monkeypatch)
    assert resp.authorized is True


def test_wasm_engine_denies_a_policy_violating_commitment(make_signed_pack, monkeypatch):
    pack_dir, signer = make_signed_pack(build_wasm=True)
    settings = Settings(**_base(pack_dir, signer))
    policy = PackPolicy.load(settings)
    agent_id, key = new_agent()  # not on the clinical allowlist
    resp = _run(settings, policy, agent_id, key, "SECURE_EMR_WRITE", monkeypatch)
    assert resp.authorized is False


def test_wasm_mode_refuses_to_start_without_a_built_wasm(make_signed_pack):
    pack_dir, signer = make_signed_pack(build_wasm=False)  # verifiable, but no policy.wasm
    with pytest.raises(PackPolicyError) as exc:
        PackPolicy.load(Settings(**_base(pack_dir, signer)))
    assert "WASM_MISSING" in str(exc.value) or "policy.wasm" in str(exc.value)


def test_wasm_mode_refuses_to_start_when_the_pack_does_not_verify(make_signed_pack):
    pack_dir, signer = make_signed_pack(build_wasm=True, tamper_after=lambda t: t + "\n# tampered\n")
    with pytest.raises(PackPolicyError):
        PackPolicy.load(Settings(**_base(pack_dir, signer)))


def test_wasm_decisions_match_a_real_opa_server(make_signed_pack, start_empty_opa):
    """Same pack, same commitments, through wasm and through an OPA server: identical allow/reason."""
    pack_dir, signer = make_signed_pack(build_wasm=True)
    wasm_policy = PackPolicy.load(Settings(**_base(pack_dir, signer)))
    opa_policy = PackPolicy.load(Settings(**_base(pack_dir, signer, policy_engine="pack", pack_opa_url=start_empty_opa())))
    for intent in ("read_file", "SECURE_EMR_WRITE", "DISPENSE_MEDICATION", "run_command", "payment"):
        agent_id, key = new_agent()
        payload = sign_commitment(key, agent_id=agent_id, intent_type=intent, nonce=1, intent_rationale=RATIONALE)
        a = asyncio.run(wasm_policy.decide(payload))
        b = asyncio.run(opa_policy.decide(payload))
        assert (a.allow, a.reason_code) == (b.allow, b.reason_code), intent
