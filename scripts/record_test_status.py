#!/usr/bin/env python3
"""
Record the outcome of a test run so the next commit's Trust Vault leaf can attest to it.

Without this, every anchored leaf commits to `test_result_hash = "unverified"` — an honest
statement, but it means the anchored history records only that work *happened*, never that it
was *sound*. That is the difference between a log and evidence.

Writes `.integrity-test-status` at the repo root (gitignored — it describes a local run, not a
property of the tree). `scripts/vault_commit_leaf.py` hashes the file's bytes into the leaf, so
two different passing runs produce different leaves and the commitment is specific rather than
a bare boolean.

**The tree hash is what makes it non-transferable.** The status records the exact tree the
suites ran against, so a stale status file from an earlier tree cannot silently vouch for new
code — the leaf writer treats a tree mismatch as `unverified`, which is the whole point.

Usage:
    record_test_status.py <suite> <outcome> [detail]
    record_test_status.py --finalize
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import pathlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATUS = REPO / ".integrity-test-status"


def _tree_hash() -> str:
    """Fingerprint of the code that would actually run: HEAD, tracked modifications, AND
    untracked files.

    The untracked part is not incidental. A first version of this hashed only
    `HEAD + git diff HEAD`, which omits untracked files entirely — so adding a brand-new
    source file left the fingerprint unchanged and a stale test status kept validating. Caught
    by testing the stale path rather than assuming it worked: editing an untracked script
    produced no change at all.
    """
    import hashlib
    import subprocess

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(REPO), *args], text=True)

    try:
        parts = [git("rev-parse", "HEAD").strip(), git("diff", "HEAD")]
        for rel in git("ls-files", "--others", "--exclude-standard").split("\n"):
            rel = rel.strip()
            if not rel:
                continue
            p = REPO / rel
            try:
                parts.append(rel + ":" + hashlib.sha256(p.read_bytes()).hexdigest())
            except OSError:
                parts.append(rel + ":unreadable")
    except Exception:
        return "unknown"

    from eth_utils import keccak

    return "0x" + keccak(text="\n".join(parts)).hex()


def _load() -> dict:
    if STATUS.exists():
        try:
            return json.loads(STATUS.read_text())
        except Exception:
            pass
    return {"suites": {}, "tree_hash": _tree_hash(), "started_at": int(time.time())}


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--finalize":
        doc = _load()
        # Re-stamp the tree hash at finalize time: if the tree changed mid-run, the recorded
        # hash must reflect what actually ran last rather than what it looked like at the start.
        doc["tree_hash"] = _tree_hash()
        doc["finished_at"] = int(time.time())
        outcomes = [s["outcome"] for s in doc["suites"].values()]
        doc["overall"] = "pass" if outcomes and all(o == "pass" for o in outcomes) else "fail"
        STATUS.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        print(f"[test-status] {doc['overall']} across {len(outcomes)} suites → {STATUS.name}")
        return 0

    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    suite, outcome = sys.argv[1], sys.argv[2]
    detail = sys.argv[3] if len(sys.argv) > 3 else ""
    doc = _load()
    doc["suites"][suite] = {"outcome": outcome, "detail": detail, "at": int(time.time())}
    STATUS.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
