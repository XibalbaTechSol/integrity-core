"""Real on-chain tests for evidence_anchor.py (B4), against a real local anvil running the
real `Deploy.s.sol` (not a mock).

v2 graph deletion, slice D1 (owner question 8a): evidence roots anchor on the shared
`ActionAnchor` singleton, keyed by the signer that submits them -- one slot per anchoring
service. `ActionAnchor` keeps only the latest root in storage, so an older checkpoint is proved
anchored by its `RootAnchored(anchorer, epoch, root)` event, and its leaf by the local Merkle
check against that root.
"""
from __future__ import annotations

import pytest
from eth_account import Account
from web3 import Web3

from integrity_sdk import evidence_anchor
from integrity_sdk.core import merkle
from integrity_sdk.core.receipt_queue import ReceiptQueue
from integrity_sdk.did import Keypair

import v3_onchain


@pytest.fixture(scope="session")
def evidence_anchor_address(deployed_chain) -> str:
    return deployed_chain["addresses"]["ActionAnchor"]


def test_anchor_checkpoint_root_and_verify_round_trip(deployed_chain, evidence_anchor_address):
    w3 = deployed_chain["w3"]
    account = deployed_chain["funder"]
    leaves = [Web3.keccak(text=f"evidence-{i}") for i in range(4)]
    first_root = merkle.merkle_root(leaves)

    tx_hash = evidence_anchor.anchor_checkpoint_root(w3, account, evidence_anchor_address, deployed_chain["chain_id"], first_root)
    assert tx_hash

    # A later checkpoint replaces the latest root; the earlier one must stay verifiable.
    later = Web3.keccak(text="single-leaf-tree")
    tx_hash_2 = evidence_anchor.anchor_checkpoint_root(w3, account, evidence_anchor_address, deployed_chain["chain_id"], later)
    assert tx_hash_2 != tx_hash

    proof = merkle.merkle_proof(leaves, 2)
    assert evidence_anchor.verify_root_anchored(w3, evidence_anchor_address, account.address, first_root, leaves[2], proof)
    assert evidence_anchor.verify_root_anchored(w3, evidence_anchor_address, account.address, later, later, [])
    # A leaf not in the tree fails the Merkle half, even under a genuinely anchored root.
    assert not evidence_anchor.verify_root_anchored(
        w3, evidence_anchor_address, account.address, first_root, Web3.keccak(text="outsider"), proof
    )
    # A root that was never anchored must not verify, even with a matching leaf==root shape.
    never_anchored = Web3.keccak(text="never-anchored")
    assert not evidence_anchor.verify_root_anchored(w3, evidence_anchor_address, account.address, never_anchored, never_anchored, [])


def test_a_root_anchored_by_another_signer_does_not_verify(deployed_chain, evidence_anchor_address):
    """The anchorer IS the namespace: someone else's root is not this service's evidence."""
    w3 = deployed_chain["w3"]
    chain_id = deployed_chain["chain_id"]
    stranger = Account.create()
    v3_onchain.fund(w3, deployed_chain["funder"], stranger.address, chain_id)
    root = Web3.keccak(text="stranger-root")
    evidence_anchor.anchor_checkpoint_root(w3, stranger, evidence_anchor_address, chain_id, root)

    assert evidence_anchor.verify_root_anchored(w3, evidence_anchor_address, stranger.address, root, root, [])
    assert not evidence_anchor.verify_root_anchored(
        w3, evidence_anchor_address, deployed_chain["funder"].address, root, root, []
    )


def test_anchor_pending_receipts_checkpoints_and_acknowledges(deployed_chain, evidence_anchor_address, tmp_path):
    w3 = deployed_chain["w3"]
    account = deployed_chain["funder"]
    signer = Keypair.generate()
    queue = ReceiptQueue(signer, "evidence-anchor-test-log", tmp_path / "queue.json")
    queue.append(
        agent_did="did:integrity:test", device_id_hmac="hmac-sha256:" + "11" * 32,
        action_hmac="hmac-sha256:" + "22" * 32, event_class="agent_event", pack_hash="0x" + "33" * 32,
        decision="deny", reason_code="TEST", mode="enforce",
    )
    assert len(queue.pending()) == 1

    accepted = evidence_anchor.anchor_pending_receipts(queue, w3, account, evidence_anchor_address, deployed_chain["chain_id"])

    assert len(accepted) == 1
    assert queue.pending() == []  # acknowledged

    # Re-loading the same durable queue file confirms the acknowledgement persisted.
    reloaded = ReceiptQueue(signer, "evidence-anchor-test-log", tmp_path / "queue.json")
    assert reloaded.pending() == []


def test_anchor_pending_receipts_leaves_queue_pending_on_submission_failure(tmp_path):
    signer = Keypair.generate()
    queue = ReceiptQueue(signer, "evidence-anchor-failure-log", tmp_path / "queue.json")
    queue.append(
        agent_did="did:integrity:test", device_id_hmac="hmac-sha256:" + "11" * 32,
        action_hmac="hmac-sha256:" + "22" * 32, event_class="agent_event", pack_hash="0x" + "33" * 32,
        decision="deny", reason_code="TEST", mode="enforce",
    )
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:1"))  # unreachable, deliberately
    account = Account.create()

    with pytest.raises(Exception):
        evidence_anchor.anchor_pending_receipts(queue, w3, account, "0x0000000000000000000000000000000000000000", 1)

    # Nothing was acknowledged -- the next recovery attempt will retry the same receipt.
    assert len(queue.pending()) == 1
