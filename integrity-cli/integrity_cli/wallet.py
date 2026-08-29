"""
EVM (secp256k1) wallet module for the Integrity CLI.

Deliberately a SEPARATE keypair from identity.py's Ed25519 DID key, not a
re-derivation of it -- same rationale as integrity-sdk's wallet.py (see that
module's docstring, which this file's logic mirrors): the DID key proves
"which agent said this" for off-chain DID documents; the EVM key proves
"which wallet deployed/controls this agent's on-chain primitives" -- per
docs/INTERFACE_CONTRACT.md's "Agent Primitives" section, self-sovereign
registration means the agent's OWN wallet signs the SovereignAgent/
StateAnchor deployment transactions, so that signature is real,
independently-verifiable proof of control. EVM/secp256k1 and Ed25519 are
different curves with different scalar validity ranges -- there is no safe
bit-for-bit reuse between the two key types.

This is a CLI-local reimplementation, not an import of integrity_sdk.wallet
-- see identity.py's module docstring for why this package deliberately
duplicates identity/wallet logic instead of depending on the sibling SDK
package while both are still in flux. The on-disk format and library calls
are the same (Ethereum V3 encrypted keystore via eth_account); only the
storage path convention differs, to match this CLI's own layout:
~/.integrity-cli/identity/<name>.wallet.json, alongside identity.py's
~/.integrity-cli/identity/<name>.pem -- the two files are siblings for the
same local identity, distinguished only by extension. Note this module reads
identity.IDENTITY_DIR *inside* each function (not a copied module-level
constant) so that tests which monkeypatch identity.IDENTITY_DIR (see
tests/conftest.py's isolated_home fixture) transparently also redirect
wallet storage -- no separate test scaffolding needed to keep the two paths
in sync.

Storage posture is intentionally stronger than identity.py's plain PEM: this
key signs real value-bearing transactions (contract deploys, ITK transfers),
so it's persisted as an Ethereum V3 encrypted keystore (the same format
MetaMask/geth use) rather than plaintext, gated by a password the caller
must supply out-of-band (INTEGRITY_WALLET_PASSWORD) rather than a
convenience default.
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

from . import identity

# Registers extended key-derivation/message-signing functionality onto
# `Account` (HD wallets, EIP-712, etc.) -- not strictly required for the
# plain `Account.create`/`Account.encrypt` calls below, but importing it
# keeps the full `eth_account` feature surface available, same as
# integrity-sdk's wallet.py.
Account.enable_unaudited_hdwallet_features()


class WalletPasswordNotSet(RuntimeError):
    """Raised when a keystore operation needs INTEGRITY_WALLET_PASSWORD and
    it isn't set. No silent fallback to an empty/default password -- an EVM
    wallet controls real (even if testnet) value, and a convenience default
    here would be exactly the kind of silent security downgrade identity.py's
    own docstring warns against for the DID key's storage posture."""


class CorruptedKeystoreError(RuntimeError):
    """Raised when a keystore file exists but isn't valid JSON (a truncated/
    torn write from a prior crash, disk corruption, etc). PRODUCTION_GAPS.md
    §3 -- mirrors integrity-sdk's wallet.py (same bug, duplicated logic, both
    packages fixed identically per that finding's own "duplicated in both
    packages" note)."""


class WalletDecryptionError(RuntimeError):
    """Raised when a keystore parses fine but the supplied
    INTEGRITY_WALLET_PASSWORD doesn't decrypt it. Wraps eth_account's raw
    ValueError with a clearer, keystore-specific error -- PRODUCTION_GAPS.md
    §3, mirrors integrity-sdk's wallet.py."""


def _wallet_path(name: str) -> Path:
    return identity.IDENTITY_DIR / f"{name}.wallet.json"


def _load_keystore(keystore_path: Path, password: str) -> LocalAccount:
    try:
        keystore_json = json.loads(keystore_path.read_text())
    except json.JSONDecodeError as exc:
        raise CorruptedKeystoreError(
            f"keystore at {keystore_path} is not valid JSON (truncated write? disk "
            f"corruption?) -- cannot recover the private key from this file: {exc}"
        ) from exc
    try:
        private_key = Account.decrypt(keystore_json, password)
    except ValueError as exc:
        raise WalletDecryptionError(
            f"could not decrypt keystore at {keystore_path} with the supplied "
            f"INTEGRITY_WALLET_PASSWORD -- wrong password, or the file is corrupted: {exc}"
        ) from exc
    return Account.from_key(private_key)


def _wallet_password() -> str:
    password = os.getenv("INTEGRITY_WALLET_PASSWORD")
    if not password:
        raise WalletPasswordNotSet(
            "INTEGRITY_WALLET_PASSWORD is not set. An EVM wallet keystore "
            "cannot be created or unlocked without it -- see wallet.py's "
            "module docstring for why this has no default."
        )
    return password


def wallet_exists(name: str = "default") -> bool:
    return _wallet_path(name).exists()


def generate_or_load_evm_wallet(name: str = "default") -> LocalAccount:
    """
    Load the persisted EVM keypair for the local identity `name`, or
    generate a fresh secp256k1 keypair and encrypted keystore if none exists
    yet.

    Returns an `eth_account.signers.local.LocalAccount` -- has `.address`
    and `.key` (raw private key bytes) and can sign transactions/messages
    directly, or be handed to `chain.py`'s deploy/registration functions.

    Creation is atomic against two concurrent callers for the same `name`
    (PRODUCTION_GAPS.md §3): the old `.exists()` check then `write_text()`
    was a check-then-act race where two callers racing to bootstrap the same
    identity could each generate a DIFFERENT keypair, with whichever wrote
    last silently winning -- the loser then keeps signing with an in-memory
    account whose key the persisted file no longer contains. Fixed by
    writing the new keystore to a per-call temp file first, then claiming
    the final path with `os.link` (fails atomically with `FileExistsError`
    if another caller already claimed it, unlike `os.rename`, which would
    silently overwrite) -- the loser discards its own generated keypair and
    loads the winner's instead. Mirrors integrity-sdk's wallet.py fix
    exactly (same bug, duplicated logic, both packages fixed identically).
    """
    identity.IDENTITY_DIR.mkdir(parents=True, exist_ok=True)
    keystore_path = _wallet_path(name)

    password = _wallet_password()

    if keystore_path.exists():
        return _load_keystore(keystore_path, password)

    account: LocalAccount = Account.create()
    keystore_json = Account.encrypt(account.key, password)

    tmp_path = keystore_path.parent / f".{keystore_path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
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
    # still the right default posture -- same reasoning as identity.py's PEM.
    # (Already created 0o600 via os.open above; chmod again defensively in
    # case umask altered it.)
    os.chmod(str(keystore_path), stat.S_IRUSR | stat.S_IWUSR)

    return account


def load_evm_address(name: str = "default") -> Optional[str]:
    """
    Read-only address lookup that does NOT require the wallet password --
    the V3 keystore format's top-level `address` field is unencrypted (only
    the private key material inside `crypto` is), so callers that just need
    "does this identity have a wallet, and what's its address" don't need to
    prompt for a password. Returns None if no keystore exists yet.
    """
    keystore_path = _wallet_path(name)
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
