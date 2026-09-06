"""Smoke-test a clean integrity-sdk wheel installation.

This script is intentionally outside pytest collection. Continuous Integration builds the
wheel, installs it into an isolated virtual environment, changes to a directory outside the
checkout, and invokes this script with the genuine Nitro attestation fixture. That boundary
prevents the source tree from masking omitted package data.
"""

from __future__ import annotations

import argparse
from importlib import metadata
from pathlib import Path

import integrity_sdk
from integrity_sdk.security.attestation import verify_nitro_attestation


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--expected-install-prefix", required=True, type=Path)
    args = parser.parse_args()

    package_path = Path(integrity_sdk.__file__).resolve()
    install_prefix = args.expected_install_prefix.resolve()
    _require(
        package_path.is_relative_to(install_prefix),
        f"integrity_sdk imported from {package_path}, outside isolated install {install_prefix}",
    )
    _require(bool(metadata.version("integrity-sdk")), "installed distribution has no version")
    result = verify_nitro_attestation(
        args.fixture.read_bytes(),
        enforce_validity_period=False,
    )
    _require(result.signature_valid is True, f"signature invalid: {result.errors}")
    _require(result.chain_valid is True, f"certificate chain invalid: {result.errors}")
    _require(result.root_pinned is True, f"trust root not pinned: {result.errors}")
    _require(result.valid is True, f"attestation invalid: {result.errors}")


if __name__ == "__main__":
    main()
