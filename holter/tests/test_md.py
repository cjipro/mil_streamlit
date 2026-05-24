"""HOL-78 — scoped Markdown→HTML converter for altitude samples.

Validates holter/preview/_md.render_markdown against every real decision-pack
sample (bank/journey/signal × all packs) plus targeted construct + escaping
assertions. The converter is deliberately small (no Markdown dependency in the
bank-env front-end), so this test pins the exact subset it must keep handling.

Run:  python -m pytest holter/tests/test_md.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from holter.preview._md import render_markdown

REPO = Path(__file__).resolve().parents[2]
SAMPLES = sorted((REPO / "pulse" / "decision_packs").glob("*/samples/*.md"))


def test_samples_present():
    assert SAMPLES, "no decision-pack samples found"
    # 12 packs × 3 altitudes
    assert len(SAMPLES) >= 36


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_every_sample_renders_without_error(sample: Path):
    html = render_markdown(sample.read_text(encoding="utf-8"))
    assert html.strip()
    # h2 title present in every sample → becomes an <h2>
    assert "<h2>" in html
    # no raw markdown markers leak as literal heading/bold syntax
    assert "## " not in html
    assert "**" not in html


def test_table_alignment_and_structure():
    md = "| Cohort | Share |\n|---|---:|\n| Mobile | 41.0% |\n"
    html = render_markdown(md)
    assert "<table" in html and "<thead>" in html and "<tbody>" in html
    assert "<th>Cohort</th>" in html
    assert 'style="text-align:right"' in html          # ---: → right
    assert "<td>Mobile</td>" in html


def test_fenced_code_is_escaped_and_not_inline_processed():
    md = "```yaml\nmethod: dwell_z_score\nthreshold: <0.01>\n```\n"
    html = render_markdown(md)
    assert "<pre" in html and "<code" in html
    assert "&lt;0.01&gt;" in html                       # escaped inside code


def test_bold_inline_code_blockquote_bullets():
    md = ("**high** confidence with `p<0.01`\n\n"
          "> Fairness check triggered.\n\n"
          "- one\n- two\n")
    html = render_markdown(md)
    assert "<strong>high</strong>" in html
    assert "<code>p&lt;0.01</code>" in html             # escaped + wrapped
    assert "<blockquote>" in html and "Fairness check" in html
    assert html.count("<li>") == 2


def test_html_is_escaped_at_boundary():
    # an injected tag must never survive as live markup
    html = render_markdown("a <script>alert(1)</script> b\n")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
