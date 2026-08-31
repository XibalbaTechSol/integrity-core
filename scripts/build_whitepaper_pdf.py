#!/usr/bin/env python3
"""Build a print-ready PDF from the Integrity Protocol v3.1 Markdown draft."""
from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "integrity-protocol-v3.1.md"
OUT_DIR = ROOT / "docs" / "releases"
HTML_OUT = OUT_DIR / "Integrity_Protocol_Whitepaper_v3.1.html"
PDF_OUT = OUT_DIR / "Integrity_Protocol_Whitepaper_v3.1.pdf"


def inline(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
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
    list_items: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            text = " ".join(x.strip() for x in paragraph)
            out.append(f"<p>{inline(html.escape(text))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in list_items) + "</ul>")
            list_items = []

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush_paragraph(); flush_list()
            lang = html.escape(line[3:].strip())
            code: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i]); i += 1
            code_text = "\n".join(code)
            out.append(f'<pre class="code" data-lang="{lang}">{html.escape(code_text)}</pre>')
            i += 1
            continue
        if is_table_row(line):
            flush_paragraph(); flush_list()
            rows = [line]; i += 1
            while i < len(lines) and is_table_row(lines[i]):
                rows.append(lines[i]); i += 1
            out.append(table_html(rows)); continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_paragraph(); flush_list()
            level = len(m.group(1)); title = m.group(2).strip()
            headings.append(title)
            anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append(f'<h{level} id="{anchor}">{inline(html.escape(title))}</h{level}>')
            i += 1; continue
        if re.match(r"^---+$", line.strip()):
            flush_paragraph(); flush_list(); out.append("<hr>"); i += 1; continue
        if line.startswith(">"):
            flush_paragraph(); flush_list()
            quote: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i][1:].strip()); i += 1
            out.append(f'<blockquote>{inline(html.escape(" ".join(quote)))}</blockquote>'); continue
        lm = re.match(r"^\s*[-*]\s+(.*)$", line)
        if lm:
            flush_paragraph(); list_items.append(inline(html.escape(lm.group(1)))); i += 1; continue
        if not line.strip():
            flush_paragraph(); flush_list(); i += 1; continue
        if re.match(r"^\[\^[^]]+\]:", line):
            flush_paragraph(); flush_list(); out.append(f'<p class="footnote">{inline(html.escape(line))}</p>'); i += 1; continue
        paragraph.append(line); i += 1
    flush_paragraph(); flush_list()
    return "\n".join(out), headings


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body, headings = convert(SOURCE.read_text(encoding="utf-8"))
    toc = "".join(
        f'<li><a href="#{re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-")}">{html.escape(h)}</a></li>'
        for h in headings if re.match(r"^(?:\d+|Appendix)", h)
    )
    document = f'''<!doctype html><html><head><meta charset="utf-8"><title>Integrity Protocol — Whitepaper v3.1</title>
<style>
@page {{ size: A4; margin: 20mm 17mm 19mm; @bottom-center {{ content: "Integrity Protocol · Whitepaper v3.1 · " counter(page); font: 8pt Arial; color:#667085; }} }}
* {{ box-sizing:border-box; }} body {{ font-family: Arial, Helvetica, sans-serif; color:#182230; line-height:1.45; font-size:9.5pt; }}
.cover {{ min-height:245mm; display:flex; flex-direction:column; justify-content:center; page-break-after:always; border-top:8px solid #0b7285; }}
.cover h1 {{ font-size:31pt; line-height:1.08; color:#073b4c; margin:0 0 10px; }} .cover h2 {{ font-size:17pt; font-weight:normal; color:#0b7285; margin:0 0 28px; }}
.meta {{ color:#52606d; font-size:11pt; }} .notice {{ margin-top:35px; border-left:4px solid #f59f00; padding:12px 15px; background:#fff8e6; font-size:9pt; }}
.toc {{ page-break-after:always; }} .toc h1 {{ color:#073b4c; }} .toc li {{ margin:4px 0; }}
h1 {{ color:#073b4c; font-size:20pt; border-bottom:2px solid #0b7285; padding-bottom:5px; margin-top:26px; }} h2 {{ color:#0b7285; font-size:15pt; margin-top:22px; }} h3 {{ color:#155e75; font-size:12pt; margin-top:17px; }}
p {{ margin:7px 0; }} a {{ color:#0b7285; }} code {{ font-family: Consolas, monospace; font-size:8.3pt; background:#eef2f4; padding:1px 3px; }}
blockquote {{ margin:12px 0; padding:9px 13px; border-left:4px solid #0b7285; background:#f1f8fa; }} hr {{ border:0; border-top:1px solid #ccd5db; margin:18px 0; }}
ul {{ margin-top:4px; }} li {{ margin:3px 0; }} table {{ width:100%; border-collapse:collapse; margin:12px 0; font-size:8.2pt; page-break-inside:avoid; }} th {{ background:#073b4c; color:white; text-align:left; }} th,td {{ border:1px solid #cbd5dc; padding:5px 6px; vertical-align:top; }} tr:nth-child(even) td {{ background:#f7fafb; }}
.code {{ white-space:pre-wrap; font:7.2pt/1.3 Consolas, monospace; background:#f5f7f8; border:1px solid #d7dee3; padding:10px; border-radius:3px; page-break-inside:avoid; }} .footnote {{ font-size:8pt; color:#52606d; }}
</style></head><body>
<section class="cover"><h1>Integrity Protocol</h1><h2>A Verification and Execution-Control Layer for the Autonomous Intellectual Property Economy</h2><div class="meta"><strong>Jacob S. Vickers</strong><br>Xibalba Solutions, LLC · Racine, Wisconsin<br><br><strong>Version 3.1</strong> · Markdown working draft · August 2026</div><div class="notice"><strong>Publication status.</strong> This PDF is a typeset release of the v3.1 Markdown working draft. It preserves the source document's distinction between implemented reference components, planned architecture, normative obligations, and unresolved risks. It is not a description of deployed v3 execution-firewall code.</div></section>
<section class="toc"><h1>Contents</h1><ol>{toc}</ol></section>
<main>{body}</main></body></html>'''
    HTML_OUT.write_text(document, encoding="utf-8")
    subprocess.run(["google-chrome", "--headless", "--no-sandbox", "--disable-gpu", f"--print-to-pdf={PDF_OUT}", str(HTML_OUT)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(PDF_OUT)

if __name__ == "__main__":
    main()
