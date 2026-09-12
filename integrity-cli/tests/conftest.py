"""
Shared test fixtures.

Every test gets its own tmp_path standing in for the user's home directory
(~/.integrity-cli) -- this is what lets the suite run safely in CI/dev
without ever touching a real developer's actual config or identity keys,
and lets tests run in parallel without clobbering each other's state.
"""
from __future__ import annotations

import pytest
from rich.console import Console

from integrity_cli import bcc, config, identity, wallet
from integrity_cli import main as main_module


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect every module-level path constant to a per-test tmp dir, and
    clear any AUTH_TOKEN/ORACLE_URL/etc. the host shell might have set (so a
    developer's real env doesn't leak into test assertions)."""
    config_dir = tmp_path / ".integrity-cli"
    identity_dir = config_dir / "identity"

    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(identity, "IDENTITY_DIR", identity_dir)
    monkeypatch.setattr(bcc, "NONCE_STATE_FILE", identity_dir / "nonces.json")
    # wallet.py now has its own storage root (matching integrity-sdk's separate
    # INTEGRITY_WALLET_HOME) rather than piggybacking on identity.IDENTITY_DIR --
    # redirect it explicitly so tests don't touch a real ~/.integrity/wallet.
    monkeypatch.setattr(wallet, "WALLET_DIR", config_dir / "wallet")

    for env_var in ("ORACLE_URL", "BCC_MIDDLEWARE_URL", "AUTH_TOKEN", "ENVIRONMENT"):
        monkeypatch.delenv(env_var, raising=False)

    # main.py's `console` is constructed at import time, so it captured a
    # force-terminal setting before this fixture runs — setting NO_COLOR in the
    # env now wouldn't affect it. Replace it with a plain console for the duration
    # of each test: `no_color` strips ANSI color escapes and `force_terminal=False`
    # disables the animated `console.status(...)` spinner (whose cursor/animation
    # control codes would otherwise pollute captured stdout). Real CLI output,
    # constructed outside tests, stays colored and animated.
    monkeypatch.setattr(main_module, "console", Console(no_color=True, force_terminal=False))

    return tmp_path
