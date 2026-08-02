#!/usr/bin/env python3
"""
The single, canonical "fingerprint of the working tree" used by the test-status/vault-leaf
pair (F5): `record_test_status.py` stamps this hash onto `.integrity-test-status` when a
test run finishes; `vault_commit_leaf.py` recomputes it at commit time and compares. A
match means "the recorded test outcome is for this exact tree"; a mismatch means
`unverified:stale`.

Extracted here because the two callers used to carry independent, hand-copied
implementations of the same algorithm — each file said, in a comment, that it "must match
the other exactly" without anything enforcing that. They happened to agree, but nothing
stopped them drifting the next time either one was edited, which is exactly the kind of gap
that turns "tests passed" into a claim nobody can actually trust. One function, two
importers, is the fix that makes drift structurally impossible instead of hoping the
comments get read.

Covers HEAD, tracked modifications, AND untracked files — the untracked half is not
incidental. An earlier version hashed only `HEAD + git diff HEAD`, which left the
fingerprint unchanged when a brand-new source file was added, so a stale status kept
validating against tree states it never actually described.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def tree_hash(repo: Path) -> str:
    """`0x`-prefixed keccak256 fingerprint of `repo`'s current working tree, or
    `"unknown"` if git state can't be read (never raises)."""
    from eth_utils import keccak

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True)

    try:
        parts = [git("rev-parse", "HEAD").strip(), git("diff", "HEAD")]
        for rel in git("ls-files", "--others", "--exclude-standard").split("\n"):
            rel = rel.strip()
            if not rel:
                continue
            p = repo / rel
            try:
                parts.append(rel + ":" + hashlib.sha256(p.read_bytes()).hexdigest())
            except OSError:
                parts.append(rel + ":unreadable")
    except Exception:  # noqa: BLE001
        return "unknown"

    return "0x" + keccak(text="\n".join(parts)).hex()
