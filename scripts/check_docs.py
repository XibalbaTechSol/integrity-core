#!/usr/bin/env python3
"""Check the repository's small set of machine-verifiable documentation contracts."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
STATUS_LIMIT = 150
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
AUTHORITY_PATH_RE = re.compile(r"^\s+path:\s+([^\s#]+)\s*$", re.MULTILINE)
INDEX_COUNT_RE = re.compile(r"Total pages:\s*(\d+)")


def markdown_files() -> list[Path]:
    import subprocess

    tracked = subprocess.check_output(
        ["git", "ls-files", "*.md"], cwd=ROOT, text=True
    ).splitlines()
    return [
        ROOT / relative
        for relative in tracked
        if not relative.startswith("docs/archive/")
        and "node_modules/" not in relative
        and (ROOT / relative).exists()
    ]


def check_status_cap(errors: list[str]) -> None:
    path = ROOT / "STATUS.md"
    if not path.exists():
        errors.append("STATUS.md is missing")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > STATUS_LIMIT:
        errors.append(f"STATUS.md has {len(lines)} lines; limit is {STATUS_LIMIT}")


def check_authority_map(errors: list[str]) -> None:
    path = ROOT / "docs/DOCUMENT_STATUS.yaml"
    text = path.read_text(encoding="utf-8")
    pointers = AUTHORITY_PATH_RE.findall(text)
    if not pointers:
        errors.append("DOCUMENT_STATUS.yaml has no authority paths")
    for pointer in pointers:
        if not (ROOT / pointer).exists():
            errors.append(f"DOCUMENT_STATUS.yaml points to missing path: {pointer}")
    if "path: docs/EXECUTION_PLAN.md" not in text or "authority: execution" not in text:
        errors.append("docs/EXECUTION_PLAN.md is not recorded as the execution authority")
    if "status: superseded" not in text or "path: docs/IMPLEMENTATION_PLAN.md" not in text:
        errors.append("historical implementation-plan status is not recorded")
    if text.count("authority: execution") != 1:
        errors.append("DOCUMENT_STATUS.yaml must have exactly one execution authority")


def check_markdown_links(errors: list[str]) -> None:
    for source in markdown_files():
        if source.name in {"WIKI_LOG.md", "WIKI_SCHEMA.md"}:
            continue
        text = source.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(text):
            target = raw_target.strip().split()[0].strip("<>")
            if not target or target.startswith(("#", "/", "http://", "https://", "mailto:", "app://")):
                continue
            if target in {"relative/path.md", "string,", "x", "y", "NaN"}:
                continue
            if source.as_posix().endswith("docs/wiki/entities/integrity-dashboard.md") and target.startswith("../../integrity-dashboard/"):
                continue
            target_path = unquote(target.split("#", 1)[0])
            resolved = (source.parent / target_path).resolve()
            if not resolved.exists():
                errors.append(f"{source.relative_to(ROOT)} links to missing path: {target}")


def check_wiki_index(errors: list[str]) -> None:
    index = ROOT / "docs/wiki/WIKI_INDEX.md"
    text = index.read_text(encoding="utf-8")
    listed = set(re.findall(r"\]\(([^)]+\.md)\)", text))
    actual = {
        path.relative_to(index.parent).as_posix()
        for path in (index.parent / "concepts").glob("*.md")
    } | {
        path.relative_to(index.parent).as_posix()
        for path in (index.parent / "entities").glob("*.md")
    } | {
        path.relative_to(index.parent).as_posix()
        for path in (index.parent / "queries").glob("*.md")
    } | {
        path.relative_to(index.parent).as_posix()
        for path in (index.parent / "architecture").glob("*.md")
    }
    if listed != actual:
        errors.append(f"WIKI_INDEX.md differs from actual article set (listed {len(listed)}, actual {len(actual)})")
    match = INDEX_COUNT_RE.search(text)
    if not match or int(match.group(1)) != len(actual):
        errors.append(f"WIKI_INDEX.md page count is not {len(actual)}")


def main() -> int:
    errors: list[str] = []
    check_status_cap(errors)
    check_authority_map(errors)
    check_markdown_links(errors)
    check_wiki_index(errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Documentation contracts pass: authority, links, wiki index, and STATUS.md cap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
