from __future__ import annotations

import pytest

from integrity_sdk.core import ReceiptQueue, ReceiptQueueError, hmac_identifier, receipt_hash
from integrity_sdk.did import Keypair


def _append(queue: ReceiptQueue) -> dict:
    return queue.append(
        agent_did="did:integrity:" + "a" * 64,
        device_id_hmac=hmac_identifier(b"k" * 32, "device", "laptop"),
        action_hmac=hmac_identifier(b"k" * 32, "action", "tool.call"),
        event_class="agent.tool_call",
        pack_hash="sha256:" + "a" * 64,
        decision="deny",
        reason_code="TEST",
        mode="enforce",
        timestamp="2026-09-28T12:00:00Z",
    )


def test_queue_survives_restart_and_acknowledges_only_submitted_receipts(tmp_path):
    signer = Keypair.generate()
    path = tmp_path / "receipts.json"
    queue = ReceiptQueue(signer, "shield:device-1", path)
    first = _append(queue)
    second = _append(queue)
    accepted = queue.submit(lambda pending: [receipt_hash(pending[0])])
    assert accepted == [receipt_hash(first)]

    resumed = ReceiptQueue(signer, "shield:device-1", path)
    assert resumed.pending() == [second]


def test_failed_submission_leaves_queue_unchanged(tmp_path):
    queue = ReceiptQueue(Keypair.generate(), "shield:device-1", tmp_path / "receipts.json")
    receipt = _append(queue)
    with pytest.raises(RuntimeError, match="offline"):
        queue.submit(lambda _pending: (_ for _ in ()).throw(RuntimeError("offline")))
    assert queue.pending() == [receipt]


def test_unknown_acknowledgement_is_refused(tmp_path):
    queue = ReceiptQueue(Keypair.generate(), "shield:device-1", tmp_path / "receipts.json")
    _append(queue)
    with pytest.raises(ReceiptQueueError, match="unknown receipt"):
        queue.acknowledge(["0x" + "0" * 64])
