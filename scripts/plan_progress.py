#!/usr/bin/env python3
"""Print per-section progress for docs/EXECUTION_PLAN.md from its task-list checkboxes.

The plan tracks work as GitHub task-list items (`- [ ]` open, `- [x]` done,
also `1. [ ]` in ordered lists). Counting them here, instead of keeping totals
in the document, means progress can never drift from the checkboxes
themselves. Sections are the plan's `#` phases and `##` steps/gates; a
section with no checkboxes is omitted.

Usage:
    python3 scripts/plan_progress.py [path/to/EXECUTION_PLAN.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DEFAULT_PLAN = Path(__file__).resolve().parents[1] / "docs" / "EXECUTION_PLAN.md"

# A task item: optional indent, a bullet or ordered-list marker, then [ ] or [x].
TASK = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\[([ xX])\]\s")
HEADING = re.compile(r"^(#{1,2})\s+(.*)$")


def progress(text: str) -> list[tuple[int, str, int, int]]:
    """Return (heading level, heading, done, total) for each section holding tasks."""
    sections: list[list] = [[0, "(preamble)", 0, 0]]
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = HEADING.match(line)
        if heading:
            sections.append([len(heading.group(1)), heading.group(2).strip(), 0, 0])
            continue
        task = TASK.match(line)
        if task:
            sections[-1][3] += 1
            if task.group(1) in "xX":
                sections[-1][2] += 1
    return [tuple(section) for section in sections if section[3]]


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_PLAN
    rows = progress(path.read_text(encoding="utf-8"))
    done = sum(row[2] for row in rows)
    total = sum(row[3] for row in rows)
    width = max(len(row[1]) for row in rows) + 2
    for level, name, section_done, section_total in rows:
        mark = "✔" if section_done == section_total else " "
        print(f"{mark} {('  ' if level == 2 else '') + name:<{width + 2}} {section_done:>3}/{section_total:<3}")
    print(f"\nTotal: {done}/{total} ({100 * done // total}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
