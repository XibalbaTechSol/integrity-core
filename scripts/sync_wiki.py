#!/usr/bin/env python3
"""
Syncs docs/wiki/ (this repo's compiled "memory" wiki, see .agents/AGENTS.md)
into the separate GitHub Wiki repo (<repo>.wiki.git), flattened.

Why flattened: GitHub Wiki's rendered page URLs
(github.com/OWNER/REPO/wiki/PAGE) only exist for files at the wiki repo's
ROOT. A file under a subdirectory (concepts/foo.md, entities/bar.md) has no
such route and 302-redirects to raw.githubusercontent.com instead --
literal unrendered markdown text, discovered from a real screenshot of a
page rendering that way. docs/wiki/ itself keeps its concepts/entities/
subdirectories unchanged (browsed via GitHub's normal repo file browser,
a different rendering path that DOES support directories) -- only this
mirror needs flattening.

Usage:
    python scripts/sync_wiki.py <path-to-wiki-repo-checkout>

The destination must already be a git checkout of the wiki repo (this
script only writes files -- committing/pushing is the caller's job, see
.github/workflows/sync-wiki.yml).
"""

from __future__ import annotations

import os
import re
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_WIKI = os.path.join(REPO_ROOT, "docs", "wiki")
SRC_DOCS = os.path.join(REPO_ROOT, "docs")
SRC_GUIDES = os.path.join(REPO_ROOT, "docs", "guides")


def build_source_map() -> dict[str, str]:
    """Maps a docs/-relative logical path -> the flat basename it becomes
    in the wiki repo. Asserts no basename collisions across categories."""
    sources: dict[str, str] = {}

    for sub in ("concepts", "entities"):
        for fname in os.listdir(os.path.join(SRC_WIKI, sub)):
            if fname.endswith(".md"):
                sources[f"wiki/{sub}/{fname}"] = fname

    for fname in ("WIKI_INDEX.md", "WIKI_LOG.md", "WIKI_SCHEMA.md", "index.md"):
        sources[f"wiki/{fname}"] = fname

    sources["INTERFACE_CONTRACT.md"] = "INTERFACE_CONTRACT.md"
    sources["TESTING.md"] = "TESTING.md"

    for fname in os.listdir(SRC_GUIDES):
        if fname.endswith(".md"):
            sources[f"guides/{fname}"] = fname

    basenames = list(sources.values())
    dupes = {b for b in basenames if basenames.count(b) > 1}
    if dupes:
        raise SystemExit(
            f"sync_wiki.py: filename collision(s) across concepts/entities/guides "
            f"would overwrite each other once flattened: {sorted(dupes)}. "
            f"Rename one of the source files before syncing."
        )
    return sources


def rewrite_links(content: str, current_docs_relpath: str, basename_registry: set[str]) -> str:
    """Rewrites every relative markdown link in `content` (a file originally
    at `current_docs_relpath`, relative to docs/) to a flat sibling
    reference. Links that don't resolve to a known wiki-mirrored file
    (e.g. an intentional escape to a main-repo path outside docs/) are left
    untouched -- callers handle those few cases explicitly (see below)."""
    current_dir = os.path.dirname(current_docs_relpath)

    def repl(m: re.Match) -> str:
        text, link = m.group(1), m.group(2)
        if link.startswith(("http://", "https://", "mailto:")):
            return m.group(0)
        path_part, _, frag = link.partition("#")
        if not path_part or path_part.endswith("/"):
            return m.group(0)
        resolved = os.path.normpath(os.path.join(current_dir, path_part)).replace(os.sep, "/")
        basename = os.path.basename(resolved)
        if basename in basename_registry:
            new_link = basename + (("#" + frag) if frag else "")
            return f"[{text}]({new_link})"
        return m.group(0)

    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", repl, content)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sync_wiki.py <path-to-wiki-repo-checkout>")
    dst = sys.argv[1]
    if not os.path.isdir(os.path.join(dst, ".git")):
        raise SystemExit(f"{dst} is not a git checkout (no .git/) -- refusing to write into it")

    sources = build_source_map()
    basename_registry = set(sources.values())

    # Wipe every tracked .md file at the destination root (but not .git, and
    # not _Sidebar.md/_Footer.md -- those are wiki-only navigation files
    # with no docs/wiki/ source, hand-maintained directly in the wiki repo).
    for fname in os.listdir(dst):
        if fname in (".git", "_Sidebar.md", "_Footer.md"):
            continue
        path = os.path.join(dst, fname)
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif fname.endswith(".md"):
            os.remove(path)

    for sub in ("concepts", "entities"):
        for fname in os.listdir(os.path.join(SRC_WIKI, sub)):
            if not fname.endswith(".md"):
                continue
            with open(os.path.join(SRC_WIKI, sub, fname), encoding="utf-8") as f:
                content = f.read()
            content = rewrite_links(content, f"wiki/{sub}/{fname}", basename_registry)
            with open(os.path.join(dst, fname), "w", encoding="utf-8") as f:
                f.write(content)

    for fname in ("WIKI_INDEX.md", "WIKI_LOG.md", "WIKI_SCHEMA.md"):
        with open(os.path.join(SRC_WIKI, fname), encoding="utf-8") as f:
            content = f.read()
        content = rewrite_links(content, f"wiki/{fname}", basename_registry)
        with open(os.path.join(dst, fname), "w", encoding="utf-8") as f:
            f.write(content)

    # index.md is the source of truth; mirrored to both Home.md (GitHub
    # Wiki's required landing-page filename) and index.md (kept for anyone
    # who clones the wiki repo directly and expects a normal README-style entry).
    with open(os.path.join(SRC_WIKI, "index.md"), encoding="utf-8") as f:
        content = f.read()
    content = rewrite_links(content, "wiki/index.md", basename_registry)
    content = content.replace(
        "[entities/](entities/)",
        "[the Entities section of WIKI_INDEX](WIKI_INDEX.md#entities-built)",
    )
    with open(os.path.join(dst, "Home.md"), "w", encoding="utf-8") as f:
        f.write(content)
    with open(os.path.join(dst, "index.md"), "w", encoding="utf-8") as f:
        f.write(content)

    with open(os.path.join(SRC_DOCS, "INTERFACE_CONTRACT.md"), encoding="utf-8") as f:
        content = f.read()
    content = rewrite_links(content, "INTERFACE_CONTRACT.md", basename_registry)
    with open(os.path.join(dst, "INTERFACE_CONTRACT.md"), "w", encoding="utf-8") as f:
        f.write(content)

    with open(os.path.join(SRC_DOCS, "TESTING.md"), encoding="utf-8") as f:
        content = f.read()
    content = rewrite_links(content, "TESTING.md", basename_registry)
    with open(os.path.join(dst, "TESTING.md"), "w", encoding="utf-8") as f:
        f.write(content)

    for fname in os.listdir(SRC_GUIDES):
        if not fname.endswith(".md"):
            continue
        with open(os.path.join(SRC_GUIDES, fname), encoding="utf-8") as f:
            content = f.read()
        content = rewrite_links(content, f"guides/{fname}", basename_registry)
        # The one known link that escapes docs/ entirely (to contracts/README.md,
        # a real main-repo file with no place in the wiki mirror) -- rewritten
        # to a real, working absolute GitHub URL instead of left dangling.
        content = content.replace(
            "](../../contracts/README.md)",
            "](https://github.com/XibalbaTechSol/integrity-latest/blob/main/contracts/README.md)",
        )
        with open(os.path.join(dst, fname), "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Synced {len(sources)} source files -> {dst} (flat, {len(os.listdir(dst)) - 1} files)")


if __name__ == "__main__":
    main()
