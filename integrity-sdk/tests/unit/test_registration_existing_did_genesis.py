from __future__ import annotations

from types import SimpleNamespace

import pytest

from integrity_sdk import chain, registration


ZERO_ROOT = b"\x00" * 32
NONZERO_ROOT = b"\x01" * 32


class _FakeW3:
    eth = SimpleNamespace(chain_id=84532)

    def is_connected(self) -> bool:
        return True


class _FakeKeypair:
    def public_bytes(self) -> bytes:
        return b"test-ed25519-public-key"


def _existing_primitives() -> chain.PrimitivesRegistered:
    return chain.PrimitivesRegistered(
        did_hash="0x1234",
        sovereign_agent="0x1000000000000000000000000000000000000001",
        controller="0x2000000000000000000000000000000000000002",
        state_anchor="0x3000000000000000000000000000000000000003",
        reputation_registry="0x4000000000000000000000000000000000000004",
        slasher="0x5000000000000000000000000000000000000005",
        verifier_registry="0x6000000000000000000000000000000000000006",
        compliance_gate="0x7000000000000000000000000000000000000007",
        agent_profile="0x8000000000000000000000000000000000000008",
        domain_id="0xabc",
    )


@pytest.fixture
def existing_did_harness(tmp_path, monkeypatch):
    events: list[str] = []
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()

    monkeypatch.setenv(
        "FUNDER_PRIVATE_KEY",
        "0x" + "11" * 32,
    )
    monkeypatch.setattr(registration.chain, "get_w3", lambda _rpc_url: _FakeW3())
    monkeypatch.setattr(
        registration.chain,
        "load_deployments",
        lambda _path: {
            "singletons": {
                "AgentPrimitivesFactory": "0xf000000000000000000000000000000000000001",
                "IntegrityToken": "0xf000000000000000000000000000000000000002",
                "XibalbaAgentRegistry": "0xf000000000000000000000000000000000000003",
                "DomainRegistry": "0xf000000000000000000000000000000000000005",
            },
            "protocolAddresses": {"oracleSigner": "0xf000000000000000000000000000000000000004"},
        },
    )
    monkeypatch.setattr(
        registration.did,
        "load_or_create_did",
        lambda _agent_id: ("did:integrity:existing", _FakeKeypair(), {"id": "did:integrity:existing"}),
    )
    monkeypatch.setattr(
        registration.wallet,
        "generate_or_load_evm_wallet",
        lambda _agent_id: SimpleNamespace(address="0x9000000000000000000000000000000000000009"),
    )
    monkeypatch.setattr(
        registration.did,
        "attach_evm_account",
        lambda doc, _address, _chain_id: {**doc, "attached": True},
    )
    monkeypatch.setattr(registration.did, "agent_dir", lambda _agent_id: agent_dir)
    monkeypatch.setattr(registration.chain, "resolve_did", lambda *_args: _existing_primitives())

    def post_to_oracle(*_args, **_kwargs) -> None:
        events.append("post_to_oracle")

    monkeypatch.setattr(registration, "_post_to_oracle", post_to_oracle)
    return events


def test_existing_primitives_with_zero_root_anchor_genesis_before_oracle_post(
    existing_did_harness, monkeypatch
):
    events = existing_did_harness

    def latest_root(*_args) -> bytes:
        events.append("latest_root")
        return ZERO_ROOT

    def anchor_genesis(*_args) -> str:
        events.append("anchor_genesis")
        return "0xanchor"

    monkeypatch.setattr(registration.chain, "state_anchor_latest_root", latest_root)
    monkeypatch.setattr(registration.chain, "anchor_genesis_root", anchor_genesis)

    result = registration.register_agent("existing-agent")

    assert result.sovereign_agent == _existing_primitives().sovereign_agent
    assert events == ["latest_root", "anchor_genesis", "post_to_oracle"]


def test_existing_primitives_with_nonzero_root_do_not_reanchor(existing_did_harness, monkeypatch):
    events = existing_did_harness

    def latest_root(*_args) -> bytes:
        events.append("latest_root")
        return NONZERO_ROOT

    def anchor_genesis(*_args) -> str:
        events.append("anchor_genesis")
        return "0xanchor"

    monkeypatch.setattr(registration.chain, "state_anchor_latest_root", latest_root)
    monkeypatch.setattr(registration.chain, "anchor_genesis_root", anchor_genesis)

    registration.register_agent("existing-agent")

    assert events == ["latest_root", "post_to_oracle"]


def test_existing_primitives_anchor_failure_is_registration_error_without_oracle_post(
    existing_did_harness, monkeypatch
):
    events = existing_did_harness

    def latest_root(*_args) -> bytes:
        events.append("latest_root")
        return ZERO_ROOT

    def anchor_genesis(*_args) -> str:
        events.append("anchor_genesis")
        raise RuntimeError("simulated anchor failure")

    monkeypatch.setattr(registration.chain, "state_anchor_latest_root", latest_root)
    monkeypatch.setattr(registration.chain, "anchor_genesis_root", anchor_genesis)

    with pytest.raises(registration.RegistrationError, match="step 8b .*anchor_genesis_root"):
        registration.register_agent("existing-agent")

    assert events == ["latest_root", "anchor_genesis"]
