"""Registration v3 Phase 4, PR 4.4: the SDK side of `register --onchain`.

The digest golden vector is the one the Oracle pins in
`integrity-oracle/backend/src/onchain_registration.rs::digest_matches_independent_eip712_vector`,
so the digest the agent signs and the digest the Oracle attests can never drift apart silently.
"""
from __future__ import annotations

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from web3.exceptions import ContractCustomError

from integrity_sdk import registration_onchain as ro
from integrity_sdk.did import Keypair, fingerprint_for_pubkey

GOLDEN_REGISTRY = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
GOLDEN_DIGEST = "0bbab02f7088d62ff5d3fe5df3b43061122f0e797f6b1b971498a62fdffcfa69"
GOLDEN_FIELDS = dict(
    pubkey=b"\x11" * 32,
    guardian="0x" + "22" * 20,
    actor="0x" + "33" * 20,
    domain_id=b"\x44" * 32,
    uri="ipfs://x",
    deadline=1_700_000_000,
)
REGISTRY = "0x" + "ab" * 20
GUARDIAN = "0x" + "cd" * 20


def test_register_digest_matches_the_oracle_golden_vector():
    assert ro.register_digest(31337, GOLDEN_REGISTRY, **GOLDEN_FIELDS).hex() == GOLDEN_DIGEST


def test_register_digest_binds_the_domain_and_every_field():
    base = ro.register_digest(31337, GOLDEN_REGISTRY, **GOLDEN_FIELDS)
    assert ro.register_digest(84532, GOLDEN_REGISTRY, **GOLDEN_FIELDS) != base
    assert ro.register_digest(31337, REGISTRY, **GOLDEN_FIELDS) != base
    for field, value in [("actor", ro.ZERO_ADDRESS), ("uri", "ipfs://y"), ("deadline", 1_700_000_001),
                         ("domain_id", b"\x45" * 32), ("guardian", GUARDIAN), ("pubkey", b"\x12" * 32)]:
        assert ro.register_digest(31337, GOLDEN_REGISTRY, **{**GOLDEN_FIELDS, field: value}) != base, field


def test_domain_id_accepts_a_name_or_bytes32():
    from eth_utils import keccak

    assert ro.domain_id("general.integrity") == keccak(text="general.integrity")
    assert ro.domain_id("0x" + "44" * 32) == b"\x44" * 32
    with pytest.raises(ValueError):
        ro.domain_id("0x1234")


class _Resp:
    def __init__(self, status: int, payload):
        self.status_code, self._payload = status, payload
        self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _agent():
    kp = Keypair.generate()
    return kp, "did:integrity:" + fingerprint_for_pubkey(kp.public_bytes())


def _oracle_reply(kp, *, digest: bytes, actor: str, domain: bytes, deadline: int, chain_id=31337, registry=REGISTRY):
    return {
        "agent_id": "x", "digest": "0x" + digest.hex(), "attestation": "0x" + "ee" * 65,
        "attester": "0x" + "99" * 20, "proof_kind": 1, "chain_id": chain_id, "agent_registry": registry,
        "pubkey": "0x" + kp.public_bytes().hex(), "guardian": GUARDIAN, "actor": actor,
        "domain_id": "0x" + domain.hex(), "uri": "", "deadline": deadline,
    }


def test_request_attestation_signs_the_local_digest_and_posts_the_fields(monkeypatch):
    kp, did = _agent()
    actor, domain, deadline = "0x" + "33" * 20, b"\x44" * 32, 1_900_000_000
    digest = ro.register_digest(31337, REGISTRY, pubkey=kp.public_bytes(), guardian=GUARDIAN, actor=actor,
                                domain_id=domain, uri="", deadline=deadline)
    seen = {}

    def post(url, json, timeout):
        seen["url"], seen["body"] = url, json
        return _Resp(200, _oracle_reply(kp, digest=digest, actor=actor, domain=domain, deadline=deadline))

    monkeypatch.setattr(ro.requests, "post", post)
    att = ro.request_attestation("http://oracle/", did, kp, chain_id=31337, agent_registry=REGISTRY,
                                 guardian=GUARDIAN, actor=actor, domain=domain, uri="", deadline=deadline)

    assert seen["url"] == f"http://oracle/v1/agent/{did}/onchain/attestation"
    body = seen["body"]
    assert body["guardian"].lower() == GUARDIAN and body["actor"].lower() == actor
    assert body["domain_id"] == "0x" + domain.hex() and body["deadline"] == deadline and body["uri"] == ""
    # The agent's Ed25519 signature verifies over exactly the digest AgentRegistry recomputes.
    Ed25519PublicKey.from_public_bytes(kp.public_bytes()).verify(bytes.fromhex(body["signature"]), digest)
    assert att.attestation == b"\xee" * 65 and att.digest == digest and att.proof_kind == 1


def test_request_attestation_refuses_an_oracle_that_attested_another_digest(monkeypatch):
    """An Oracle wired to another chain or registry would hand back a proof `register` reverts on:
    refuse before spending gas."""
    kp, did = _agent()
    other = b"\x01" * 32
    monkeypatch.setattr(ro.requests, "post", lambda url, json, timeout: _Resp(
        200, _oracle_reply(kp, digest=other, actor=ro.ZERO_ADDRESS, domain=b"\x00" * 32, deadline=1_900_000_000)))
    with pytest.raises(ro.OnchainRegistrationError) as e:
        ro.request_attestation("http://oracle", did, kp, chain_id=31337, agent_registry=REGISTRY,
                               guardian=GUARDIAN, deadline=1_900_000_000)
    assert e.value.status is None and "digest" in e.value.detail
    assert e.value.stage == "attestation"


def test_request_attestation_maps_http_refusals_and_outages(monkeypatch):
    kp, did = _agent()
    monkeypatch.setattr(ro.requests, "post", lambda url, json, timeout: _Resp(404, {"error": "no off-chain row"}))
    with pytest.raises(ro.OnchainRegistrationError) as e:
        ro.request_attestation("http://oracle", did, kp, chain_id=1, agent_registry=REGISTRY,
                               guardian=GUARDIAN, deadline=1_900_000_000)
    assert e.value.status == 404 and e.value.detail == "no off-chain row" and not e.value.unreachable

    def down(url, json, timeout):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(ro.requests, "post", down)
    with pytest.raises(ro.OnchainRegistrationError) as e:
        ro.request_attestation("http://oracle", did, kp, chain_id=1, agent_registry=REGISTRY,
                               guardian=GUARDIAN, deadline=1_900_000_000)
    assert e.value.status is None and e.value.unreachable

    monkeypatch.setattr(ro.requests, "post", lambda url, json, timeout: _Resp(503, {"error": "no registry"}))
    with pytest.raises(ro.OnchainRegistrationError) as e:
        ro.sync_onchain("http://oracle", did)
    assert e.value.status == 503 and e.value.unreachable and e.value.stage == "sync"


def test_revert_name_decodes_registry_custom_errors():
    from eth_utils import keccak

    selector = "0x" + keccak(text="AlreadyRegistered(bytes32)")[:4].hex()
    exc = ContractCustomError(selector + "00" * 32, data=selector + "00" * 32)
    assert ro.revert_name(exc) == "AlreadyRegistered"
    assert ro.revert_name(ContractCustomError("0xdeadbeef", data="0xdeadbeef")) is None
    assert ro.revert_name(ValueError("not a revert")) is None
