#!/usr/bin/env python3
"""
Append one Trust Vault leaf per commit — the per-commit half of the two-level memory
structure (spec v0.4 §4.1/§7; `integrity_sdk/vault.py`).

Invoked from `.git/hooks/post-commit`. Lives in `scripts/` rather than inside `.git/hooks`
so it is version-controlled and reviewable: a hook that writes cryptographic commitments
about this repository should not itself be an untracked file nobody can diff.

**Honesty rule.** `test_result_hash` records what is actually known. If no test run is
recorded for the working tree, the leaf says `unverified` rather than claiming `ok` — a leaf
asserting tests passed when nothing checked would be exactly the kind of unearned claim this
protocol exists to prevent, and it would be anchored permanently.

Never fails a commit. A telemetry/memory problem must not block the developer's actual work,
so every error path exits 0 with a message on stderr.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SDK = REPO / "integrity-sdk"
sys.path.insert(0, str(SDK))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: Written by a test run (see `make test`-adjacent tooling); absent means "not verified".
TEST_STATUS_FILE = REPO / ".integrity-test-status"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def _current_tree_hash() -> str:
    """Delegates to the shared `tree_hash.py` (F5) — imports the identical implementation
    `record_test_status.py` uses, rather than a hand-copied one, so the two can no longer
    silently drift out of agreement and turn every status stale."""
    from tree_hash import tree_hash

    return tree_hash(REPO)


def _test_result_hash() -> str:
    """What is known about tests for THIS tree, never more.

    Three outcomes, and the distinctions are the point:

      * `unverified`        — no run recorded at all
      * `unverified:stale`  — a run exists but against a different tree, so it says nothing
                              about this code. Accepting it would let a passing run vouch for
                              changes made after it, which is precisely the unearned claim this
                              refuses to anchor.
      * `0x…`               — hash of the recorded status. Specific rather than a bare boolean,
                              so two different passing runs produce different leaves.
    """
    if not TEST_STATUS_FILE.exists():
        return "unverified"

    from eth_utils import keccak

    try:
        recorded = json.loads(TEST_STATUS_FILE.read_text()).get("tree_hash")
    except Exception:  # noqa: BLE001
        return "unverified"

    if recorded != _current_tree_hash():
        return "unverified:stale"

    return "0x" + keccak(TEST_STATUS_FILE.read_bytes()).hex()


def main() -> int:
    try:
        from integrity_sdk.vault import TrustVault, VaultLeaf
    except Exception as exc:  # noqa: BLE001
        print(f"[vault] integrity-sdk unavailable, leaf not recorded: {exc!r}", file=sys.stderr)
        return 0

    try:
        commit_sha = _git("rev-parse", "HEAD")
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    except Exception as exc:  # noqa: BLE001
        print(f"[vault] could not read git state: {exc!r}", file=sys.stderr)
        return 0

    # An explicit task id wins; otherwise the branch is the unit of work, which is the
    # closest honest approximation this repo already maintains.
    task_id = os.environ.get("INTEGRITY_TASK_ID") or branch
    agent_id = os.environ.get(
        "INTEGRITY_AGENT_DID",
        "did:integrity:68fed1331613937555a59398223e8e87520a87dd0305aac4fd7ecdc32a14a861",
    )

    try:
        leaf = VaultLeaf.for_commit(task_id, commit_sha, _test_result_hash())
        vault = TrustVault(agent_id)
        vault.append(leaf)
        pending = len(vault.pending_leaves())
        print(f"[vault] leaf {leaf.leaf_hash[:18]}… for {commit_sha[:8]} ({pending} pending anchor)")
    except Exception as exc:  # noqa: BLE001
        print(f"[vault] leaf not recorded: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
