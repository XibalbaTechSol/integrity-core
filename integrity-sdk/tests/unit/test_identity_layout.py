"""Identity layout: public DID file in the harness root, private key outside it.

Covers the relocation of keys that earlier builds wrote inside a harness root
(`<root>/.integrity/did/<agent>/`), the fail-closed cases around it, and the
removal of env-var precedence between harness roots. Every test pins HOME to a
temporary directory so the default key home (`~/.integrity/did`) never touches
the developer's real one.
"""

from __future__ import annotations

import json

import pytest

from integrity_sdk import did
from integrity_sdk.agent_runtime import AgentIdentityError, IntegrityAgent

_CLIENT = {"auto_flush": False, "enable_otel_export": False}


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("INTEGRITY_DID_HOME", raising=False)


def _make_legacy_profile(root, slug="agent-a"):
    """Recreate the pre-relocation layout exactly as earlier builds wrote it."""
    legacy_home = root / ".integrity" / "did"
    legacy_did, keypair, _ = did.load_or_create_did(slug, did_home_root=legacy_home, legacy_home=legacy_home)
    (legacy_home / slug / "primitives.json").write_text('{"chain_id": 84532}\n', encoding="utf-8")
    (root / ".integrity" / "identity.json").write_text(
        json.dumps({
            "identity_version": 1,
            "agent_id": slug,
            "did": legacy_did,
            "harness": "hermes",
            "profile": None,
            "profile_root": str(root.resolve()),
            "identity_store": str(legacy_home / slug),
        }),
        encoding="utf-8",
    )
    return legacy_did, keypair


def test_new_identity_writes_only_public_data_into_the_harness_root(tmp_path):
    root = tmp_path / "hermes-home"
    root.mkdir()
    agent = IntegrityAgent.open("agent-a", harness="hermes", profile_root=root, client_kwargs=_CLIENT)
    agent.close(flush=False)

    assert sorted(p.name for p in root.iterdir()) == ["agent.did.json"]
    payload = json.loads((root / "agent.did.json").read_text(encoding="utf-8"))
    assert payload["did"] == agent.did
    assert payload["agent_id"] == "agent-a"
    assert not any(marker in key for key in payload for marker in ("private", "secret", "seed"))
    key_path = did.key_store_for_profile(root.resolve()) / "agent-a" / "private_key.pem"
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert key_path.parent.stat().st_mode & 0o777 == 0o700


def test_legacy_in_root_key_is_relocated_without_changing_the_did(tmp_path):
    root = tmp_path / "hermes-home"
    root.mkdir()
    legacy_did, legacy_keypair = _make_legacy_profile(root)

    agent = IntegrityAgent.open(harness="hermes", profile_root=root, client_kwargs=_CLIENT)
    agent.close(flush=False)

    assert agent.did == legacy_did
    assert agent.keypair.private_bytes_raw() == legacy_keypair.private_bytes_raw()
    assert not list(root.rglob("*.pem"))
    assert not (root / ".integrity" / "identity.json").exists()
    store = did.key_store_for_profile(root.resolve()) / "agent-a"
    assert (store / "private_key.pem").is_file()
    # Non-secret registration state travels with the key.
    assert json.loads((store / "primitives.json").read_text(encoding="utf-8")) == {"chain_id": 84532}
    assert did.read_did_file(root)["did"] == legacy_did


def test_relocation_refuses_a_conflicting_external_key_and_keeps_the_legacy_key(tmp_path):
    root = tmp_path / "hermes-home"
    root.mkdir()
    _make_legacy_profile(root)
    # A different identity already occupies the external slot for the same agent.
    did.load_or_create_did("agent-a", did_home_root=did.key_store_for_profile(root.resolve()))

    with pytest.raises(did.IdentityInconsistentError):
        IntegrityAgent.open(harness="hermes", profile_root=root, client_kwargs=_CLIENT)
    assert (root / ".integrity" / "did" / "agent-a" / "private_key.pem").is_file()


def test_default_resolution_relocates_before_it_would_mint_a_key(tmp_path, monkeypatch):
    """Registration calls load_or_create_did without a store; it must find the legacy key."""
    root = tmp_path / "codex-home"
    root.mkdir()
    legacy_did, _ = _make_legacy_profile(root)
    monkeypatch.setenv("CODEX_HOME", str(root))

    resolved_did, _, _ = did.load_or_create_did("agent-a")

    assert resolved_did == legacy_did
    assert not list(root.rglob("*.pem"))


def test_two_different_harness_roots_fail_closed_until_one_is_chosen(tmp_path, monkeypatch):
    hermes, codex = tmp_path / "hermes-home", tmp_path / "codex-home"
    hermes.mkdir()
    codex.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes))
    monkeypatch.setenv("CODEX_HOME", str(codex))

    with pytest.raises(AgentIdentityError, match="more than one harness root"):
        IntegrityAgent.open("agent-a", harness="codex", client_kwargs=_CLIENT)
    with pytest.raises(did.AmbiguousProfileRootError):
        did.load_or_create_did("agent-a")

    monkeypatch.setenv("INTEGRITY_PROFILE_ROOT", str(codex))
    agent = IntegrityAgent.open("agent-a", harness="codex", client_kwargs=_CLIENT)
    agent.close(flush=False)
    assert (codex / "agent.did.json").is_file()
    assert not (hermes / "agent.did.json").exists()


def test_the_same_root_in_two_variables_is_not_ambiguous(tmp_path, monkeypatch):
    root = tmp_path / "shared-home"
    root.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(root))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root))
    assert did.resolve_profile_root() == root.resolve()


def test_key_store_inside_the_harness_root_is_rejected(tmp_path, monkeypatch):
    root = tmp_path / "hermes-home"
    root.mkdir()
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(root / ".integrity" / "did"))
    with pytest.raises(AgentIdentityError, match="outside the harness root"):
        IntegrityAgent.open("agent-a", harness="hermes", profile_root=root, client_kwargs=_CLIENT)
    assert not list(root.rglob("*.pem"))


def test_did_file_rejects_secret_fields_and_mismatched_keys(tmp_path):
    root = tmp_path / "hermes-home"
    root.mkdir()
    agent = IntegrityAgent.open("agent-a", harness="hermes", profile_root=root, client_kwargs=_CLIENT)
    agent.close(flush=False)
    path = root / "agent.did.json"
    original = json.loads(path.read_text(encoding="utf-8"))

    path.write_text(json.dumps({**original, "private_key": "leak"}), encoding="utf-8")
    with pytest.raises(did.DidFileError, match="secret-bearing"):
        did.read_did_file(root)

    path.write_text(json.dumps({**original, "did": "did:integrity:" + "0" * 64}), encoding="utf-8")
    with pytest.raises(AgentIdentityError, match="does not derive"):
        IntegrityAgent.open(harness="hermes", profile_root=root, client_kwargs=_CLIENT)


def test_copied_harness_root_does_not_reuse_the_original_identity(tmp_path):
    root = tmp_path / "hermes-home"
    root.mkdir()
    agent = IntegrityAgent.open("agent-a", harness="hermes", profile_root=root, client_kwargs=_CLIENT)
    agent.close(flush=False)
    copy = tmp_path / "hermes-home-copy"
    copy.mkdir()
    (copy / "agent.did.json").write_bytes((root / "agent.did.json").read_bytes())

    with pytest.raises(AgentIdentityError, match="different harness root"):
        IntegrityAgent.open(harness="hermes", profile_root=copy, client_kwargs=_CLIENT)


def test_find_existing_identity_never_creates_a_key(tmp_path, monkeypatch):
    monkeypatch.setenv("INTEGRITY_DID_HOME", str(tmp_path / "dids"))
    assert did.find_existing_identity("unknown-agent") == (None, None)
    assert not (tmp_path / "dids" / "unknown-agent").exists()
    with pytest.raises(ValueError):
        did.find_existing_identity("../escape")
