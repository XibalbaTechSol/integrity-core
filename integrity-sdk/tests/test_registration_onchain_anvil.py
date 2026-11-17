"""PR 4.4 on Anvil: `register_onchain` against the real Deploy.s.sol `AgentRegistry`.

The Oracle is stood in for at the HTTP boundary by `FakeOracle`, which does what the real
handlers do (PR 4.3, proven by `integrity-oracle/backend/tests/e2e.rs`): it verifies the agent's
Ed25519 signature over the digest the *contract* computes (`registerDigest`), signs that digest
with the attester key (Anvil's deployer holds ATTESTER_ROLE locally), and syncs by reading
`resolveDID` from the chain.
"""
from __future__ import annotations

import os

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from eth_account import Account
from eth_utils import keccak
from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError

from integrity_sdk import chain
from integrity_sdk import registration_onchain as ro
from integrity_sdk.did import Keypair, fingerprint_for_pubkey

GENERAL = keccak(text="general.integrity")


class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code, self._payload, self.text = status, payload, str(payload)

    def json(self):
        return self._payload


class FakeOracle:
    def __init__(self, w3, registry_address: str, chain_id: int, attester):
        self.w3, self.chain_id, self.attester = w3, chain_id, attester
        self.registry_address = registry_address
        self.registry = chain._contract(w3, "AgentRegistry", address=registry_address)
        self.keys: dict[str, bytes] = {}
        self.calls: list[str] = []

    def post(self, url: str, json: dict, timeout: float):
        path = url.split("://", 1)[1].split("/", 1)[1]
        self.calls.append(path)
        if path == "v1/agent/register/offchain":
            self.keys[json["did"]] = bytes.fromhex(json["ed25519_pubkey_hex"])
            return _Resp(201, {"agent_id": json["did"], "verification_tier": 1, "outcome": "created"})
        did = path.split("/")[2]  # v1/agent/<did>/onchain/<step>
        if path.endswith("/onchain/attestation"):
            pubkey = self.keys.get(did)
            if pubkey is None:
                return _Resp(404, {"error": "no off-chain registration"})
            dom = bytes.fromhex(json["domain_id"][2:])
            digest = self.registry.functions.registerDigest(
                pubkey, json["guardian"], json["actor"], dom, json["uri"], json["deadline"]
            ).call()
            try:
                Ed25519PublicKey.from_public_bytes(pubkey).verify(bytes.fromhex(json["signature"]), digest)
            except InvalidSignature:
                return _Resp(401, {"error": "bad signature"})
            return _Resp(200, {
                "agent_id": did, "digest": "0x" + digest.hex(),
                "attestation": "0x" + self.attester.unsafe_sign_hash(digest).signature.hex(),
                "attester": self.attester.address, "proof_kind": 1, "chain_id": self.chain_id,
                "agent_registry": self.registry_address, "pubkey": "0x" + pubkey.hex(),
                "guardian": json["guardian"], "actor": json["actor"], "domain_id": json["domain_id"],
                "uri": json["uri"], "deadline": json["deadline"],
            })
        if path.endswith("/onchain/sync"):
            rec = self.registry.functions.resolveDID(did).call()
            if not rec[5]:
                return _Resp(404, {"error": "not registered on-chain"})
            actor = None if int(rec[2], 16) == 0 else rec[2]
            return _Resp(200, {"agent_id": did, "actor": actor, "guardian": rec[1], "active": rec[6] == 0,
                               "settlement_eligible": actor is not None and rec[6] == 0})
        return _Resp(404, {"error": f"no route {path}"})


@pytest.fixture
def setup(deployed_chain, monkeypatch):
    w3 = deployed_chain["w3"]
    oracle = FakeOracle(w3, deployed_chain["addresses"]["AgentRegistry"], deployed_chain["chain_id"],
                        deployed_chain["funder"])
    monkeypatch.setattr(ro.requests, "post", oracle.post)
    guardian = Account.create()
    w3.eth.wait_for_transaction_receipt(w3.eth.send_transaction(
        {"from": deployed_chain["funder"].address, "to": guardian.address, "value": 10**18}))
    kp = Keypair.generate()
    did = "did:integrity:" + fingerprint_for_pubkey(kp.public_bytes())
    return w3, oracle, guardian, kp, did


def test_local_digest_equals_the_registry_digest(deployed_chain):
    registry_address = deployed_chain["addresses"]["AgentRegistry"]
    registry = chain._contract(deployed_chain["w3"], "AgentRegistry", address=registry_address)
    for actor, dom, uri in [(ro.ZERO_ADDRESS, ro.ZERO_BYTES32, ""), (Account.create().address, os.urandom(32), "ipfs://a")]:
        pubkey, guardian, deadline = os.urandom(32), Account.create().address, 1_900_000_123
        assert ro.register_digest(deployed_chain["chain_id"], registry_address, pubkey=pubkey, guardian=guardian,
                                  actor=actor, domain_id=dom, uri=uri, deadline=deadline) == \
            registry.functions.registerDigest(pubkey, guardian, actor, dom, uri, deadline).call()


def test_confined_registration_binds_the_agent_as_actor_in_one_register(setup, deployed_chain):
    w3, oracle, guardian, kp, did = setup
    registry_address = deployed_chain["addresses"]["AgentRegistry"]

    result = ro.register_onchain(w3, "http://oracle", did, kp, guardian, registry_address,
                                 confined=True, domain=GENERAL)

    registry = chain._contract(w3, "AgentRegistry", address=registry_address)
    rec = registry.functions.resolveDID(did).call()
    assert rec[0] == kp.public_bytes() and rec[1] == guardian.address and rec[3] == GENERAL
    assert rec[2] == result.actor and registry.functions.isRegisteredAgent(result.actor).call()
    sa = chain._contract(w3, "SovereignAgent", address=result.actor)
    assert sa.functions.hasRole(sa.functions.DEFAULT_ADMIN_ROLE().call(), guardian.address).call()
    assert result.outcome == "registered" and result.record["settlement_eligible"] is True
    assert [c.rsplit("/", 1)[-1] for c in oracle.calls] == ["offchain", "attestation", "sync"]


def test_existence_only_registration_has_no_actor(setup, deployed_chain):
    w3, _, guardian, kp, did = setup
    result = ro.register_onchain(w3, "http://oracle", did, kp, guardian, deployed_chain["addresses"]["AgentRegistry"])
    assert result.actor is None and result.record["actor"] is None
    assert result.record["settlement_eligible"] is False


def test_rerun_is_idempotent_and_sends_nothing(setup, deployed_chain, monkeypatch):
    w3, oracle, guardian, kp, did = setup
    registry_address = deployed_chain["addresses"]["AgentRegistry"]
    first = ro.register_onchain(w3, "http://oracle", did, kp, guardian, registry_address, confined=True, domain=GENERAL)

    def no_send(*_a, **_k):
        raise AssertionError("an already-registered DID must not send a transaction")

    monkeypatch.setattr(chain, "_send_signed", no_send)
    monkeypatch.setattr(chain, "deploy_sovereign_agent", no_send)
    again = ro.register_onchain(w3, "http://oracle", did, kp, guardian, registry_address, confined=True, domain=GENERAL)
    assert again.outcome == "already_registered" and again.actor == first.actor and again.tx is None


def test_a_revert_surfaces_with_its_decoded_name(setup, deployed_chain):
    """An unknown domain: `register` reverts DomainJoinNotAllowed before anything is written."""
    w3, _, guardian, kp, did = setup
    with pytest.raises((ContractCustomError, ContractLogicError)) as e:
        ro.register_onchain(w3, "http://oracle", did, kp, guardian, deployed_chain["addresses"]["AgentRegistry"],
                            confined=True, domain=keccak(text="no-such-domain.integrity"))
    assert ro.revert_name(e.value) == "DomainJoinNotAllowed"
    registry = chain._contract(w3, "AgentRegistry", address=deployed_chain["addresses"]["AgentRegistry"])
    assert registry.functions.resolveDID(did).call()[5] == 0
