#!/usr/bin/env python3
"""Build a print-ready PDF from the Integrity Protocol v1.0.0 Normative Specification (docs/SPEC.md)."""
from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "SPEC.md"
OUT_DIR = ROOT / "docs" / "releases"
SPEC_DIR = ROOT / "spec"
HTML_OUT = OUT_DIR / "Integrity_Protocol_Specification_v1.0.0.html"
PDF_OUT = OUT_DIR / "Integrity_Protocol_Specification_v1.0.0.pdf"
PDF_ALIAS = OUT_DIR / "integrity-protocol-specification.pdf"
SPEC_PDF_OUT = SPEC_DIR / "Integrity_Protocol_Specification_v1.0.0.pdf"
SPEC_PDF_ALIAS = SPEC_DIR / "integrity-protocol-specification.pdf"


def inline(text: str) -> str:
    # Markdown links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # Inline math \( ... \)
    text = re.sub(r"\\\((.+?)\\\)", r'<span class="math-inline">\1</span>', text)
    return text


def is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|")


def table_html(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"[-: ]+", c or " ") for c in cells):
            continue
        rows.append(cells)
    if not rows:
        return ""
    out = ["<table><thead><tr>"]
    out.extend(f"<th>{inline(html.escape(c))}</th>" for c in rows[0])
    out.append("</tr></thead><tbody>")
    for row in rows[1:]:
        out.append("<tr>")
        for i in range(len(rows[0])):
            value = row[i] if i < len(row) else ""
            out.append(f"<td>{inline(html.escape(value))}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def convert(md: str) -> tuple[str, list[str]]:
    lines = md.replace("\r\n", "\n").splitlines()
    out: list[str] = []
    headings: list[str] = []
    i = 0
    paragraph: list[str] = []
    ul_items: list[str] = []
    ol_items: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(x.strip() for x in paragraph)
            out.append(f"<p>{inline(html.escape(text))}</p>")
            paragraph = []

    def flush_lists() -> None:
        nonlocal ul_items, ol_items
        if ul_items:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in ul_items) + "</ul>")
            ul_items = []
        if ol_items:
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in ol_items) + "</ol>")
            ol_items = []

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.startswith("```"):
            flush_paragraph()
            flush_lists()
            lang = html.escape(line[3:].strip())
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            code_text = "\n".join(code)
            out.append(f'<pre class="code" data-lang="{lang}">{html.escape(code_text)}</pre>')
            i += 1
            continue

        # Math display block \[ ... \]
        if line.strip() == "\\[":
            flush_paragraph()
            flush_lists()
            math_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != "\\]":
                math_lines.append(lines[i])
                i += 1
            math_content = html.escape("\n".join(math_lines))
            out.append(f'<div class="math-block">{math_content}</div>')
            i += 1
            continue

        # Tables
        if is_table_row(line):
            flush_paragraph()
            flush_lists()
            rows = [line]
            i += 1
            while i < len(lines) and is_table_row(lines[i]):
                rows.append(lines[i])
                i += 1
            out.append(table_html(rows))
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_paragraph()
            flush_lists()
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append(title)
            anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append(f'<h{level} id="{anchor}">{inline(html.escape(title))}</h{level}>')
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^---+$", line.strip()):
            flush_paragraph()
            flush_lists()
            out.append("<hr>")
            i += 1
            continue

        # Blockquote
        if line.startswith(">"):
            flush_paragraph()
            flush_lists()
            quote: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i][1:].strip())
                i += 1
            out.append(f'<blockquote>{inline(html.escape(" ".join(quote)))}</blockquote>')
            continue

        # Unordered list item
        ul_m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if ul_m:
            flush_paragraph()
            if ol_items:
                flush_lists()
            ul_items.append(inline(html.escape(ul_m.group(1))))
            i += 1
            continue

        # Ordered list item
        ol_m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if ol_m:
            flush_paragraph()
            if ul_items:
                flush_lists()
            ol_items.append(inline(html.escape(ol_m.group(2))))
            i += 1
            continue

        # Empty line
        if not line.strip():
            flush_paragraph()
            flush_lists()
            i += 1
            continue

        # Footnote definition
        if re.match(r"^\[\^[^]]+\]:", line):
            flush_paragraph()
            flush_lists()
            out.append(f'<p class="footnote">{inline(html.escape(line))}</p>')
            i += 1
            continue

        # Normal text line inside a paragraph
        paragraph.append(line)
        i += 1

    flush_paragraph()
    flush_lists()
    return "\n".join(out), headings


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)

    body, headings = convert(SOURCE.read_text(encoding="utf-8"))
    toc = "".join(
        f'<li><a href="#{re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-")}">{html.escape(h)}</a></li>'
        for h in headings if re.match(r"^(?:\d+|\§\d+|Appendix)", h)
    )

    document = f'''<!doctype html><html><head><meta charset="utf-8"><title>Integrity Protocol Specification v1.0.0</title>
<style>
@page {{
    size: A4;
    margin: 20mm 17mm 19mm;
    @bottom-center {{
        content: "Integrity Protocol · Specification v1.0.0 · " counter(page);
        font: 8pt Arial, sans-serif;
        color: #667085;
    }}
}}
* {{ box-sizing: border-box; }}
body {{
    font-family: Arial, Helvetica, sans-serif;
    color: #182230;
    line-height: 1.45;
    font-size: 9.5pt;
}}
.cover {{
    min-height: 245mm;
    display: flex;
    flex-direction: column;
    justify-content: center;
    page-break-after: always;
    border-top: 8px solid #0284c7;
}}
.cover h1 {{
    font-size: 30pt;
    line-height: 1.1;
    color: #0f172a;
    margin: 0 0 10px;
    letter-spacing: -0.5px;
}}
.cover h2 {{
    font-size: 16pt;
    font-weight: normal;
    color: #0284c7;
    margin: 0 0 28px;
}}
.meta {{
    color: #475569;
    font-size: 11pt;
    line-height: 1.6;
}}
.notice {{
    margin-top: 35px;
    border-left: 4px solid #0284c7;
    padding: 12px 15px;
    background: #f0f9ff;
    font-size: 9pt;
    color: #0369a1;
}}
.toc {{ page-break-after: always; }}
.toc h1 {{ color: #0f172a; }}
.toc ol {{ padding-left: 20px; }}
.toc li {{ margin: 4px 0; font-size: 9pt; }}
h1 {{
    color: #0f172a;
    font-size: 19pt;
    border-bottom: 2px solid #0284c7;
    padding-bottom: 5px;
    margin-top: 26px;
    page-break-after: avoid;
}}
h2 {{
    color: #0284c7;
    font-size: 14pt;
    margin-top: 22px;
    page-break-after: avoid;
}}
h3 {{
    color: #0369a1;
    font-size: 11.5pt;
    margin-top: 17px;
    page-break-after: avoid;
}}
h4 {{
    color: #334155;
    font-size: 10pt;
    margin-top: 14px;
    page-break-after: avoid;
}}
p {{ margin: 7px 0; }}
a {{ color: #0284c7; text-decoration: none; }}
code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 8.3pt;
    background: #f1f5f9;
    color: #0f172a;
    padding: 1px 4px;
    border-radius: 2px;
}}
.math-inline {{
    font-family: "Times New Roman", Times, serif;
    font-style: italic;
    font-size: 9.5pt;
    background: #f8fafc;
    padding: 0 2px;
}}
.math-block {{
    font-family: "Times New Roman", Times, serif;
    font-style: italic;
    font-size: 10pt;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 3px solid #0284c7;
    padding: 8px 12px;
    margin: 10px 0;
    border-radius: 2px;
    text-align: center;
    white-space: pre-wrap;
}}
blockquote {{
    margin: 12px 0;
    padding: 9px 13px;
    border-left: 4px solid #0284c7;
    background: #f0f9ff;
}}
hr {{
    border: 0;
    border-top: 1px solid #cbd5e1;
    margin: 18px 0;
}}
ul, ol {{ margin-top: 4px; padding-left: 20px; }}
li {{ margin: 3px 0; }}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 8.2pt;
    page-break-inside: avoid;
}}
th {{
    background: #0f172a;
    color: white;
    text-align: left;
    font-weight: 600;
}}
th, td {{
    border: 1px solid #cbd5e1;
    padding: 5px 6px;
    vertical-align: top;
}}
tr:nth-child(even) td {{ background: #f8fafc; }}
.code {{
    white-space: pre-wrap;
    font: 7.2pt/1.3 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 10px;
    border-radius: 3px;
    page-break-inside: avoid;
}}
.footnote {{ font-size: 8pt; color: #64748b; }}
</style></head><body>
<section class="cover">
    <h1>Integrity Protocol</h1>
    <h2>Normative Technical Specification · Version 1.0.0</h2>
    <div class="meta">
        <strong>Jacob S. Vickers</strong><br>
        Founder, Xibalba Solutions, LLC · Racine, Wisconsin<br><br>
        <strong>Normative Specification</strong> · November 2026<br>
        Baseline Authority for Implementations
    </div>
    <div class="notice">
        <strong>Normative Authority.</strong> This specification defines the conformance requirements for the Integrity Protocol v1 execution firewall, 3-Tier Identity & Actor Topology, SovereignAgent smart account wallet stack, post-state invariance enforcement, canonical singletons, and evidence verification pipelines.
    </div>
</section>
<section class="toc">
    <h1>Table of Contents</h1>
    <ol>{toc}</ol>
</section>
<main>{body}</main>
</body></html>'''

    HTML_OUT.write_text(document, encoding="utf-8")
    subprocess.run(
        [
            "google-chrome",
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            f"--print-to-pdf={PDF_OUT}",
            str(HTML_OUT),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Create aliases and copies
    shutil.copy2(PDF_OUT, PDF_ALIAS)
    shutil.copy2(PDF_OUT, SPEC_PDF_OUT)
    shutil.copy2(PDF_OUT, SPEC_PDF_ALIAS)

    print(f"Generated: {PDF_OUT}")
    print(f"Aliased to: {PDF_ALIAS}")
    print(f"Copied to: {SPEC_PDF_OUT}")
    print(f"Copied to: {SPEC_PDF_ALIAS}")


if __name__ == "__main__":
    main()
