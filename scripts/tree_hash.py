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

An earlier version hashed `rev-parse HEAD + diff HEAD + untracked-file contents`. That
formula is unusable across the exact boundary it exists to bridge: `git commit` advances
`HEAD` to a new SHA and collapses `git diff HEAD` to empty, so the string being hashed
changes shape (old SHA + full diff text) → (new SHA + empty string) even when zero file
bytes changed. Measured directly against this repo: **every one of 48 anchored leaves**
landed `unverified` or `unverified:stale`, because the pre-commit stamp and the
post-commit check could never structurally agree — not a discipline gap, a formula bug.

Fixed by hashing the actual bytes of every tracked file (`git ls-files`) rather than a
commit-relative diff. `git commit` never rewrites working-tree files — it snapshots the
index into a new commit object — so this hash is identical immediately before and
immediately after the commit that follows a `record_test_status.py` run, as long as no
file is edited or (re)staged in between. Untracked files are deliberately excluded now:
a file `git commit` will not include isn't part of the tree being attested to, and their
churn (build artifacts, reports) was adding noise unrelated to what was actually tested.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path


def tree_hash(repo: Path) -> str:
    """`0x`-prefixed keccak256 fingerprint of `repo`'s tracked file contents, or
    `"unknown"` if git state can't be read (never raises). Invariant across a `git commit`
    that snapshots exactly this content — see module docstring."""
    from eth_utils import keccak

    try:
        files = subprocess.check_output(["git", "-C", str(repo), "ls-files"], text=True)
    except Exception:  # noqa: BLE001
        return "unknown"

    parts = []
    for rel in sorted(f for f in files.split("\n") if f.strip()):
        p = repo / rel
        try:
            parts.append(rel + ":" + hashlib.sha256(p.read_bytes()).hexdigest())
        except OSError:
            parts.append(rel + ":unreadable")

    return "0x" + keccak(text="\n".join(parts)).hex()


def _self_test() -> int:
    """Pin the property this whole module exists for: the hash must be identical
    immediately before and immediately after the `git commit` that snapshots the same
    content, and must change when tracked content actually changes. This is what the
    original HEAD+diff formula silently failed at 48/48 times in production."""
    failures = 0

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)

        (repo / "a.txt").write_text("hello\n")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
        pre_commit = tree_hash(repo)
        subprocess.run(["git", "commit", "-q", "-m", "1"], cwd=repo, check=True)
        post_commit = tree_hash(repo)
        ok = pre_commit == post_commit and pre_commit != "unknown"
        print(f"  {'ok  ' if ok else 'FAIL'} stable across commit boundary "
              f"({pre_commit[:12]}… == {post_commit[:12]}…)" if ok else
              f"  FAIL stable across commit boundary: {pre_commit} != {post_commit}")
        failures += 0 if ok else 1

        (repo / "b.txt").write_text("untracked, should not affect the hash\n")
        untracked_hash = tree_hash(repo)
        ok = untracked_hash == post_commit
        print(f"  {'ok  ' if ok else 'FAIL'} untracked file does not change the hash")
        failures += 0 if ok else 1

        (repo / "a.txt").write_text("hello, changed\n")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
        changed_hash = tree_hash(repo)
        ok = changed_hash != post_commit
        print(f"  {'ok  ' if ok else 'FAIL'} staged content change changes the hash")
        failures += 0 if ok else 1

        subprocess.run(["git", "commit", "-q", "-m", "2"], cwd=repo, check=True)
        post_second_commit = tree_hash(repo)
        ok = post_second_commit == changed_hash
        print(f"  {'ok  ' if ok else 'FAIL'} stable across a second commit boundary")
        failures += 0 if ok else 1

    total = 4
    print(f"\n  {total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print(tree_hash(Path(subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True
    ).strip())))
