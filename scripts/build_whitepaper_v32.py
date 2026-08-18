#!/usr/bin/env python3
"""Build and verify the non-normative Integrity Protocol Whitepaper v3.2 PDF.

Install pinned browser assets outside the repository first:
  npm install --prefix ~/.cache/integrity-whitepaper-v32 \
    mermaid@11.16.1 katex@0.16.47
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "integrity-protocol-v3.2.md"
PDF_OUT = ROOT / "spec" / "Integrity_Protocol_Whitepaper_v3.2.pdf"
EXPECTED_ASSET_VERSIONS = {"mermaid": "11.16.1", "katex": "0.16.47"}
CACHE = Path(os.environ.get("INTEGRITY_WHITEPAPER_CACHE", "~/.cache/integrity-whitepaper-v32")).expanduser()
STAGE = CACHE / "stage"
NODE_MODULES = CACHE / "node_modules"
CHROME = shutil.which("google-chrome") or shutil.which("chromium")


def require(path: Path, explanation: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing {explanation}: {path}")


def render_markdown(source: str) -> tuple[str, int]:
    renderer = MarkdownIt("commonmark", {"html": True, "linkify": True, "typographer": False})
    renderer.enable("table")
    body = renderer.render(source)
    pattern = re.compile(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>', re.DOTALL
    )
    body, diagram_count = pattern.subn(
        lambda match: f'<div class="mermaid">{html.unescape(match.group(1))}</div>', body
    )
    return body, diagram_count


def build_html(body: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Integrity Protocol v3.2</title>
<link rel="stylesheet" href="katex/katex.min.css">
<style>
@page {{ size: A4; margin: 17mm 16mm 17mm; @bottom-center {{ content: "Xibalba Solutions, LLC · Integrity Protocol v3.2 · " counter(page); font: 8pt Arial; color: #718096; }} }}
* {{ box-sizing: border-box; }}
body {{ font-family: Arial, Helvetica, sans-serif; color: #182230; line-height: 1.46; font-size: 9.2pt; max-width: 100%; }}
h1 {{ color: #12233f; font-size: 21pt; border-bottom: 1px solid #177e86; padding-bottom: 5px; margin-top: 26px; break-after: avoid; }}
h1:first-of-type {{ font-size: 29pt; text-transform: uppercase; letter-spacing: 1.2px; text-align: center; border: 0; margin-top: 55mm; }}
h2 {{ color: #177e86; font-size: 14.5pt; margin-top: 22px; break-after: avoid; }}
h3 {{ color: #24566a; font-size: 11.5pt; margin-top: 17px; break-after: avoid; }}
h4 {{ color: #334e68; font-size: 10pt; break-after: avoid; }}
p {{ margin: 7px 0; orphans: 3; widows: 3; }}
a {{ color: #087f8c; }}
blockquote {{ margin: 12px 0; padding: 9px 13px; border-left: 4px solid #177e86; background: #f1f3f5; break-inside: avoid; }}
hr {{ border: 0; border-top: 1px solid #cbd5e0; margin: 17px 0; }}
ul, ol {{ margin-top: 5px; }} li {{ margin: 3px 0; }}
table {{ width: 100%; border-collapse: collapse; margin: 11px 0; font-size: 7.6pt; break-inside: avoid; }}
th {{ background: #12233f; color: white; text-align: left; }} th, td {{ border: 1px solid #cbd5e0; padding: 5px; vertical-align: top; }} tr:nth-child(even) td {{ background: #f7f9fa; }}
code {{ font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 8pt; background: #eef2f4; padding: 1px 3px; }}
pre {{ white-space: pre-wrap; font: 7pt/1.32 "DejaVu Sans Mono", Consolas, monospace; background: #f5f7f8; border: 1px solid #d7dee3; padding: 9px; break-inside: avoid; }}
.mermaid {{ display: flex; justify-content: center; margin: 12px auto; break-inside: avoid; max-width: 100%; }}
.mermaid svg {{ max-width: 100% !important; height: auto !important; }}
.katex-display {{ margin: 0.75em 0; padding: 6px 8px; background: #f1f3f5; overflow: hidden; break-inside: avoid; }}
</style>
<script src="katex/katex.min.js"></script>
<script src="katex/contrib/auto-render.min.js"></script>
<script src="mermaid.min.js"></script>
</head><body>{body}
<script>
(async () => {{
  renderMathInElement(document.body, {{
    delimiters: [
      {{left: "$$", right: "$$", display: true}},
      {{left: "$", right: "$", display: false}}
    ],
    throwOnError: false
  }});
  mermaid.initialize({{startOnLoad: false, securityLevel: "strict", theme: "neutral"}});
  await mermaid.run({{querySelector: ".mermaid"}});
  document.documentElement.dataset.renderComplete = "true";
}})().catch((error) => {{
  document.documentElement.dataset.renderError = String(error);
  console.error(error);
}});
</script></body></html>"""


def run() -> None:
    if not CHROME:
        raise SystemExit("google-chrome or chromium is required")
    mermaid = NODE_MODULES / "mermaid" / "dist" / "mermaid.min.js"
    katex = NODE_MODULES / "katex" / "dist"
    require(mermaid, "pinned Mermaid browser bundle")
    require(katex / "katex.min.js", "pinned KaTeX browser bundle")
    require(SOURCE, "v3.2 Markdown source")

    for package, expected in EXPECTED_ASSET_VERSIONS.items():
        metadata = NODE_MODULES / package / "package.json"
        try:
            observed = json.loads(metadata.read_text(encoding="utf-8"))["version"]
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot verify {package} package version at {metadata}: {exc}") from exc
        if observed != expected:
            raise SystemExit(
                f"Unsupported {package} version {observed}; expected {expected}. "
                "Reinstall the pinned whitepaper build dependencies."
            )

    STAGE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mermaid, STAGE / "mermaid.min.js")
    target_katex = STAGE / "katex"
    if target_katex.exists():
        shutil.rmtree(target_katex)
    shutil.copytree(katex, target_katex)

    body, expected_diagrams = render_markdown(SOURCE.read_text(encoding="utf-8"))
    source_html = STAGE / "Integrity_Protocol_Whitepaper_v3.2.source.html"
    rendered_html = STAGE / "Integrity_Protocol_Whitepaper_v3.2.rendered.html"
    source_html.write_text(build_html(body), encoding="utf-8")

    browser = [
        CHROME,
        "--headless",
        "--no-sandbox",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=30000",
    ]
    rendered = subprocess.run(
        [*browser, "--dump-dom", source_html.as_uri()],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.decode("utf-8")
    rendered_html.write_text(rendered, encoding="utf-8")

    if 'data-render-complete="true"' not in rendered:
        error = re.search(r'data-render-error="([^"]+)"', rendered)
        raise SystemExit(f"Browser rendering did not complete: {error.group(1) if error else 'unknown error'}")
    svg_count = rendered.count("<svg")
    if svg_count < expected_diagrams:
        raise SystemExit(f"Rendered {svg_count} SVGs; expected at least {expected_diagrams} Mermaid diagrams")

    subprocess.run(
        [
            *browser,
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF_OUT}",
            rendered_html.as_uri(),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(PDF_OUT, "generated v3.2 PDF")
    if PDF_OUT.stat().st_size < 100_000:
        raise SystemExit(f"Generated PDF is unexpectedly small: {PDF_OUT.stat().st_size} bytes")
    print(f"pdf={PDF_OUT}")
    print(f"mermaid_expected={expected_diagrams} svg_rendered={svg_count}")
    print(f"bytes={PDF_OUT.stat().st_size}")


if __name__ == "__main__":
    try:
        run()
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc), file=sys.stderr)
        raise
