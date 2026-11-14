"""Off-chain registration client. The golden vector is shared with the Oracle's
`signing_message_golden_vector` test in integrity-oracle/backend/src/offchain_registration.rs."""
import json
from unittest import mock

import pytest
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from integrity_sdk import did as did_mod
from integrity_sdk.did import Keypair, fingerprint_for_pubkey
from integrity_sdk.registration_offchain import (
    DOMAIN,
    OffchainRegistration,
    OffchainRegistrationError,
    register_offchain,
    signing_message,
)

GOLDEN_PUBKEY_SEED7_HEX = "ea4a6c63e29c520abef5507b132ec5f9954776aebebe7b92421eea691446d22c"
NOW = 1_800_000_000
URL = "https://oracle.example"


def seed7() -> Keypair:
    return Keypair(Ed25519PrivateKey.from_private_bytes(bytes([7] * 32)))


def did_for(kp: Keypair) -> str:
    return "did:integrity:" + fingerprint_for_pubkey(kp.public_bytes())


def resp(status: int, body=None, text: str = ""):
    r = mock.Mock()
    r.status_code = status
    r.text = text or json.dumps(body or {})
    r.json.return_value = body if body is not None else json.loads(r.text)
    return r


def test_signing_message_matches_oracle_golden_vector():
    kp = seed7()
    assert kp.public_bytes().hex() == GOLDEN_PUBKEY_SEED7_HEX
    did = did_for(kp)
    msg = signing_message(did, "0x" + GOLDEN_PUBKEY_SEED7_HEX.upper(), NOW).decode()
    assert DOMAIN == "integrity.agent.register.offchain.v1"
    assert msg == (
        '{"did":"%s","domain":"integrity.agent.register.offchain.v1",'
        '"ed25519_pubkey_hex":"%s","timestamp":1800000000}' % (did, GOLDEN_PUBKEY_SEED7_HEX)
    )


def test_register_offchain_posts_signed_body():
    kp = Keypair.generate()
    did = did_for(kp)
    with mock.patch("requests.post", return_value=resp(201, {
        "agent_id": "a", "verification_tier": 1, "outcome": "created", "handle": None})) as post:
        register_offchain(URL + "/", did, kp, now=NOW)
        # handle only when given
        assert "handle" not in post.call_args.kwargs["json"]
        register_offchain(URL, did, kp, handle="bob", now=NOW)
    assert post.call_args.args[0] == URL + "/v1/agent/register/offchain"
    body = post.call_args.kwargs["json"]
    assert set(body) == {"did", "ed25519_pubkey_hex", "timestamp", "signature", "handle"}
    assert body["handle"] == "bob"
    assert body["timestamp"] == NOW
    assert body["ed25519_pubkey_hex"] == kp.public_bytes().hex()
    assert did_mod.verify_signature(
        kp.public_bytes(),
        signing_message(did, body["ed25519_pubkey_hex"], NOW),
        bytes.fromhex(body["signature"]),
    )


def test_register_offchain_maps_201_and_200():
    kp = Keypair.generate()
    did = did_for(kp)
    created = {"agent_id": "a", "verification_tier": 1, "outcome": "created", "handle": "h"}
    again = {"agent_id": "a", "verification_tier": 1, "outcome": "already_registered", "handle": None}
    with mock.patch("requests.post", return_value=resp(201, created)):
        r = register_offchain(URL, did, kp, now=NOW)
    assert r == OffchainRegistration("a", 1, "created", "h")
    with mock.patch("requests.post", return_value=resp(200, again)):
        r = register_offchain(URL, did, kp, now=NOW)
    assert r == OffchainRegistration("a", 1, "already_registered", None)


def test_register_offchain_raises_with_status_on_409():
    kp = Keypair.generate()
    with mock.patch("requests.post", return_value=resp(409, {"error": "handle taken"})):
        with pytest.raises(OffchainRegistrationError) as ei:
            register_offchain(URL, did_for(kp), kp, now=NOW)
    assert ei.value.status == 409
    assert ei.value.detail == "handle taken"


def test_register_offchain_unreachable_raises_status_none():
    kp = Keypair.generate()
    with mock.patch("requests.post", side_effect=requests.ConnectionError("down")):
        with pytest.raises(OffchainRegistrationError) as ei:
            register_offchain(URL, did_for(kp), kp, now=NOW)
    assert ei.value.status is None


def test_register_offchain_rejects_did_not_matching_key():
    kp = Keypair.generate()
    with mock.patch("requests.post") as post:
        with pytest.raises(ValueError):
            register_offchain(URL, did_for(Keypair.generate()), kp, now=NOW)
    post.assert_not_called()
