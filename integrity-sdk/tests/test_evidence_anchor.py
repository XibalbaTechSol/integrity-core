"""Real on-chain tests for evidence_anchor.py (B4), against a real local anvil
with `contracts/script/DeployProtocolEvidenceAnchor.s.sol` actually run against it
(not a mock) -- same "prove the eth_call/eth_sendTransaction path for real" bar
`deployed_chain`'s own fixture docstring sets for the rest of this test module.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

from integrity_sdk import evidence_anchor
from integrity_sdk.core.receipt_queue import ReceiptQueue
from integrity_sdk.did import Keypair

from conftest import ANVIL_DEV_PRIVATE_KEY, CONTRACTS_DIR


@pytest.fixture(scope="session")
def evidence_anchor_address(deployed_chain) -> str:
    result = subprocess.run(
        ["forge", "script", "script/DeployProtocolEvidenceAnchor.s.sol", "--rpc-url", deployed_chain["rpc_url"], "--broadcast"],
        cwd=CONTRACTS_DIR,
        capture_output=True,
        text=True,
        env=__import__("os").environ | {"FUNDER_PRIVATE_KEY": ANVIL_DEV_PRIVATE_KEY},
    )
    if result.returncode != 0:
        raise RuntimeError(f"DeployProtocolEvidenceAnchor.s.sol failed:\n{result.stdout}\n{result.stderr}")
    broadcast_path = CONTRACTS_DIR / "broadcast" / "DeployProtocolEvidenceAnchor.s.sol" / str(deployed_chain["chain_id"]) / "run-latest.json"
    broadcast = json.loads(broadcast_path.read_text())
    (address,) = (
        Web3.to_checksum_address(tx["contractAddress"])
        for tx in broadcast["transactions"]
        if tx.get("transactionType") == "CREATE" and tx.get("contractName") == "StateAnchor"
    )
    return address


def test_anchor_checkpoint_root_and_verify_round_trip(deployed_chain, evidence_anchor_address):
    w3 = deployed_chain["w3"]
    account = deployed_chain["funder"]
    root = Web3.keccak(text="evidence-anchor-smoke-test")

    tx_hash = evidence_anchor.anchor_checkpoint_root(w3, account, evidence_anchor_address, deployed_chain["chain_id"], root)
    assert tx_hash

    leaf = Web3.keccak(text="single-leaf-tree")
    # A single-leaf tree's own leaf is its own root, under this protocol's
    # sorted-pair convention with no siblings -- anchor that leaf AS a root,
    # then verify it with an empty proof.
    tx_hash_2 = evidence_anchor.anchor_checkpoint_root(w3, account, evidence_anchor_address, deployed_chain["chain_id"], leaf)
    assert tx_hash_2 != tx_hash
    assert evidence_anchor.verify_root_anchored(w3, evidence_anchor_address, leaf, leaf, [])
    # A root that was never anchored must not verify, even with a technically
    # valid (empty) proof for a matching leaf==root shape.
    never_anchored = Web3.keccak(text="never-anchored")
    assert not evidence_anchor.verify_root_anchored(w3, evidence_anchor_address, never_anchored, never_anchored, [])


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
