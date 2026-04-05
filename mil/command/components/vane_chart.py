"""
vane_chart.py — MIL-12 Vane Trajectory Chart component.

Renders a 14-day sentiment trajectory line chart for all monitored competitors.
Computed directly from enriched app_store + google_play records (the 'at' field).
Barclays (brand competitor) is visually separated.

Data source: mil/data/historical/enriched/*_enriched.json
Chart engine: Plotly (dark theme to match command dashboard)

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIL_ROOT     = Path(__file__).parent.parent.parent
ENRICHED_DIR = MIL_ROOT / "data" / "historical" / "enriched"

# Competitors — display order, Barclays last (brand = special treatment)
COMPETITORS = ["natwest", "lloyds", "monzo", "revolut", "barclays"]

COMP_LABELS = {
    "natwest":  "NatWest",
    "lloyds":   "Lloyds",
    "monzo":    "Monzo",
    "revolut":  "Revolut",
    "barclays": "Barclays",
}

# Colour palette — matches command dashboard CSS vars
COMP_COLOURS = {
    "natwest":  "#F5A623",   # amber
    "lloyds":   "#00AFA0",   # teal
    "monzo":    "#7B5EA7",   # purple
    "revolut":  "#4A9BD4",   # mid-blue
    "barclays": "#00AEEF",   # brand blue (emphasis)
}

# Min daily records to plot a point — avoids noise from single reviews
MIN_DAILY_N = 3

# Chart styling
BG_COLOUR   = "#00273D"
GRID_COLOUR = "#003A5C"
TEXT_COLOUR = "#7AACBF"
PAPER_BG    = "#001828"


# ─────────────────────────────────────────────────────────────────────────────
# Data layer
# ─────────────────────────────────────────────────────────────────────────────

def build_vane_data(window_days: int = 14) -> dict[str, dict[str, Optional[float]]]:
    """
    Build daily sentiment scores per competitor over the last `window_days`.

    Returns:
        {
          "natwest":  {"2026-03-22": 68.0, "2026-03-23": None, ...},
          "barclays": {"2026-03-22": 90.0, ...},
          ...
        }
    None means no qualifying data for that day (gap in line).
    """
    cutoff = date.today() - timedelta(days=window_days)
    all_dates = [
        (date.today() - timedelta(days=i)).isoformat()
        for i in range(window_days - 1, -1, -1)
    ]

    # Accumulate: competitor -> day -> [ratings]
    daily: dict[str, dict[str, list[int]]] = {c: defaultdict(list) for c in COMPETITORS}

    for enriched_file in ENRICHED_DIR.glob("*.json"):
        fname = enriched_file.stem  # e.g. google_play_barclays_enriched
        competitor = None
        for comp in COMPETITORS:
            if fname.endswith(f"_{comp}_enriched") or f"_{comp}_" in fname:
                competitor = comp
                break
        if competitor is None:
            continue

        # Only app_store and google_play for ratings (other sources lack star ratings)
        if not (fname.startswith("app_store") or fname.startswith("google_play")):
            continue

        try:
            payload = json.loads(enriched_file.read_text(encoding="utf-8"))
            records = payload.get("records", [])
        except Exception as exc:
            logger.warning("[vane_chart] failed to read %s: %s", enriched_file.name, exc)
            continue

        for r in records:
            at = r.get("at") or r.get("date") or ""
            if not at:
                continue
            day = str(at)[:10]
            if day < cutoff.isoformat():
                continue
            rating = r.get("rating")
            if rating and isinstance(rating, (int, float)):
                daily[competitor][day].append(int(rating))

    # Convert raw ratings to sentiment scores (avg_rating × 20 → 0-100)
    result: dict[str, dict[str, Optional[float]]] = {}
    for comp in COMPETITORS:
        series: dict[str, Optional[float]] = {}
        for day in all_dates:
            ratings = daily[comp].get(day, [])
            if len(ratings) >= MIN_DAILY_N:
                series[day] = round(sum(ratings) / len(ratings) * 20, 1)
            else:
                series[day] = None
        result[comp] = series

    return result


def _daily_n(competitor: str, window_days: int = 14) -> dict[str, int]:
    """Return daily record count per competitor (for tooltips)."""
    cutoff = date.today() - timedelta(days=window_days)
    counts: dict[str, int] = defaultdict(int)

    for enriched_file in ENRICHED_DIR.glob("*.json"):
        fname = enriched_file.stem
        if not (fname.endswith(f"_{competitor}_enriched") or f"_{competitor}_" in fname):
            continue
        if not (fname.startswith("app_store") or fname.startswith("google_play")):
            continue
        try:
            payload = json.loads(enriched_file.read_text(encoding="utf-8"))
            for r in payload.get("records", []):
                at = r.get("at") or r.get("date") or ""
                day = str(at)[:10] if at else ""
                if day and day >= cutoff.isoformat() and r.get("rating"):
                    counts[day] += 1
        except Exception:
            continue
    return dict(counts)


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit render function
# ─────────────────────────────────────────────────────────────────────────────

def render_vane_chart(window_days: int = 14) -> None:
    """
    Render the Vane Trajectory Chart into the active Streamlit context.
    Plots 14-day daily sentiment for all competitors.
    Barclays shown with thick line + fill; competitors shown as thinner lines.
    """
    try:
        import plotly.graph_objects as go
        import streamlit as st
    except ImportError as exc:
        import streamlit as st
        st.warning(f"[vane_chart] missing dependency: {exc}")
        return

    vane_data = build_vane_data(window_days)
    all_dates = sorted(next(iter(vane_data.values())).keys()) if vane_data else []

    if not all_dates:
        import streamlit as st
        st.info("No trajectory data available yet.")
        return

    # Format x-axis labels: "Apr 01"
    x_labels = [
        datetime.strptime(d, "%Y-%m-%d").strftime("%b %d")
        for d in all_dates
    ]

    fig = go.Figure()

    # --- Competitors (not Barclays) ---
    for comp in [c for c in COMPETITORS if c != "barclays"]:
        series = vane_data.get(comp, {})
        y_vals = [series.get(d) for d in all_dates]
        n_counts = _daily_n(comp, window_days)
        hover = [
            f"<b>{COMP_LABELS[comp]}</b><br>Score: {v:.0f}<br>n={n_counts.get(d, 0)}"
            if v is not None else ""
            for d, v in zip(all_dates, y_vals)
        ]

        # Split into segments at None gaps so lines break cleanly
        fig.add_trace(go.Scatter(
            x=x_labels,
            y=y_vals,
            name=COMP_LABELS[comp],
            mode="lines+markers",
            line=dict(color=COMP_COLOURS[comp], width=1.5, dash="dot"),
            marker=dict(size=4, color=COMP_COLOURS[comp]),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
            connectgaps=False,
            opacity=0.75,
        ))

    # --- Barclays (brand) — prominent line ---
    barcl_series = vane_data.get("barclays", {})
    y_barcl = [barcl_series.get(d) for d in all_dates]
    n_barcl = _daily_n("barclays", window_days)
    hover_barcl = [
        f"<b>Barclays</b><br>Score: {v:.0f}<br>n={n_barcl.get(d, 0)}"
        if v is not None else ""
        for d, v in zip(all_dates, y_barcl)
    ]

    # Filled area under Barclays line
    fig.add_trace(go.Scatter(
        x=x_labels,
        y=y_barcl,
        name="Barclays",
        mode="lines+markers",
        line=dict(color=COMP_COLOURS["barclays"], width=3),
        marker=dict(size=6, color=COMP_COLOURS["barclays"]),
        fill="tozeroy",
        fillcolor="rgba(0,174,239,0.06)",
        hovertemplate="%{customdata}<extra></extra>",
        customdata=hover_barcl,
        connectgaps=False,
    ))

    # --- Baseline reference line ---
    fig.add_hline(
        y=75,
        line_dash="dash",
        line_color=GRID_COLOUR,
        line_width=1,
        annotation_text="75 floor",
        annotation_font_color=TEXT_COLOUR,
        annotation_font_size=10,
        annotation_position="right",
    )

    fig.update_layout(
        paper_bgcolor=PAPER_BG,
        plot_bgcolor=BG_COLOUR,
        font=dict(family="DM Mono, monospace", color=TEXT_COLOUR, size=11),
        margin=dict(l=40, r=20, t=36, b=36),
        height=260,
        title=dict(
            text="VANE — 14-DAY SENTIMENT TRAJECTORY",
            font=dict(size=11, color=TEXT_COLOUR),
            x=0,
            xanchor="left",
            pad=dict(l=0, t=0),
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(size=10, color=TEXT_COLOUR),
            tickangle=0,
            nticks=7,
        ),
        yaxis=dict(
            range=[0, 105],
            showgrid=True,
            gridcolor=GRID_COLOUR,
            gridwidth=0.5,
            zeroline=False,
            tickfont=dict(size=10, color=TEXT_COLOUR),
            ticksuffix="",
            dtick=25,
        ),
        legend=dict(
            orientation="h",
            y=-0.18,
            x=0,
            font=dict(size=10, color=TEXT_COLOUR),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
        ),
        hovermode="x unified",
    )

    import streamlit as st
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Vane trajectory data (14 days)\n")
    data = build_vane_data()
    for comp, series in data.items():
        filled = {d: v for d, v in series.items() if v is not None}
        if filled:
            latest_day = max(filled)
            latest_score = filled[latest_day]
            print(f"  {comp:<12} {len(filled):>2} days data | latest {latest_day}: {latest_score:.0f}")
        else:
            print(f"  {comp:<12}  0 days data")
