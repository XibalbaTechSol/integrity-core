#!/usr/bin/env python3
"""
Detect deployed-vs-source drift: is the running stack built from current code?

Why this exists
---------------
On 2026-07-30 the oracle's `/v1/agent/{id}/ais` endpoint returned 839.41 for a
tier-1 agent whose Verification Ladder ceiling is 600. The handler was correct;
`score_with_tier` was called; the DB held tier 1; the tests passed; the docs were
accurate. The `oracle-backend` image had simply been built at 03:18:46, and the
commit that added the ceiling landed at 03:22:18 — three and a half minutes later.

A security-relevant control that exists in source but not in the running system is
**worse** than one that was never written, because every signal you would use to
check it says it is there. Nothing in this repo could detect that, and the same
drift was simultaneously true of the dashboard image.

This script makes that condition visible. It compares each service image's build
timestamp against the last commit touching that service's source tree, and
reports anything built before its code.

Usage:
    python scripts/check_deploy_freshness.py            # report, exit 1 if stale
    python scripts/check_deploy_freshness.py --warn-only # report, always exit 0

Exit codes: 0 = all fresh (or --warn-only), 1 = at least one stale image,
2 = could not determine (docker missing, not a git repo).

Content-hash comparison (§22, fixed)
-------------------------------------
Every image now carries a `source.hash` LABEL, baked in at build time from
`scripts/service_content_hash.py` via docker-compose.yml's `build.args` (see the `up` target
in the root Makefile, which computes it fresh before every `--build`). That hash is a
content-address (`git rev-parse HEAD:<path>`, keccak256'd), so it has none of the mtime
approximation's failure modes: identical for any two checkouts of the same commit regardless
of when the files were touched on disk, and an exact match/mismatch rather than a timing proxy.

When a running image carries this label, this script trusts it exclusively and reports
`fresh`/`STALE` from an exact hash comparison. The mtime comparison below is now only a
fallback for images built before this label existed (reported as `STALE (approximate)` /
`fresh (approximate)` so the distinction stays visible) — it is not the primary signal
anymore.

Known limitation of the fallback path, stated rather than hidden
------------------------------------------------------------------
Freshness is decided by comparing the image build time against the newest **file
mtime** among that image's tracked sources. That is right for local development
and wrong in one case: a fresh `git clone` (or a branch switch) sets every file's
mtime to *now*, so a correctly-built image will report STALE until it is rebuilt.
Erring toward a false STALE on a fresh clone is also the safer direction there: the
failure mode is an unnecessary rebuild, not an undetected drift.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# service name in docker-compose.yml -> source paths BAKED INTO THE IMAGE.
#
# Precision matters more than coverage here. A checker that fires on changes which
# do not actually require a rebuild gets ignored within a week, and an ignored
# checker is how the original drift survived. So bind-mounted paths are excluded
# deliberately: `bcc_middleware/policies` is mounted read-only into the `opa`
# container (docker-compose.yml), so editing a .rego file changes behavior after an
# `opa` restart WITHOUT any image rebuild. Listing it here would produce a
# permanent false positive for every policy edit.
#
# Conversely `deployments.*.json` are bind-mounted into oracle-backend and
# bcc-middleware and are likewise excluded.
SERVICES = {
    "oracle-backend": ["integrity-oracle"],
    "bcc-middleware": ["bcc_middleware/app", "bcc_middleware/pyproject.toml",
                       "bcc_middleware/Dockerfile"],
    "userapi": ["integrity-userapi"],
    "dashboard": ["integrity-dashboard"],
}

# Paths whose changes take effect without a rebuild, listed so the reason is
# discoverable rather than implicit in an omission.
BIND_MOUNTED = {
    "bcc_middleware/policies": "mounted into the `opa` container; restart opa, no rebuild",
    "deployments.baseSepolia.json": "mounted into oracle-backend / bcc-middleware",
    "deployments.local.json": "mounted into oracle-backend / bcc-middleware",
}


def _run(args: list[str], cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


_TS_RE = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<frac>\d+))?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)


def _parse_ts(raw: str) -> datetime | None:
    """Docker emits RFC3339 with 9 fractional digits and a numeric offset
    (`2026-07-30T18:42:45.077815077-05:00`); git `%cI` emits 0 fractional digits.
    `fromisoformat` rejects >6 fractional digits on older Pythons, so the fraction
    must be trimmed — but the offset must survive that trimming.

    An earlier version sliced the tail by *counting* digit characters, which also
    counted the digits inside `-05:00` and silently discarded the offset. A local
    timestamp then read as UTC, shifting it by 5 hours and reporting a freshly
    built image as STALE. That false positive is worse than no checker: the whole
    premise here is that this tool stays trustworthy enough to act on.
    """
    raw = raw.strip()
    if not raw:
        return None
    m = _TS_RE.match(raw)
    if not m:
        return None
    base, frac, tz = m.group("base"), m.group("frac"), m.group("tz")
    if tz in (None, "Z"):
        tz = "+00:00"
    elif ":" not in tz:  # +0500 -> +05:00
        tz = f"{tz[:3]}:{tz[3:]}"
    text = base + (f".{frac[:6]}" if frac else "") + tz
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def _running_image_id(service: str) -> str | None:
    cid = _run(["docker", "compose", "ps", "-q", service], cwd=REPO)
    if not cid:
        return None
    return _run(["docker", "inspect", cid.splitlines()[0], "--format", "{{.Image}}"])


def image_built_at(service: str) -> datetime | None:
    image = _running_image_id(service)
    if not image:
        return None
    created = _run(["docker", "inspect", image, "--format", "{{.Created}}"])
    return _parse_ts(created) if created else None


def image_source_hash(service: str) -> str | None:
    """The `source.hash` LABEL baked in at build time (scripts/service_content_hash.py),
    or None if the image predates that label / isn't running."""
    image = _running_image_id(service)
    if not image:
        return None
    label = _run(["docker", "inspect", image, "--format", '{{index .Config.Labels "source.hash"}}'])
    if not label or label == "unknown" or label == "<no value>":
        return None
    return label


def source_changed_at(paths: list[str]) -> datetime | None:
    """When the image's baked-in source last actually CHANGED.

    Uses file mtime, not commit time. Commit time is the obvious proxy and it is
    wrong for the ordinary workflow: you edit, rebuild, test, *then* commit — so
    the commit timestamp lands after the image was built even though the content
    is identical, and every correct build reports STALE the moment it is
    committed. A checker that fires on the normal workflow gets ignored, and an
    ignored checker is how the drift it exists to catch survived in the first
    place.

    `git ls-files` scopes this to tracked files, which keeps build artifacts
    (`target/`, `node_modules/`, `.venv/`) from dominating the maximum.
    """
    listing = _run(["git", "ls-files", "-z", "--", *paths], cwd=REPO)
    if listing is None:
        return None

    newest = 0.0
    for rel in listing.split("\0"):
        rel = rel.strip()
        if not rel:
            continue
        try:
            newest = max(newest, (REPO / rel).stat().st_mtime)
        except OSError:
            continue  # deleted-but-tracked, or unreadable

    if newest <= 0:
        return None
    return datetime.fromtimestamp(newest, tz=timezone.utc)


def _self_test() -> int:
    """Pin the timestamp parser. This exists because a subtle bug here produced a
    confident, wrong STALE verdict on a freshly built image -- the failure mode
    that makes a checker worth ignoring. Offsets are the whole risk, so every
    shape docker or git can emit is covered."""
    cases = [
        # (input, expected UTC isoformat prefix)
        ("2026-07-30T18:42:45.077815077-05:00", "2026-07-30T23:42:45"),  # docker, local offset
        ("2026-07-30T08:18:49.128885723Z", "2026-07-30T08:18:49"),       # docker, Z
        ("2026-07-30T23:38:33+00:00", "2026-07-30T23:38:33"),            # git %cI, UTC
        ("2026-07-29T14:03:16-05:00", "2026-07-29T19:03:16"),            # git %cI, offset
        ("2026-07-30T18:42:45+0500", "2026-07-30T13:42:45"),             # compact offset
        ("2026-07-30T18:42:45", "2026-07-30T18:42:45"),                  # naive -> UTC
    ]
    failures = 0
    for raw, expected in cases:
        got = _parse_ts(raw)
        ok = got is not None and got.isoformat().startswith(expected)
        if not ok:
            failures += 1
            print(f"  FAIL {raw!r}: expected {expected}…, got {got}")
        else:
            print(f"  ok   {raw!r} -> {got.isoformat()}")
    for bad in ("", "garbage", "not-a-date", "2026-13-45T99:99:99"):
        if _parse_ts(bad) is not None:
            failures += 1
            print(f"  FAIL {bad!r}: expected None")
    print(f"\n  {len(cases) + 4 - failures}/{len(cases) + 4} passed")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--warn-only", action="store_true",
                    help="report drift but always exit 0 (for non-blocking use in `make up`)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--self-test", action="store_true",
                    help="verify the timestamp parser and exit")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    if not (REPO / ".git").exists():
        print("check-deploy: not a git repo; cannot determine source dates", file=sys.stderr)
        return 2

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from service_content_hash import content_hash_for

    rows, stale = [], []
    for service, srcs in SERVICES.items():
        built = image_built_at(service)
        image_hash = image_source_hash(service)
        current_hash = content_hash_for(srcs)

        if built is None:
            status = "not running"
        elif image_hash is not None and current_hash != "unknown":
            # Exact comparison — no timing proxy, no fresh-clone false positive.
            if image_hash == current_hash:
                status = "fresh"
            else:
                status = "STALE"
                stale.append(service)
        else:
            # Fallback: image predates the source.hash LABEL, or the hash couldn't be
            # computed. Approximate via mtime, and say so — this is not the same
            # guarantee as the hash comparison above.
            changed = source_changed_at(srcs)
            if changed is None:
                status = "unknown (no commits touch source)"
            elif built < changed:
                status = "STALE (approximate — image predates content-hash labeling)"
                stale.append(service)
            else:
                status = "fresh (approximate — image predates content-hash labeling)"

        rows.append({
            "service": service,
            "source": ", ".join(srcs),
            "image_built": built.isoformat() if built else None,
            "image_source_hash": image_hash,
            "current_source_hash": current_hash,
            "status": status,
        })

    if args.json:
        print(json.dumps({"stale": stale, "services": rows}, indent=2))
    else:
        width = max(len(r["service"]) for r in rows)
        print("Deployed-vs-source freshness:\n")
        for r in rows:
            built = r["image_built"][:19] if r["image_built"] else "—"
            img_hash = (r["image_source_hash"] or "—")[:10]
            cur_hash = (r["current_source_hash"] or "—")[:10]
            print(
                f"  {r['service']:<{width}}  image {built}  "
                f"hash {img_hash} vs {cur_hash}  {r['status']}"
            )
        if stale:
            print(f"\n  {len(stale)} STALE image(s): {', '.join(stale)}")
            print("  The running service is NOT the code in this tree. Rebuild with:")
            print(f"    docker compose up -d --build {' '.join(stale)}")
            print("  (An oracle image three minutes older than its source silently")
            print("   disabled the Verification Ladder ceiling — see PRODUCTION_GAPS.md §21.)")
        else:
            print("\n  All running images are at or ahead of their source.")

    if stale and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
