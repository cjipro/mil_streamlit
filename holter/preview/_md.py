"""Minimal, dependency-free Markdown → HTML for decision-pack altitude samples.

The engine writes each pack's investigation at three altitudes as Markdown
(`pulse/decision_packs/<pack>/samples/{bank,journey,signal}.md`). HOL-78 renders
those in the Workspace. Rather than add a Markdown runtime dependency to the
bank-env front-end, this converts the *exact, stable* subset those engine-authored
samples use — nothing more:

  ## h2 · ### h3 · **bold** · `inline code` · ```fenced code``` ·
  | alignment-aware tables | · > blockquotes · - bullet lists · paragraphs

It is deliberately NOT a general Markdown engine. All text is HTML-escaped at the
boundary before any markup is emitted (renderer escaping discipline: never trust a
string in the DOM, even engine-authored), so the converter is also XSS-safe.
"""

from __future__ import annotations

import re
from html import escape as _e

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_SEP_CELL = re.compile(r":?-{1,}:?")


def _inline(text: str) -> str:
    """Escape, then apply inline `code` and **bold**. Escaping leaves `*` and
    backticks intact, so the markup regexes still match the original markers."""
    out = _e(text)
    out = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    return out


def _split_row(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    cells = _split_row(s)
    return bool(cells) and all(_SEP_CELL.fullmatch(c) for c in cells)


def _aligns(sep_line: str) -> list[str]:
    out: list[str] = []
    for c in _split_row(sep_line):
        left, right = c.startswith(":"), c.endswith(":")
        out.append("center" if left and right else
                   "right" if right else "left" if left else "")
    return out


def _cell(tag: str, text: str, align: str) -> str:
    style = f' style="text-align:{align}"' if align else ""
    return f"<{tag}{style}>{_inline(text)}</{tag}>"


def _render_table(header: list[str], aligns: list[str], body: list[list[str]]) -> str:
    def al(j: int) -> str:
        return aligns[j] if j < len(aligns) else ""
    thead = "<tr>" + "".join(_cell("th", h, al(j)) for j, h in enumerate(header)) + "</tr>"
    rows = [
        "<tr>" + "".join(_cell("td", c, al(j)) for j, c in enumerate(r)) + "</tr>"
        for r in body
    ]
    return (f'<table class="alt-md-table"><thead>{thead}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def render_markdown(md: str) -> str:
    """Convert the engine-authored sample subset to HTML. Unknown constructs
    fall through as escaped paragraph text — never raw, never dropped silently."""
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n = len(lines)
    html: list[str] = []
    para: list[str] = []
    i = 0

    def flush() -> None:
        if para:
            html.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            flush(); i += 1; continue

        if stripped.startswith("```"):               # fenced code
            flush()
            lang = stripped[3:].strip()
            code: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i]); i += 1
            i += 1                                     # skip closing fence
            cls = f' class="lang-{_e(lang)}"' if lang else ""
            html.append(f"<pre class=\"alt-md-pre\"><code{cls}>"
                        f"{_e(chr(10).join(code))}</code></pre>")
            continue

        if stripped.startswith("### "):
            flush(); html.append(f"<h3>{_inline(stripped[4:])}</h3>"); i += 1; continue
        if stripped.startswith("## "):
            flush(); html.append(f"<h2>{_inline(stripped[3:])}</h2>"); i += 1; continue

        if stripped.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):
            flush()
            header = _split_row(stripped)
            aligns = _aligns(lines[i + 1])
            i += 2
            body: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                body.append(_split_row(lines[i].strip())); i += 1
            html.append(_render_table(header, aligns, body))
            continue

        if stripped.startswith(">"):
            flush()
            quote: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip()); i += 1
            html.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            continue

        if stripped.startswith("- "):
            flush()
            items: list[str] = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:]); i += 1
            html.append("<ul>" + "".join(f"<li>{_inline(it)}</li>" for it in items) + "</ul>")
            continue

        para.append(stripped); i += 1

    flush()
    return "\n".join(html)
