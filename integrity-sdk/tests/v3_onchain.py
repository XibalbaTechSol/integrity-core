"""Shared on-chain helpers for the anvil suites: v3 `AgentRegistry` binding and AIS checkpoints.

Registration v3 Phase 3: the execute gate, AISRegistry, XNS, lineage and EHRGate read the
v3 `AgentRegistry`. Until PR 3.4 gives the SDK a v3 onboarding path, the suites bind agents
here, the way production does: an oracle attester (on anvil, the deployer;
`ATTESTER_ADDRESS` defaults to it locally) signs the register digest, and the agent consents
via EIP-1271 with its controller's signature. Both are raw EIP-712 digests, so
`unsafe_sign_hash` over the contract's own digest getters is exact.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from eth_utils import keccak
from web3 import Web3

CONTRACTS_OUT = Path(__file__).resolve().parents[2] / "contracts" / "out"


def artifact(name: str) -> dict:
    return json.loads((CONTRACTS_OUT / f"{name}.sol" / f"{name}.json").read_text())


def send(w3, signer, fn, chain_id):
    tx = fn.build_transaction(
        {"from": signer.address, "nonce": w3.eth.get_transaction_count(signer.address), "chainId": chain_id}
    )
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.send_raw_transaction(signer.sign_transaction(tx).raw_transaction), timeout=30
    )
    assert receipt.status == 1
    return receipt


def fund(w3, funder, to, chain_id, wei=10**18):
    tx = {
        "to": to, "value": wei, "gas": 21000, "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(funder.address), "chainId": chain_id,
    }
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(funder.sign_transaction(tx).raw_transaction))


def deploy_canonical_agent(w3, chain_id, controller, registry_address, did):
    """A SovereignAgent built for `registry_address` (registry pin = registry): the only
    shape the registry's codehash pin accepts as an actor. `controller` must hold gas."""
    sa = artifact("SovereignAgent")
    factory = w3.eth.contract(abi=sa["abi"], bytecode=sa["bytecode"]["object"])
    receipt = send(w3, controller, factory.constructor(did, controller.address, registry_address), chain_id)
    return Web3.to_checksum_address(receipt.contractAddress)


def bind(w3, chain_id, attester, controller, registry_address, agent, domain_name="general.integrity", pubkey=None):
    """Creates a record for `pubkey` (fresh if omitted) and binds `agent` as its actor in `domain_name`.
    The record's DID is `did:integrity:` + sha256(pubkey), so pass `pubkey` to resolve it afterwards."""
    registry = w3.eth.contract(address=registry_address, abi=artifact("AgentRegistry")["abi"])
    pubkey = pubkey if pubkey is not None else os.urandom(32)
    domain_id = keccak(text=domain_name)
    deadline = w3.eth.get_block("latest")["timestamp"] + 3600
    proof = attester.unsafe_sign_hash(
        registry.functions.registerDigest(pubkey, controller.address, agent, domain_id, "", deadline).call()
    ).signature
    consent = controller.unsafe_sign_hash(
        registry.functions.bindActorDigest(hashlib.sha256(pubkey).digest(), agent, deadline).call()
    ).signature
    send(
        w3, attester,
        registry.functions.register(pubkey, controller.address, agent, domain_id, "", deadline, 1, proof, consent),
        chain_id,
    )
    assert registry.functions.isRegisteredAgent(agent).call()


_POST_CHECKPOINT_ABI = [{
    "type": "function", "name": "postCheckpoint", "stateMutability": "nonpayable", "outputs": [],
    "inputs": [
        {"name": "agent", "type": "address"}, {"name": "score", "type": "uint32"},
        {"name": "epoch", "type": "uint64"}, {"name": "root", "type": "bytes32"},
        {"name": "reward", "type": "uint256"},
    ],
}]


def post_ais(w3, chain_id, scorer, ais_registry_address, agent, score_bps, epoch=1):
    """Posts an AIS checkpoint (basis points, 0..10000). On anvil the deployer holds the scorer role."""
    ais = w3.eth.contract(address=ais_registry_address, abi=_POST_CHECKPOINT_ABI)
    send(w3, scorer, ais.functions.postCheckpoint(agent, score_bps, epoch, b"\x33" * 32, 0), chain_id)
