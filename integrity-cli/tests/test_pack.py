"""`integrity pack build-wasm / verify-wasm` -- surface and the error paths that need no opa.

The integrity-cli CI job installs no opa, so these cover the guards that fire before any compile
(signed-pack refusal, missing opa, wrong opa version, an unloadable pack). The real build/verify
round-trip is covered in integrity-sdk's test_core_wasm_build.py, whose CI job has the pinned opa.
"""
from __future__ import annotations

import stat
from pathlib import Path

from typer.testing import CliRunner

from integrity_cli.main import app
from integrity_sdk.core.wasm_build import PINNED_OPA_VERSION

runner = CliRunner()


def _pack(tmp_path: Path, *, signed: bool) -> Path:
    d = tmp_path / "pack"
    d.mkdir()
    (d / "pack.yaml").write_text("entrypoint: data.integrity.pack.decision\n")
    (d / "policy.rego").write_text("package integrity.pack\n")
    if signed:
        (d / "pack.sig.json").write_text("{}")
    return d


def _fake_opa(tmp_path: Path, version: str) -> str:
    s = tmp_path / "opa"
    s.write_text(f'#!/bin/sh\nif [ "$1" = "version" ]; then echo "Version: {version}"; exit 0; fi\nexit 1\n')
    s.chmod(s.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(s)


def test_pack_help_lists_both_commands():
    res = runner.invoke(app, ["pack", "--help"])
    assert res.exit_code == 0
    assert "build-wasm" in res.output and "verify-wasm" in res.output


def test_build_wasm_refuses_a_signed_pack(tmp_path):
    res = runner.invoke(app, ["pack", "build-wasm", "--pack-dir", str(_pack(tmp_path, signed=True))])
    assert res.exit_code == 1
    assert "BEFORE signing" in res.output


def test_build_wasm_reports_a_missing_opa(tmp_path):
    res = runner.invoke(
        app, ["pack", "build-wasm", "--pack-dir", str(_pack(tmp_path, signed=False)),
              "--opa-bin", str(tmp_path / "no-such-opa")]
    )
    assert res.exit_code == 1
    assert "opa binary is required" in res.output


def test_build_wasm_refuses_a_non_pinned_opa(tmp_path):
    res = runner.invoke(
        app, ["pack", "build-wasm", "--pack-dir", str(_pack(tmp_path, signed=False)),
              "--opa-bin", _fake_opa(tmp_path, "1.17.0")]
    )
    assert res.exit_code == 1
    assert "1.17.0" in res.output and PINNED_OPA_VERSION in res.output


def test_build_wasm_allow_opa_version_overrides_the_pin(tmp_path):
    # With the override the wrong-version opa passes the pin, so we fail later at the fake compiler
    # instead of at the version gate -- proving --allow-opa-version actually loosens the check.
    res = runner.invoke(
        app, ["pack", "build-wasm", "--pack-dir", str(_pack(tmp_path, signed=False)),
              "--opa-bin", _fake_opa(tmp_path, "1.17.0"), "--allow-opa-version", "1.17.0"]
    )
    assert res.exit_code == 1
    assert "opa build failed" in res.output


def test_verify_wasm_rejects_an_unsigned_pack(tmp_path):
    res = runner.invoke(
        app, ["pack", "verify-wasm", "--pack-dir", str(_pack(tmp_path, signed=False)),
              "--trusted-signer", "z6MkdummySigner"]
    )
    assert res.exit_code == 1
    assert "did not load" in res.output


def test_verify_wasm_requires_a_trusted_signer(tmp_path):
    res = runner.invoke(app, ["pack", "verify-wasm", "--pack-dir", str(_pack(tmp_path, signed=False))])
    assert res.exit_code == 2  # typer usage error: --trusted-signer is required
