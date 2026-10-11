"""The shared gate receipt writer (`integrity_sdk.core.receipt_writer`), exercised against the real SDK verifier.

Nothing here mocks the receipt format: every log the writer produces is checked with `verify_log`, the same
function `integrity-cli verify` re-implements independently. Failure injection uses real OS errors (a read-only
file descriptor, a directory in place of a file), not stubs of the writer's own helpers.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import threading

import pytest

from integrity_sdk.core import (
    EpochClosure, GateReceiptWriter, ReceiptSetupError, ReceiptWriteError, RotationPolicy, derive_log_id, epoch_log_id,
    hmac_identifier, load_hmac_key, load_signer, verify_epoch_directory, verify_log,
)
from integrity_sdk.core.receipts import verify_checkpoint
from integrity_sdk.did import Keypair

HMAC_KEY = bytes(range(32))
SIGNER_PEM_SEED = Keypair.generate()
KW = dict(agent_did="did:integrity:agent", device_id="gate-1", action="EMR_WRITE|0xabc",
          event_class="agent.tool_call", pack_hash="sha256:" + "11" * 32, decision="deny",
          reason_code="POLICY_VIOLATION", mode="enforce", controls=("HIPAA-164.312(b)",))


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def _writer(tmp_path, **extra):
    return GateReceiptWriter(tmp_path / "r", signer=Keypair.generate(), hmac_key=HMAC_KEY, log_id="t:1", **extra)


def _verify(directory, signer_key):
    receipts, checkpoints = _rows(directory / "receipts.jsonl"), _rows(directory / "checkpoints.jsonl")
    verify_log(receipts, trusted_signers=[signer_key], checkpoint=checkpoints[-1] if checkpoints else None)
    return receipts, checkpoints


def test_receipts_verify_and_hide_what_they_hash(tmp_path):
    writer = _writer(tmp_path)
    ref = writer.record(**KW)
    writer.close()
    receipts, checkpoints = _verify(tmp_path / "r", writer.signer_key)
    assert ref.seq == 0 and ref.log_id == "t:1" and len(checkpoints) == 1 and checkpoints[0]["tree_size"] == 1
    raw = (tmp_path / "r" / "receipts.jsonl").read_text()
    assert "gate-1" not in raw and "EMR_WRITE" not in raw, "device and action must appear only as HMACs"
    assert receipts[0]["device_id_hmac"] == hmac_identifier(HMAC_KEY, "device", "gate-1")
    assert receipts[0]["action_hmac"] == hmac_identifier(HMAC_KEY, "action", "EMR_WRITE|0xabc")


def test_files_are_private(tmp_path):
    writer = _writer(tmp_path)
    writer.record(**KW)
    writer.checkpoint()
    for name in ("receipts.jsonl", "checkpoints.jsonl"):
        assert (tmp_path / "r" / name).stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "r").stat().st_mode & 0o777 == 0o700
    writer.close()


def test_concurrent_records_never_fork_the_chain(tmp_path):
    writer = _writer(tmp_path, checkpoint_every=7)
    errors = []

    def work():
        try:
            for _ in range(25):
                writer.record(**KW)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    writer.close()
    assert not errors
    receipts, _ = _verify(tmp_path / "r", writer.signer_key)
    assert [r["seq"] for r in receipts] == list(range(200))


def test_restart_continues_the_chain_and_a_torn_tail_is_discarded(tmp_path):
    signer = Keypair.generate()
    first = GateReceiptWriter(tmp_path / "r", signer=signer, hmac_key=HMAC_KEY, log_id="t:1")
    for _ in range(3):
        first.record(**KW)
    first.close()
    with (tmp_path / "r" / "receipts.jsonl").open("ab") as handle:
        handle.write(b'{"torn":')  # a crash mid-write: never acknowledged
    second = GateReceiptWriter(tmp_path / "r", signer=signer, hmac_key=HMAC_KEY, log_id="t:1")
    assert second.record(**KW).seq == 3
    second.close()
    receipts, _ = _verify(tmp_path / "r", second.signer_key)
    assert len(receipts) == 4


@pytest.mark.parametrize("damage", ["flip", "delete_middle", "other_log", "other_key", "garbage_line"])
def test_a_log_that_does_not_verify_refuses_start(tmp_path, damage):
    signer = Keypair.generate()
    w = GateReceiptWriter(tmp_path / "r", signer=signer, hmac_key=HMAC_KEY, log_id="t:1")
    for _ in range(4):
        w.record(**KW)
    w.close()
    path = tmp_path / "r" / "receipts.jsonl"
    lines = path.read_text().splitlines()
    log_id, key = "t:1", signer
    if damage == "flip":
        row = json.loads(lines[1]); row["decision"] = "permit"; lines[1] = json.dumps(row)
    elif damage == "delete_middle":
        del lines[1]
    elif damage == "garbage_line":
        lines[1] = "not json"
    elif damage == "other_log":
        log_id = "t:2"
    else:
        key = Keypair.generate()
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ReceiptSetupError):
        GateReceiptWriter(tmp_path / "r", signer=key, hmac_key=HMAC_KEY, log_id=log_id)


def test_truncating_the_tail_below_a_checkpoint_refuses_start(tmp_path):
    signer = Keypair.generate()
    w = GateReceiptWriter(tmp_path / "r", signer=signer, hmac_key=HMAC_KEY, log_id="t:1")
    for _ in range(4):
        w.record(**KW)
    w.close()
    path = tmp_path / "r" / "receipts.jsonl"
    path.write_text("\n".join(path.read_text().splitlines()[:2]) + "\n")
    with pytest.raises(ReceiptSetupError):
        GateReceiptWriter(tmp_path / "r", signer=signer, hmac_key=HMAC_KEY, log_id="t:1")


def test_a_failed_write_does_not_advance_the_chain(tmp_path, monkeypatch):
    writer = _writer(tmp_path)
    writer.record(**KW)
    real_fsync = os.fsync
    state = {"fail": True}

    def flaky(fd):
        if state["fail"]:
            raise OSError(28, "No space left on device")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", flaky)
    with pytest.raises(ReceiptWriteError):
        writer.record(**KW)
    state["fail"] = False
    assert writer.record(**KW).seq == 1, "the failed receipt must not leave a hole"
    writer.close()
    receipts, _ = _verify(tmp_path / "r", writer.signer_key)
    assert [r["seq"] for r in receipts] == [0, 1]


def test_a_closed_writer_refuses(tmp_path):
    writer = _writer(tmp_path)
    writer.close()
    with pytest.raises(ReceiptWriteError):
        writer.record(**KW)


def test_setup_validation(tmp_path):
    with pytest.raises(ReceiptSetupError):
        GateReceiptWriter(tmp_path / "a", signer=Keypair.generate(), hmac_key=b"short", log_id="t")
    with pytest.raises(ReceiptSetupError):
        GateReceiptWriter(tmp_path / "b", signer=Keypair.generate(), hmac_key=HMAC_KEY, log_id="t", checkpoint_every=0)
    with pytest.raises(ValueError):
        RotationPolicy()
    with pytest.raises(ValueError):
        RotationPolicy(max_receipts=0)


def test_key_files_must_be_private_and_long_enough(tmp_path):
    key = tmp_path / "hmac"
    key.write_bytes(HMAC_KEY)
    key.chmod(0o644)
    with pytest.raises(ReceiptSetupError, match="chmod 600"):
        load_hmac_key(key)
    key.chmod(0o600)
    assert load_hmac_key(key) == HMAC_KEY
    key.write_bytes(b"x" * 8)
    with pytest.raises(ReceiptSetupError):
        load_hmac_key(key)
    pem = tmp_path / "sign.pem"
    pem.write_text("not a pem")
    pem.chmod(0o600)
    with pytest.raises(ReceiptSetupError):
        load_signer(pem)


def test_log_id_does_not_contain_the_gate_id():
    log_id = derive_log_id("bcc", HMAC_KEY, "bcc-middleware")
    assert "bcc-middleware" not in log_id and log_id.startswith("bcc:") and len(log_id) == len("bcc:") + 16
    assert log_id != derive_log_id("bcc", HMAC_KEY, "other-gate")


def test_golden_vector_pins_the_receipt_bytes(tmp_path):
    """Fixed key, timestamps and inputs -> fixed receipt hashes. A second gate (Shield) pins the same values, so
    the two writers cannot drift apart unnoticed."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    seed = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    pem = seed.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    signer = Keypair.from_pem(pem)
    writer = GateReceiptWriter(tmp_path / "g", signer=signer, hmac_key=HMAC_KEY, log_id="golden:1")
    refs = [writer.record(**KW, timestamp="2026-01-01T00:00:0%dZ" % i) for i in range(2)]
    writer.close()
    assert [r.hash for r in refs] == GOLDEN_HASHES, [r.hash for r in refs]


# Ed25519 is deterministic, so these are stable; computed once from this exact input and pinned.
GOLDEN_HASHES = [
    "0xdb4da1b0d6acf290c8bb5abef8dac08a40408b2092d664d7a7fac463628abf01",
    "0x2a445d8ab3b21a16a6996826490ac395234456760371eadbea21d08a0b9f05a5",
]


# --------------------------------------------------------------------------------------------- rotation


def _rotating(tmp_path, signer=None, clock=None, **policy):
    kwargs = {"clock": clock} if clock else {}
    return GateReceiptWriter(tmp_path / "e", signer=signer or Keypair.generate(), hmac_key=HMAC_KEY, log_id="t:1",
                             rotation=RotationPolicy(**policy), **kwargs)


def test_rotation_by_count_closes_each_epoch_with_a_covering_checkpoint(tmp_path):
    writer = _rotating(tmp_path, max_receipts=3, signer=(signer := Keypair.generate()))
    refs = [writer.record(**KW) for _ in range(8)]
    writer.close()
    assert [(r.log_id, r.seq) for r in refs] == [
        (epoch_log_id("t:1", 1), 0), (epoch_log_id("t:1", 1), 1), (epoch_log_id("t:1", 1), 2),
        (epoch_log_id("t:1", 2), 0), (epoch_log_id("t:1", 2), 1), (epoch_log_id("t:1", 2), 2),
        (epoch_log_id("t:1", 3), 0), (epoch_log_id("t:1", 3), 1)]
    audits = verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=[writer.signer_key])
    assert [(a.number, a.receipts, a.closed) for a in audits] == [(1, 3, True), (2, 3, True), (3, 2, True)]


def test_rotation_by_age(tmp_path):
    now = [1_000_000.0]
    writer = _rotating(tmp_path, clock=lambda: now[0], max_age_seconds=60)
    assert writer.record(**KW).log_id.endswith("e000001")
    now[0] += 59
    assert writer.record(**KW).log_id.endswith("e000001")
    now[0] += 2
    assert writer.record(**KW).log_id.endswith("e000002")
    writer.close()


def test_restart_resumes_only_the_newest_epoch(tmp_path):
    signer = Keypair.generate()
    first = _rotating(tmp_path, signer=signer, max_receipts=2)
    for _ in range(3):
        first.record(**KW)
    first.close()
    second = _rotating(tmp_path, signer=signer, max_receipts=2)
    assert second.epoch == 2 and second.record(**KW).seq == 1
    assert second.record(**KW).log_id.endswith("e000003")
    second.close()


def test_a_missing_middle_epoch_refuses_start_and_audit(tmp_path):
    signer = Keypair.generate()
    w = _rotating(tmp_path, signer=signer, max_receipts=1)
    for _ in range(3):
        w.record(**KW)
    w.close()
    import shutil
    shutil.rmtree(tmp_path / "e" / "epoch-000002")
    with pytest.raises(ReceiptSetupError, match="missing epoch"):
        _rotating(tmp_path, signer=signer, max_receipts=1)
    with pytest.raises(ReceiptSetupError):
        verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=[w.signer_key])


def test_audit_catches_tampering_in_an_old_epoch_that_start_up_does_not_read(tmp_path):
    signer = Keypair.generate()
    w = _rotating(tmp_path, signer=signer, max_receipts=2)
    for _ in range(5):
        w.record(**KW)
    w.close()
    path = tmp_path / "e" / "epoch-000001" / "receipts.jsonl"
    lines = path.read_text().splitlines()
    row = json.loads(lines[0]); row["decision"] = "permit"; lines[0] = json.dumps(row)
    path.write_text("\n".join(lines) + "\n")
    _rotating(tmp_path, signer=signer, max_receipts=2).close()  # start-up reads only the newest epoch: still starts
    with pytest.raises(Exception):
        verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=[w.signer_key])


def test_a_failed_rotation_leaves_the_old_epoch_usable(tmp_path):
    w = _rotating(tmp_path, max_receipts=1)
    w.record(**KW)
    blocker = tmp_path / "e" / "epoch-000002"
    blocker.write_text("a file where the next epoch's directory must go")
    with pytest.raises(ReceiptWriteError):
        w.record(**KW)
    blocker.unlink()
    assert w.record(**KW).log_id.endswith("e000002")
    w.close()


def test_checkpoints_are_periodic_not_per_record(tmp_path):
    writer = _writer(tmp_path, checkpoint_every=3)
    for _ in range(7):
        writer.record(**KW)
    sizes = [c["tree_size"] for c in _rows(tmp_path / "r" / "checkpoints.jsonl")]
    assert sizes == [3, 6], "a checkpoint every 3 receipts, and none in between"
    writer.close()
    assert [c["tree_size"] for c in _rows(tmp_path / "r" / "checkpoints.jsonl")] == [3, 6, 7]


# ------------------------------------------------------------------------------------ anchoring closed epochs


def _rotated(tmp_path, receipts=5, per_epoch=2):
    """Epochs 1 and 2 closed (2 receipts each), epoch 3 open with 1 receipt."""
    signer = Keypair.generate()
    writer = GateReceiptWriter(tmp_path / "e", signer=signer, hmac_key=HMAC_KEY, log_id="t:1", rotation=RotationPolicy(max_receipts=per_epoch))
    for _ in range(receipts):
        writer.record(**KW)
    return writer, signer


def _final_root(directory, number):
    return _rows(directory / f"epoch-{number:06d}" / "checkpoints.jsonl")[-1]["root"]


def test_closed_epochs_are_rooted_in_their_signed_final_checkpoints(tmp_path):
    writer, _ = _rotated(tmp_path)
    closed = writer.closed_epochs()
    assert [(c.epoch, c.tree_size) for c in closed] == [(1, 2), (2, 2)]
    assert [c.root for c in closed] == [_final_root(tmp_path / "e", 1), _final_root(tmp_path / "e", 2)]
    assert [c.log_id for c in closed] == [epoch_log_id("t:1", 1), epoch_log_id("t:1", 2)]
    assert writer.pending_anchors() == closed
    writer.close()


def test_marking_an_epoch_anchored_removes_it_from_pending_and_survives_a_restart(tmp_path):
    writer, signer = _rotated(tmp_path)
    first = writer.pending_anchors()[0]
    writer.mark_anchored(first, "0xtx1")
    assert [c.epoch for c in writer.pending_anchors()] == [2]
    writer.close()
    reopened = GateReceiptWriter(tmp_path / "e", signer=signer, hmac_key=HMAC_KEY, log_id="t:1", rotation=RotationPolicy(max_receipts=2))
    assert [c.epoch for c in reopened.pending_anchors()] == [2], "the ledger is durable"
    ledger = _rows(tmp_path / "e" / "anchors.jsonl")
    assert [(r["epoch"], r["root"], r["tx_hash"]) for r in ledger] == [(1, first.root, "0xtx1")]
    assert (tmp_path / "e" / "anchors.jsonl").stat().st_mode & 0o777 == 0o600
    reopened.close()


def test_a_new_epoch_closing_adds_to_pending(tmp_path):
    writer, _ = _rotated(tmp_path)
    for closure in writer.pending_anchors():
        writer.mark_anchored(closure, "0xtx")
    assert writer.pending_anchors() == []
    writer.record(**KW)  # fills epoch 3 (2 receipts)
    writer.record(**KW)  # rotates: epoch 3 closes, epoch 4 opens
    assert [c.epoch for c in writer.pending_anchors()] == [3]
    writer.close()


def test_mark_anchored_refuses_what_the_log_does_not_have(tmp_path):
    writer, _ = _rotated(tmp_path)
    closure = writer.pending_anchors()[0]
    with pytest.raises(ReceiptWriteError, match="transaction hash"):
        writer.mark_anchored(closure, "")
    with pytest.raises(ReceiptWriteError, match="not a closed epoch"):  # the OPEN epoch cannot be anchored
        writer.mark_anchored(dataclasses.replace(closure, epoch=3), "0xtx")
    with pytest.raises(ReceiptWriteError, match="not a closed epoch"):
        writer.mark_anchored(dataclasses.replace(closure, epoch=9), "0xtx")
    with pytest.raises(ReceiptWriteError, match="root is"):  # a root the epoch's signed checkpoint does not have
        writer.mark_anchored(dataclasses.replace(closure, root="0x" + "ab" * 32), "0xtx")
    assert not (tmp_path / "e" / "anchors.jsonl").exists()
    writer.close()


def test_a_tampered_final_checkpoint_cannot_be_anchored(tmp_path):
    writer, _ = _rotated(tmp_path)
    path = tmp_path / "e" / "epoch-000001" / "checkpoints.jsonl"
    row = _rows(path)[-1]
    row["root"] = "0x" + "cd" * 32  # signature no longer covers this
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ReceiptSetupError, match="does not verify"):
        writer.pending_anchors()
    writer.close()


def test_without_rotation_there_is_nothing_to_anchor(tmp_path):
    writer = _writer(tmp_path)
    writer.record(**KW)
    assert writer.closed_epochs() == [] and writer.pending_anchors() == []
    with pytest.raises(ReceiptWriteError):
        writer.mark_anchored(EpochClosure(1, "t:1.e000001", 1, "0x" + "00" * 32, tmp_path), "0xtx")
    writer.close()


def test_audit_detects_a_removed_newest_closed_epoch_given_the_chains_roots(tmp_path):
    writer, signer = _rotated(tmp_path)
    chain_roots = [c.root for c in writer.pending_anchors()]  # what the gate anchored: epochs 1 and 2
    writer.close()
    signers = [writer.signer_key]
    audits = verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers, anchored_roots=chain_roots)
    assert [(a.number, a.anchored) for a in audits] == [(1, True), (2, True), (3, False)]

    shutil.rmtree(tmp_path / "e" / "epoch-000003")
    shutil.rmtree(tmp_path / "e" / "epoch-000002")  # the attacker removes the newest closed epoch (and the open one)
    with pytest.raises(ReceiptSetupError, match="match no epoch"):
        verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers, anchored_roots=chain_roots)
    # ...and without the chain's roots the removal is, as documented, invisible:
    assert len(verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers)) == 1


def test_audit_ignores_chain_roots_it_was_not_given_but_requires_every_one_it_was(tmp_path):
    writer, _ = _rotated(tmp_path)
    writer.close()
    signers = [writer.signer_key]
    with pytest.raises(ReceiptSetupError, match="match no epoch"):
        verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers, anchored_roots=["0x" + "ee" * 32])
    assert verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers, anchored_roots=[])  # nothing to check


def test_audit_cross_checks_the_ledger_against_the_epochs(tmp_path):
    writer, _ = _rotated(tmp_path)
    for closure in writer.pending_anchors():
        writer.mark_anchored(closure, "0xtx")
    writer.close()
    signers = [writer.signer_key]
    audits = verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers)
    assert [(a.number, a.anchored) for a in audits] == [(1, True), (2, True), (3, False)]

    ledger = tmp_path / "e" / "anchors.jsonl"
    original = ledger.read_text()
    rows = _rows(ledger)
    rows[0]["root"] = "0x" + "ff" * 32
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ReceiptSetupError, match="not its final checkpoint root"):
        verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers)
    ledger.write_text(original)
    shutil.rmtree(tmp_path / "e" / "epoch-000003")
    shutil.rmtree(tmp_path / "e" / "epoch-000002")
    with pytest.raises(ReceiptSetupError, match="not in"):  # the ledger survived the deletion and says epoch 2 existed
        verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=signers)


def test_anchored_is_unknown_when_nothing_can_say(tmp_path):
    writer, _ = _rotated(tmp_path)
    writer.close()
    audits = verify_epoch_directory(tmp_path / "e", base_log_id="t:1", trusted_signers=[writer.signer_key])
    assert [a.anchored for a in audits] == [None, None, None]


def test_an_epoch_whose_final_checkpoint_does_not_cover_its_receipts_cannot_be_anchored(tmp_path):
    """Rotation closes an epoch only after a covering checkpoint. If that checkpoint was cut away, anchoring the earlier one would
    anchor a root that leaves the epoch's tail uncovered -- refuse rather than certify a truncatable log."""
    signer = Keypair.generate()
    writer = GateReceiptWriter(tmp_path / "e", signer=signer, hmac_key=HMAC_KEY, log_id="t:1", checkpoint_every=1,
                               rotation=RotationPolicy(max_receipts=2))
    for _ in range(3):
        writer.record(**KW)  # epoch 1: receipts 0,1 with checkpoints at sizes 1 and 2; epoch 2 open
    path = tmp_path / "e" / "epoch-000001" / "checkpoints.jsonl"
    path.write_text("\n".join(path.read_text().splitlines()[:-1]) + "\n")  # drop the covering (size 2) checkpoint
    with pytest.raises(ReceiptSetupError, match="does not cover"):
        writer.pending_anchors()
    writer.close()


def test_the_first_ledger_entry_makes_the_new_files_name_durable(tmp_path, monkeypatch):
    import integrity_sdk.core.receipt_writer as module

    synced: list[str] = []
    real = module._fsync_directory
    monkeypatch.setattr(module, "_fsync_directory", lambda directory: (synced.append(directory.name), real(directory))[1])
    writer, _ = _rotated(tmp_path)
    synced.clear()
    first, second = writer.pending_anchors()
    writer.mark_anchored(first, "0xa")
    writer.mark_anchored(second, "0xb")
    assert synced == ["e"], "the directory is synced once, when anchors.jsonl is created, not on every append"
    writer.close()
