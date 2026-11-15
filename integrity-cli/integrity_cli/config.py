"""
Configuration management for the Integrity CLI.

Config is stored as JSON at ~/.integrity-cli/config.json. Values can be
overridden per-invocation by environment variables using the exact names
pinned in docs/INTERFACE_CONTRACT.md section 3 (ORACLE_URL,
BCC_MIDDLEWARE_URL) so this CLI behaves the same way as integrity-sdk and
other packages when wired into docker-compose or CI, without needing a
config file at all.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Optional

CONFIG_DIR = Path.home() / ".integrity-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Safe defaults matching docs/INTERFACE_CONTRACT.md section 2 (local
# docker-compose port map). Deliberately NO default AUTH_TOKEN: the old
# prototype shipped "mock_demo_token" as a hardcoded default, which is
# exactly the kind of insecure default that ends up copy-pasted into a
# shared/staging config by accident. Auth must be configured explicitly via
# `integrity auth set-token` or the AUTH_TOKEN env var -- there is no
# fallback value here.
DEFAULT_CONFIG: dict[str, Any] = {
    "ORACLE_URL": "http://localhost:8080",
    "BCC_MIDDLEWARE_URL": "http://localhost:8000",
    "AUTH_TOKEN": "",
    # "local" relaxes the placeholder-token check in get_auth_token() below.
    # Anything else (e.g. "staging", "prod") is treated as a real environment
    # where an obviously-fake token must not silently work.
    "ENVIRONMENT": "local",
    # On-chain endpoints. Read through get_config_value like everything else, so a
    # --network profile can move them together with ORACLE_URL.
    "RPC_URL": "http://localhost:8545",
    "DEPLOYMENTS_FILE": "../deployments.local.json",
}

# --network profiles. A profile fixes the RPC, the deployments file and the Oracle as one unit,
# so a command can never read Base Sepolia's deployments through a local RPC (or the reverse).
# Precedence: an explicit flag > env var > active profile > config file > DEFAULT_CONFIG.
# A profile sets ENVIRONMENT to something other than "local" for real networks, which keeps
# get_auth_token() refusing placeholder tokens there.
_REPO_ROOT = Path(__file__).resolve().parents[2]
NETWORK_PROFILES: dict[str, dict[str, str]] = {
    "local": {
        "ORACLE_URL": "http://localhost:8080",
        "BCC_MIDDLEWARE_URL": "http://localhost:8000",
        "RPC_URL": "http://localhost:8545",
        "DEPLOYMENTS_FILE": "../deployments.local.json",
        "ENVIRONMENT": "local",
    },
    "base-sepolia": {
        "ORACLE_URL": "https://integrity-oracle.onrender.com",
        # Public read-only endpoint. For writes or heavier reads, override RPC_URL (env or flag)
        # with a keyed provider; never put that key in this file.
        "RPC_URL": "https://sepolia.base.org",
        # Resolved from the source checkout; set DEPLOYMENTS_FILE when the CLI is installed elsewhere.
        "DEPLOYMENTS_FILE": str(_REPO_ROOT / "deployments.baseSepolia.json"),
        "ENVIRONMENT": "base-sepolia",
    },
}
NETWORK_ENV = "INTEGRITY_NETWORK"

# Set by the root `--network` flag for this process; wins over INTEGRITY_NETWORK and the
# config file's NETWORK key.
_network: Optional[str] = None

# If someone sets one of these as AUTH_TOKEN while ENVIRONMENT != "local",
# we fail loudly instead of quietly authenticating with a demo value.
_KNOWN_INSECURE_TOKENS = {"mock_demo_token", "changeme", "test", "demo", "insecure", "password"}


def load_config() -> dict[str, Any]:
    """Load configuration from disk, filling in any keys missing from an
    older/partial config file with defaults (forward-compatible with config
    files written by earlier versions of this CLI)."""
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, sort_keys=True)
    # The config file can hold AUTH_TOKEN -- restrict it to the owner, same
    # as the private key files under ~/.integrity-cli/identity/.
    os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)


def _check_network(name: str) -> str:
    if name not in NETWORK_PROFILES:
        raise ValueError(f"unknown network {name!r}; choose one of {', '.join(NETWORK_PROFILES)}")
    return name


def set_network(name: Optional[str]) -> None:
    """Select a --network profile for this process (None clears the flag)."""
    global _network
    _network = _check_network(name) if name is not None else None


def active_network() -> Optional[str]:
    """The profile in force: the --network flag, else $INTEGRITY_NETWORK, else config NETWORK.

    Raises ValueError for an unknown name from any of those sources, so a typo fails loudly
    instead of silently falling back to localhost.
    """
    if _network is not None:
        return _network
    name = os.environ.get(NETWORK_ENV) or _file_config().get("NETWORK")
    return _check_network(name) if name else None


def _file_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def value_with_source(key: str) -> tuple[Any, str]:
    """(value, source), source being "env", "profile:<name>", "config file" or "default".

    Environment variables win over everything on disk (INTERFACE_CONTRACT.md section 3), so
    docker-compose/CI can override endpoints without touching a developer's config. A command's
    own flag beats all of these; callers apply it as `flag or get_config_value(key)`.
    """
    if key in os.environ:
        return os.environ[key], "env"
    network = active_network()
    if network is not None and key in NETWORK_PROFILES[network]:
        return NETWORK_PROFILES[network][key], f"profile:{network}"
    on_disk = _file_config()
    if key in on_disk:
        return on_disk[key], "config file"
    return DEFAULT_CONFIG.get(key), "default"


def get_config_value(key: str) -> Any:
    """Read a single config value; see value_with_source for the precedence."""
    return value_with_source(key)[0]


def set_config_value(key: str, value: str) -> None:
    config = load_config()
    config[key] = value
    save_config(config)


def get_auth_token() -> str | None:
    """Return the configured auth token, or None if none is usable.

    Refuses known-insecure placeholder values outside of local dev so a
    demo/test token can't accidentally authenticate against a real
    deployment -- see _KNOWN_INSECURE_TOKENS above.
    """
    token = get_config_value("AUTH_TOKEN")
    if not token:
        return None
    environment = get_config_value("ENVIRONMENT")
    if environment != "local" and token.strip().lower() in _KNOWN_INSECURE_TOKENS:
        raise ValueError(
            f"Refusing to use placeholder AUTH_TOKEN {token!r} while "
            f"ENVIRONMENT={environment!r}. Configure a real token with "
            "`integrity auth set-token <token>` or the AUTH_TOKEN env var, "
            "or set ENVIRONMENT=local if this really is a local dev box."
        )
    return token
