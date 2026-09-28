"""Local signed-pack distribution and version-pin reference implementation.

The store is intentionally not a package registry or billing surface. It records
which verified pack a tenant is allowed to use locally; every resolution calls
``load_pack`` again with the pinned hash so a changed source directory cannot be
silently enforced.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Collection

from .packs import LoadedPack, PackError, load_pack


class PackPinError(ValueError):
    """A pack could not be pinned or no longer matches its tenant pin."""


@dataclass(frozen=True)
class PackPin:
    tenant_id: str
    pack_name: str
    version: str
    pack_hash: str
    signer_key: str
    source_dir: str


class PackPinStore:
    """Atomic local store of tenant -> verified pack pins."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PackPinError(f"unable to read pack pins: {exc}") from exc
        if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, dict) for key, item in value.items()):
            raise PackPinError("pack pin document is malformed")
        return value

    def _write(self, value: dict[str, dict[str, str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    @staticmethod
    def _key(tenant_id: str, pack_name: str) -> str:
        if not tenant_id or not pack_name:
            raise PackPinError("tenant_id and pack_name are required")
        return f"{tenant_id}\x00{pack_name}"

    def pin(
        self,
        tenant_id: str,
        pack_dir: str | Path,
        *,
        trusted_signers: Collection[str],
        replace: bool = False,
        expected_previous_hash: str | None = None,
    ) -> PackPin:
        try:
            loaded = load_pack(pack_dir, trusted_signers=trusted_signers)
        except PackError as exc:
            raise PackPinError(f"pack verification failed: {exc}") from exc
        pin = PackPin(
            tenant_id=tenant_id,
            pack_name=loaded.manifest["name"],
            version=loaded.manifest["version"],
            pack_hash=loaded.pack_hash,
            signer_key=loaded.signer_key,
            source_dir=str(Path(pack_dir).resolve()),
        )
        document = self._read()
        key = self._key(tenant_id, pin.pack_name)
        current = document.get(key)
        if current is not None:
            if current == asdict(pin):
                return pin
            if not replace:
                raise PackPinError(f"pack pin {tenant_id}/{pin.pack_name} already exists; explicit replacement is required")
            if expected_previous_hash != current.get("pack_hash"):
                raise PackPinError("pack replacement requires the currently pinned hash")
        document[key] = asdict(pin)
        self._write(document)
        return pin

    def resolve(self, tenant_id: str, pack_name: str, *, trusted_signers: Collection[str]) -> LoadedPack:
        key = self._key(tenant_id, pack_name)
        pin = self._read().get(key)
        if pin is None:
            raise PackPinError(f"no pack pin exists for {tenant_id}/{pack_name}")
        try:
            loaded = load_pack(
                pin["source_dir"],
                trusted_signers=trusted_signers,
                expected_pack_hash=pin["pack_hash"],
            )
        except (PackError, KeyError) as exc:
            raise PackPinError(f"pinned pack no longer verifies: {exc}") from exc
        if loaded.manifest["name"] != pin["pack_name"] or loaded.manifest["version"] != pin["version"]:
            raise PackPinError("pinned pack metadata changed")
        if loaded.signer_key != pin["signer_key"]:
            raise PackPinError("pinned pack signer changed")
        return loaded

    def get(self, tenant_id: str, pack_name: str) -> PackPin | None:
        value = self._read().get(self._key(tenant_id, pack_name))
        return PackPin(**value) if value is not None else None
