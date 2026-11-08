"""Building and auditing a pack's `policy.wasm`, and the OPA-version pin that makes it reproducible.

Deliberately does NOT import wasmtime: `build_pack_wasm`/`verify_pack_wasm` only shell out to `opa`,
so they must work in an environment with the pinned OPA binary but without the `[wasm]` extra -- which
is exactly CI's integrity-sdk job, and the operator signing a pack. The hermetic tests (a fake `opa`)
run everywhere; the round-trip tests skip unless the pinned OPA is installed.
"""

from __future__ import annotations

import hashlib
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from integrity_sdk.core import packs
from integrity_sdk.core.wasm_build import (
    PINNED_OPA_VERSION,
    WasmBuildError,
    build_pack_wasm,
    verify_pack_wasm,
)
from integrity_sdk.did import Keypair, public_key_multibase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BCC_PACK = _REPO_ROOT / "packs" / "bcc"


def _opa_is_pinned() -> bool:
    opa = shutil.which("opa")
    if not opa:
        return False
    out = subprocess.run([opa, "version"], capture_output=True, text=True)
    return any(line.strip() == f"Version: {PINNED_OPA_VERSION}" for line in out.stdout.splitlines())


_needs_pinned_opa = pytest.mark.skipif(
    not _opa_is_pinned(), reason=f"the pinned opa {PINNED_OPA_VERSION} is not installed (scripts/install_toolchain.sh)"
)


def _fake_opa(tmp_path: Path, reported_version: str) -> str:
    """A stand-in `opa` whose `version` prints `reported_version`; nothing else is called before the pin check."""
    script = tmp_path / "opa"
    script.write_text(f'#!/bin/sh\nif [ "$1" = "version" ]; then echo "Version: {reported_version}"; exit 0; fi\nexit 1\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(script)


def _minimal_pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "pack.yaml").write_text("entrypoint: data.integrity.pack.decision\n")
    (pack / "policy.rego").write_text("package integrity.pack\n")
    return pack


# --- the OPA-version pin (hermetic: a fake opa, no real compiler) ---------------------------------

def test_pinned_version_matches_toolchain_script():
    """The Python constant cannot silently drift from the version install_toolchain.sh installs."""
    text = (_REPO_ROOT / "scripts" / "install_toolchain.sh").read_text()
    pinned = next(
        line.split("=", 1)[1].split("#", 1)[0].strip().strip('"')
        for line in text.splitlines()
        if line.strip().startswith("OPA_VERSION=")
    )
    assert pinned == PINNED_OPA_VERSION


def test_build_refuses_a_different_opa_version(tmp_path):
    pack = _minimal_pack(tmp_path)
    with pytest.raises(WasmBuildError) as exc:
        build_pack_wasm(pack, opa_bin=_fake_opa(tmp_path, "1.17.0"))
    assert "1.17.0" in str(exc.value) and PINNED_OPA_VERSION in str(exc.value)
    # the refusal happens before any compile, and writes no artifact
    assert not (pack / packs.WASM_FILE).exists()


def test_version_match_is_exact_not_prefix(tmp_path):
    # '1.18.20' starts with the pinned '1.18.2' but is a different release; the refusal must be the
    # version refusal (naming the reported version), not the later "opa build failed" from the fake.
    pack = _minimal_pack(tmp_path)
    reported = f"{PINNED_OPA_VERSION}0"
    with pytest.raises(WasmBuildError) as exc:
        build_pack_wasm(pack, opa_bin=_fake_opa(tmp_path, reported))
    assert reported in str(exc.value) and PINNED_OPA_VERSION in str(exc.value)


def test_version_check_opts_out_with_none(tmp_path):
    # With the check disabled the wrong-version opa is accepted, so we get past the pin and
    # fail later at the (fake) compiler instead -- proving the pin was the only thing stopping it.
    pack = _minimal_pack(tmp_path)
    with pytest.raises(WasmBuildError) as exc:
        build_pack_wasm(pack, opa_bin=_fake_opa(tmp_path, "1.17.0"), expected_opa_version=None)
    assert "opa build failed" in str(exc.value)


def test_missing_opa_binary_is_reported(tmp_path):
    pack = _minimal_pack(tmp_path)
    with pytest.raises(WasmBuildError, match="opa binary is required"):
        build_pack_wasm(pack, opa_bin=str(tmp_path / "does-not-exist"))


def test_build_refuses_an_already_signed_pack(tmp_path):
    pack = _minimal_pack(tmp_path)
    (pack / packs.SIGNATURE_FILE).write_text("{}")
    with pytest.raises(WasmBuildError, match="BEFORE signing"):
        build_pack_wasm(pack)  # refused before any opa call
    assert not (pack / packs.WASM_FILE).exists()


# --- real compile round-trip (needs the pinned opa; no wasmtime) ----------------------------------

def _copy_bcc_pack(tmp_path: Path) -> Path:
    dest = tmp_path / "bcc"
    shutil.copytree(_BCC_PACK, dest)
    # never carry a signature into the copy
    (dest / packs.SIGNATURE_FILE).unlink(missing_ok=True)
    return dest


@_needs_pinned_opa
def test_build_then_sign_then_verify_roundtrip(tmp_path):
    pack_dir = _copy_bcc_pack(tmp_path)
    out = build_pack_wasm(pack_dir)
    assert out == pack_dir / packs.WASM_FILE
    assert out.read_bytes().startswith(b"\x00asm")

    signer = Keypair.generate()
    packs.sign_pack(pack_dir, signer)  # signs policy.wasm too -- it is a pack file now
    loaded = packs.load_pack(pack_dir, trusted_signers=[public_key_multibase(signer.public_bytes())])
    assert packs.WASM_FILE in loaded.files
    assert verify_pack_wasm(loaded) is True


# The sha256 of `packs/bcc` compiled by the pinned OPA. Recompute ONLY when packs/bcc/policy.rego
# changes (print build_pack_wasm(...)'s output file's sha256). Precedent: GOLDEN_PACK_HASH. This is the
# cross-OPA-build reproducibility check the version pin assumes: CI runs the official 1.18.2 static
# binary, so if a different 1.18.2 build (e.g. a distro/-dirty one) emits different bytes, THIS test
# goes red -- which means the version-string pin is insufficient and must pin the binary's hash. Do not
# "fix" a red here by updating the constant; investigate first.
_GOLDEN_BCC_WASM_SHA256 = "d1460da6e46c434ea2a2bec14817c5c5d4da86f6e60f736e7fc547e5a5bec81e"


@_needs_pinned_opa
def test_bcc_pack_wasm_is_byte_reproducible(tmp_path):
    pack_dir = _copy_bcc_pack(tmp_path)
    out = build_pack_wasm(pack_dir)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == _GOLDEN_BCC_WASM_SHA256


@_needs_pinned_opa
def test_verify_catches_wasm_that_is_not_the_compile_of_the_rego(tmp_path):
    # Build a valid, signed, loadable pack, then replace its wasm with a *different* pack's wasm and
    # re-sign so load_pack still passes. verify_pack_wasm is the only check that catches the swap.
    good = _copy_bcc_pack(tmp_path)
    build_pack_wasm(good)

    other = tmp_path / "other"
    other.mkdir()
    (other / "pack.yaml").write_text("entrypoint: data.integrity.pack.decision\n")
    (other / "policy.rego").write_text(
        "package integrity.pack\n\ndecision := {\"effect\": \"deny\"}\n"
    )
    other_wasm = build_pack_wasm(other)

    (good / packs.WASM_FILE).write_bytes(other_wasm.read_bytes())  # the swap
    signer = Keypair.generate()
    packs.sign_pack(good, signer)  # hashes now match the swapped bytes -> load_pack is happy
    loaded = packs.load_pack(good, trusted_signers=[public_key_multibase(signer.public_bytes())])
    assert verify_pack_wasm(loaded) is False
