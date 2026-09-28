"""SDK core: the decision contract and signed packs (contract C3)."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from integrity_sdk.core import decision as d
from integrity_sdk.core import packs
from integrity_sdk.did import Keypair, public_key_multibase

DEFAULTS = {"agent.tool_call": d.DENY, "device.sensor": d.LOG_ONLY, "agent.read": d.PERMIT}


# ---------------------------------------------------------------------------- decision contract ---


def test_permit_means_permitted():
    result = d.resolve("agent.tool_call", {"decision": "permit", "reason_code": "BAA_ACTIVE"}, event_defaults=DEFAULTS)
    assert (result.decision, result.reason_code, result.blocks) == ("permit", "BAA_ACTIVE", False)


def test_deny_blocks_only_in_enforce_mode():
    denied = {"decision": "deny", "reason_code": "NO_BAA", "controls": ["HIPAA-164.502(b)"]}
    enforced = d.resolve("agent.tool_call", denied, event_defaults=DEFAULTS)
    shadowed = d.resolve("agent.tool_call", denied, event_defaults=DEFAULTS, mode=d.SHADOW)
    assert enforced.blocks and enforced.controls == ("HIPAA-164.502(b)",)
    assert not shadowed.blocks and shadowed.decision == "deny"  # recorded, not enforced


@pytest.mark.parametrize(
    "event_class, expected", [("agent.tool_call", "deny"), ("device.sensor", "log_only"), ("agent.read", "permit")]
)
def test_no_match_takes_the_declared_per_class_default(event_class, expected):
    for undefined in (d.NO_MATCH, None):
        result = d.resolve(event_class, undefined, event_defaults=DEFAULTS)
        assert (result.decision, result.reason_code) == (expected, d.REASON_NO_MATCH)


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"event_defaults": None}, d.REASON_NO_PACK),
        ({"event_defaults": DEFAULTS, "evaluator_error": RuntimeError("opa down")}, d.REASON_EVALUATOR_ERROR),
    ],
)
def test_missing_pack_and_evaluator_errors_deny(kwargs, reason):
    result = d.resolve("agent.read", {"decision": "permit", "reason_code": "OK"}, **kwargs)
    assert (result.decision, result.reason_code, result.blocks) == ("deny", reason, True)


def test_an_undeclared_event_class_denies_even_when_the_policy_permits():
    result = d.resolve("agent.unknown", {"decision": "permit", "reason_code": "OK"}, event_defaults=DEFAULTS)
    assert (result.decision, result.reason_code) == ("deny", d.REASON_UNKNOWN_EVENT_CLASS)


@pytest.mark.parametrize(
    "result",
    [
        True,  # Shield's old boolean `allow`
        {"allow": True},
        {"decision": "allow", "reason_code": "OK"},  # unknown decision value
        {"decision": "permit"},  # no reason
        {"decision": "permit", "reason_code": "lowercase"},
        {"decision": "permit", "reason_code": "INTEGRITY_NO_MATCH"},  # reserved for the gate
        {"decision": "permit", "reason_code": "OK", "controls": "HIPAA"},
        {"decision": "permit", "reason_code": "OK", "extra": 1},
    ],
)
def test_malformed_results_deny_rather_than_guess(result):
    resolved = d.resolve("agent.read", result, event_defaults=DEFAULTS)
    assert (resolved.decision, resolved.reason_code) == ("deny", d.REASON_MALFORMED_DECISION)


def test_an_unknown_mode_is_a_configuration_error():
    with pytest.raises(ValueError):
        d.resolve("agent.read", None, event_defaults=DEFAULTS, mode="audit")


# -------------------------------------------------------------------------------------- packs ---

MANIFEST = """\
pack_format: integrity.pack/1
name: hipaa
version: 0.1.0
kernel_range: ">=1.0.0 <2.0.0"
decision_contract: integrity.decision/1
entrypoint: data.integrity.pack.decision
event_classes:
  agent.tool_call: {no_match: deny}
  device.sensor: {no_match: log_only}
"""
POLICY = 'package integrity.pack\n\ndecision := {"decision": "deny", "reason_code": "NO_BAA"} if { not input.baa_active }\n'


@pytest.fixture
def signer():
    return Keypair.generate()


@pytest.fixture
def pack_dir(tmp_path):
    root = tmp_path / "hipaa"
    root.mkdir()
    (root / "pack.yaml").write_text(MANIFEST)
    (root / "policy.rego").write_text(POLICY)
    (root / "controls.yaml").write_text("NO_BAA: [HIPAA-164.502(b)]\n")
    return root


def _trusted(signer):
    return [public_key_multibase(signer.public_bytes())]


def test_signed_pack_loads_and_its_hash_covers_the_rego(pack_dir, signer):
    signed = packs.sign_pack(pack_dir, signer)
    loaded = packs.load_pack(pack_dir, trusted_signers=_trusted(signer))
    assert loaded.pack_hash == signed.pack_hash
    assert set(loaded.manifest["files"]) == {"pack.yaml", "policy.rego", "controls.yaml"}
    assert loaded.policy_modules() == {"policy.rego": POLICY}
    assert loaded.event_defaults == {"agent.tool_call": "deny", "device.sensor": "log_only"}
    assert loaded.entrypoint == "data.integrity.pack.decision"


def test_pack_hash_is_deterministic(pack_dir, signer):
    assert packs.compile_pack(pack_dir).pack_hash == packs.compile_pack(pack_dir).pack_hash


@pytest.mark.parametrize(
    "mutate",
    [
        lambda root: (root / "policy.rego").write_text(POLICY.replace("deny", "permit")),
        lambda root: (root / "extra.rego").write_text("package integrity.extra\n"),
        lambda root: (root / "controls.yaml").unlink(),
        lambda root: (root / "pack.yaml").write_text(MANIFEST.replace("{no_match: deny}", "{no_match: permit}")),
    ],
    ids=["rego-edited", "file-added", "file-removed", "default-relaxed"],
)
def test_any_change_after_signing_is_refused(pack_dir, signer, mutate):
    packs.sign_pack(pack_dir, signer)
    mutate(pack_dir)
    with pytest.raises(packs.PackError) as refused:
        packs.load_pack(pack_dir, trusted_signers=_trusted(signer))
    assert refused.value.code == "TAMPERED"


def test_unsigned_untrusted_and_forged_packs_are_refused(pack_dir, signer):
    with pytest.raises(packs.PackError) as unsigned:
        packs.load_pack(pack_dir, trusted_signers=_trusted(signer))
    assert unsigned.value.code == "UNSIGNED"

    packs.sign_pack(pack_dir, signer)
    with pytest.raises(packs.PackError) as untrusted:
        packs.load_pack(pack_dir, trusted_signers=_trusted(Keypair.generate()))
    assert untrusted.value.code == "UNTRUSTED_SIGNER"
    with pytest.raises(packs.PackError) as nobody:
        packs.load_pack(pack_dir, trusted_signers=[])
    assert nobody.value.code == "UNTRUSTED_SIGNER"

    sig_path = pack_dir / packs.SIGNATURE_FILE
    document = json.loads(sig_path.read_text())
    document["signed_manifest"]["event_classes"]["agent.tool_call"]["no_match"] = "permit"
    sig_path.write_text(json.dumps(document))
    with pytest.raises(packs.PackError) as forged:
        packs.load_pack(pack_dir, trusted_signers=_trusted(signer))
    assert forged.value.code == "BAD_SIGNATURE"


def test_expired_incompatible_and_unpinned_packs_are_refused(pack_dir, signer):
    (pack_dir / "pack.yaml").write_text(MANIFEST + "not_after: 2026-01-01T00:00:00Z\n")
    packs.sign_pack(pack_dir, signer)
    with pytest.raises(packs.PackError) as stale:
        packs.load_pack(pack_dir, trusted_signers=_trusted(signer), now=dt.datetime(2026, 9, 28, tzinfo=dt.timezone.utc))
    assert stale.value.code == "STALE"

    (pack_dir / "pack.yaml").write_text(MANIFEST.replace("integrity.pack/1", "integrity.pack/2"))
    packs.sign_pack(pack_dir, signer)
    with pytest.raises(packs.PackError) as incompatible:
        packs.load_pack(pack_dir, trusted_signers=_trusted(signer))
    assert incompatible.value.code == "INCOMPATIBLE"

    (pack_dir / "pack.yaml").write_text(MANIFEST)
    packs.sign_pack(pack_dir, signer)
    with pytest.raises(packs.PackError) as pinned:
        packs.load_pack(pack_dir, trusted_signers=_trusted(signer), expected_pack_hash="sha256:" + "0" * 64)
    assert pinned.value.code == "UNEXPECTED_PACK"


@pytest.mark.parametrize(
    "manifest",
    [
        MANIFEST.replace("{no_match: deny}", "{no_match: allow}"),
        MANIFEST.replace("{no_match: deny}", "{}"),
        MANIFEST.replace("name: hipaa", "name: HIPAA Pack"),
        MANIFEST + "unexpected: 1\n",
        "- not a mapping\n",
    ],
)
def test_malformed_manifests_never_compile(pack_dir, manifest):
    (pack_dir / "pack.yaml").write_text(manifest)
    with pytest.raises(packs.PackError) as malformed:
        packs.compile_pack(pack_dir)
    assert malformed.value.code == "MALFORMED"


def test_symlinks_are_refused(pack_dir, tmp_path):
    outside = tmp_path / "outside.rego"
    outside.write_text("package x\n")
    os.symlink(outside, pack_dir / "linked.rego")
    with pytest.raises(packs.PackError) as linked:
        packs.compile_pack(pack_dir)
    assert linked.value.code == "MALFORMED"


def test_enforced_bytes_are_the_verified_bytes(pack_dir, signer):
    packs.sign_pack(pack_dir, signer)
    loaded = packs.load_pack(pack_dir, trusted_signers=_trusted(signer))
    (pack_dir / "policy.rego").write_text("package integrity.pack\n\ndecision := {\"decision\": \"permit\"}\n")
    # The gate evaluates what it verified, not what is on disk now.
    assert loaded.policy_modules()["policy.rego"] == POLICY


def test_loaded_pack_drives_the_decision_contract(pack_dir, signer):
    packs.sign_pack(pack_dir, signer)
    loaded = packs.load_pack(pack_dir, trusted_signers=_trusted(signer))
    no_match = d.resolve("agent.tool_call", d.NO_MATCH, event_defaults=loaded.event_defaults, pack_hash=loaded.pack_hash)
    assert (no_match.decision, no_match.pack_hash) == ("deny", loaded.pack_hash)
    sensor = d.resolve("device.sensor", d.NO_MATCH, event_defaults=packs.event_defaults_of(loaded))
    assert sensor.decision == "log_only" and not sensor.blocks
    assert d.resolve("agent.tool_call", None, event_defaults=packs.event_defaults_of(None)).reason_code == d.REASON_NO_PACK
