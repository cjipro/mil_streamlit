"""Cerno friction surface — renders the real Cerno marts / D-014 shortlist
through the Holter design system (HOL-90).

Uses the _shared.py PRESENTATION component library (render_box, body_bars,
headline_stat_card, …) + the dark CSS shell, served via server._page() so it
inherits Row-1 Themes + Row-2 Journey/Op-code + the bounded .holter-app shell
(HOL-73/83/85/86). Does NOT touch the pulse engine objects (HOL-36 coupling) —
data comes from cerno_source (the marts/D-014 adapter). On the work machine,
CERNO_MARTS_DIR makes it LIVE; otherwise a synthetic SAMPLE fixture renders.

This is the PRIMARY surface in the work-machine deployment; the pulse-synthetic
surfaces (Decisions/Intelligence/Verification) remain for the OSS reference.
"""
from __future__ import annotations

from html import escape as _e

from holter.preview import cerno_source as src
from holter.preview._shared import (
    CSS,
    NOW,
    body_action_primary,
    body_bars,
    body_chip_strip,
    body_quality_strip,
    box_footer,
    box_header,
    headline_stat_card,
    render_box,
    render_glossary_panel,
)

# Dark-theme tier colours (the _shared :root tokens).
_ADDR_COLOR = {"AGENTIC": "var(--green)", "ENGINEERING": "var(--blue)",
               "DESIGN": "var(--amber)", "MIXED": "var(--teal)"}
_CLARK_COLOR = {"CLARK_1": "var(--red)", "CLARK_2": "var(--amber)",
                "CLARK_3": "var(--teal)", "CLARK_4": "var(--text-3)"}
_CLASS_COLOR = {"SEAM": "var(--blue)", "CASCADE": "var(--amber)", "SINGLE": "var(--teal)"}
_MODE_GLYPH = {"loop": "↻", "error": "✕", "abandon": "↘"}
_ADDR_ACTION = {"AGENTIC": "Agentic intervention candidate — guided assist",
                "ENGINEERING": "Engineering triage — functional fix",
                "DESIGN": "Design review — flow change", "MIXED": "Mixed — name the dominant"}


def render_topnav() -> str:
    """Identity-only topnav (HOL-86 — journey filtering is the Row-2 global
    selector injected by server._page). Carries the brand-logo anchor _page
    replaces with Row-1, and the glossary panel."""
    return f'''
<header class="holter-topnav">
  <span class="brand-logo">Cerno</span>
  <span class="topnav-spacer"></span>
  <button class="topnav-icon" type="button" title="Search (/)">⌕</button>
  <button class="topnav-icon" type="button" title="Notifications">🔔</button>
  <details class="topnav-glossary">
    <summary class="topnav-icon topnav-glossary-trigger" title="Status glossary">Aa</summary>
    <div class="topnav-glossary-panel">
      <div class="topnav-glossary-panel-header">STATUS GLOSSARY</div>
      <div class="topnav-glossary-panel-body">{render_glossary_panel()}</div>
    </div>
  </details>
  <button class="topnav-icon" type="button" title="Settings">⚙</button>
  <button class="topnav-avatar" type="button" title="Hussain Ahmed">HA</button>
</header>'''


def _dominant_mode(row: dict) -> str:
    comps = {"abandon": row.get("risk_abandon", 0) or 0,
             "error": row.get("risk_error", 0) or 0,
             "loop": row.get("risk_loop", 0) or 0}
    return max(comps, key=comps.get)


def _compact(n) -> str:
    n = n or 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def _context_box(stats: dict, live: bool, n_rows: int) -> str:
    """Compact FULL-WIDTH summary band (header zone above the hero) — not a
    4-layer box, so it doesn't orphan a grid column (R1 panel fix)."""
    kpis = [
        (str(stats.get("n_candidates", n_rows)), "candidates"),
        (str(stats.get("n_agentic", 0)), "agentic"),
        (_compact(stats.get("total_sessions")), "sessions"),
        (_compact(stats.get("total_customers")), "customers"),
        (f'{stats.get("concentration_pct", 0):.0f}%',
         f'friction in {stats.get("concentration_states", 0)} states'),
        (f'{stats.get("error_free_pct", 0):.0f}%', "error-free"),
    ]
    kpi_html = "".join(f'<span class="ccb-kpi"><b>{v}</b>{l}</span>' for v, l in kpis)
    insight = (
        "Friction is strongly concentrated (Pareto). Top priority is high-volume "
        "<b>loop-driven</b> friction with no strong error signal — customers stuck, "
        "not failing, so it's invisible to error-log monitoring. The agentic sweet spot."
    )
    badge = "" if live else '<span class="ccb-badge">SAMPLE</span> '
    tail = "" if live else " — set CERNO_MARTS_DIR for LIVE"
    foot = (f'{badge}Risk: {stats.get("risk_weights", "abandon 0.5 · error 0.3 · loop 0.2")} · '
            f'snapshot {stats.get("snapshot_id", "—")} · map {stats.get("map_version", "—")}{tail}')
    return (
        '<div class="cerno-context-band">'
        '<div class="ccb-title">CERNO · FRICTION <span>D-014 decision feed</span></div>'
        f'<div class="ccb-kpis">{kpi_html}</div>'
        f'<div class="ccb-insight">{insight}</div>'
        f'<div class="ccb-foot">{foot}</div>'
        "</div>"
    )


def _candidate_box(r: dict, live: bool, hero: bool = False) -> str:
    rank = r.get("rank")
    cls = r.get("system_class", "—")
    addr = r.get("addressability", "—")
    clark = r.get("clark_tier", "—")
    accent = _CLARK_COLOR.get(clark, "var(--border)")
    mode = _dominant_mode(r)

    star = " ★" if r.get("is_agentic") else ""
    title = f"#{rank} · {cls}{star}"
    if hero:
        title = "▲ TOP PRIORITY · " + title
    header = box_header(title, _e(str(r.get("role_shape", ""))))
    headline = headline_stat_card(
        label="PRIORITY",
        value=f'{r.get("priority", 0)}',
        delta=f'risk {r.get("risk", 0):.2f}',
        traj=_MODE_GLYPH.get(mode, ""),
        meta_left=f'{(r.get("reach_customers") or 0):,} customers',
        meta_right=clark.replace("_", " "),
        progress_pct=int((r.get("risk", 0) or 0) * 100),
    )
    bars = body_bars([
        ("Abandon", int((r.get("risk_abandon", 0) or 0) * 100), f'{r.get("risk_abandon", 0):.2f}', "var(--red)"),
        ("Error", int((r.get("risk_error", 0) or 0) * 100), f'{r.get("risk_error", 0):.2f}', "var(--amber)"),
        ("Loop", int((r.get("risk_loop", 0) or 0) * 100), f'{r.get("risk_loop", 0):.2f}', "var(--blue)"),
    ])
    chips = body_chip_strip([
        (cls, "", _CLASS_COLOR.get(cls, "var(--text-3)")),
        (addr, "", _ADDR_COLOR.get(addr, "var(--text-3)")),
    ])
    action = body_action_primary(addr, _ADDR_ACTION.get(addr, ""), _ADDR_COLOR.get(addr, "var(--border)"))
    body = bars + chips + action + body_quality_strip(
        ["Value deferred", "Fairness deferred", f"Reach {(r.get('reach_sessions') or 0):,} sessions"],
        label="DEFERRED",
    )
    footer = box_footer("D-014", clark.replace("_", " "), live=live,
                        note=f'<a class="cerno-drill" href="/cerno/candidate/{rank}">Drill into candidate →</a>')
    return render_box(header=header, headline=headline, body=body, footer=footer,
                      accent_color=accent, box_attrs=('data-hero="1"' if hero else ""))


_CERNO_CSS = """<style id="cerno-css">
.cerno-insight{font:400 12.5px/1.5 var(--sans);color:var(--text-2);margin:0 0 .7rem}
.cerno-insight b{color:var(--text);font-weight:700}
.cerno-drill{color:var(--blue);text-decoration:none;font-weight:600}
.cerno-drill:hover{text-decoration:underline}
.cerno-back{color:var(--blue);text-decoration:none;font-weight:600;font-size:12px}
.cerno-tbl{width:100%;border-collapse:collapse;font:500 11.5px/1.4 var(--sans)}
.cerno-tbl th{font:700 8px/1 var(--sans);letter-spacing:.1em;text-transform:uppercase;
  color:var(--text-3);text-align:left;padding:.3rem .4rem;border-bottom:1px solid var(--border)}
.cerno-tbl td{padding:.32rem .4rem;border-bottom:1px solid rgba(0,58,92,.4);color:var(--text-2)}
.cerno-tbl td.num{text-align:right;font-family:var(--mono);color:var(--text)}
.cerno-mono{font:500 11px/1.55 var(--mono);color:var(--text);background:var(--bg);
  border:1px solid var(--border);border-radius:4px;padding:.5rem .6rem;margin:0 0 .4rem;
  white-space:pre-wrap;word-break:break-word;display:block}
.cerno-sig{font:400 12.5px/1.55 var(--sans);color:var(--text-2);margin:0}
.cerno-note{font:400 11px/1.5 var(--sans);color:var(--text-3);margin:.6rem 0 0}
.holter-box[data-hero]{grid-column:1 / -1;background:linear-gradient(180deg,rgba(0,183,245,.07),transparent 55%)}
.cerno-context-band{grid-column:1 / -1;background:var(--card);border:1px solid var(--border);
  border-left:3px solid var(--blue);border-radius:2px;padding:1rem 1.2rem}
.ccb-title{font:700 13px/1 var(--sans);color:var(--blue);letter-spacing:.05em;text-transform:uppercase;margin:0 0 .8rem}
.ccb-title span{color:var(--text-3);font-weight:500;text-transform:none;letter-spacing:0;margin-left:.6rem;font-size:11px}
.ccb-kpis{display:flex;flex-wrap:wrap;gap:1.6rem;margin:0 0 .7rem}
.ccb-kpi{font:400 10.5px/1.2 var(--sans);color:var(--text-3);text-transform:uppercase;letter-spacing:.06em;display:flex;align-items:baseline;gap:.35rem}
.ccb-kpi b{font-family:var(--mono);font-size:19px;color:var(--text);font-weight:600;text-transform:none;letter-spacing:0}
.ccb-insight{font:400 12.5px/1.5 var(--sans);color:var(--text-2);max-width:64rem;margin:0 0 .55rem}
.ccb-insight b{color:var(--text)}
.ccb-foot{font:400 10.5px/1.4 var(--mono);color:var(--text-3)}
.ccb-badge{background:#E5E0D2;color:#8a6d1a;font-weight:700;padding:.05rem .35rem;border-radius:3px;font-family:var(--sans);font-size:9px}
</style>"""


def _mini_table(headers: list[tuple[str, bool]], rows: list[list[str]]) -> str:
    """Compact dark table. headers = [(label, is_num)]; rows pre-formatted.
    No backslashes inside f-string expressions (SyntaxError on Python 3.11)."""
    num_attr = ' class="num"'
    head = "".join(f'<th{num_attr if num else ""}>{h}</th>' for h, num in headers)
    body = ""
    for row in rows:
        cells = "".join(
            f'<td{num_attr if headers[i][1] else ""}>{c}</td>'
            for i, c in enumerate(row)
        )
        body += f"<tr>{cells}</tr>"
    return f'<table class="cerno-tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _doc(main_html: str, title: str) -> str:
    """Full Holter document shell — the brand-logo + </header> + </head> +
    </body> anchors are what server._page() injects Row-1/Row-2/layout into."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
{_CERNO_CSS}
</head>
<body>
<div class="holter-app">
  {render_topnav()}
  <main class="holter-main">{main_html}</main>
</div>
</body>
</html>'''


# ── Stage-C marts as evidence boxes ──────────────────────────────────────────
def _marts_boxes() -> str:
    weak, w_live = src.weak_links()
    fric, _ = src.friction_matrix()
    casc, _ = src.error_cascades()

    w_rows = [[_e(str(r["step"])), f'{(r["reach_customers"] or 0):,}',
               f'{(r["fail_rate"] or 0) * 100:.0f}%', f'{r["score"]:.0f}'] for r in weak[:8]]
    weak_box = render_box(
        header=box_header("C_WEAK_LINKS", "reach × fail — the shortlist spine"),
        headline="", body=_mini_table(
            [("Step", False), ("Reach", True), ("Fail", True), ("Score", True)], w_rows),
        footer=box_footer("Stage C", "marts", live=w_live), accent_color="var(--blue)")

    f_rows = [[_e(str(r["step"])),
               ("— loop" if r["error_code"] in ("—", "", None) else _e(str(r["error_code"]))),
               f'{(r["n_sessions"] or 0):,}', f'{r["pct_of_friction"]}%'] for r in fric[:8]]
    fric_box = render_box(
        header=box_header("C_FRICTION_MATRIX", "step × error by affected sessions"),
        headline="", body=_mini_table(
            [("Step", False), ("Error", False), ("Sessions", True), ("% fric", True)], f_rows),
        footer=box_footer("Stage C", "marts", live=w_live), accent_color="var(--amber)")

    c_rows = [[_e(str(r["pattern"])), f'{(r["n_sessions"] or 0):,}',
               str(r["n_distinct_errors"]), f'{(r["abandon_rate"] or 0) * 100:.0f}%'] for r in casc[:8]]
    casc_box = render_box(
        header=box_header("C_ERROR_CASCADES", "error accumulation within sessions"),
        headline="", body=_mini_table(
            [("Pattern", False), ("Sessions", True), ("Errors", True), ("Abandon", True)], c_rows),
        footer=box_footer("Stage C", "marts", live=w_live), accent_color="var(--teal)")

    return ('<div class="holter-row" data-row="cerno-marts">'
            + weak_box + fric_box + casc_box + "</div>")


def friction_main() -> str:
    """The friction EXPLORE content (context + feed + marts) as holter-rows.
    Reusable: the standalone page wraps it in _doc; the Exploration surface
    (render_exploration) places it above the verify panes."""
    rows, live = src.shortlist()
    stats, _ = src.overview()
    boxes = '<div class="holter-row" data-row="cerno-context">'
    boxes += _context_box(stats, live, len(rows))
    boxes += "</div>"
    # #3 — hero the top-priority candidate above the uniform tail (it recommends
    # "start here" instead of reading as a flat browse-list).
    if rows:
        boxes += '<div class="holter-row" data-row="cerno-hero">'
        boxes += _candidate_box(rows[0], live, hero=True)
        boxes += "</div>"
    boxes += '<div class="holter-row" data-row="cerno-feed">'
    for r in rows[1:]:
        boxes += _candidate_box(r, live)
    boxes += "</div>"
    boxes += _marts_boxes()
    return boxes


def render_page() -> str:
    return _doc(friction_main(), "Cerno — friction")


# ── per-candidate drill page ─────────────────────────────────────────────────
def render_candidate_page(rank: int) -> str | None:
    c = src.candidate(rank)
    if c is None:
        return None
    live = src.data_mode() == "LIVE"
    addr = c.get("addressability", "—")
    cls = c.get("system_class", "—")
    clark = c.get("clark_tier", "—")
    accent = _CLARK_COLOR.get(clark, "var(--border)")
    star = " ★" if c.get("is_agentic") else ""

    # verdict box
    verdict = render_box(
        header=box_header(f"#{c.get('rank')} · {cls}{star}", _e(str(c.get("role_shape", "")))),
        headline=headline_stat_card(
            label="PRIORITY", value=f'{c.get("priority", 0)}',
            delta=f'risk {c.get("risk", 0):.2f}', traj=_MODE_GLYPH.get(c.get("dominant_mode", ""), ""),
            meta_left=f'{(c.get("reach_customers") or 0):,} customers · {(c.get("reach_sessions") or 0):,} sessions',
            meta_right=clark.replace("_", " "), progress_pct=int((c.get("risk", 0) or 0) * 100)),
        body=body_bars([
            ("Abandon", int((c.get("risk_abandon", 0) or 0) * 100), f'{c.get("risk_abandon", 0):.2f}', "var(--red)"),
            ("Error", int((c.get("risk_error", 0) or 0) * 100), f'{c.get("risk_error", 0):.2f}', "var(--amber)"),
            ("Loop", int((c.get("risk_loop", 0) or 0) * 100), f'{c.get("risk_loop", 0):.2f}', "var(--blue)"),
        ]) + body_chip_strip([
            (cls, "", _CLASS_COLOR.get(cls, "var(--text-3)")),
            (addr, "", _ADDR_COLOR.get(addr, "var(--text-3)")),
        ]) + body_quality_strip(["Value deferred", "Fairness deferred"], label="DEFERRED"),
        footer=box_footer("D-014", clark.replace("_", " "), live=live), accent_color=accent)

    # signature box
    sig_box = render_box(
        header=box_header("FRICTION SIGNATURE", "what's concretely happening"),
        headline="", body=f'<p class="cerno-sig">{_e(c.get("signature", ""))}</p>',
        footer=box_footer("D-014", "signature", live=live), accent_color="var(--blue)")

    # neighbourhood box
    inb = [[_e(s), f"{int(p * 100)}%", ("friction" if fr else "clean")]
           for s, p, fr in c.get("inbound", [])]
    outb = [[_e(s), f"{int(p * 100)}%"] for s, p in c.get("outbound", [])]
    nb_body = (
        _mini_table([("Inbound — precedes", False), ("%", True), ("", False)], inb)
        + '<div style="height:.6rem"></div>'
        + _mini_table([("Outbound — goes to", False), ("%", True)], outb)
        + f'<p class="cerno-note">{_e(c.get("attribution_note", ""))}</p>'
    )
    nb_box = render_box(
        header=box_header("NEIGHBOURHOOD", "raw material for cause-vs-symptom"),
        headline="", body=nb_body, footer=box_footer("D-014", "edges", live=live),
        accent_color="var(--teal)")

    # examples box
    ex = "".join(f'<code class="cerno-mono">{_e(e)}</code>' for e in c.get("examples", []))
    ex_box = render_box(
        header=box_header("EXAMPLE SESSIONS", "sanitised event_step evidence"),
        headline="", body=ex, footer=box_footer("D-014", "evidence", live=live),
        accent_color="var(--text-3)")

    # action box
    act = c.get("action", {})
    act_box = render_box(
        header=box_header(f"ACTION — {addr}", "recommended routing"),
        headline="", body=(
            body_action_primary(addr, _e(act.get("recommendation", "")), _ADDR_COLOR.get(addr, "var(--border)"))
            + f'<p class="cerno-sig" style="margin-top:.5rem">{_e(act.get("rationale", ""))}</p>'),
        footer=box_footer("D-014", clark.replace("_", " "), live=live),
        accent_color=_ADDR_COLOR.get(addr, "var(--border)"))

    back = '<div class="holter-row" data-row="cerno-back"><a class="cerno-back" href="/exploration">← Exploration</a></div>'
    grid = (back + '<div class="holter-row" data-row="cerno-detail">'
            + verdict + sig_box + nb_box + ex_box + act_box + "</div>")
    return _doc(grid, f"Cerno — candidate #{rank}")
