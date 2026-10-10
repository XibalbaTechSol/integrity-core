"""Loading, verifying and deciding with the signed BCC pack (app/pack_policy.py).

Everything here uses a REAL `opa run --server` and a REAL signed pack (conftest's `make_signed_pack`
signs a copy of packs/bcc with a fresh Ed25519 key). Nothing mocks OPA's answer: this codebase has been
bitten by a mocked policy reply hiding a "no rule matched means deny" bug.

Failure postures under test: loading fails closed (an unverifiable pack never reaches OPA); evaluation
fails closed (an unreachable or forgetful OPA denies); the gate, not the commitment, owns the keys that
select rules and grant authority.
"""

from __future__ import annotations

import json

import httpx
import pytest

import app.pack_policy as pack_policy_module
from app.clinical_allowlist import ClinicalAllowlist
from app.config import Settings
from app.pack_policy import CLINICAL_INTENT_TYPES, EVENT_CLASS, PackPolicy, PackPolicyError, requires_baa
from integrity_sdk.core.opa import POLICY_ID_PREFIX

AGENT = "did:integrity:" + "ab" * 32
STATIC_CLINICAL_AGENT = "did:integrity:agent_scribe_01"


def _settings(pack_dir: str, signer: str, pack_opa_url: str | None, **overrides) -> Settings:
    values = dict(
        policy_pack_dir=pack_dir, trusted_pack_signers=frozenset({signer}), pack_opa_url=pack_opa_url,
        opa_timeout_seconds=2.0,
    )
    values.update(overrides)
    return Settings(**values)


def _commitment(**overrides) -> dict:
    base = {
        "agent_id": AGENT, "intent_type": "payment", "intended_state_hash": "0x" + "11" * 32, "nonce": 1,
        "timestamp": 1730000000000, "verification_tier": 1, "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "span_id": "00f067aa0ba902b7", "intent_rationale": "A sufficiently long declared rationale.",
        "token_count": 0, "daily_token_spend": 0,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def loaded(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack()
    return PackPolicy.load(_settings(pack_dir, signer, start_empty_opa()))


# ------------------------------------------------------------------------------ loading


def test_a_verified_pack_loads_and_is_installed(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack()
    opa_url = start_empty_opa()
    policy = PackPolicy.load(_settings(pack_dir, signer, opa_url))
    assert (policy.name, policy.version) == ("bcc", "0.1.0")
    assert policy.pack_hash.startswith("sha256:")
    installed = httpx.get(f"{opa_url}/v1/policies").json()["result"]
    assert any(entry["id"].startswith(POLICY_ID_PREFIX) for entry in installed)


def test_a_pack_signed_by_an_untrusted_key_is_refused(make_signed_pack, start_empty_opa):
    pack_dir, _signer = make_signed_pack()
    _other_dir, other_signer = make_signed_pack()
    opa_url = start_empty_opa()
    with pytest.raises(PackPolicyError, match="failed verification"):
        PackPolicy.load(_settings(pack_dir, other_signer, opa_url))
    assert httpx.get(f"{opa_url}/v1/policies").json()["result"] == [], "an unverified pack must never reach OPA"


def test_a_pack_edited_after_signing_is_refused(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack(tamper_after=lambda text: text.replace('"EMR_WRITE": 1,', '"EMR_WRITE": 0,'))
    opa_url = start_empty_opa()
    with pytest.raises(PackPolicyError, match="failed verification"):
        PackPolicy.load(_settings(pack_dir, signer, opa_url))
    assert httpx.get(f"{opa_url}/v1/policies").json()["result"] == []


def test_an_unsigned_pack_is_refused(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack(sign=False)
    with pytest.raises(PackPolicyError, match="failed verification"):
        PackPolicy.load(_settings(pack_dir, signer, start_empty_opa()))


def test_the_pinned_hash_is_enforced(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack()
    good = PackPolicy.load(_settings(pack_dir, signer, start_empty_opa()))
    PackPolicy.load(_settings(pack_dir, signer, start_empty_opa(), policy_pack_hash=good.pack_hash))
    with pytest.raises(PackPolicyError, match="failed verification"):
        PackPolicy.load(_settings(pack_dir, signer, start_empty_opa(), policy_pack_hash="sha256:" + "00" * 32))


def test_required_settings_are_named_when_missing(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack()
    opa_url = start_empty_opa()
    with pytest.raises(PackPolicyError, match="BCC_POLICY_PACK_DIR"):
        PackPolicy.load(Settings(trusted_pack_signers=frozenset({signer}), pack_opa_url=opa_url))
    with pytest.raises(PackPolicyError, match="BCC_TRUSTED_PACK_SIGNERS"):
        PackPolicy.load(_settings(pack_dir, signer, opa_url, trusted_pack_signers=frozenset()))
    with pytest.raises(PackPolicyError, match="no fallback to OPA_URL"):
        PackPolicy.load(_settings(pack_dir, signer, None, opa_url=opa_url))


def test_a_pack_that_does_not_declare_the_event_class_is_refused(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack(
        edit_manifest=lambda text: text.replace("agent.tool_call: {no_match: deny}", "agent.read: {no_match: deny}")
    )
    with pytest.raises(PackPolicyError, match="does not declare event class"):
        PackPolicy.load(_settings(pack_dir, signer, start_empty_opa()))


def test_an_unreachable_opa_fails_the_load(make_signed_pack):
    pack_dir, signer = make_signed_pack()
    with pytest.raises(PackPolicyError, match="could not install"):
        PackPolicy.load(_settings(pack_dir, signer, "http://127.0.0.1:9"))  # discard port: nothing listens


# ---------------------------------------------------------------------------- deciding


def test_an_ordinary_commitment_is_permitted(loaded):
    verdict = loaded.decide_sync(_commitment())
    assert verdict.allow is True and verdict.reason_code == "BCC_POLICY_PERMIT"


def test_an_unlisted_agent_cannot_commit_a_clinical_intent(loaded):
    verdict = loaded.decide_sync(_commitment(intent_type="EMR_WRITE"))
    assert verdict.allow is False
    assert verdict.reason_code == "HIPAA_ACCESS_CONTROL_VIOLATION"
    assert verdict.controls == ("HIPAA-164.312(a)(1)",)


def test_a_static_agent_is_permitted_for_a_clinical_intent(loaded):
    assert loaded.decide_sync(_commitment(intent_type="EMR_WRITE", agent_id=STATIC_CLINICAL_AGENT)).allow is True


def test_the_allowlist_file_grants_and_revokes_authority_live(make_signed_pack, start_empty_opa, tmp_path):
    path = tmp_path / "allow.json"
    path.write_text(json.dumps({"agents": [AGENT]}))
    pack_dir, signer = make_signed_pack()
    policy = PackPolicy.load(_settings(pack_dir, signer, start_empty_opa(), clinical_allowlist_file=str(path)))
    assert policy.decide_sync(_commitment(intent_type="EMR_WRITE")).allow is True
    path.write_text(json.dumps({"agents": []}))
    assert policy.decide_sync(_commitment(intent_type="EMR_WRITE")).allow is False, "revocation must apply without a restart"
    path.write_text("{ broken")
    assert policy.decide_sync(_commitment(intent_type="EMR_WRITE")).allow is False, "a broken file must not authorize anyone"


def test_the_commitment_cannot_override_the_gate_owned_keys(make_signed_pack, start_empty_opa):
    """`event_class` selects the rules and `clinical_allowlist` grants authority. Both come from the gate; a
    commitment that carries keys of the same names must not win."""
    pack_dir, signer = make_signed_pack()
    policy = PackPolicy.load(_settings(pack_dir, signer, start_empty_opa()))
    forged = _commitment(intent_type="EMR_WRITE", clinical_allowlist=[AGENT], event_class="device.sensor")
    verdict = policy.decide_sync(forged)
    assert verdict.allow is False and verdict.reason_code == "HIPAA_ACCESS_CONTROL_VIOLATION"


def test_a_malformed_commitment_is_denied(loaded):
    for broken in ({"agent_id": None}, {"intent_type": 7}):
        verdict = loaded.decide_sync(_commitment(**broken))
        assert (verdict.allow, verdict.reason_code) == (False, "BCC_MALFORMED_COMMITMENT")


def test_an_unreachable_opa_fails_closed_at_evaluation(make_signed_pack, start_empty_opa):
    pack_dir, signer = make_signed_pack()
    policy = PackPolicy.load(_settings(pack_dir, signer, start_empty_opa()))
    policy._client._base = "http://127.0.0.1:9"  # the sidecar went away after a successful start
    with pytest.raises(PackPolicyError, match="pack evaluation failed"):
        policy.decide_sync(_commitment())


# ----------------------------------------------------- OPA forgets the pack (restart)


def _forget_pack(opa_url: str) -> None:
    for entry in httpx.get(f"{opa_url}/v1/policies").json()["result"]:
        if entry["id"].startswith(POLICY_ID_PREFIX):
            httpx.delete(f"{opa_url}/v1/policies/{entry['id']}").raise_for_status()


def test_an_opa_that_forgot_the_pack_is_healed_with_one_reinstall(make_signed_pack, start_empty_opa, monkeypatch):
    pack_dir, signer = make_signed_pack()
    opa_url = start_empty_opa()
    policy = PackPolicy.load(_settings(pack_dir, signer, opa_url))
    assert policy.decide_sync(_commitment()).allow is True
    _forget_pack(opa_url)  # what an OPA restart does
    monkeypatch.setattr(pack_policy_module, "REINSTALL_MIN_INTERVAL_SECONDS", 0.0)
    assert policy.decide_sync(_commitment()).allow is True, "the pack should have been re-installed"


def test_a_forgotten_pack_denies_until_it_can_be_reinstalled(make_signed_pack, start_empty_opa):
    """Within the throttle interval a missing pack is the pack's default deny, never an allow."""
    pack_dir, signer = make_signed_pack()
    opa_url = start_empty_opa()
    policy = PackPolicy.load(_settings(pack_dir, signer, opa_url))
    policy._last_reinstall = pack_policy_module.time.monotonic()  # a re-install just happened
    _forget_pack(opa_url)
    verdict = policy.decide_sync(_commitment())
    assert verdict.allow is False and verdict.reason_code == "INTEGRITY_NO_MATCH"


# ------------------------------------------------------------ requires_baa is pinned


def test_the_baa_constant_matches_bcc_rego_and_the_pack(real_opa_server, loaded):
    """The decision contract has no requires_baa output, so the gate keeps the clinical set itself. A sixth
    intent type added to bcc.rego or the pack and not to the constant would silently skip the BAA check."""
    in_rego = set(httpx.get(f"{real_opa_server}/v1/data/integrity/bcc/clinical_intent_types").json()["result"])
    assert in_rego == set(CLINICAL_INTENT_TYPES)

    # The pack's set is a private rule, so check it through behaviour: an unlisted agent is denied for access
    # control exactly for the clinical types (and for no others in this list).
    probes = sorted(CLINICAL_INTENT_TYPES | {"payment", "emr_write", "claude_tool:Bash", "EMR_WRITE_V2", ""})
    denied = {i for i in probes if loaded.decide_sync(_commitment(intent_type=i)).reason_code == "HIPAA_ACCESS_CONTROL_VIOLATION"}
    assert denied == set(CLINICAL_INTENT_TYPES)
    assert all(requires_baa(i) for i in CLINICAL_INTENT_TYPES) and not requires_baa("payment")


def test_the_event_class_constant_is_the_one_the_pack_declares(loaded):
    assert EVENT_CLASS in loaded._pack.event_defaults
