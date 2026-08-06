#!/usr/bin/env python3
"""
Propagates deploy-derived addresses from the repo-root deployments.<network>.json
into integrity-mvp's curated mirror (integrity-mvp/src/deployments.baseSepolia.json),
without clobbering the fields that mirror deliberately does NOT take from the root
file (rpcUrl, explorerUrl, domains, and the `_source` header comment).

Why this exists
----------------
`scripts/sync_abis.py`'s own docstring already flags the failure mode this avoids: a
prior sync target did a raw copy of the full deployments.*.json over a frontend's
curated mirror, silently dropping that curation, and was deleted rather than fixed.
That docstring explicitly says a real sync step should be "re-added deliberately, if
one is wanted" -- this is that, built narrow on purpose: it only ever writes the keys
`chainId`, `singletons` (the whole object -- extra keys are harmless, and this means a
newly-deployed singleton like EHRGate starts flowing through automatically the next
time this runs, no script edit required), and the two `protocolAddresses` keys mvp's
constants.ts actually reads (`oracleSigner`, `arbitrator`). Everything else in the
mirror file is left exactly as a human wrote it.

integrity-mvp is deliberately a SEPARATE repo from this one (public/investor-facing
demo vs. the core protocol repo), not a package inside this monorepo, so this script
assumes a sibling checkout (../integrity-mvp next to this repo) by default -- pass
--mvp-path to point elsewhere.

Usage:
    python scripts/sync_mvp_deployments.py                # sync, print a diff, exit 0
    python scripts/sync_mvp_deployments.py --check         # exit 1 if out of sync, don't write
    python scripts/sync_mvp_deployments.py --mvp-path ~/elsewhere/integrity-mvp
    python scripts/sync_mvp_deployments.py --network local # sync deployments.local.json instead

Exit codes: 0 = synced (or --check found nothing stale), 1 = --check found drift,
2 = couldn't find the root or mvp deployments file.
"""

import argparse
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Keys this script owns in the mirror file. Anything not listed here is treated as
# mvp-curated and never touched, no matter what the root file contains.
SYNCED_TOP_LEVEL_KEYS = ["chainId", "singletons"]
SYNCED_PROTOCOL_ADDRESS_KEYS = ["oracleSigner", "arbitrator"]


def git_head_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def diff_dict(label: str, old: dict, new: dict) -> list[str]:
    """Per-key diff of two flat address dicts, rather than dumping both whole."""
    lines = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            lines.append(f"{label}.{key}: {old.get(key)!r} -> {new.get(key)!r}")
    return lines


def sync(root_file: Path, mvp_file: Path, check_only: bool) -> int:
    root = load_json(root_file)
    mirror = load_json(mvp_file)

    changes: list[str] = []

    for key in SYNCED_TOP_LEVEL_KEYS:
        if key not in root:
            continue
        if isinstance(root[key], dict) and isinstance(mirror.get(key), dict):
            changes.extend(diff_dict(key, mirror[key], root[key]))
        elif mirror.get(key) != root[key]:
            changes.append(f"{key}: {mirror.get(key)!r} -> {root[key]!r}")
        mirror[key] = root[key]

    root_protocol = root.get("protocolAddresses", {})
    mirror_protocol = mirror.setdefault("protocolAddresses", {})
    for key in SYNCED_PROTOCOL_ADDRESS_KEYS:
        if key not in root_protocol:
            continue
        if mirror_protocol.get(key) != root_protocol[key]:
            changes.append(f"protocolAddresses.{key}: {mirror_protocol.get(key)!r} -> {root_protocol[key]!r}")
            mirror_protocol[key] = root_protocol[key]

    if not changes:
        print(f"{mvp_file} is already in sync with {root_file}.")
        return 0

    print(f"{'Would update' if check_only else 'Updating'} {mvp_file}:")
    for c in changes:
        print(f"  {c}")

    if check_only:
        return 1

    commit = git_head_commit()
    if commit:
        mirror["_synced_from_commit"] = commit

    # Preserve key order as much as possible by writing the mutated dict back
    # wholesale; json.dumps keeps insertion order, and mutating in place (rather
    # than rebuilding the dict) means untouched keys keep their original position.
    mvp_file.write_text(json.dumps(mirror, indent=2) + "\n")
    print("Done. Review the diff and commit in integrity-mvp's own repo.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mvp-path", type=Path, default=REPO_ROOT.parent / "integrity-mvp",
                         help="Path to the integrity-mvp checkout (default: sibling of this repo)")
    parser.add_argument("--network", default="baseSepolia", choices=["baseSepolia", "local"],
                         help="Which deployments.<network>.json to sync (default: baseSepolia)")
    parser.add_argument("--check", action="store_true",
                         help="Report drift and exit 1 if any; don't write")
    args = parser.parse_args()

    root_file = REPO_ROOT / f"deployments.{args.network}.json"
    mvp_file = args.mvp_path / "src" / f"deployments.{args.network}.json"

    if not root_file.exists():
        print(f"error: {root_file} not found")
        return 2
    if not mvp_file.exists():
        print(f"error: {mvp_file} not found (wrong --mvp-path?)")
        return 2

    return sync(root_file, mvp_file, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
