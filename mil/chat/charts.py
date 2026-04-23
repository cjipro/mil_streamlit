"""
mil/chat/charts.py — MIL-44.

Five chart templates for Ask CJI Pro answers. Each template takes
domain-shaped input and returns a Plotly figure ready for st.plotly_chart.

Templates:
    trend      — time series, multi-series line
    compare    — grouped bar, head-to-head competitors
    heatmap    — 2D matrix (competitor x issue_type)
    quote      — stylised quote card (no Plotly; returns HTML string)
    peer_rank  — sorted horizontal bar

The synthesis layer emits a chart_hint in {trend, compare, heatmap, quote, peer_rank};
the Streamlit page dispatches to the matching template with data drawn from the
evidence bundle.
"""
from __future__ import annotations

from typing import Any, Optional

_MIL_BLUE   = "#0077CC"
_MIL_ORANGE = "#FF8A00"
_MIL_RED    = "#CC3333"
_MIL_TEAL   = "#1AB0A1"
_MIL_BG     = "#001E30"
_MIL_FG     = "#E8F4FA"

_PALETTE = [_MIL_BLUE, _MIL_ORANGE, _MIL_TEAL, _MIL_RED, "#A060D0", "#D0B050"]


def _layout_defaults(title: str) -> dict:
    return {
        "title": {"text": title, "font": {"color": _MIL_FG, "size": 16}},
        "paper_bgcolor": _MIL_BG,
        "plot_bgcolor": _MIL_BG,
        "font": {"color": _MIL_FG},
        "xaxis": {"gridcolor": "#003A5C", "color": _MIL_FG},
        "yaxis": {"gridcolor": "#003A5C", "color": _MIL_FG},
        "margin": {"l": 50, "r": 30, "t": 50, "b": 40},
        "legend": {"font": {"color": _MIL_FG}},
    }


def trend(series: dict[str, list[tuple[str, float]]], *, y_label: str = "value",
          title: str = "Trend") -> "Any":
    """
    series = {"barclays": [("2026-04-01", 3.2), ("2026-04-02", 3.5), ...], "natwest": ...}
    """
    import plotly.graph_objects as go
    fig = go.Figure()
    for i, (name, points) in enumerate(series.items()):
        if not points:
            continue
        xs, ys = zip(*points)
        fig.add_trace(go.Scatter(
            x=list(xs), y=list(ys),
            mode="lines+markers",
            name=name,
            line={"color": _PALETTE[i % len(_PALETTE)], "width": 2},
        ))
    fig.update_layout(**_layout_defaults(title),
                      yaxis_title=y_label, xaxis_title="date", height=360)
    return fig


def compare(values: dict[str, float], *, y_label: str = "value",
            title: str = "Head-to-head") -> "Any":
    """
    values = {"barclays": 3.2, "natwest": 2.7, ...}
    """
    import plotly.graph_objects as go
    items = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k for k, _ in items]
    scores = [v for _, v in items]
    fig = go.Figure(go.Bar(
        x=labels, y=scores,
        marker_color=[_PALETTE[i % len(_PALETTE)] for i in range(len(labels))],
    ))
    fig.update_layout(**_layout_defaults(title),
                      yaxis_title=y_label, height=320)
    return fig


def heatmap(matrix: list[list[float]], *, x_labels: list[str], y_labels: list[str],
            title: str = "Issue heatmap") -> "Any":
    """Heat intensity for (y_label, x_label) pairs. Higher = darker red."""
    import plotly.graph_objects as go
    fig = go.Figure(go.Heatmap(
        z=matrix, x=x_labels, y=y_labels,
        colorscale=[[0, _MIL_BG], [0.5, _MIL_ORANGE], [1, _MIL_RED]],
    ))
    fig.update_layout(**_layout_defaults(title), height=360)
    return fig


def quote(text: str, *, attribution: str = "", rating: Optional[float] = None,
          severity: Optional[str] = None) -> str:
    """Return an HTML snippet for the `quote` chart hint."""
    tags: list[str] = []
    if severity:
        tags.append(f"<span style='background:{_MIL_RED};padding:2px 8px;border-radius:4px;"
                    f"color:{_MIL_FG};font-size:11px;letter-spacing:0.5px'>{severity}</span>")
    if rating is not None:
        tags.append(f"<span style='color:{_MIL_ORANGE};font-weight:600'>★ {rating:.1f}</span>")
    tag_block = " &nbsp; ".join(tags)

    body = text.replace("<", "&lt;").replace(">", "&gt;")
    attr_line = f"<div style='color:#90B0C0;font-size:12px;margin-top:8px'>{attribution}</div>" if attribution else ""
    return (
        f"<blockquote style='background:{_MIL_BG};border-left:4px solid {_MIL_BLUE};"
        f"padding:14px 18px;margin:10px 0;border-radius:4px;color:{_MIL_FG};"
        f"font-style:italic;font-size:14px;line-height:1.5'>"
        f"<div style='margin-bottom:6px'>{tag_block}</div>"
        f"“{body}”{attr_line}"
        f"</blockquote>"
    )


def peer_rank(items: list[tuple[str, float]], *, y_label: str = "score",
              title: str = "Peer ranking") -> "Any":
    """items = [("revolut", 1.0), ("monzo", 1.5), ...] — ordered as supplied."""
    import plotly.graph_objects as go
    items = list(items)
    labels = [k for k, _ in items]
    scores = [v for _, v in items]
    fig = go.Figure(go.Bar(
        x=scores, y=labels,
        orientation="h",
        marker_color=[_PALETTE[i % len(_PALETTE)] for i in range(len(labels))],
    ))
    fig.update_layout(**_layout_defaults(title),
                      xaxis_title=y_label,
                      yaxis={"autorange": "reversed", "color": _MIL_FG, "gridcolor": "#003A5C"},
                      height=max(280, 40 * len(items) + 100))
    return fig


# ── Dispatcher used by the /ask page ──────────────────────────────────────
# Picks the template matching the synthesis chart_hint. If no hint, returns None.

TEMPLATES = {
    "trend":     trend,
    "compare":   compare,
    "heatmap":   heatmap,
    "quote":     quote,
    "peer_rank": peer_rank,
}


def render(hint: Optional[str], data: dict) -> Any:
    """Render by chart_hint. `data` must match the chosen template's signature."""
    if not hint or hint not in TEMPLATES:
        return None
    return TEMPLATES[hint](**data)
