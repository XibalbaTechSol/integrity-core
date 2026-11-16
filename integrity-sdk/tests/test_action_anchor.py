"""v2 graph deletion, slice D1: vault anchoring lands on the shared `ActionAnchor`, keyed by actor.

`ActionAnchor` keys every root on `msg.sender`. The v3 actor is the agent's `SovereignAgent`
(`AgentRegistry.resolveDID(did).actor`), so a vault root must be anchored THROUGH
`SovereignAgent.execute`: called from the controller EOA directly, the root lands under the
controller's address and the actor's `latestRoot` never moves (the mutation this suite pins).

An agent with no bound actor (owner question 8b) gets a typed `NO_ACTOR` result and no
transaction: its vault stays local and verifiable off-chain.
"""

from __future__ import annotations

import pytest
from eth_account import Account
from web3 import Web3

import v3_onchain
from integrity_sdk import chain
from integrity_sdk.core import merkle


def _bound_agent(deployed_chain, did):
    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    funder = deployed_chain["funder"]
    registry = deployed_chain["addresses"]["AgentRegistry"]
    controller = Account.create()
    v3_onchain.fund(w3, funder, controller.address, chain_id)
    actor = v3_onchain.deploy_canonical_agent(w3, chain_id, controller, registry, did)
    v3_onchain.bind(w3, chain_id, funder, controller, registry, actor)
    return actor, controller


def _deployments(deployed_chain) -> dict:
    addr = deployed_chain["addresses"]
    return {"singletons": {"AgentRegistry": addr["AgentRegistry"], "ActionAnchor": addr["ActionAnchor"]}}


def _action_anchor(deployed_chain):
    return chain._contract(deployed_chain["w3"], "ActionAnchor", address=deployed_chain["addresses"]["ActionAnchor"])


def test_resolve_actor_reads_agent_registry(deployed_chain):
    did = "did:integrity:d1-resolve"
    actor, _ = _bound_agent(deployed_chain, did)
    registry = deployed_chain["addresses"]["AgentRegistry"]
    assert chain.resolve_actor(deployed_chain["w3"], registry, did) == actor
    assert chain.resolve_actor(deployed_chain["w3"], registry, "did:integrity:d1-nobody") is None


def test_vault_root_is_anchored_under_the_actor_and_verifies(deployed_chain):
    w3 = deployed_chain["w3"]
    did = "did:integrity:d1-anchor"
    actor, controller = _bound_agent(deployed_chain, did)

    leaves = [Web3.keccak(text=f"vault-entry-{i}") for i in range(3)]
    root = merkle.merkle_root(leaves)

    result = chain.anchor_vault_root_for_did(
        w3, controller, did, _deployments(deployed_chain), deployed_chain["chain_id"], root
    )

    assert result.status == "anchored"
    assert result.actor == actor
    assert result.tx_hash
    anchor = _action_anchor(deployed_chain)
    # The root lands under the ACTOR (the SovereignAgent), not the controller EOA that signed.
    assert anchor.functions.latestRoot(actor).call() == root
    assert anchor.functions.latestRoot(controller.address).call() == b"\x00" * 32

    proof = merkle.merkle_proof(leaves, 1)
    assert anchor.functions.verifyLeaf(actor, leaves[1], proof).call() is True
    outsider = Web3.keccak(text="not-in-the-vault")
    assert anchor.functions.verifyLeaf(actor, outsider, proof).call() is False
    assert chain.actor_latest_root(w3, deployed_chain["addresses"]["ActionAnchor"], actor) == root


def test_genesis_root_defaults_to_the_empty_vault_sentinel(deployed_chain):
    w3 = deployed_chain["w3"]
    actor, controller = _bound_agent(deployed_chain, "did:integrity:d1-genesis")
    chain.anchor_genesis_root(
        w3, controller, actor, deployed_chain["addresses"]["ActionAnchor"], deployed_chain["chain_id"]
    )
    assert _action_anchor(deployed_chain).functions.latestRoot(actor).call() == chain.genesis_vault_root()


class _SendForbidden(AssertionError):
    pass


def test_agent_without_an_actor_gets_no_actor_and_sends_nothing(deployed_chain, monkeypatch):
    w3 = deployed_chain["w3"]
    real_make_request = w3.provider.make_request
    sent: list[str] = []

    def guarded(method, params):
        if method in ("eth_sendRawTransaction", "eth_sendTransaction"):
            sent.append(method)
            raise _SendForbidden(f"{method} must not be called for an agent with no actor")
        return real_make_request(method, params)

    monkeypatch.setattr(w3.provider, "make_request", guarded)

    controller = Account.create()
    result = chain.anchor_vault_root_for_did(
        w3, controller, "did:integrity:d1-off-chain-only", _deployments(deployed_chain),
        deployed_chain["chain_id"], Web3.keccak(text="local-only-root"),
    )

    assert result.status == chain.NO_ACTOR
    assert result.actor is None
    assert result.tx_hash is None
    assert sent == []


def test_missing_action_anchor_in_deployments_is_a_clear_error(deployed_chain):
    with pytest.raises(chain.AnchorConfigError) as excinfo:
        chain.anchor_vault_root_for_did(
            deployed_chain["w3"], Account.create(), "did:integrity:x",
            {"singletons": {"AgentRegistry": deployed_chain["addresses"]["AgentRegistry"]}},
            deployed_chain["chain_id"], Web3.keccak(text="r"),
        )
    assert "ActionAnchor" in str(excinfo.value)
