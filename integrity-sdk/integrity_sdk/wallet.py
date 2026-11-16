"""
EVM (secp256k1) wallet module for the Integrity Protocol SDK.

This is deliberately a SEPARATE keypair from did.py's Ed25519 identity key,
not a re-derivation of it. The DID key proves "which agent said this" for
off-chain BCC commitments and telemetry signatures (§4.1/§4.2); the EVM key
proves "which wallet deployed/controls this agent's on-chain primitives" —
per docs/INTERFACE_CONTRACT.md's "Agent Primitives" section, the whole point
of self-sovereign registration is that the agent's OWN wallet signs the
SovereignAgent deployment transaction, so that deployment-time
signature is real, independently-verifiable proof of control. Mixing the two
key types (e.g. reusing the Ed25519 seed as an EVM private key) would also be
cryptographically wrong: EVM/secp256k1 keys and Ed25519 keys are different
curves with different scalar validity ranges, there is no safe bit-for-bit
reuse between them.

Storage posture is intentionally stronger than did.py's plain PEM: this key
signs real value-bearing transactions (contract deploys, ITK transfers), so
it's persisted as an Ethereum V3 encrypted keystore (the same format
MetaMask/geth use) rather than plaintext, gated by a password the caller must
supply out-of-band (INTEGRITY_WALLET_PASSWORD) rather than a convenience
default.
"""

from __future__ import annotations

import json
import os
import stat
import uuid
from pathlib import Path
from typing import Optional

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address

# Registers extended key-derivation/message-signing functionality onto
# `Account` (HD wallets, EIP-712, etc.) — not strictly required for the plain
# `Account.create`/`Account.encrypt` calls below, but importing it is the
# documented way to get the full `eth_account` feature surface predictably
# available for any sibling module that reaches for it later (e.g. EIP-712
# domain-separated signing for a future off-chain order/attestation format).
Account.enable_unaudited_hdwallet_features()


class WalletPasswordNotSet(RuntimeError):
    """Raised when a keystore operation needs INTEGRITY_WALLET_PASSWORD and
    it isn't set. No silent fallback to an empty/default password — an EVM
    wallet controls real (even if testnet) value, and a convenience default
    here would be exactly the kind of silent security downgrade did.py's own
    docstring warns against for the DID key."""


class CorruptedKeystoreError(RuntimeError):
    """Raised when a keystore.json file exists but isn't valid JSON (a
    truncated/torn write from a prior crash, disk corruption, etc). Wraps
    the raw json.JSONDecodeError with the keystore path so a caller/log
    doesn't have to guess which file was the problem — PRODUCTION_GAPS.md
    Sec3: this used to raise the bare JSONDecodeError, which reads as an
    unrelated bug rather than "this specific file is broken"."""


class WalletDecryptionError(RuntimeError):
    """Raised when a keystore.json exists and parses fine, but the supplied
    INTEGRITY_WALLET_PASSWORD doesn't decrypt it. Wraps eth_account's raw
    ValueError (a generic "MAC mismatch"-style message) with a clearer,
    keystore-specific error — PRODUCTION_GAPS.md Sec3."""


def _default_wallet_home() -> Path:
    override = os.getenv("INTEGRITY_WALLET_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".integrity" / "wallet"


def wallet_dir(agent_id: Optional[str]) -> Path:
    """Public so registration.py / the CLI can co-locate other per-agent
    on-chain state (e.g. a cached primitives.json) without duplicating the
    path-resolution logic — mirrors did.py's `agent_dir`."""
    base = _default_wallet_home()
    return base / (agent_id or "default")


def _wallet_password() -> str:
    password = os.getenv("INTEGRITY_WALLET_PASSWORD")
    if not password:
        raise WalletPasswordNotSet(
            "INTEGRITY_WALLET_PASSWORD is not set. An EVM wallet keystore "
            "cannot be created or unlocked without it — see wallet.py's "
            "module docstring for why this has no default."
        )
    return password


def _load_keystore(keystore_path: Path, password: str) -> LocalAccount:
    try:
        keystore_json = json.loads(keystore_path.read_text())
    except json.JSONDecodeError as exc:
        raise CorruptedKeystoreError(
            f"keystore at {keystore_path} is not valid JSON (truncated write? disk "
            f"corruption?) — cannot recover the private key from this file: {exc}"
        ) from exc
    try:
        private_key = Account.decrypt(keystore_json, password)
    except ValueError as exc:
        raise WalletDecryptionError(
            f"could not decrypt keystore at {keystore_path} with the supplied "
            f"INTEGRITY_WALLET_PASSWORD — wrong password, or the file is corrupted: {exc}"
        ) from exc
    return Account.from_key(private_key)


def generate_or_load_evm_wallet(agent_id: Optional[str] = None) -> LocalAccount:
    """
    Load the persisted EVM keypair for `agent_id`, or generate a fresh
    secp256k1 keypair and encrypted keystore if none exists yet.

    Returns an `eth_account.signers.local.LocalAccount` — has `.address` and
    `.key` (raw private key bytes) and can sign transactions/messages
    directly, or be handed to `chain.py`'s deploy/registration functions.

    Creation is atomic against two concurrent callers for the same
    `agent_id` (PRODUCTION_GAPS.md Sec3): the old `.exists()` check then
    `write_text()` was a check-then-act race where two callers racing to
    bootstrap the same identity could each generate a DIFFERENT keypair,
    with whichever wrote last silently winning — the loser then keeps
    signing with an in-memory account whose key the persisted file no
    longer contains, permanently locking it out of anything (like a
    SovereignAgent) it already deployed. Fixed by writing the new keystore
    to a per-call temp file first, then claiming the final path with
    `os.link` (fails atomically with `FileExistsError` if another caller
    already claimed it first, unlike `os.rename`, which would silently
    overwrite) — the loser discards its own generated keypair and loads the
    winner's instead, so every caller ends up agreeing on the same account.
    """
    this_wallet_dir = wallet_dir(agent_id)
    this_wallet_dir.mkdir(parents=True, exist_ok=True)
    keystore_path = this_wallet_dir / "keystore.json"

    password = _wallet_password()

    if keystore_path.exists():
        return _load_keystore(keystore_path, password)

    account: LocalAccount = Account.create()
    keystore_json = Account.encrypt(account.key, password)

    tmp_path = this_wallet_dir / f".keystore.json.tmp.{os.getpid()}.{uuid.uuid4().hex}"
    try:
        fd = os.open(str(tmp_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(keystore_json, indent=2) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

        try:
            os.link(str(tmp_path), str(keystore_path))
        except FileExistsError:
            # Another caller won the race and already created a (possibly
            # different) keypair between our .exists() check and this claim
            # -- load THEIRS rather than silently returning a keypair no
            # persisted file will ever agree with again.
            return _load_keystore(keystore_path, password)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Keystore JSON is password-encrypted, but owner-only permissions are
    # still the right default posture — same reasoning as did.py's PEM file.
    # (Already created 0o600 via os.open above; chmod again defensively in
    # case umask altered it — cheap, and keeps this invariant explicit here
    # rather than only implicit in the os.open flags.)
    os.chmod(str(keystore_path), stat.S_IRUSR | stat.S_IWUSR)

    return account


def load_evm_address(agent_id: Optional[str] = None) -> Optional[str]:
    """
    Read-only address lookup that does NOT require the wallet password —
    the V3 keystore format's top-level `address` field is unencrypted (only
    the private key material inside `crypto` is), so callers that just need
    "does this agent have a wallet, and what's its address" (e.g. the CLI's
    `agent status` command, or a UI) don't need to prompt for a password.
    Returns None if no keystore exists yet.
    """
    keystore_path = wallet_dir(agent_id) / "keystore.json"
    if not keystore_path.exists():
        return None
    try:
        keystore_json = json.loads(keystore_path.read_text())
    except json.JSONDecodeError as exc:
        raise CorruptedKeystoreError(
            f"keystore at {keystore_path} is not valid JSON (truncated write? disk corruption?): {exc}"
        ) from exc
    raw_address = keystore_json.get("address")
    if not raw_address:
        return None
    return to_checksum_address("0x" + raw_address.removeprefix("0x"))
