"""Live HTML fragments for the Pulse front-end (HOL-72).

Each fragment runs the DuckDB engine read on call and returns a small,
self-contained HTML snippet — swapped into the page by vanilla ``fetch`` when a
filter changes. No templating dependency; plain f-strings (3.11-safe). Styled
inline with the locked design's palette so it sits cleanly in the page.

The data comes from ``pulse.serving.read`` (the same DuckDB-over-Parquet read
layer the surfaces render from), so the fragment is genuinely live, not baked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from holter.preview._shared import discover_packs
from pulse.serving import read

# Design palette (subset of the locked tokens).
_FG = "#e8f4fa"
_MUTED = "#7da8c9"
_DIM = "#5b7a92"
_PANEL_BG = "#0b1f30"
_BORDER = "rgba(125,168,201,.22)"


def _tier(fire_rate: float | None) -> tuple[str, str]:
    """Map a fire-rate to a (label, colour) verdict tier."""
    if fire_rate is None:
        return "NEEDS_MORE_DATA", _MUTED
    if fire_rate >= 0.5:
        return "ACUTE", "#ff8a8a"
    if fire_rate >= 0.25:
        return "ELEVATED", "#ffcf8a"
    if fire_rate > 0:
        return "WATCH", "#9ec7e6"
    return "NOMINAL", "#34d3a6"


def _pack_target(pack_name: str) -> tuple[str, str] | None:
    """pack_name -> (screen_id, signature_id) via the pack registry."""
    for p in discover_packs():
        if p["meta"].get("pack_name") == pack_name:
            h = p.get("hypothesis") or {}
            return h.get("screen_id", ""), h.get("signature_id", "")
    return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _panel(eyebrow: str, title: str, tier: str, colour: str,
           metrics: list[tuple[str, str]], note: str) -> str:
    tiles = "".join(
        f'<div style="flex:1;min-width:108px">'
        f'<div style="font:700 26px/1 ui-monospace,SFMono-Regular,monospace;color:{_FG}">{escape(str(value))}</div>'
        f'<div style="font:600 10px/1.4 ui-sans-serif,system-ui,sans-serif;letter-spacing:.08em;'
        f'text-transform:uppercase;color:{_MUTED};margin-top:.3rem">{escape(label)}</div></div>'
        for label, value in metrics
    )
    return (
        f'<section style="background:{_PANEL_BG};border:1px solid {_BORDER};border-radius:10px;'
        f'padding:1rem 1.2rem">'
        f'<div style="display:flex;align-items:center;gap:.6rem;margin-bottom:.15rem">'
        f'<span style="font:700 11px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.1em;'
        f'text-transform:uppercase;color:{colour}">{escape(tier)}</span>'
        f'<span style="font:600 10px/1 ui-sans-serif,system-ui,sans-serif;letter-spacing:.08em;'
        f'text-transform:uppercase;color:{_MUTED}">{escape(eyebrow)}</span></div>'
        f'<div style="font:600 15px/1.3 ui-sans-serif,system-ui,sans-serif;color:{_FG};'
        f'margin-bottom:.85rem">{escape(title)}</div>'
        f'<div style="display:flex;gap:1.2rem;flex-wrap:wrap">{tiles}</div>'
        f'<div style="font:500 10px/1.4 ui-sans-serif,system-ui,sans-serif;color:{_DIM};'
        f'margin-top:.85rem">{escape(note)}</div>'
        f'</section>'
    )


def verdict_fragment(pack: str | None) -> str:
    """Live verdict panel for the selected pack — or the portfolio aggregate
    when no pack is selected. Runs the DuckDB read on every call."""
    if pack:
        target = _pack_target(pack)
        if target:
            screen_id, signature = target
            rows = [
                r for r in read.friction_by_journey()
                if r["screen_id"] == screen_id and r["signature"] == signature
            ]
            if rows:
                r = rows[0]
                fire_rate = r["fire_rate"]
                tier, colour = _tier(fire_rate)
                mc = r.get("mean_confidence")
                metrics = [
                    ("Sessions", f'{r["sessions"]:,}'),
                    ("Friction sessions", f'{r["friction_sessions"]:,}'),
                    ("Fire-rate", f'{fire_rate:.0%}' if fire_rate is not None else "—"),
                    ("Mean confidence", f'{mc:.2f}' if mc is not None else "—"),
                ]
                title = f'{r["journey"]} · {signature.replace("_", " ")}'
                note = f'pack: {pack} · LIVE · DuckDB (PULSE-127) · {_now()}'
                return _panel("verdict · live", title, tier, colour, metrics, note)
        # Pack selected but no live detection in the current mart.
        return _panel(
            "verdict · live", pack.replace("__", " · ").replace("_", " "),
            "NEEDS_MORE_DATA", _MUTED,
            [("Sessions", "0"), ("Friction sessions", "0")],
            f'No live detections for this selection · {_now()}',
        )

    # No pack selected → portfolio aggregate.
    s = read.summary()
    fire_rate = s.get("fire_rate")
    tier, colour = _tier(fire_rate)
    metrics = [
        ("Sessions", f'{s.get("total_sessions", 0):,}'),
        ("Friction sessions", f'{s.get("friction_sessions", 0):,}'),
        ("Fire-rate", f'{fire_rate:.0%}' if fire_rate is not None else "—"),
        ("Screens", s.get("screens", 0)),
        ("Journeys", s.get("journeys", 0)),
    ]
    return _panel("portfolio · live", "ALL PACKS — friction posture",
                  tier, colour, metrics,
                  f'all packs · LIVE · DuckDB (PULSE-127) · {_now()}')
