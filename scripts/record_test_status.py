#!/usr/bin/env python3
"""Record test outcomes bound to the exact tracked tree each suite exercised.

Usage:
    record_test_status.py --run-id ID --begin <suite> [<suite> ...]
    record_test_status.py --run-id ID <suite> <pass|fail> [detail]
    record_test_status.py --run-id ID --finalize
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from pathlib import Path

from test_status_schema import ROOT_SUITE_PROFILE, ROOT_SUITES

REPO = Path(__file__).resolve().parent.parent
STATUS = REPO / ".integrity-test-status"
SCHEMA_VERSION = 2
VALID_OUTCOMES = {"pass", "fail"}


class StatusError(ValueError):
    """The local test-status document cannot support an honest attestation."""


def _tree_hash() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tree_hash import tree_hash

    return tree_hash(REPO)


def _known_tree_hash() -> str:
    value = _tree_hash()
    if value == "unknown":
        raise StatusError("tracked tree hash is unknown; refusing to record test evidence")
    return value


def _write(doc: dict) -> None:
    tmp = STATUS.with_name(f"{STATUS.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, STATUS)


def _load_v2(run_id: str) -> dict:
    if not STATUS.exists():
        raise StatusError("no active test run; start one with --begin")
    try:
        doc = json.loads(STATUS.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise StatusError(f"malformed test status: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        raise StatusError("legacy or unsupported test status; start a new run with --begin")
    if doc.get("run_id") != run_id:
        raise StatusError("test run id does not match the active run; refusing cross-run mixing")
    expected = doc.get("expected_suites")
    suites = doc.get("suites")
    if (
        not isinstance(expected, list)
        or not expected
        or not all(isinstance(name, str) and name for name in expected)
        or len(expected) != len(set(expected))
        or not isinstance(suites, dict)
    ):
        raise StatusError("invalid expected_suites or suites in test status")
    return doc


def _begin(expected: list[str], run_id: str) -> int:
    if not expected or len(expected) != len(set(expected)) or any(not name for name in expected):
        raise StatusError("--begin requires a nonempty, unique suite list")
    _known_tree_hash()
    _write(
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "suite_profile": (
                ROOT_SUITE_PROFILE if tuple(expected) == ROOT_SUITES else "custom"
            ),
            "expected_suites": expected,
            "suites": {},
            "started_at": int(time.time()),
            "finalized": False,
        }
    )
    print(f"[test-status] began v{SCHEMA_VERSION} run for {len(expected)} suites")
    return 0


def _record(suite: str, outcome: str, detail: str, run_id: str) -> int:
    if outcome not in VALID_OUTCOMES:
        raise StatusError(f"invalid outcome {outcome!r}; expected pass or fail")
    doc = _load_v2(run_id)
    if suite not in doc["expected_suites"]:
        raise StatusError(f"unexpected suite {suite!r}; expected {doc['expected_suites']}")
    doc["suites"][suite] = {
        "outcome": outcome,
        "detail": detail,
        "at": int(time.time()),
        "tree_hash": _known_tree_hash(),
    }
    doc["finalized"] = False
    for key in ("tree_hash", "finished_at", "overall"):
        doc.pop(key, None)
    _write(doc)
    return 0


def _finalize(run_id: str) -> int:
    doc = _load_v2(run_id)
    current = _known_tree_hash()
    expected = set(doc["expected_suites"])
    observed = set(doc["suites"])
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing or unexpected:
        raise StatusError(f"suite set incomplete (missing={missing}, unexpected={unexpected})")

    stale = []
    for name in doc["expected_suites"]:
        entry = doc["suites"].get(name)
        if not isinstance(entry, dict) or entry.get("outcome") not in VALID_OUTCOMES:
            raise StatusError(f"suite {name!r} has an invalid result")
        if entry.get("tree_hash") != current:
            stale.append(name)
    if stale:
        raise StatusError(
            f"suite results are not for the current tracked tree: {', '.join(stale)}; rerun all suites"
        )

    outcomes = [doc["suites"][name]["outcome"] for name in doc["expected_suites"]]
    doc.update(
        tree_hash=current,
        finished_at=int(time.time()),
        overall="pass" if all(value == "pass" for value in outcomes) else "fail",
        finalized=True,
    )
    _write(doc)
    print(f"[test-status] {doc['overall']} across {len(outcomes)} suites → {STATUS.name}")
    return 0 if doc["overall"] == "pass" else 1


def _main_locked(args: list[str], run_id: str) -> int:
    if args and args[0] == "--begin":
        return _begin(args[1:], run_id)
    if args == ["--finalize"]:
        return _finalize(run_id)
    if len(args) < 2 or len(args) > 3:
        print(__doc__, file=sys.stderr)
        return 2
    return _record(args[0], args[1], args[2] if len(args) == 3 else "", run_id)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) < 2 or args[0] != "--run-id" or not args[1]:
            raise StatusError("every operation requires --run-id <nonempty-id>")
        run_id, args = args[1], args[2:]
        lock_path = STATUS.with_name(f"{STATUS.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return _main_locked(args, run_id)
    except StatusError as exc:
        print(f"[test-status] error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
