"""
hodos_kernel.surface — config-driven Holter-style surface (HODOS-4 spike).

Renders a decision product to a single HTML page from the manifest `surface:`
block. Laptop-first, fixed-size cells, news-portal-ish (the locked Holter UI
model) — generated from config, not hand-built per product. One card per
decision: verdict-coloured, with the recommended action, the narrative (from the
selected runtime), and the evidence. A lineage badge shows the DecisionLog hash.
"""
from __future__ import annotations

from html import escape
from typing import Any

from hodos_kernel.decision import Decision, DecisionLog

_VERDICT_COLOR = {"ACT": "#c0392b", "WATCH": "#b9770e", "IGNORE": "#1e8449"}

_CSS = """
*{box-sizing:border-box} body{margin:0;background:#0f1720;color:#e8eef4;
font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:14px}
.top{padding:16px 24px;border-bottom:2px solid #1f2d3a;display:flex;
align-items:baseline;gap:16px;flex-wrap:wrap}
.top h1{margin:0;font-size:20px;letter-spacing:.3px}
.badge{font-size:12px;padding:2px 8px;border-radius:10px;background:#1f2d3a;color:#9fb3c8}
.badge.run{background:#10202e;color:#7fd1c2}
.badge.ok{background:#10261a;color:#5fd08a}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
gap:14px;padding:20px 24px;align-items:start}
.card{background:#14202c;border:1px solid #223344;border-radius:10px;padding:14px 16px;
min-height:150px}
.v{display:inline-block;font-weight:700;font-size:12px;padding:2px 8px;border-radius:6px;color:#fff}
.subj{font-size:15px;font-weight:600;margin:8px 0 2px}
.score{float:right;font-family:ui-monospace,monospace;color:#9fb3c8}
.act{margin:8px 0;color:#cfe0ee}
.narr{margin:8px 0;color:#aebfce;font-style:italic;border-left:2px solid #2a3b4c;padding-left:8px}
.ev{margin-top:8px;font-size:12px;color:#7f93a6;font-family:ui-monospace,monospace}
.altis{color:#6f8398;font-size:12px}
"""


def render(product_title: str, runtime: str, decisions: list[Decision],
           log: DecisionLog, surface_cfg: dict[str, Any]) -> str:
    altitudes = " · ".join(surface_cfg.get("altitudes", []))
    chain_ok = log.verify()
    head_hash = log.rows[-1]["row_hash"][:12] if log.rows else "—"

    cards = []
    for d in decisions:
        color = _VERDICT_COLOR.get(d.verdict, "#555")
        ev = escape(", ".join(f"{k}={v}" for k, v in d.inputs["signals_by_type"].items())) or "—"
        cards.append(f"""
        <div class="card">
          <span class="v" style="background:{color}">{escape(d.verdict)}</span>
          <span class="score">score {d.score:g}</span>
          <div class="subj">{escape(d.subject)}</div>
          <div class="act">{escape(d.recommended_action)}</div>
          <div class="narr">{escape(d.narrative)}</div>
          <div class="ev">{d.inputs['entity_count']} affected · {ev}</div>
        </div>""")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{escape(product_title)}</title><style>{_CSS}</style></head><body>
<div class="top">
  <h1>{escape(product_title)}</h1>
  <span class="badge run">runtime: {escape(runtime)}</span>
  <span class="badge">{len(decisions)} decisions</span>
  <span class="badge {'ok' if chain_ok else ''}">lineage {'verified' if chain_ok else 'BROKEN'} · {head_hash}</span>
  <span class="altis">{escape(altitudes)}</span>
</div>
<div class="grid">{''.join(cards)}</div>
</body></html>"""
