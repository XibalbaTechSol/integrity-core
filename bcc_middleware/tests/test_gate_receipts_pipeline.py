"""Signed decision receipts THROUGH THE REAL PIPELINE (B2 stage 3b).

Every receipt BCC writes here is verified offline with the SDK's own `verify_log`, the function a customer's
auditor (or `integrity-cli verify`) runs. Nothing about the receipt format is stubbed. Failure injection uses a
real OS error (`os.fsync` raising ENOSPC), not a fake writer.

What is pinned:
  * authenticated-only: replay / expiry / policy / budget / BAA / allow get receipts; a bad signature, a chain
    mismatch and an open breaker do not (their agent id is unproven);
  * the receipt names the policy that DECIDED (pack hash in pack mode; the all-zero sentinel under bcc.rego,
    including dual-run where the pack is only advisory);
  * strict: an allow that cannot be recorded is denied BEFORE admission (no Merkle leaf, no token, breaker
    uncharged); lenient and shadow let it through, and say so;
  * a log that cannot be opened refuses to start.
"""

from __future__ import annotations

import errno
import json
import os
import time

import httpx
import pytest

import app.main as main_module
from app.config import Settings
from app.gate_receipts import NO_PACK_HASH, BccReceipts
from app.main import run_intercept
from app.pack_policy import PackPolicy
from integrity_sdk.core import ReceiptSetupError, verify_epoch_directory, verify_log
from integrity_sdk.did import Keypair
from tests.helpers import make_commitment_model, new_agent, sign_commitment

RATIONALE = "A sufficiently long declared intent rationale."
HMAC_KEY = bytes(range(32))


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


class World:
    """One agent, a real OPA with bcc.rego, optionally the signed pack, and a receipt log in tmp_path."""

    def __init__(self, tmp_path, real_opa_server, pack_kwargs, monkeypatch):
        self.tmp, self.monkeypatch = tmp_path, monkeypatch
        self.agent_id, self.key = new_agent()
        self.nonce = 0
        self.opa = real_opa_server
        self.pack_kwargs = pack_kwargs
        self.signer_pem = tmp_path / "receipt.pem"
        self.signer_pem.write_bytes(Keypair.generate().private_pem())
        self.hmac_file = tmp_path / "receipt.hmac"
        self.hmac_file.write_bytes(HMAC_KEY)
        for path in (self.signer_pem, self.hmac_file):
            path.chmod(0o600)
        self.dir = tmp_path / "receipts"
        self.policy: PackPolicy | None = None
        monkeypatch.setattr(main_module, "resolve_verification_tier", lambda agent_id, oracle_url=None: 1)
        main_module.circuit_breaker.reset()
        main_module.token_budget_enforcer.reset()
        main_module.batcher.reset()

    def settings(self, **extra) -> Settings:
        base = dict(
            opa_url=self.opa, merkle_batch_size=999, quarantine_fail_closed_intents=frozenset(), shadow_mode=False,
            receipt_epoch_max_receipts=0, receipt_epoch_max_age_seconds=0,  # one flat log; the rotation test opts in
            receipt_dir=str(self.dir), receipt_key_file=str(self.signer_pem), receipt_hmac_key_file=str(self.hmac_file),
            **self.pack_kwargs,
        )
        return Settings(**{**base, **extra})

    def open(self, settings: Settings, *, pack: bool = False) -> BccReceipts:
        receipts = BccReceipts.from_settings(settings)
        self.monkeypatch.setattr(main_module, "receipts", receipts)
        self.policy = PackPolicy.load(settings) if pack else None
        self.monkeypatch.setattr(main_module, "pack_policy", self.policy)
        return receipts

    def commitment(self, intent_type="payment", token_count=None, **overrides):
        self.nonce += 1
        payload = sign_commitment(self.key, agent_id=self.agent_id, intent_type=intent_type, nonce=self.nonce,
                                  intent_rationale=RATIONALE, **overrides)
        if token_count is not None:
            payload["token_count"] = token_count  # not part of the signed bytes, as in test_policy_engine_switch
        return make_commitment_model(**payload)

    def logged(self):
        receipts = _rows(self.dir / "receipts.jsonl") if (self.dir / "receipts.jsonl").exists() else []
        return receipts


@pytest.fixture()
def world(tmp_path, real_opa_server, make_signed_pack, start_empty_opa, monkeypatch):
    pack_dir, signer = make_signed_pack()
    pack_kwargs = dict(policy_pack_dir=pack_dir, trusted_pack_signers=frozenset({signer}), pack_opa_url=start_empty_opa())
    yield World(tmp_path, real_opa_server, pack_kwargs, monkeypatch)
    monkeypatch.setattr(main_module, "receipts", None)


async def _go(world: World, settings: Settings, commitment):
    return await run_intercept(commitment, settings)


def _verify(world: World, receipts: BccReceipts):
    rows = world.logged()
    checkpoints = _rows(world.dir / "checkpoints.jsonl") if (world.dir / "checkpoints.jsonl").exists() else []
    verify_log(rows, trusted_signers=[receipts.signer_key], checkpoint=checkpoints[-1] if checkpoints else None)
    return rows


# -------------------------------------------------------------------------------- what is recorded


async def test_an_allow_is_recorded_before_admission_and_verifies_offline(world):
    settings = world.settings()
    receipts = world.open(settings)
    response = await _go(world, settings, world.commitment())
    assert response.authorized and response.receipt_status == "recorded"
    receipts.close()
    [row] = _verify(world, receipts)
    assert (row["decision"], row["mode"], row["reason_code"]) == ("permit", "enforce", "BCC_REGO_POLICY_PERMIT")
    assert row["pack_hash"] == NO_PACK_HASH and row["agent_did"] == world.agent_id
    assert response.receipt == {"log_id": row["log_id"], "seq": 0, "hash": response.receipt["hash"]}
    assert "bcc-middleware" not in (world.dir / "receipts.jsonl").read_text(), "the gate id must be HMAC-hashed"


async def test_a_policy_denial_under_bcc_rego_is_recorded(world):
    settings = world.settings()
    receipts = world.open(settings)
    response = await _go(world, settings, world.commitment("EXFILTRATE_records"))
    assert not response.authorized and response.receipt_status == "recorded"
    receipts.close()
    [row] = _verify(world, receipts)
    assert (row["decision"], row["reason_code"], row["pack_hash"]) == ("deny", "BCC_REGO_POLICY_DENY", NO_PACK_HASH)


async def test_in_pack_mode_the_receipt_names_the_pack_and_the_specific_code_and_controls(world):
    settings = world.settings(policy_engine="pack")
    receipts = world.open(settings, pack=True)
    allowed = await _go(world, settings, world.commitment())
    denied = await _go(world, settings, world.commitment("DISPENSE_MEDICATION"))  # unlisted agent, clinical intent
    receipts.close()
    permit, deny = _verify(world, receipts)
    assert allowed.authorized and not denied.authorized
    assert (permit["decision"], permit["reason_code"], permit["pack_hash"]) == ("permit", "BCC_POLICY_PERMIT", world.policy.pack_hash)
    assert (deny["decision"], deny["reason_code"], deny["pack_hash"]) == ("deny", "HIPAA_ACCESS_CONTROL_VIOLATION", world.policy.pack_hash)
    assert deny["controls"] == ["HIPAA-164.312(a)(1)"]


async def test_in_dual_run_the_pack_is_advisory_so_the_receipt_does_not_name_it(world):
    settings = world.settings()  # engine stays "rego" with a pack loaded
    receipts = world.open(settings, pack=True)
    await _go(world, settings, world.commitment())
    receipts.close()
    [row] = _verify(world, receipts)
    assert row["pack_hash"] == NO_PACK_HASH != world.policy.pack_hash


@pytest.mark.parametrize("case", ["replay", "expired"])
async def test_post_signature_gate_denials_are_recorded(world, case):
    settings = world.settings()
    receipts = world.open(settings)
    if case == "replay":
        first = world.commitment()
        await _go(world, settings, first)
        response = await _go(world, settings, first)  # same nonce again
        expected = "BCC_NONCE_REPLAY"
    else:
        stale = world.commitment(timestamp=int(time.time() * 1000) - 10 * 60_000)
        response = await _go(world, settings, stale)
        expected = "BCC_EXPIRED"
    receipts.close()
    assert not response.authorized and response.receipt_status == "recorded"
    rows = _verify(world, receipts)
    assert rows[-1]["decision"] == "deny" and rows[-1]["reason_code"] == expected and rows[-1]["pack_hash"] == NO_PACK_HASH


async def test_a_policy_allow_that_the_baa_gate_then_denies_is_recorded_as_a_deny(world):
    """EMR_WRITE passes bcc.rego for an allowlisted agent, then BAA verification cannot confirm (no chain in
    tests). The receipt must say deny/BAA_CANNOT_VERIFY, not the policy's permit."""
    httpx.put(f"{world.opa}/v1/data/clinical_allowlist/agents", json=[world.agent_id]).raise_for_status()
    try:
        settings = world.settings()
        receipts = world.open(settings)
        response = await _go(world, settings, world.commitment("EMR_WRITE"))
        receipts.close()
        assert not response.authorized
        [row] = _verify(world, receipts)
        assert (row["decision"], row["reason_code"]) == ("deny", "BAA_CANNOT_VERIFY")
    finally:
        httpx.put(f"{world.opa}/v1/data/clinical_allowlist/agents", json=[])


async def test_a_python_layer_token_budget_denial_is_recorded(world, monkeypatch):
    """OPA's own budget rule sees the same spend the Python enforcer does, so with a real policy the Python
    layer is never the first to refuse. Its branch is exercised here by making the enforcer refuse; the
    enforcer's own arithmetic is tested in test_token_budget.py."""
    monkeypatch.setattr(main_module.token_budget_enforcer, "check_and_record", lambda *a, **k: (False, "daily budget spent"))
    settings = world.settings()
    receipts = world.open(settings)
    response = await _go(world, settings, world.commitment(token_count=100))
    receipts.close()
    assert not response.authorized and response.reason.startswith("TOKEN_BUDGET_EXCEEDED")
    [row] = _verify(world, receipts)
    assert (row["decision"], row["reason_code"]) == ("deny", "TOKEN_BUDGET_EXCEEDED")


async def test_the_opa_budget_rule_is_recorded_as_a_policy_denial(world, monkeypatch):
    monkeypatch.setattr(main_module, "resolve_verification_tier", lambda agent_id, oracle_url=None: 0)
    settings = world.settings()
    receipts = world.open(settings)
    assert (await _go(world, settings, world.commitment(token_count=9000))).authorized
    assert not (await _go(world, settings, world.commitment(token_count=9000))).authorized
    receipts.close()
    rows = _verify(world, receipts)
    assert [r["decision"] for r in rows] == ["permit", "deny"] and rows[1]["reason_code"] == "BCC_REGO_POLICY_DENY"


# ------------------------------------------------------------------------ authenticated-only


async def test_unauthenticated_denials_get_no_receipt(world):
    settings = world.settings()
    receipts = world.open(settings)
    forged = world.commitment().model_copy(update={"signature": "00" * 64})
    wrong_chain = world.commitment(chain_id=999_999)
    for commitment in (forged, wrong_chain):
        response = await _go(world, settings, commitment)
        assert not response.authorized and response.receipt is None and response.receipt_status is None
    receipts.close()
    assert world.logged() == [], "an unproven agent id must never be named in a signed receipt"


async def test_an_open_breaker_denial_gets_no_receipt(world, monkeypatch):
    monkeypatch.setattr(main_module.circuit_breaker, "violation_threshold", 1)
    settings = world.settings()
    receipts = world.open(settings)
    await _go(world, settings, world.commitment("EXFILTRATE_records"))  # trips the breaker
    before = len(world.logged())
    response = await _go(world, settings, world.commitment())
    assert "CIRCUIT_BREAKER_OPEN" in response.reason and response.receipt_status is None
    assert len(world.logged()) == before
    receipts.close()


async def test_without_receipts_configured_nothing_changes(world, monkeypatch):
    monkeypatch.setattr(main_module, "receipts", None)
    response = await _go(world, world.settings(receipt_dir=None, receipt_key_file=None, receipt_hmac_key_file=None), world.commitment())
    assert response.authorized and response.receipt is None and response.receipt_status is None
    assert not world.dir.exists()


# ------------------------------------------------------------------------ strict / lenient / shadow


def _break_disk(monkeypatch):
    def full(fd):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(os, "fsync", full)


async def test_strict_denies_an_allow_it_cannot_record_and_admits_nothing(world, monkeypatch):
    settings = world.settings()
    receipts = world.open(settings)
    admitted_before = main_module.batcher.pending_count
    _break_disk(monkeypatch)
    response = await _go(world, settings, world.commitment())
    monkeypatch.undo()
    assert not response.authorized and response.reason.startswith("BCC_RECEIPT_UNAVAILABLE")
    assert response.verification_token is None and response.batch_index is None
    assert main_module.batcher.pending_count == admitted_before, "no Merkle leaf for a decision with no receipt"
    assert response.receipt is None and response.receipt_status == "failed"
    assert not main_module.circuit_breaker.is_locked_out(world.agent_id), "our storage failure is not the agent's violation"
    receipts.close()


async def test_strict_recovers_without_repair_once_the_disk_is_writable(world, monkeypatch):
    settings = world.settings()
    receipts = world.open(settings)
    real_fsync = os.fsync
    _break_disk(monkeypatch)
    assert not (await _go(world, settings, world.commitment())).authorized
    monkeypatch.setattr(os, "fsync", real_fsync)
    assert (await _go(world, settings, world.commitment())).authorized
    receipts.close()
    assert [r["seq"] for r in _verify(world, receipts)] == [0], "the failed receipt left no hole"


async def test_lenient_lets_the_allow_through_and_says_it_has_no_receipt(world, monkeypatch):
    settings = world.settings(lenient_receipts=True)
    receipts = world.open(settings)
    _break_disk(monkeypatch)
    response = await _go(world, settings, world.commitment())
    monkeypatch.undo()
    assert response.authorized and response.receipt is None and response.receipt_status == "failed"
    receipts.close()


async def test_shadow_mode_never_blocks_on_a_receipt(world, monkeypatch):
    settings = world.settings(shadow_mode=True)
    receipts = world.open(settings)
    _break_disk(monkeypatch)
    response = await _go(world, settings, world.commitment())
    monkeypatch.undo()
    assert response.authorized and response.receipt_status == "failed"
    assert not response.shadow_would_deny and response.verification_token, "a clean allow, not a would-deny"
    receipts.close()


async def test_shadow_decisions_are_recorded_with_mode_shadow(world):
    settings = world.settings(shadow_mode=True)
    receipts = world.open(settings)
    response = await _go(world, settings, world.commitment("EXFILTRATE_records"))
    receipts.close()
    assert response.authorized and response.shadow_would_deny
    [row] = _verify(world, receipts)
    assert (row["decision"], row["mode"]) == ("deny", "shadow")


async def test_a_shadow_mode_allow_is_recorded_with_mode_shadow(world):
    settings = world.settings(shadow_mode=True)
    receipts = world.open(settings)
    assert (await _go(world, settings, world.commitment())).authorized
    receipts.close()
    [row] = _verify(world, receipts)
    assert (row["decision"], row["mode"]) == ("permit", "shadow")


async def test_the_receipt_is_bound_to_the_exact_signed_commitment(world):
    from integrity_sdk.core import hmac_identifier
    settings = world.settings()
    receipts = world.open(settings)
    commitment = world.commitment()
    await _go(world, settings, commitment)
    receipts.close()
    [row] = _verify(world, receipts)
    assert row["action_hmac"] == hmac_identifier(HMAC_KEY, "action", f"{commitment.intent_type}|{commitment.intended_state_hash}")
    assert row["device_id_hmac"] == hmac_identifier(HMAC_KEY, "device", "bcc-middleware")


async def test_a_denial_that_cannot_be_recorded_is_still_a_denial(world, monkeypatch):
    settings = world.settings()
    receipts = world.open(settings)
    _break_disk(monkeypatch)
    response = await _go(world, settings, world.commitment("EXFILTRATE_records"))
    monkeypatch.undo()
    assert not response.authorized and response.receipt_status == "failed"
    receipts.close()


# ------------------------------------------------------------------------ epochs, startup, health


async def test_epochs_rotate_through_the_pipeline_and_audit_clean(world):
    settings = world.settings(receipt_epoch_max_receipts=2, receipt_checkpoint_every=1)
    receipts = world.open(settings)
    for _ in range(5):
        assert (await _go(world, settings, world.commitment())).authorized
    receipts.close()
    log_id = receipts.health()["log_id"].rsplit(".e", 1)[0]
    audits = verify_epoch_directory(world.dir, base_log_id=log_id, trusted_signers=[receipts.signer_key])
    assert [(a.number, a.receipts) for a in audits] == [(1, 2), (2, 2), (3, 1)]


def test_a_tampered_existing_log_refuses_to_start(world):
    settings = world.settings()
    first = BccReceipts.from_settings(settings)
    import asyncio
    asyncio.run(first.record(agent_id="did:integrity:x", intent_type="payment", intended_state_hash="0x1", permit=True,
                             reason_code="R", pack_hash=None, controls=(), shadow=False))
    first.close()
    path = world.dir / "receipts.jsonl"
    row = json.loads(path.read_text().splitlines()[0]); row["decision"] = "deny"
    path.write_text(json.dumps(row) + "\n")
    with pytest.raises(ReceiptSetupError):
        main_module._init_receipts(settings)


def test_an_unreadable_signing_key_refuses_to_start(world):
    world.signer_pem.chmod(0o644)
    with pytest.raises(ReceiptSetupError):
        main_module._init_receipts(world.settings())


def test_settings_reject_half_configured_receipts(tmp_path):
    with pytest.raises(ValueError, match="requires"):
        Settings(receipt_dir=str(tmp_path))
    with pytest.raises(ValueError, match="BCC_RECEIPT_DIR is not"):
        Settings(receipt_key_file="k")


def test_health_reports_receipts(world, monkeypatch):
    from fastapi.testclient import TestClient
    off = TestClient(main_module.app).get("/health").json()
    assert off["receipts"] == {"enabled": False}
    settings = world.settings()
    receipts = world.open(settings)
    monkeypatch.setattr(main_module, "default_settings", settings)
    on = TestClient(main_module.app).get("/health").json()["receipts"]
    assert on["enabled"] and on["strict"] and on["signer_key"] == receipts.signer_key
    receipts.close()
