"""`integrity pack ...` -- build and audit the `policy.wasm` a daemonless gate runs.

The signing runbook (`docs/runbooks/bcc-policy-pack.md` in integrity-core) sequences these:

    integrity pack build-wasm  --pack-dir /secure/workdir/bcc-pack   # 1. compile, BEFORE signing
    shield  sign-pack          --pack-dir /secure/workdir/bcc-pack   # 2. sign (hashes policy.wasm too)
    integrity pack verify-wasm --pack-dir /secure/workdir/bcc-pack --trusted-signer z6Mk...  # 3. audit

`build-wasm` and `verify-wasm` only shell out to `opa`; they do not need the `[wasm]` runtime extra.
Both refuse an OPA whose version is not the pinned one (wasm is reproducible only per OPA build).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

pack_app = typer.Typer(help="Build and audit a policy pack's compiled policy.wasm")


@pack_app.command("build-wasm")
def build_wasm(
    pack_dir: Path = typer.Option(..., "--pack-dir", exists=True, file_okay=False, help="Unsigned pack directory (a COPY, not the repo)"),
    opa_bin: Optional[str] = typer.Option(None, "--opa-bin", help="opa binary to use (default: PATH, then ~/.local/bin/opa)"),
    allow_opa_version: Optional[str] = typer.Option(None, "--allow-opa-version", help="Build with this OPA version instead of the pinned one (you own the reproducibility risk)"),
) -> None:
    """Compile the pack's Rego to policy.wasm IN the pack dir. Run before `shield sign-pack`.

    Refuses a pack that is already signed (any file added after signing breaks verification) and an
    OPA whose version is not the pinned one. The written policy.wasm is then covered by the signature.
    """
    from integrity_sdk.core.wasm_build import PINNED_OPA_VERSION, WasmBuildError, build_pack_wasm

    expected = allow_opa_version if allow_opa_version is not None else PINNED_OPA_VERSION
    try:
        out = build_pack_wasm(pack_dir, opa_bin=opa_bin, expected_opa_version=expected)
    except WasmBuildError as exc:
        typer.secho(f"integrity pack build-wasm: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"OK   built {out}  (opa {expected})", fg=typer.colors.GREEN)
    typer.echo("Next: review the pack, then `shield sign-pack` -- the signature will cover policy.wasm.")


@pack_app.command("verify-wasm")
def verify_wasm(
    pack_dir: Path = typer.Option(..., "--pack-dir", exists=True, file_okay=False, help="Signed pack directory"),
    trusted_signer: list[str] = typer.Option(..., "--trusted-signer", help="Trusted z-prefixed Ed25519 pack-signing key; repeatable"),
    opa_bin: Optional[str] = typer.Option(None, "--opa-bin", help="opa binary to use (default: PATH, then ~/.local/bin/opa)"),
    allow_opa_version: Optional[str] = typer.Option(None, "--allow-opa-version", help="Verify with this OPA version instead of the pinned one"),
) -> None:
    """Audit that the signed pack's policy.wasm is the compile of its signed Rego.

    Loads and verifies the signature first (so only trusted, untampered Rego is rebuilt), then rebuilds
    the wasm and compares. Exit 0 only when the pack is signed, trusted, and its wasm matches.
    """
    from integrity_sdk.core.packs import PackError, load_pack
    from integrity_sdk.core.wasm_build import PINNED_OPA_VERSION, WasmBuildError, verify_pack_wasm

    expected = allow_opa_version if allow_opa_version is not None else PINNED_OPA_VERSION
    try:
        loaded = load_pack(pack_dir, trusted_signers=trusted_signer)
    except PackError as exc:
        typer.secho(f"integrity pack verify-wasm: pack did not load -- {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    try:
        ok = verify_pack_wasm(loaded, opa_bin=opa_bin, expected_opa_version=expected)
    except WasmBuildError as exc:
        typer.secho(f"integrity pack verify-wasm: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    if not ok:
        typer.secho(
            "FAIL the shipped policy.wasm is NOT the compile of the signed Rego "
            "(or the pack ships no policy.wasm). Rebuild with the pinned OPA, or investigate.",
            err=True, fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.secho(f"OK   policy.wasm matches the signed Rego  (opa {expected}, pack {loaded.pack_hash})", fg=typer.colors.GREEN)
