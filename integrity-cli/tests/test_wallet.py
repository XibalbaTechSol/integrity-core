from __future__ import annotations

import pytest

from integrity_cli import identity, wallet


@pytest.fixture(autouse=True)
def _wallet_password(monkeypatch):
    monkeypatch.setenv("INTEGRITY_WALLET_PASSWORD", "test-only-password")


def _keystore_path(name: str):
    return identity.IDENTITY_DIR / f"{name}.wallet.json"


def test_generate_creates_and_persists_keystore():
    account = wallet.generate_or_load_evm_wallet("agent-a")
    assert account.address.startswith("0x")
    assert len(account.address) == 42


def test_reload_returns_same_address():
    account1 = wallet.generate_or_load_evm_wallet("agent-a")
    account2 = wallet.generate_or_load_evm_wallet("agent-a")
    assert account1.address == account2.address


def test_different_identities_get_different_wallets():
    account1 = wallet.generate_or_load_evm_wallet("agent-a")
    account2 = wallet.generate_or_load_evm_wallet("agent-b")
    assert account1.address != account2.address


def test_missing_password_raises(monkeypatch):
    monkeypatch.delenv("INTEGRITY_WALLET_PASSWORD", raising=False)
    with pytest.raises(wallet.WalletPasswordNotSet):
        wallet.generate_or_load_evm_wallet("agent-a")


def test_wrong_password_fails_to_decrypt():
    wallet.generate_or_load_evm_wallet("agent-a")
    import os

    os.environ["INTEGRITY_WALLET_PASSWORD"] = "a-different-password"
    with pytest.raises(wallet.WalletDecryptionError):
        wallet.generate_or_load_evm_wallet("agent-a")


def test_corrupted_keystore_raises_typed_error():
    wallet.generate_or_load_evm_wallet("agent-a")
    _keystore_path("agent-a").write_text("{not valid json")

    with pytest.raises(wallet.CorruptedKeystoreError):
        wallet.generate_or_load_evm_wallet("agent-a")


def test_load_evm_address_raises_typed_error_on_corrupted_keystore():
    wallet.generate_or_load_evm_wallet("agent-a")
    _keystore_path("agent-a").write_text("{not valid json")

    with pytest.raises(wallet.CorruptedKeystoreError):
        wallet.load_evm_address("agent-a")


def test_concurrent_bootstrap_converges_on_one_keypair(monkeypatch):
    """
    Regression test for PRODUCTION_GAPS.md §3: simulates two callers racing
    to bootstrap the SAME identity's wallet, both passing the
    `.exists()`-is-False check before either has written anything. The fix's
    os.link-based claim must make both callers agree on ONE keypair
    regardless of scheduling order. Mirrors integrity-sdk's
    tests/unit/test_wallet.py::test_concurrent_bootstrap_converges_on_one_keypair.
    """
    import os as _os

    real_open = _os.open
    calls = {"count": 0}

    def racing_open(path, flags, mode=0o777):
        calls["count"] += 1
        if calls["count"] == 1 and ".tmp." in str(path):
            wallet.generate_or_load_evm_wallet("agent-race")
        return real_open(path, flags, mode)

    monkeypatch.setattr(_os, "open", racing_open)

    account = wallet.generate_or_load_evm_wallet("agent-race")
    reloaded = wallet.generate_or_load_evm_wallet("agent-race")

    assert account.address == reloaded.address
    keystore_path = _keystore_path("agent-race")
    assert keystore_path.exists()
    leftovers = [p for p in keystore_path.parent.iterdir() if ".tmp." in p.name]
    assert leftovers == []


def test_load_evm_address_does_not_require_password(monkeypatch):
    account = wallet.generate_or_load_evm_wallet("agent-a")
    monkeypatch.delenv("INTEGRITY_WALLET_PASSWORD", raising=False)
    assert wallet.load_evm_address("agent-a") == account.address


def test_load_evm_address_none_when_no_wallet():
    assert wallet.load_evm_address("never-created") is None


def test_wallet_exists():
    assert wallet.wallet_exists("agent-a") is False
    wallet.generate_or_load_evm_wallet("agent-a")
    assert wallet.wallet_exists("agent-a") is True


def test_keystore_file_is_owner_only_permissions():
    import stat

    wallet.generate_or_load_evm_wallet("agent-a")
    mode = _keystore_path("agent-a").stat().st_mode
    assert stat.S_IMODE(mode) == (stat.S_IRUSR | stat.S_IWUSR)
