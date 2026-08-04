#!/usr/bin/env python3
"""
The content-hash fix `check_deploy_freshness.py` names as the real answer (PRODUCTION_GAPS.md
§22): a deterministic fingerprint of a service's tracked source, computed from git tree/blob
SHAs rather than filesystem mtimes.

`check_deploy_freshness.py`'s mtime comparison is an approximation that goes STALE on every
fresh clone or branch switch (mtimes reset to "now"). A content hash has no such failure mode
— `git rev-parse HEAD:<path>` is itself a content-addressed tree/blob SHA, so two checkouts of
the same commit always agree regardless of when the files were touched on disk.

Usage:
    service_content_hash.py <service>          # print the hash for one service (Makefile SERVICES)
    service_content_hash.py --all              # print `SERVICE=hash` for every service

Baked into each image at build time as the `source.hash` LABEL (see each service's
Dockerfile's `ARG SOURCE_HASH` + `LABEL source.hash=$SOURCE_HASH`, and docker-compose.yml's
`build.args`). `check_deploy_freshness.py` recomputes this same hash for the current tree and
compares it against the running image's label — an exact match/mismatch, not a timing proxy.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Single source of truth for which paths belong to which service — shared with
# check_deploy_freshness.py so the two can't silently name different path sets for the
# same service.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_deploy_freshness import SERVICES  # noqa: E402


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def content_hash_for(paths: list[str]) -> str:
    """`0x`-prefixed keccak256 over the committed tree/blob SHAs of `paths` (sorted, so
    argument order never changes the result). `"unknown"` if git state can't be read —
    matching `tree_hash.py`'s own honesty convention: a hash that can't be computed must
    not be silently reported as a real one."""
    from eth_utils import keccak

    shas = []
    for path in sorted(paths):
        sha = _git("rev-parse", f"HEAD:{path}")
        if sha is None:
            return "unknown"
        shas.append(f"{path}:{sha}")

    return "0x" + keccak(text="\n".join(shas)).hex()


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--all":
        for service, paths in SERVICES.items():
            print(f"{service}={content_hash_for(paths)}")
        return 0

    if len(sys.argv) != 2 or sys.argv[1] not in SERVICES:
        print(__doc__, file=sys.stderr)
        print(f"\nKnown services: {', '.join(SERVICES)}", file=sys.stderr)
        return 2

    print(content_hash_for(SERVICES[sys.argv[1]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
