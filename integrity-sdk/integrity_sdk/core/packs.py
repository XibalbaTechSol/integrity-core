"""Signed policy packs (SDK contract C3): what gets enforced is exactly what was signed.

A pack is a directory:

    pack.yaml       manifest (format, name, version, kernel_range, entrypoint, event classes)
    policy.rego     the policy itself (any number of files; every file is covered)
    controls.yaml   control citations (HIPAA, SOC 2, ...), B1
    pack.sig.json   written by `sign_pack`; the only file excluded from hashing

`compile_pack` reads every other regular file once, hashes each, and builds a
*compiled manifest*: the manifest fields plus a ``files`` map of path -> sha256.
The pack hash is the JCS SHA-256 of that compiled manifest, so it covers the
Rego as well as the metadata. (Shield previously signed a JSON bundle while
enforcing Rego the signature never covered.)

`load_pack` is the only way a gate obtains a pack. It re-reads the directory,
recompiles, and accepts the pack only if the recompiled manifest is
byte-identical to the one the signature covers, the signer is trusted, and the
format, decision contract and expiry are acceptable. It returns the file bytes
it verified, and the evaluator must run those bytes, never re-read the
directory, so there is no window between verification and use. A load either
succeeds whole or raises `PackError`; a gate keeps its previous pack on failure
("atomic pack load").

Signing is Ed25519 over a domain-separated message
(``b"integrity.pack.v1\\x00" || JCS(compiled manifest)``), so a pack signature
can never be replayed as a receipt or checkpoint signature.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection, Dict, Mapping, Optional

import yaml

from ..did import Keypair, public_key_multibase
from .decision import DECISION_CONTRACT, NO_MATCH_DEFAULTS
from .jcs import canonical_bytes
from .signing import signer_matches, verify_multibase_signature

PACK_FORMAT = "integrity.pack/1"
SUPPORTED_PACK_FORMATS = frozenset({PACK_FORMAT})
SUPPORTED_DECISION_CONTRACTS = frozenset({DECISION_CONTRACT})
MANIFEST_FILE = "pack.yaml"
SIGNATURE_FILE = "pack.sig.json"
SIGNATURE_DOC_VERSION = "integrity.pack-signature/1"
_PACK_DOMAIN = b"integrity.pack.v1\x00"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_EVENT_CLASS_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_ENTRYPOINT_RE = re.compile(r"^data(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")
_REQUIRED_FIELDS = ("pack_format", "name", "version", "kernel_range", "decision_contract", "entrypoint", "event_classes")
_OPTIONAL_FIELDS = ("not_after", "description")


class PackError(Exception):
    """A pack was refused. `code` is stable and suitable for a receipt reason or a log field."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class CompiledPack:
    manifest: Dict[str, Any]  # the compiled manifest the signature covers
    files: Dict[str, bytes]  # relative POSIX path -> exact bytes that were hashed
    pack_hash: str


@dataclass(frozen=True)
class LoadedPack(CompiledPack):
    signer_key: str

    @property
    def event_defaults(self) -> Dict[str, str]:
        """event_class -> no-match default, for `decision.resolve`."""
        return {name: spec["no_match"] for name, spec in self.manifest["event_classes"].items()}

    @property
    def entrypoint(self) -> str:
        return self.manifest["entrypoint"]

    def policy_modules(self) -> Dict[str, str]:
        """The verified Rego sources, for handing to the evaluator (never re-read from disk)."""
        return {path: data.decode("utf-8") for path, data in self.files.items() if path.endswith(".rego")}


def _validate_manifest(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise PackError("MALFORMED", f"{MANIFEST_FILE} must be a mapping")
    unknown = set(raw) - set(_REQUIRED_FIELDS) - set(_OPTIONAL_FIELDS)
    if unknown:
        raise PackError("MALFORMED", f"unknown manifest fields: {sorted(unknown)}")
    missing = [key for key in _REQUIRED_FIELDS if key not in raw]
    if missing:
        raise PackError("MALFORMED", f"missing manifest fields: {missing}")
    if not isinstance(raw["name"], str) or not _NAME_RE.fullmatch(raw["name"]):
        raise PackError("MALFORMED", "name must be lowercase [a-z0-9_-], starting with a letter")
    if not isinstance(raw["version"], str) or not _VERSION_RE.fullmatch(raw["version"]):
        raise PackError("MALFORMED", "version must be semver (MAJOR.MINOR.PATCH)")
    if not isinstance(raw["kernel_range"], str) or not raw["kernel_range"].strip():
        raise PackError("MALFORMED", "kernel_range must be a non-empty version range")
    if not isinstance(raw["entrypoint"], str) or not _ENTRYPOINT_RE.fullmatch(raw["entrypoint"]):
        raise PackError("MALFORMED", "entrypoint must be a Rego rule path such as data.integrity.pack.decision")
    classes = raw["event_classes"]
    if not isinstance(classes, dict) or not classes:
        raise PackError("MALFORMED", "event_classes must declare at least one event class")
    for name, spec in classes.items():
        if not isinstance(name, str) or not _EVENT_CLASS_RE.fullmatch(name):
            raise PackError("MALFORMED", f"invalid event class name {name!r}")
        if not isinstance(spec, dict) or set(spec) != {"no_match"} or spec["no_match"] not in NO_MATCH_DEFAULTS:
            raise PackError(
                "MALFORMED", f"event class {name!r} must declare exactly no_match: deny | log_only | permit"
            )
    if "not_after" in raw:
        _parse_timestamp(raw["not_after"])
    if "description" in raw and not isinstance(raw["description"], str):
        raise PackError("MALFORMED", "description must be a string")
    return raw


def _parse_timestamp(value: Any) -> _dt.datetime:
    if isinstance(value, _dt.datetime):  # YAML may already have parsed it
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PackError("MALFORMED", f"not_after is not an ISO 8601 timestamp: {value!r}") from exc
    else:
        raise PackError("MALFORMED", "not_after must be an ISO 8601 timestamp")
    if parsed.tzinfo is None:
        raise PackError("MALFORMED", "not_after must carry a timezone (use Z for UTC)")
    return parsed


def _read_files(pack_dir: Path) -> Dict[str, bytes]:
    if not pack_dir.is_dir():
        raise PackError("MALFORMED", f"{pack_dir} is not a directory")
    files: Dict[str, bytes] = {}
    for path in sorted(pack_dir.rglob("*")):
        relative = path.relative_to(pack_dir).as_posix()
        if path.is_symlink():
            # A symlink would let the enforced bytes change without the directory changing.
            raise PackError("MALFORMED", f"symlinks are not allowed in a pack: {relative}")
        if path.is_dir() or relative == SIGNATURE_FILE:
            continue
        files[relative] = path.read_bytes()
    if MANIFEST_FILE not in files:
        raise PackError("MALFORMED", f"{MANIFEST_FILE} is missing")
    if not any(name.endswith(".rego") for name in files):
        raise PackError("MALFORMED", "a pack must contain at least one .rego file")
    return files


def _compile_from_files(files: Dict[str, bytes]) -> CompiledPack:
    try:
        raw = yaml.safe_load(files[MANIFEST_FILE].decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PackError("MALFORMED", f"{MANIFEST_FILE} is not valid YAML") from exc
    manifest = _validate_manifest(raw)
    compiled: Dict[str, Any] = {key: manifest[key] for key in _REQUIRED_FIELDS}
    if "not_after" in manifest:
        compiled["not_after"] = _parse_timestamp(manifest["not_after"]).astimezone(_dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    if "description" in manifest:
        compiled["description"] = manifest["description"]
    compiled["files"] = {path: "sha256:" + hashlib.sha256(data).hexdigest() for path, data in sorted(files.items())}
    pack_hash = "sha256:" + hashlib.sha256(canonical_bytes(compiled)).hexdigest()
    return CompiledPack(manifest=compiled, files=dict(files), pack_hash=pack_hash)


def compile_pack(pack_dir: str | Path) -> CompiledPack:
    """Read, validate and hash a pack directory (does not check any signature)."""
    return _compile_from_files(_read_files(Path(pack_dir)))


def sign_pack(pack_dir: str | Path, signer: Keypair) -> CompiledPack:
    """Compile the pack and write `pack.sig.json` beside it. Returns what was signed.

    Run by the operator (or CI) after reviewing the compiled output; adapters
    produce packs but never sign them.
    """
    pack_dir = Path(pack_dir)
    compiled = compile_pack(pack_dir)
    signature = signer.sign(_PACK_DOMAIN + canonical_bytes(compiled.manifest))
    document = {
        "signature_version": SIGNATURE_DOC_VERSION,
        "pack_hash": compiled.pack_hash,
        "signer_key": public_key_multibase(signer.public_bytes()),
        "signature": signature.hex(),
        "signed_manifest": compiled.manifest,
    }
    (pack_dir / SIGNATURE_FILE).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return compiled


def load_pack(
    pack_dir: str | Path,
    *,
    trusted_signers: Collection[str],
    expected_pack_hash: Optional[str] = None,
    now: Optional[_dt.datetime] = None,
) -> LoadedPack:
    """Verify and load a signed pack for enforcement, or raise `PackError`.

    `trusted_signers` holds multibase Ed25519 public keys (the organization's
    pack-signing keys); it must be non-empty. `expected_pack_hash` pins an
    exact version (a device told which pack to run refuses any other).
    Refusal codes: MALFORMED, UNSIGNED, BAD_SIGNATURE, UNTRUSTED_SIGNER,
    TAMPERED, INCOMPATIBLE, STALE, UNEXPECTED_PACK.
    """
    if not trusted_signers:
        raise PackError("UNTRUSTED_SIGNER", "no trusted pack signers configured; refusing to load any pack")
    pack_dir = Path(pack_dir)
    signature_path = pack_dir / SIGNATURE_FILE
    if not signature_path.is_file() or signature_path.is_symlink():
        raise PackError("UNSIGNED", f"{SIGNATURE_FILE} is missing")
    try:
        document = json.loads(signature_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackError("MALFORMED", f"{SIGNATURE_FILE} is not valid JSON") from exc
    if not isinstance(document, dict) or document.get("signature_version") != SIGNATURE_DOC_VERSION:
        raise PackError("MALFORMED", f"unsupported {SIGNATURE_FILE}")
    signed_manifest = document.get("signed_manifest")
    signer_key = document.get("signer_key")
    signature_hex = document.get("signature")
    if not isinstance(signed_manifest, dict) or not isinstance(signer_key, str) or not isinstance(signature_hex, str):
        raise PackError("MALFORMED", f"{SIGNATURE_FILE} is incomplete")

    # Authenticity first: nothing in an unsigned or foreign-signed manifest is trusted.
    if not signer_matches(signer_key, trusted_signers):
        raise PackError("UNTRUSTED_SIGNER", "the pack is signed by a key that is not trusted")
    if not verify_multibase_signature(signer_key, _PACK_DOMAIN + canonical_bytes(signed_manifest), signature_hex):
        raise PackError("BAD_SIGNATURE", "the pack signature does not verify")

    # Integrity: what is on disk now must be exactly what was signed, file for file.
    compiled = _compile_from_files(_read_files(pack_dir))
    if canonical_bytes(compiled.manifest) != canonical_bytes(signed_manifest):
        raise PackError("TAMPERED", "the pack contents differ from what was signed")
    if document.get("pack_hash") != compiled.pack_hash:
        raise PackError("TAMPERED", "the recorded pack hash does not match the pack")

    # Compatibility and freshness.
    if compiled.manifest["pack_format"] not in SUPPORTED_PACK_FORMATS:
        raise PackError("INCOMPATIBLE", f"unsupported pack_format {compiled.manifest['pack_format']!r}")
    if compiled.manifest["decision_contract"] not in SUPPORTED_DECISION_CONTRACTS:
        raise PackError("INCOMPATIBLE", f"unsupported decision_contract {compiled.manifest['decision_contract']!r}")
    if "not_after" in compiled.manifest:
        current = now or _dt.datetime.now(_dt.timezone.utc)
        if current > _parse_timestamp(compiled.manifest["not_after"]):
            raise PackError("STALE", f"the pack expired at {compiled.manifest['not_after']}")
    if expected_pack_hash is not None and compiled.pack_hash != expected_pack_hash:
        raise PackError("UNEXPECTED_PACK", f"expected {expected_pack_hash}, found {compiled.pack_hash}")

    return LoadedPack(
        manifest=compiled.manifest, files=compiled.files, pack_hash=compiled.pack_hash, signer_key=signer_key
    )


def event_defaults_of(pack: Optional[LoadedPack]) -> Optional[Mapping[str, str]]:
    """Convenience for `decision.resolve`: None when no verified pack is loaded."""
    return None if pack is None else pack.event_defaults
