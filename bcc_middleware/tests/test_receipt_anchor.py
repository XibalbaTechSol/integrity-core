"""Closed receipt epochs are anchored on-chain, and that makes their removal detectable (app/receipt_anchor.py).

REAL anvil, REAL contract, REAL signed receipts. The roots the audit compares against are read back from the contract's
`RootAnchored` events, not from anything the test computed, so "detectable" is checked against what the chain actually holds.
"""

from __future__ import annotations

import asyncio
import json
import shutil

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.gate_receipts import BccReceipts
from app.receipt_anchor import _sweep_lock, anchor_pending_epochs
from integrity_sdk.core import ReceiptSetupError, ReceiptWriteError, verify_epoch_directory
from integrity_sdk.did import Keypair

HMAC_KEY = bytes(range(32))
ANCHOR_EVENT_ABI = [{"anonymous": False, "type": "event", "name": "RootAnchored",
                     "inputs": [{"indexed": True, "name": "root", "type": "bytes32"}, {"indexed": True, "name": "index", "type": "uint256"}]}]
TOKEN = "t" * 40


class World:
    def __init__(self, tmp_path, anvil_chain, **overrides):
        self.tmp, self.chain = tmp_path, anvil_chain
        pem, hmac = tmp_path / "receipt.pem", tmp_path / "receipt.hmac"
        pem.write_bytes(Keypair.generate().private_pem())
        hmac.write_bytes(HMAC_KEY)
        pem.chmod(0o600), hmac.chmod(0o600)
        deployments = tmp_path / "deployments.json"
        deployments.write_text(json.dumps({"singletons": {"ProtocolEvidenceAnchor": anvil_chain["anchor_address"]}}))
        self.dir = tmp_path / "receipts"
        values = dict(
            receipt_dir=str(self.dir), receipt_key_file=str(pem), receipt_hmac_key_file=str(hmac), receipt_checkpoint_every=1,
            receipt_epoch_max_receipts=2, receipt_epoch_max_age_seconds=0, receipt_anchor_enabled=True,
            rpc_url=anvil_chain["rpc_url"], chain_id=anvil_chain["chain_id"], deployments_file=str(deployments),
            anchor_signer_private_key=anvil_chain["signer_private_key"],
        )
        values.update(overrides)
        self.settings = Settings(**values)
        self.receipts = BccReceipts.from_settings(self.settings)
        self.start_block = anvil_chain["w3"].eth.block_number

    async def record(self, count: int):
        for _ in range(count):
            result = await self.receipts.record(agent_id="did:integrity:x", intent_type="payment", intended_state_hash="0x1",
                                                permit=True, reason_code="R", pack_hash=None, controls=(), shadow=False)
            assert result.ref is not None, result.error

    def chain_roots(self) -> list[str]:
        """Every root this test's anchoring put on the (shared) mock contract, read back from its events."""
        w3 = self.chain["w3"]
        if w3.eth.block_number <= self.start_block:
            return []  # nothing was mined since this test began
        contract = w3.eth.contract(address=self.chain["anchor_address"], abi=ANCHOR_EVENT_ABI)
        events = contract.events.RootAnchored().get_logs(from_block=self.start_block + 1)
        return ["0x" + e["args"]["root"].hex() for e in events]

    def audit(self, **kwargs):
        return verify_epoch_directory(self.dir, base_log_id=self.base_log_id(), trusted_signers=[self.receipts.signer_key], **kwargs)

    def base_log_id(self) -> str:
        return self.receipts.health()["log_id"].rsplit(".e", 1)[0]


@pytest.fixture()
def world(tmp_path, anvil_chain):
    w = World(tmp_path, anvil_chain)
    yield w
    w.receipts.close()


# -------------------------------------------------------------------------------- anchoring


async def test_a_sweep_anchors_every_closed_epoch_once_and_only_closed_ones(world):
    await world.record(5)  # epochs 1 and 2 closed (2 receipts each), epoch 3 open with 1
    pending = world.receipts.pending_anchors()
    assert [c.epoch for c in pending] == [1, 2]

    sweep = await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    assert (sweep.attempted, sweep.anchored, sweep.failed, sweep.skipped) == (2, 2, 0, False)
    assert world.chain_roots() == [c.root for c in pending], "oldest first, each epoch's SIGNED final root, the open epoch not at all"
    assert world.receipts.pending_anchors() == [] and world.receipts.health()["pending_anchors"] == 0

    again = await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    assert (again.attempted, again.anchored) == (0, 0) and len(world.chain_roots()) == 2, "idempotent: nothing anchored twice"


async def test_an_epoch_that_closes_later_is_anchored_by_the_next_sweep(world):
    await world.record(5)
    await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    await world.record(1)  # epoch 3 reaches 2 receipts
    await world.record(1)  # rotates: epoch 3 closes
    sweep = await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    assert (sweep.attempted, sweep.anchored) == (1, 1)
    assert len(world.chain_roots()) == 3


async def test_removing_the_newest_closed_epoch_is_detected_against_the_chain(world):
    """The point of the whole feature, checked against the roots the CHAIN holds."""
    await world.record(5)
    await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    roots = world.chain_roots()
    world.receipts.close()
    audits = world.audit(anchored_roots=roots)
    assert [(a.number, a.anchored) for a in audits] == [(1, True), (2, True), (3, False)]

    shutil.rmtree(world.dir / "epoch-000003")
    shutil.rmtree(world.dir / "epoch-000002")
    (world.dir / "anchors.jsonl").unlink()  # the attacker also removes the local ledger
    with pytest.raises(ReceiptSetupError, match="match no epoch"):
        world.audit(anchored_roots=roots)
    # Without the chain, the same removal is invisible -- which is exactly what anchoring fixes.
    assert len(world.audit()) == 1


# ------------------------------------------------------------------------- best-effort failures


async def test_an_unreachable_chain_leaves_epochs_pending_and_stops_at_the_first_failure(world, tmp_path):
    await world.record(5)
    dead = Settings(**{**world.settings.__dict__, "rpc_url": "http://127.0.0.1:1"})
    sweep = await asyncio.to_thread(anchor_pending_epochs, dead, world.receipts)
    assert (sweep.attempted, sweep.anchored, sweep.failed) == (1, 0, 1), "one attempt, not one per epoch"
    assert "unreachable" in sweep.details[0] and "anchored (tx" not in sweep.details[0], "a failed submission is not reported as anchored"
    assert [c.epoch for c in world.receipts.pending_anchors()] == [1, 2] and not (world.dir / "anchors.jsonl").exists()
    healed = await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    assert (healed.anchored, healed.failed) == (2, 0)


async def test_a_missing_evidence_anchor_address_or_signer_leaves_epochs_pending(world, tmp_path):
    await world.record(3)
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"singletons": {}}))
    no_address = Settings(**{**world.settings.__dict__, "deployments_file": str(empty)})
    assert (await asyncio.to_thread(anchor_pending_epochs, no_address, world.receipts)).failed == 1
    no_signer = Settings(**{**world.settings.__dict__, "anchor_signer_private_key": None})
    assert (await asyncio.to_thread(anchor_pending_epochs, no_signer, world.receipts)).failed == 1
    assert [c.epoch for c in world.receipts.pending_anchors()] == [1] and world.chain_roots() == []


async def test_epoch_roots_go_to_the_configured_contract_not_the_shared_evidence_anchor(world, tmp_path):
    """The evidence anchor also receives per-agent Merkle sub-roots; BCC_RECEIPT_ANCHOR_CONTRACT_NAME keeps the epochs apart."""
    await world.record(3)
    real = world.chain["anchor_address"]
    deployments = tmp_path / "split.json"
    # ProtocolEvidenceAnchor points at an address with no contract: if the sweep used it, the transaction would not land.
    deployments.write_text(json.dumps({"singletons": {"ProtocolEvidenceAnchor": "0x000000000000000000000000000000000000dEaD",
                                                       "ReceiptEpochAnchor": real}}))
    split = Settings(**{**world.settings.__dict__, "deployments_file": str(deployments), "receipt_anchor_contract_name": "ReceiptEpochAnchor"})
    assert split.receipt_anchor_target == "ReceiptEpochAnchor"
    sweep = await asyncio.to_thread(anchor_pending_epochs, split, world.receipts)
    assert (sweep.anchored, sweep.failed) == (1, 0), sweep.details
    assert len(world.chain_roots()) == 1

    missing = Settings(**{**split.__dict__, "receipt_anchor_contract_name": "NoSuchAnchor"})
    await world.record(2)  # closes epoch 2
    sweep = await asyncio.to_thread(anchor_pending_epochs, missing, world.receipts)
    assert sweep.failed == 1 and "NoSuchAnchor" in sweep.details[0]


def test_the_receipt_anchor_target_defaults_to_the_evidence_anchor():
    assert Settings().receipt_anchor_target == Settings().protocol_evidence_anchor_contract_name


async def test_a_closed_epoch_that_no_longer_verifies_is_never_anchored(world, caplog):
    await world.record(3)
    path = world.dir / "epoch-000001" / "checkpoints.jsonl"
    row = json.loads(path.read_text().splitlines()[-1])
    row["root"] = "0x" + "cd" * 32
    path.write_text(json.dumps(row) + "\n")
    with caplog.at_level("CRITICAL", logger="app.receipt_anchor"):
        sweep = await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    assert sweep.failed == 1 and sweep.anchored == 0 and world.chain_roots() == []
    assert "does not verify" in caplog.text


async def test_anchored_on_chain_but_not_recorded_is_anchored_again_not_forgotten(world, monkeypatch):
    await world.record(3)
    real = world.receipts.mark_anchored
    monkeypatch.setattr(world.receipts, "mark_anchored", lambda *a, **k: (_ for _ in ()).throw(ReceiptWriteError("disk full")))
    sweep = await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    assert sweep.failed == 1 and "anchored" in sweep.details[0] and len(world.chain_roots()) == 1
    monkeypatch.setattr(world.receipts, "mark_anchored", real)
    await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    assert world.receipts.pending_anchors() == [] and len(world.chain_roots()) == 2, "the same root, anchored again: harmless to verification"


async def test_overlapping_sweeps_do_not_run_together(world):
    await world.record(3)
    assert _sweep_lock.acquire(blocking=False)
    try:
        sweep = await asyncio.to_thread(anchor_pending_epochs, world.settings, world.receipts)
    finally:
        _sweep_lock.release()
    assert sweep.skipped and world.chain_roots() == [] and len(world.receipts.pending_anchors()) == 1


# ---------------------------------------------------------------------------------------- config


def test_settings_reject_anchoring_that_could_never_work(tmp_path):
    with pytest.raises(ValueError, match="requires BCC_RECEIPT_DIR"):
        Settings(receipt_anchor_enabled=True)
    with pytest.raises(ValueError, match="requires receipt epochs"):
        Settings(receipt_anchor_enabled=True, receipt_dir=str(tmp_path), receipt_key_file="k", receipt_hmac_key_file="h",
                 receipt_epoch_max_receipts=0, receipt_epoch_max_age_seconds=0)
    with pytest.raises(ValueError, match="greater than zero"):
        Settings(receipt_anchor_enabled=True, receipt_dir=str(tmp_path), receipt_key_file="k", receipt_hmac_key_file="h",
                 receipt_anchor_interval_seconds=0)


# --------------------------------------------------------------------------- endpoint and loop


@pytest.fixture()
def client(world, monkeypatch):
    settings = Settings(**{**world.settings.__dict__, "admin_token": TOKEN})
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "receipts", world.receipts)
    return TestClient(main_module.app)


def test_the_endpoint_requires_the_admin_token_and_reports_the_sweep(client, world):
    asyncio.run(world.record(5))
    assert client.post("/v1/admin/receipts/anchor").status_code == 401
    assert client.get("/health").json()["receipts"]["pending_anchors"] == 2
    body = client.post("/v1/admin/receipts/anchor", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert (body["attempted"], body["anchored"], body["failed"], body["skipped"]) == (2, 2, 0, False)
    assert client.get("/health").json()["receipts"]["pending_anchors"] == 0


def test_the_endpoint_is_409_without_receipts(monkeypatch):
    monkeypatch.setattr(main_module, "default_settings", Settings(admin_token=TOKEN))
    monkeypatch.setattr(main_module, "receipts", None)
    response = TestClient(main_module.app).post("/v1/admin/receipts/anchor", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 409


async def test_the_periodic_loop_anchors_without_being_asked(world, monkeypatch):
    settings = Settings(**{**world.settings.__dict__, "receipt_anchor_interval_seconds": 1})
    monkeypatch.setattr(main_module, "receipts", world.receipts)
    await world.record(3)
    task = asyncio.create_task(main_module._receipt_anchor_loop(settings))
    try:
        for _ in range(100):
            if not world.receipts.pending_anchors():
                break
            await asyncio.sleep(0.1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert world.receipts.pending_anchors() == [] and len(world.chain_roots()) == 1


def test_the_service_starts_the_anchoring_loop_when_enabled(world, monkeypatch):
    """Through the real app lifespan: with receipts and BCC_RECEIPT_ANCHOR_ENABLED the service anchors on its own."""
    import time

    asyncio.run(world.record(3))
    world.receipts.close()  # the lifespan opens its own writer on the same directory
    settings = Settings(**{**world.settings.__dict__, "receipt_anchor_interval_seconds": 1, "score_sync_enabled": False,
                           "spool_enabled": False, "merkle_anchor_enabled": False})
    monkeypatch.setattr(main_module, "default_settings", settings)
    # The lifespan assigns the module global `receipts` and closes it on shutdown; registering it here makes monkeypatch restore
    # it, so a closed writer never leaks into later tests (it made every later strict-mode allow deny).
    monkeypatch.setattr(main_module, "receipts", None)
    ledger = world.dir / "anchors.jsonl"
    with TestClient(main_module.app):
        deadline = time.monotonic() + 15
        while not ledger.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
    assert ledger.exists(), "the lifespan did not start the receipt-anchor loop"
    assert [json.loads(line)["epoch"] for line in ledger.read_text().splitlines()] == [1]
    assert len(world.chain_roots()) == 1


def test_the_service_does_not_start_the_loop_when_anchoring_is_off(world, monkeypatch):
    import time

    asyncio.run(world.record(3))
    world.receipts.close()
    settings = Settings(**{**world.settings.__dict__, "receipt_anchor_enabled": False, "receipt_anchor_interval_seconds": 1,
                           "score_sync_enabled": False, "spool_enabled": False, "merkle_anchor_enabled": False})
    monkeypatch.setattr(main_module, "default_settings", settings)
    monkeypatch.setattr(main_module, "receipts", None)  # restored on teardown; the lifespan reassigns it
    with TestClient(main_module.app):
        time.sleep(2.5)
    assert not (world.dir / "anchors.jsonl").exists() and world.chain_roots() == []
