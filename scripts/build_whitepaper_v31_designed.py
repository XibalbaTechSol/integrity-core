#!/usr/bin/env python3
"""Create the designed v3.1 whitepaper release with local MathJax rendering."""
from __future__ import annotations
import html, re, shutil, subprocess
from pathlib import Path
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec/integrity-protocol-v3.1.md"
OUT = ROOT / "docs/releases"
ASSETS = OUT / "assets"
HTML = OUT / "Integrity_Protocol_Whitepaper_v3.1_designed.html"
PDF = OUT / "Integrity_Protocol_Whitepaper_v3.1_designed.pdf"
LOGO_SRC = Path("/home/xibalba/Projects/XibalbaTechSol.github.io/dashboard/integrity/xibalba_logo_black.png")
MATHJAX_SRC = Path("/tmp/mathjax-svg.js")


def plain_math(value: str) -> str:
    """Render LaTeX source in the restrained monospace style used by v3."""
    value = value.replace("\\\\", "\\")
    value = re.sub(r"\\(?:text|mathrm|mathbf|operatorname)\s*\{([^{}]*)\}", r"\1", value)
    value = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"(\1)/(\2)", value)
    replacements = {
        r"\cdot": "·", r"\times": "×", r"\in": "∈", r"\notin": "∉",
        r"\leq": "≤", r"\geq": "≥", r"\neq": "≠", r"\to": "→",
        r"\infty": "∞", r"\sum": "Σ", r"\prod": "Π", r"\Theta": "Θ",
        r"\pi": "π", r"\rho": "ρ", r"\iota": "ι", r"\omega": "ω", r"\nu": "ν",
        r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\lambda": "λ",
        r"\left": "", r"\right": "", r"\displaystyle": "",
        r"\,": " ", r"\;": " ", r"\!": "", r"\\": " ",
    }
    for key, replacement in replacements.items():
        value = value.replace(key, replacement)
    value = re.sub(r"\\tag\s*\{[^{}]*\}", "", value)
    value = re.sub(r"\\[a-zA-Z]+", "", value)
    value = value.replace("\\ ", " ").replace("\\", "")
    value = value.replace("{", "").replace("}", "")
    for label in ("balances", "allowances", "nonces", "licence budgets", "module config", "policy params"):
        value = value.replace("_" + label, " (" + label + ")")
    return re.sub(r"[ \t]+", " ", value).strip()


def rich(text: str) -> str:
    tokens = []
    def hold(value: str) -> str:
        tokens.append(value); return f"\x00{len(tokens)-1}\x00"
    # Protect math before HTML escaping and render it as v3-style formula text.
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: hold(f'<span class="math-display">{html.escape(plain_math(m.group(1)))}</span>'), text)
    text = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", lambda m: hold(f'<code class="math-inline">{html.escape(plain_math(m.group(1)))}</code>'), text)
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    for i, value in enumerate(tokens):
        text = text.replace(f"\x00{i}\x00", value)
    return text


def table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if not all(re.fullmatch(r"[-: ]+", c or " ") for c in cells): rows.append(cells)
    if not rows: return ""
    out = ["<table><thead><tr>"] + [f"<th>{rich(x)}</th>" for x in rows[0]] + ["</tr></thead><tbody>"]
    for row in rows[1:]:
        out.append("<tr>" + "".join(f"<td>{rich(row[i] if i < len(row) else '')}</td>" for i in range(len(rows[0]))) + "</tr>")
    return "".join(out) + "</tbody></table>"


def convert(md: str) -> tuple[str, list[str]]:
    lines = md.replace("\r\n", "\n").splitlines(); out=[]; headings=[]; para=[]; bullets=[]; i=0
    def flush():
        nonlocal para
        if para: out.append(f"<p>{rich(' '.join(x.strip() for x in para))}</p>"); para=[]
    def flush_bullets():
        nonlocal bullets
        if bullets: out.append("<ul>"+"".join(f"<li>{x}</li>" for x in bullets)+"</ul>"); bullets=[]
    while i < len(lines):
        line=lines[i]
        if line.startswith("```"):
            flush(); flush_bullets(); lang=html.escape(line[3:].strip()); i+=1; code=[]
            while i<len(lines) and not lines[i].startswith("```"): code.append(lines[i]); i+=1
            out.append(f'<pre class="code" data-lang="{lang}">{html.escape(chr(10).join(code))}</pre>'); i+=1; continue
        if line.strip()=="$$":
            flush(); flush_bullets(); i+=1; eq=[]
            while i<len(lines) and lines[i].strip()!="$$": eq.append(lines[i]); i+=1
            out.append(f'<div class="equation"><code>{html.escape(plain_math(chr(10).join(eq)))}</code></div>'); i+=1; continue
        if line.strip().startswith("|") and line.strip().endswith("|"):
            flush(); flush_bullets(); rows=[line]; i+=1
            while i<len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"): rows.append(lines[i]); i+=1
            out.append(table(rows)); continue
        m=re.match(r"^(#{1,6})\s+(.*)$",line)
        if m:
            flush(); flush_bullets(); title=m.group(2).strip(); headings.append(title); anchor=re.sub(r"[^a-z0-9]+","-",title.lower()).strip("-")
            out.append(f'<h{len(m.group(1))} id="{anchor}">{rich(title)}</h{len(m.group(1))}>'); i+=1; continue
        if line.strip()=="---": flush(); flush_bullets(); out.append("<hr>"); i+=1; continue
        if line.startswith(">"):
            flush(); flush_bullets(); q=[]
            while i<len(lines) and lines[i].startswith(">"):
                q.append(lines[i][1:].strip()); i+=1
            out.append("<blockquote>"+rich(" ".join(q))+"</blockquote>"); continue
        m=re.match(r"^\s*[-*]\s+(.*)$",line)
        if m: flush(); bullets.append(rich(m.group(1))); i+=1; continue
        if not line.strip(): flush(); flush_bullets(); i+=1; continue
        para.append(line); i+=1
    flush(); flush_bullets(); return "\n".join(out), headings


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); ASSETS.mkdir(parents=True, exist_ok=True)
    # Crop the existing black Xibalba mark's white margins for clean cover placement.
    cropped=ASSETS/"xibalba_logo_black_cropped.png"
    with Image.open(LOGO_SRC).convert("RGB") as im:
        bg=Image.new("RGB", im.size, color=255)
        diff=ImageChops.difference(im, bg)
        box=diff.getbbox()
        if box: im.crop(box).save(cropped)
        else: im.save(cropped)
    if not MATHJAX_SRC.exists(): raise SystemExit("Missing /tmp/mathjax.js; download MathJax before building")
    shutil.copy2(MATHJAX_SRC, ASSETS/"mathjax-tex-svg.js")
    body, headings=convert(SOURCE.read_text(encoding="utf-8"))
    toc="".join(f'<li><a href="#{re.sub(r"[^a-z0-9]+","-",h.lower()).strip("-")}">{html.escape(h)}</a></li>' for h in headings if re.match(r"^(?:\d+|Appendix)",h))
    doc=f'''<!doctype html><html><head><meta charset="utf-8"><title>Integrity Protocol — Whitepaper v3.1</title>
<script>window.MathJax={{tex:{{inlineMath:[["\\\\(","\\\\)"],["$","$"]],displayMath:[["\\\\[","\\\\]"]] }},svg:{{fontCache:"global"}},startup:{{typeset:false}}}};</script><script src="assets/mathjax-tex-svg.js"></script>
<style>
@page{{size:letter;margin:0.78in 0.78in 0.72in;@bottom-center{{content:"Xibalba Solutions, LLC  ·  Integrity Protocol v3.1  ·  " counter(page);font:8pt Arial;color:#718096}}}}
*{{box-sizing:border-box}}body{{font-family:Arial,Helvetica,sans-serif;color:#182230;line-height:1.45;font-size:9.3pt}}a{{color:#087f8c}}.cover{{height:9.45in;display:flex;flex-direction:column;align-items:center;text-align:center;justify-content:center;page-break-after:always}}.cover img{{width:2.55in;margin-bottom:0.62in}}.cover h1{{font-size:29pt;letter-spacing:1.8px;color:#12233f;margin:0;text-transform:uppercase}}.cover .rule{{width:90%;border-top:1px solid #cbd5e0;margin:20px 0 15px}}.cover h2{{font-size:17pt;font-weight:normal;color:#177e86;margin:0 0 34px}}.cover .meta{{color:#697586;font-size:11pt;line-height:1.7}}.ground{{margin-top:46px;width:90%;padding:13px 17px;background:#f1f3f5;border-left:4px solid #177e86;text-align:left;font-size:9pt;font-style:italic}}.cover .footer{{margin-top:95px;color:#697586;font-size:11pt;line-height:1.8}}.toc{{page-break-after:always}}h1{{color:#12233f;font-size:19pt;border-bottom:1px solid #177e86;padding-bottom:5px;margin-top:24px}}h2{{color:#177e86;font-size:14pt;margin-top:21px}}h3{{color:#24566a;font-size:11.5pt;margin-top:16px}}p{{margin:7px 0}}blockquote{{margin:12px 0;padding:9px 13px;border-left:4px solid #177e86;background:#f1f3f5}}hr{{border:0;border-top:1px solid #cbd5e0;margin:16px 0}}ul{{margin-top:4px}}li{{margin:3px 0}}table{{width:100%;border-collapse:collapse;margin:11px 0;font-size:8pt;page-break-inside:avoid}}th{{background:#12233f;color:white;text-align:left}}th,td{{border:1px solid #cbd5e0;padding:5px 6px;vertical-align:top}}tr:nth-child(even) td{{background:#f7f9fa}}code{{font-family:Consolas,monospace;font-size:8pt;background:#eef2f4;padding:1px 3px}}.code{{white-space:pre-wrap;font:7pt/1.3 Consolas,monospace;background:#f5f7f8;border:1px solid #d7dee3;padding:9px;page-break-inside:avoid}}.equation{{text-align:left;margin:12px 10px;padding:5px 8px;background:#f1f3f5;border:1px solid #e2e8f0;min-height:24px;font:8.6pt/1.35 Consolas,"DejaVu Sans Mono",monospace;page-break-inside:avoid;color:#24364b}}.equation code,.math-inline{{font:inherit;background:transparent;padding:0;color:inherit}}.math-display{{display:block;margin:10px 0;padding:5px 8px;background:#f1f3f5;border:1px solid #e2e8f0;font:8.6pt/1.35 Consolas,"DejaVu Sans Mono",monospace;color:#24364b}}</style></head><body><section class="cover"><img src="assets/xibalba_logo_black_cropped.png"><h1>Integrity Protocol</h1><div class="rule"></div><h2>A Verification and Execution-Control Layer for the Autonomous Intellectual Property Economy</h2><div class="meta"><strong>Jacob S. Vickers</strong><br>Xibalba Solutions, LLC · Racine, Wisconsin<br><br><strong>Version 3.1</strong> · Markdown working draft · August 2026</div><div class="ground"><strong>Ground rule:</strong> This typeset release preserves the source document's distinction between implemented components, planned architecture, normative obligations, and unresolved risks. It is not a description of deployed v3 execution-firewall code.</div><div class="footer">Xibalba Solutions, LLC<br>Agentic Trust Layer for the AI Economy</div></section><section class="toc"><h1>Contents</h1><ol>{toc}</ol></section><main>{body}</main><script>MathJax.startup.promise.then(()=>MathJax.typesetPromise());</script></body></html>'''
    HTML.write_text(doc, encoding="utf-8")
    rendered = OUT / "Integrity_Protocol_Whitepaper_v3.1_rendered.html"
    rendered_html = subprocess.check_output(
        ["google-chrome", "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=10000", "--dump-dom", str(HTML)],
        stderr=subprocess.DEVNULL,
    )
    rendered.write_bytes(rendered_html)
    subprocess.run(["google-chrome","--headless","--no-sandbox","--disable-gpu", "--no-pdf-header-footer", "--run-all-compositor-stages-before-draw", f"--print-to-pdf={PDF}",str(rendered)],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    print(PDF)

if __name__ == "__main__": main()
