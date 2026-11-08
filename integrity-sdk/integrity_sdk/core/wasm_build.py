"""Build, and audit, the `policy.wasm` that ships inside a signed pack.

`build_pack_wasm` runs OPA's own compiler (`opa build -t wasm`) over the pack's Rego and writes
`policy.wasm` next to it. Run it BEFORE `sign_pack`: the pack hash then covers the wasm like any
other file, and a gate verifies it with `load_pack` before running it.

`verify_pack_wasm` is the audit that closes the one gap signing cannot: that the shipped wasm really
is the compile of the signed Rego. OPA's wasm output is byte-reproducible for a given OPA version
(checked across runs and directories), so anyone with `opa` can rebuild from `pack.policy_modules()`
and compare. A mismatch after an OPA upgrade means "rebuild with the pinned version", not tampering by
itself, but it is never silently accepted by this function.

Failure posture: raises `WasmBuildError`; never returns a partially written file.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import yaml

from .packs import MANIFEST_FILE, LoadedPack
from .wasm_engine import WASM_FILE


class WasmBuildError(Exception):
    pass


def _opa(opa_bin: Optional[str]) -> str:
    found = opa_bin or shutil.which("opa") or str(Path.home() / ".local/bin/opa")
    if not Path(found).exists() and not shutil.which(found):
        raise WasmBuildError("the opa binary is required to build a pack's wasm (scripts/install_toolchain.sh)")
    return found


def _compile(root: Path, rego_files: list[str], entrypoint: str, opa_bin: Optional[str]) -> bytes:
    """Compile `rego_files` (paths relative to `root`) with `root` as the working directory.

    The compiler records the file paths it was given in the module, so build and verify must pass the
    same relative paths from the same layout or the bytes differ for no semantic reason.
    """
    if not rego_files:
        raise WasmBuildError("no .rego files to compile")
    path = entrypoint[len("data."):].replace(".", "/") if entrypoint.startswith("data.") else entrypoint
    with tempfile.TemporaryDirectory(prefix="pack-wasm-") as tmp:
        bundle = Path(tmp) / "bundle.tar.gz"
        proc = subprocess.run(
            [_opa(opa_bin), "build", "-t", "wasm", "-e", path, "-o", str(bundle), *rego_files],
            capture_output=True, text=True, check=False, cwd=root,
        )
        if proc.returncode != 0:
            raise WasmBuildError(f"opa build failed: {proc.stderr.strip() or proc.stdout.strip()}")
        with tarfile.open(bundle) as tar:
            member = next((m for m in tar.getmembers() if m.name.lstrip("/") == "policy.wasm"), None)
            if member is None:
                raise WasmBuildError("opa build produced no policy.wasm")
            data = tar.extractfile(member).read()  # type: ignore[union-attr]
    if not data.startswith(b"\x00asm"):
        raise WasmBuildError("opa build produced something that is not a wasm module")
    return data


def build_pack_wasm(pack_dir: str | Path, *, opa_bin: Optional[str] = None) -> Path:
    """Compile the pack's Rego to `policy.wasm` in `pack_dir`. Call before `sign_pack`."""
    pack_dir = Path(pack_dir)
    manifest = yaml.safe_load((pack_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    rego = sorted(p.relative_to(pack_dir).as_posix() for p in pack_dir.rglob("*.rego") if not p.is_symlink())
    data = _compile(pack_dir, rego, manifest["entrypoint"], opa_bin)
    target = pack_dir / WASM_FILE
    tmp = target.with_suffix(".wasm.tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def verify_pack_wasm(pack: LoadedPack, *, opa_bin: Optional[str] = None) -> bool:
    """True iff the pack's shipped wasm equals a fresh compile of its (verified) Rego."""
    shipped = pack.files.get(WASM_FILE)
    if shipped is None:
        return False
    with tempfile.TemporaryDirectory(prefix="pack-wasm-verify-") as tmp:
        files = []
        for rel, source in sorted(pack.policy_modules().items()):
            target = Path(tmp) / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
            files.append(rel)
        return _compile(Path(tmp), sorted(files), pack.entrypoint, opa_bin) == shipped
