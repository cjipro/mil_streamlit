"""Render decision packs in the MIL Sonar V4 briefing template.

Per direction 2026-05-18: "follow MIL briefing template — use the EXACT same
template." This drops Streamlit and outputs static HTML matching the MIL Sonar
V4 layout (cjipro/mil_streamlit → mil/publish/output/index_v4.html), with
content sections re-keyed for Pulse decision packs:

  MIL Sonar concept               Pulse mapping
  ──────────────────────────────  ─────────────────────────────────────
  real_bank Sentiment score       Pack coverage score (12/12 cells)
  Quote cards                     Bank-altitude headlines from packs
  Issues Status box               Cell ground-truth distribution
  Journey list                    4 friction-target screens
  Intelligence Brief (Box 3)      Selected pack's Bank altitude
  Sentiment ticker                Pack lineage anchor ticker
  Journey Row                     4 friction-target screens with detection rate
  Journey cards (left col)        Per-pack cards ranked by severity
  Chronicle Failure Library       FrictionBench cell catalogue
  Active Inferences               Selected pack's hypothesis
  Signal Sources                  Cohort axes for selected pack
  Churn Risk Score                Friction risk score across packs
  Analyst Commentary              Per-pack risk/strength commentary
  Technical/Service Benchmark     FrictionBench cell scoring
  Intelligence Findings           Signal-altitude per-session evidence
  Clark Protocol                  Confidence tier tiles

CSS variables and class names are kept identical to the MIL template so the
visual treatment stays canonical.

Run with: py holter/preview/render_mil_briefing.py
Output:  dist/preview/index.html
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
PACKS_DIR = REPO / "pulse" / "decision_packs"
JOURNEY_TAXONOMY = REPO / "pulse" / "contracts" / "journey_taxonomy.yaml"
OUT_DIR = REPO / "dist" / "preview"

# Make `pulse.*` importable when this script is run directly
# (mirrors the same setup in serve_briefing.py). Pre-HOL-11 the
# renderer only needed file-path access to pulse/decision_packs/;
# HOL-11 added engine-module imports for the placement matrix.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def load_journey_taxonomy() -> dict[str, str]:
    """Returns {journey_id: category} from pulse/contracts/journey_taxonomy.yaml."""
    if not JOURNEY_TAXONOMY.exists():
        return {}
    data = yaml.safe_load(JOURNEY_TAXONOMY.read_text(encoding="utf-8"))
    return data.get("journeys", {})


# ─────────────────────────────────────────────────────────────────────────────
# Load packs
# ─────────────────────────────────────────────────────────────────────────────

def discover_packs() -> list[dict]:
    packs: list[dict] = []
    if not PACKS_DIR.exists():
        return packs
    for pack_dir in sorted(PACKS_DIR.iterdir()):
        if not pack_dir.is_dir():
            continue
        meta_path = pack_dir / "metadata.yaml"
        samples_dir = pack_dir / "samples"
        hyp_path = pack_dir / "hypothesis.yaml"
        if not meta_path.exists() or not samples_dir.exists():
            continue
        raw_bytes = meta_path.read_bytes()
        meta = yaml.safe_load(raw_bytes.decode("utf-8"))
        hypothesis = (
            yaml.safe_load(hyp_path.read_text(encoding="utf-8"))
            if hyp_path.exists() else None
        )
        bank_md = (samples_dir / "bank.md").read_text(encoding="utf-8") \
            if (samples_dir / "bank.md").exists() else ""
        packs.append({
            "dir": pack_dir,
            "meta": meta,
            "meta_raw": raw_bytes.decode("utf-8"),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "hypothesis": hypothesis,
            "bank_md": bank_md,
        })
    return packs


def short_hash(h: str) -> str:
    return f"{h[:12]}…{h[-4:]}"


def headline_pack(packs: list[dict]) -> dict:
    """Pick a load-bearing pack for the top-of-page briefing. Prefer the
    cell-10 negative if present (regulator-defensible discriminator); else
    the cards abandonment (largest opportunity cost in current samples)."""
    for p in packs:
        h = p["hypothesis"] or {}
        if h.get("cell_id") == 10:
            return p
    for p in packs:
        if "abandon_before_submit" in p["meta"]["pack_name"] and "cards" in p["meta"]["pack_name"]:
            return p
    return packs[0]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers for HTML fragments
# ─────────────────────────────────────────────────────────────────────────────

def screen_short(screen_id: str) -> str:
    """`loans.apply.step3` → `loans · step3` for compact display."""
    parts = screen_id.split(".")
    if len(parts) >= 2:
        return f"{parts[0]} · {parts[-1]}"
    return screen_id


def pack_severity(pack: dict) -> tuple[str, str, str]:
    """Return (badge_label, css_color_var, border_color)."""
    h = pack["hypothesis"] or {}
    gt = h.get("ground_truth_expectation", "positive")
    if gt == "negative":
        return ("NEGATIVE · LOAD-BEARING", "var(--amber)", "var(--amber)")
    return ("POSITIVE", "var(--red)", "var(--red)")


def cell_screens_with_counts(packs: list[dict]) -> list[dict]:
    """Aggregate detection counts by friction-target screen for the journey row."""
    screens: dict[str, list[dict]] = {}
    for p in packs:
        h = p["hypothesis"] or {}
        sc = h.get("screen_id")
        if not sc:
            continue
        screens.setdefault(sc, []).append(p)
    out = []
    for sc, ps in screens.items():
        positives = sum(1 for p in ps if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
        negatives = sum(1 for p in ps if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative")
        out.append({
            "screen": sc,
            "short": screen_short(sc),
            "packs": ps,
            "positives": positives,
            "negatives": negatives,
            "total": len(ps),
            "status": "ACUTE" if positives >= 3 else ("LOAD-BEARING" if negatives else "STABLE"),
            "status_color": "var(--red)" if positives >= 3 else (
                "var(--amber)" if negatives else "var(--teal)"
            ),
        })
    return out


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
:root {
  --bg: #00273D; --topbar-bg: #001E30; --ticker-bg: #001828; --journey-bg: #001E30;
  --summary-bg: #002030; --feed-bg: #00273D; --panel-bg: #001828; --card: #002A3F;
  --border: #003A5C; --blue: #00AEEF; --teal: #00AFA0; --amber: #F5A623;
  --red: #CC0000; --green: #2a9a5a;
  --text: #E8F4FA; --text-2: #7AACBF; --text-3: #4A7A8F; --muted: #3A6A7F;
  --mono: 'DM Mono', 'JetBrains Mono', monospace;
  --sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: var(--bg); color: var(--text); font-family: var(--sans);
  font-size: 14px; line-height: 1.5; min-height: 100vh;
}
a { color: var(--blue); text-decoration: none; }

/* ── App top nav ────────────────────────────────────────────────
   Global chrome: CJI Pulse brand + canvas-header dropdowns + utility cluster.
   Sticky at top:0; topbar below it sticks at top:48px so both stay visible. */
.app-topnav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 48px;
  background: #000810;
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; z-index: 110;
  min-width: 0;
}
.topnav-brand { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
.brand-logo {
  font-family: var(--sans); font-weight: 800; font-size: 18px;
  letter-spacing: 2.5px; color: var(--blue); text-transform: uppercase;
  white-space: nowrap;
}
.brand-tagline {
  font-family: var(--mono); font-size: 10.5px; color: var(--text-3);
  letter-spacing: 1.2px; text-transform: uppercase; white-space: nowrap;
}
.topnav-controls { display: flex; gap: 6px; align-items: center; min-width: 0; }
.topnav-select {
  background: transparent;
  border: 1px solid var(--border); border-radius: 4px;
  padding: 4px 22px 4px 10px;
  font-family: var(--mono); font-size: 11px; color: var(--text-3);
  min-width: 130px; appearance: none;
  background-image: url("data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 14 8' fill='%234A7A8F'><path d='M0 0l7 8 7-8z'/></svg>");
  background-repeat: no-repeat; background-position: right 8px center;
  background-size: 8px 6px; cursor: not-allowed; opacity: 0.7;
}
.topnav-select.active {
  cursor: pointer; opacity: 1;
  color: var(--blue);
  border-color: rgba(0,174,239,0.35);
  background-image: url("data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 14 8' fill='%2300AEEF'><path d='M0 0l7 8 7-8z'/></svg>");
}
.topnav-select.active:hover { border-color: var(--blue); color: var(--text); }
.topnav-select.active:focus { outline: none; border-color: var(--blue); color: var(--text); }
.topnav-select.active.filter-on {
  border-color: var(--amber);
  color: var(--amber);
  background-image: url("data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 14 8' fill='%23F5A623'><path d='M0 0l7 8 7-8z'/></svg>");
}
.topnav-reset {
  background: transparent;
  border: 1px solid var(--border); border-radius: 4px;
  padding: 4px 10px;
  font-family: var(--mono); font-size: 11px;
  color: var(--text-3);
  cursor: pointer; text-transform: uppercase; letter-spacing: 0.8px;
  margin-left: 4px;
}
.topnav-reset:hover { color: var(--text); border-color: var(--text-3); }
.topnav-reset.active {
  color: var(--amber); border-color: var(--amber);
}

/* ── Search overlay (HOL-10 phase 2) ─────────────────────────── */
.search-overlay {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 8, 16, 0.82);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  align-items: flex-start;
  justify-content: center;
  padding-top: 96px;
}
.search-overlay.open { display: flex; }
.search-modal {
  width: 640px;
  max-width: 92vw;
  background: var(--panel-bg);
  border: 1px solid var(--blue);
  border-radius: 8px;
  box-shadow: 0 8px 40px rgba(0, 174, 239, 0.25);
  max-height: 70vh;
  display: flex;
  flex-direction: column;
}
.search-modal-head {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}
.search-input {
  width: 100%;
  background: transparent;
  border: none;
  color: var(--text);
  font-family: var(--mono);
  font-size: 16px;
  outline: none;
  padding: 0;
}
.search-input::placeholder { color: var(--text-3); }
.search-meta {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  margin-top: 8px;
  letter-spacing: 0.6px;
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.search-hint-keys {
  display: inline-block;
  padding: 1px 5px;
  font-family: var(--mono);
  font-size: 10px;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--text-2);
  margin-right: 4px;
}
.search-results {
  overflow-y: auto;
  flex: 1;
  min-height: 80px;
}
.search-result {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto;
  gap: 12px;
  padding: 10px 18px;
  border-bottom: 1px solid #001E30;
  cursor: pointer;
  align-items: center;
}
.search-result:last-child { border-bottom: none; }
.search-result:hover, .search-result.active { background: #002030; }
.search-result.active { border-left: 3px solid var(--blue); padding-left: 15px; }
.search-result-cell {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-3);
  letter-spacing: 0.5px;
}
.search-result-title {
  font-family: var(--mono);
  font-size: 13px;
  color: var(--text);
  word-break: break-word;
}
.search-result-title mark {
  background: rgba(245, 166, 35, 0.25);
  color: var(--amber);
  padding: 0 2px;
  border-radius: 2px;
}
.search-result-screen {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--text-2);
  margin-top: 2px;
  word-break: break-word;
}
.search-result-screen mark {
  background: rgba(245, 166, 35, 0.25);
  color: var(--amber);
}
.search-result-badge {
  font-family: var(--mono);
  font-size: 9px;
  letter-spacing: 0.5px;
  padding: 2px 7px;
  border-radius: 3px;
  font-weight: 700;
}
.search-result-badge.positive { color: var(--red); border: 1px solid rgba(204,0,0,0.5); background: rgba(204,0,0,0.08); }
.search-result-badge.negative { color: var(--amber); border: 1px solid var(--amber); background: rgba(245,166,35,0.08); }
.search-no-results {
  padding: 24px 18px;
  text-align: center;
  color: var(--text-3);
  font-family: var(--mono);
  font-size: 12px;
  font-style: italic;
}

/* Pack-card flash on jump-to */
@keyframes pack-flash {
  0%   { box-shadow: 0 0 0 0 rgba(0, 174, 239, 0); }
  15%  { box-shadow: 0 0 0 4px rgba(0, 174, 239, 0.55); }
  100% { box-shadow: 0 0 0 0 rgba(0, 174, 239, 0); }
}
.pack-card.flash { animation: pack-flash 1.8s ease-out; }
.topnav-select-label {
  font-family: var(--mono); font-size: 9px; color: var(--text-3);
  text-transform: uppercase; letter-spacing: 0.8px; margin-right: 4px;
}
.topnav-control-group { display: flex; align-items: center; gap: 2px; }
.topnav-utility { display: flex; gap: 12px; align-items: center; flex-shrink: 0; }
.topnav-icon {
  font-family: var(--mono); font-size: 14px; color: var(--text-3);
  cursor: pointer; padding: 4px 8px; border-radius: 4px;
  display: inline-flex; align-items: center; gap: 4px;
}
.topnav-icon:hover { color: var(--text); background: var(--card); }
.topnav-icon-badge {
  background: var(--red); color: #fff; border-radius: 8px;
  font-size: 9px; padding: 0 5px; font-weight: 700;
  min-width: 14px; text-align: center;
}
.topnav-avatar {
  font-family: var(--mono); font-size: 11px; font-weight: 700;
  color: var(--bg); background: var(--amber);
  width: 30px; height: 30px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
}
.topnav-divider {
  width: 1px; height: 22px; background: var(--border); margin: 0 4px;
}

/* HOL-10 phase 3 — utility-cluster panels (notifications / canvas guide /
   settings / avatar menu). Buttons get default-button reset; panels are
   fixed-positioned under the topnav with right-anchoring per panel.
   ──────────────────────────────────────────────────────────────────── */
button.topnav-icon, button.topnav-avatar {
  background: transparent; border: 0; font-family: var(--mono); cursor: pointer;
  color: inherit;
}
button.topnav-icon { padding: 4px 8px; }
button.topnav-icon:focus-visible, button.topnav-avatar:focus-visible {
  outline: 1px solid var(--blue); outline-offset: 1px;
}
.topnav-icon.panel-open { color: var(--blue); background: var(--card); }
.topnav-avatar.panel-open { box-shadow: 0 0 0 2px var(--blue); }

.topnav-popover {
  position: fixed; top: 48px; z-index: 1500;
  width: 360px; max-height: calc(100vh - 60px); overflow-y: auto;
  background: var(--bg); border: 1px solid var(--border);
  box-shadow: 0 8px 24px rgba(0,0,0,0.6);
  font-family: var(--sans); color: var(--text);
}
.topnav-popover-narrow { width: 280px; }
.topnav-popover[hidden] { display: none; }

.topnav-drawer {
  position: fixed; top: 48px; right: 0; z-index: 1500;
  width: 440px; height: calc(100vh - 48px); overflow-y: auto;
  background: var(--bg); border-left: 1px solid var(--border);
  box-shadow: -8px 0 24px rgba(0,0,0,0.6);
  font-family: var(--sans); color: var(--text);
}
.topnav-drawer[hidden] { display: none; }

.topnav-panel-header {
  display: flex; flex-direction: column; gap: 2px;
  padding: 12px 16px; background: #001828;
  border-bottom: 1px solid var(--border);
}
.topnav-panel-title {
  font-size: 11px; font-weight: 700; color: var(--blue);
  letter-spacing: 1.5px; text-transform: uppercase;
}
.topnav-panel-sub { font-size: 10px; color: #5A7E92; }
.topnav-panel-body { padding: 8px 0; }
.topnav-panel-footer {
  padding: 10px 16px; border-top: 1px solid var(--border);
  font-size: 10px; color: #5A7E92; line-height: 1.5; background: #001020;
}

.topnav-panel-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 16px; border-bottom: 1px solid #001828;
  transition: background 0.15s;
}
.topnav-panel-item:hover { background: #001828; }
.topnav-panel-item:last-child { border-bottom: 0; }
.topnav-panel-dot {
  width: 8px; height: 8px; border-radius: 50%;
  margin-top: 5px; flex-shrink: 0;
}
.topnav-panel-item-body { flex: 1; min-width: 0; }
.topnav-panel-item-title {
  font-size: 12px; font-weight: 600; color: var(--text);
  margin-bottom: 3px;
}
.topnav-panel-item-detail {
  font-size: 10px; color: #A8CDDE; line-height: 1.4;
}
.topnav-panel-item-ago {
  font-size: 9px; color: #5A7E92; flex-shrink: 0;
  font-family: var(--mono);
}

/* Canvas-guide drawer specifics */
.guide-section { padding: 12px 16px; }
.guide-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  margin-bottom: 4px;
}
.guide-meta { font-size: 10px; color: #5A7E92; margin-bottom: 8px; }
.guide-list {
  list-style: none; padding: 0; margin: 0;
  font-size: 11px; color: #A8CDDE; line-height: 1.7;
}
.guide-list li { padding-left: 12px; position: relative; }
.guide-list li::before {
  content: "·"; position: absolute; left: 0; color: var(--text-3);
}
.guide-list code {
  color: var(--text); font-family: var(--mono); font-size: 10px;
}
.guide-flow {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin: 8px 0;
}
.guide-flow-step {
  display: inline-block; padding: 4px 8px;
  font-family: var(--mono); font-size: 9px; font-weight: 700;
  letter-spacing: 0.5px; background: #001020;
  border: 1px solid; border-radius: 2px;
}
.guide-flow-arrow { color: var(--text-3); font-size: 12px; }

/* Settings panel specifics */
.settings-section {
  padding: 12px 16px; border-bottom: 1px solid #001828;
}
.settings-section:last-child { border-bottom: 0; }
.settings-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  color: var(--text-3); margin-bottom: 10px;
}
.settings-toggle {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0; cursor: pointer;
}
.settings-toggle-input { cursor: pointer; }
.settings-toggle-label { font-size: 11px; color: var(--text); }
.settings-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; padding: 4px 0; color: #A8CDDE;
}
.settings-row code {
  color: var(--blue); font-family: var(--mono); font-size: 10px;
}

/* Avatar menu specifics */
.avatar-section {
  padding: 12px 16px; border-bottom: 1px solid #001828;
}
.avatar-section:last-child { border-bottom: 0; }
.avatar-label {
  font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
  color: var(--text-3); margin-bottom: 8px;
}
.avatar-link {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0; font-size: 11px; color: var(--text);
  text-decoration: none; transition: color 0.15s;
}
.avatar-link:hover { color: var(--blue); }
.avatar-link-bullet {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}
.avatar-link-arrow {
  margin-left: auto; color: var(--text-3); font-size: 10px;
}
.avatar-row {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px; padding: 3px 0; color: var(--text);
}
.avatar-row code {
  color: var(--blue); font-family: var(--mono); font-size: 10px;
}
.avatar-row span {
  color: #5A7E92; font-size: 10px;
}

/* Settings toggles drive page-state classes — targets V3 panels via the
   data-panel-id markers added to render_value_scoring_panel /
   render_risk_scoring_panel / render_placement_matrix. */
body.hide-v3-scoring [data-panel-id="value-scoring"],
body.hide-v3-scoring [data-panel-id="risk-scoring"] { display: none; }
body.hide-pack-badges .pack-tier-badges { display: none !important; }
body.hide-placement-matrix [data-panel-id="placement-matrix"] { display: none; }

/* topbar — Box0 is the first column (168px), then Box1/2/3 (1fr each).
   align-items: stretch on the grid + height: auto on boxes = all 4 share
   the row's tallest box's height. Sticky at top:48px to clear the topnav. */
.topbar {
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  padding: 16px 24px; background: var(--topbar-bg);
  border-bottom: 1px solid var(--border); position: sticky; top: 48px; z-index: 100;
  align-items: stretch;
  min-width: 0;
}
.topbar > * { min-width: 0; }
.topbar-box, .topbar-box-body, .topbar-box-header, .topbar-box-body * {
  min-width: 0;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.topbar-box { background: #002A3F; border: 1px solid #003A5C; border-radius: 12px;
              overflow: hidden; display: flex; flex-direction: column; }
.topbar-box-header { padding: 10px 16px; border-bottom: 1px solid #003A5C;
                     display: flex; align-items: center; justify-content: space-between; }
.topbar-box-title { font-size: 13px; font-weight: 700; letter-spacing: 2px;
                    text-transform: uppercase; color: var(--text-2); }
.topbar-box-body { padding: 14px 16px; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.topbar-logo { font-weight: 800; font-size: 17px; letter-spacing: 1.5px;
               color: var(--blue); margin-bottom: 2px; }

/* Box 1: brand + score card */
.topbar-sent-card { background: #002A3F; border: 1px solid #00AEEF; border-radius: 8px;
                    overflow: hidden; }
.sent-card-bar { height: 2px; background: linear-gradient(90deg, #00AEEF, #0080C0); }
.sent-card-inner { padding: 8px 14px; display: flex; flex-direction: column; gap: 3px; }
.sent-row-1 { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.sent-row-2 { display: flex; align-items: center; justify-content: space-between; }
.sent-card-label { font-size: 15px; font-weight: 700; letter-spacing: 2px;
                   color: #00AEEF; text-transform: uppercase; flex-shrink: 0; }
.sent-card-score { font-family: var(--mono); font-size: 36px; font-weight: 800;
                   color: #E8F4FA; line-height: 1; }
.sent-card-delta { font-family: var(--mono); font-size: 16px; font-weight: 600; }
.sent-card-traj { font-size: 10px; font-weight: 700; margin-left: auto; }
.sent-card-baseline { font-family: var(--mono); font-size: 10px; color: #4A7A8F; }
.sent-card-progress { height: 2px; background: #003A5C; border-radius: 1px; margin-top: 3px; }
.sent-progress-fill { height: 2px; background: linear-gradient(90deg, #00AEEF, #0080C0); }
.sent-card-ts { font-family: var(--mono); font-size: 10px; color: #3A6A7F; }
.brand-line { display: flex; align-items: flex-start; gap: 7px; font-size: 15px;
              font-weight: 400; color: var(--text-2); line-height: 1.4; }
.brand-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; margin-top: 3px; }
.brand-dot-blue { background: #00AEEF; box-shadow: 0 0 4px rgba(0,174,239,0.5); }
.brand-dot-teal { background: #00AFA0; box-shadow: 0 0 4px rgba(0,175,160,0.5); }
.topbar-pills { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 3px; }
.version-pill { font-family: var(--mono); font-size: 12px; color: var(--text-3);
                background: var(--card); border: 1px solid var(--border);
                padding: 2px 8px; border-radius: 4px; }
.live-dot { display: inline-flex; align-items: center; gap: 6px; font-size: 11px;
            color: var(--teal); font-weight: 600; letter-spacing: 0.05em; }
.live-dot::before { content: ''; width: 7px; height: 7px; background: var(--teal);
                    border-radius: 50%; animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

/* Box 2: pack status */
.issues-stat-row { display: flex; align-items: center; gap: 12px; }
.issues-stat-num { font-family: var(--mono); font-size: 40px; font-weight: 800;
                   line-height: 1; min-width: 52px; }
.issues-stat-label { font-size: 12px; font-weight: 700; letter-spacing: 1.5px;
                     color: var(--text-3); text-transform: uppercase; }
.issues-stat-sub { font-size: 13px; color: var(--text-2); margin-top: 2px; }
.issues-divider { height: 1px; background: #003A5C; margin: 4px 0; }
.journey-list-item { display: flex; align-items: center; justify-content: space-between;
                     padding: 5px 0; border-bottom: 1px solid #001E30; font-size: 14px; }
.journey-list-item:last-child { border-bottom: none; }
.journey-list-name { color: #7AACBF; font-weight: 600; }
.journey-list-right { display: flex; align-items: center; gap: 6px; }
.journey-list-score { font-family: var(--mono); font-size: 16px; font-weight: 700; }
.journey-list-meta { color: #4A7A8F; font-size: 11px; font-weight: 500; }
.journey-list-status { font-size: 10px; font-weight: 700; }

/* Box 3: intelligence brief (exec alert) */
.exec-alert-panel { background: #001828; border: 1px solid #CC0000; border-radius: 12px; }
.exec-alert-panel.nominal { border-color: #00AFA0; }
.preamble {
  padding: 10px 12px; background: #04131D; border: 1px solid #003A5C;
  border-left: 3px solid var(--amber); border-radius: 3px; margin-bottom: 14px;
  font-size: 12px; color: #E8F4FA; line-height: 1.55;
}
.preamble strong { color: #FFD580; }
.preamble-sub { color: #7AACBF; font-size: 11px; margin-top: 4px; }
.volume-strip { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.volume-card { flex: 1 1 140px; min-width: 140px; padding: 12px 14px;
               background: #001828; border: 1px solid #003A5C; border-radius: 4px; }
.volume-num { font-family: var(--mono); font-size: 24px; font-weight: 700;
              line-height: 1; margin-bottom: 6px; letter-spacing: 0.5px; }
.volume-lbl { font-size: 9px; color: #7AACBF; text-transform: uppercase;
              letter-spacing: 1.2px; margin-bottom: 4px; font-weight: 600; }
.volume-sub { font-size: 10px; color: #4A7A8F; font-family: var(--mono); }
.alert-section-label { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
                       letter-spacing: 1px; margin-bottom: 5px; }
.alert-section-text { font-size: 12px; color: #C5DDE8; line-height: 1.65; }
.alert-quote { font-size: 11px; color: #4A7A8F; font-style: italic;
               border-left: 2px solid #003A5C; padding-left: 10px; margin: 10px 0 14px; }
.alert-section + .alert-section { margin-top: 14px; border-top: 1px solid #003A5C; padding-top: 14px; }
.clark-badge-wrap { margin-top: 14px; border-top: 1px solid #003A5C; padding-top: 14px; }
.clark-badge {
  display: inline-block; padding: 8px 14px; border-radius: 4px;
}
.clark-badge-tier { display: block; font-size: 11px; font-weight: 700;
                    letter-spacing: 1px; }
.clark-badge-action { display: block; font-size: 10px; color: #7AACBF;
                      margin-top: 4px; font-family: var(--mono); letter-spacing: 0.3px; }

/* Ticker */
.ticker-wrapper { overflow: hidden; background: var(--ticker-bg);
                  border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
                  padding: 11px 0; }
.ticker-track { overflow: hidden; white-space: nowrap; }
.ticker-inner { display: inline-flex; align-items: center;
                animation: ticker-scroll 60s linear infinite; }
.ticker-inner:hover { animation-play-state: paused; }
@keyframes ticker-scroll {
  0% { transform: translateX(0); } 100% { transform: translateX(-50%); }
}
.ticker-item { display: inline-flex; align-items: center; gap: 6px; padding: 0 20px; }
.ticker-name { font-size: 13px; font-weight: 600; color: var(--text-2); }
.ticker-score { font-family: var(--mono); font-size: 15px; font-weight: 700; color: var(--text); }
.ticker-delta { font-family: var(--mono); font-size: 10px; }
.ticker-sep { color: var(--border); padding: 0 4px; font-size: 18px; }
.mini-bar { display: inline-flex; align-items: center; width: 60px; height: 4px;
            background: var(--border); border-radius: 2px; overflow: hidden; }
.mini-bar-fill { height: 4px; border-radius: 2px; }

/* Journey row */
.journey-row-header { display: flex; align-items: baseline; flex-wrap: wrap;
                      padding: 10px 20px; border-top: 1px solid var(--border);
                      background: var(--journey-bg); gap: 6px 18px; }
.journey-row-title { font-size: 12px; font-weight: 800; color: var(--text-2);
                     letter-spacing: 1.8px; text-transform: uppercase; }
.journey-row-sub { font-size: 10px; color: #4A7A8F; font-family: var(--mono); }
.journey-row { display: flex; gap: 1px; background: var(--border);
               border-bottom: 2px solid var(--border); }
.journey-cell { flex: 1; padding: 10px 32px; background: var(--journey-bg);
                border-top: 3px solid var(--border); }
.journey-cell-name { font-size: 13px; font-weight: 700; color: var(--text-2);
                     letter-spacing: 1px; margin-bottom: 4px; text-transform: uppercase; }
.journey-cell-score { font-size: 30px; font-weight: 800; font-family: var(--mono);
                      margin-bottom: 4px; color: var(--text); }
.journey-cell-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.journey-cell-submeta { font-size: 10px; color: #4A7A8F; font-family: var(--mono);
                        margin-top: 4px; letter-spacing: 0.3px; }
.journey-status-label { font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
                        font-family: var(--mono); color: var(--text-3); }

/* Metrics strip */
.metrics-strip { display: flex; gap: 1px; background: var(--border);
                 border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.metric-card { flex: 1; padding: 12px 32px; background: var(--summary-bg); }
.metric-value { font-size: 28px; font-weight: 800; font-family: var(--mono);
                line-height: 1; margin-bottom: 4px; }
.metric-label { font-size: 10px; font-weight: 700; letter-spacing: 1.5px;
                color: var(--text-3); text-transform: uppercase; }
.metric-sub { font-size: 12px; color: var(--text-2); margin-top: 2px; }

/* Body wrapper: left feed + right panel */
.body-wrapper { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 1px;
                background: var(--border); min-height: calc(100vh - 200px);
                min-width: 0; }
.body-wrapper > * { min-width: 0; }
.left-col { background: var(--feed-bg); padding: 18px 32px 24px;
            display: flex; flex-direction: column; gap: 16px; }
.right-col { background: var(--panel-bg); padding: 16px 18px;
             display: flex; flex-direction: column; gap: 16px; }

/* Journey cards (left col) */
.journey-card { background: var(--card); border: 1px solid var(--border);
                border-radius: 12px; padding: 16px 18px; display: flex;
                flex-direction: column; gap: 10px; }
.card-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.rank-num { font-family: var(--mono); font-size: 12px; font-weight: 800;
            color: var(--text-3); background: var(--border); width: 26px; height: 26px;
            border-radius: 7px; display: flex; align-items: center; justify-content: center; }
.journey-name { font-size: 16px; font-weight: 700; color: var(--text); flex: 1; }
.badge { font-size: 10px; font-weight: 700; letter-spacing: 1px;
         padding: 2px 10px; border-radius: 12px; }
.derived-note { font-size: 11px; font-family: var(--mono); color: var(--amber);
                background: rgba(245,166,35,0.08); padding: 3px 8px; border-radius: 12px;
                display: inline-block; align-self: flex-start; }
.verdict-label { font-size: 10px; font-weight: 700; letter-spacing: 2px;
                 color: var(--blue); text-transform: uppercase; }
.verdict-text { font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.65; }
.version-delta-row { display: flex; align-items: center; gap: 12px; }
.version-label { font-family: var(--mono); font-size: 10px; font-weight: 700;
                 color: var(--blue); background: var(--border);
                 padding: 2px 6px; border-radius: 4px; }
.version-delta { font-family: var(--mono); font-size: 12px; font-weight: 500;
                 background: var(--border); padding: 2px 8px; border-radius: 4px; color: var(--text-2); }
.signal-counts { display: flex; gap: 8px; }
.sig-count { font-family: var(--mono); font-size: 11px; padding: 1px 6px; border-radius: 12px; }
.sig-p1 { background: rgba(204,0,0,0.15); color: #FF4444; border: 1px solid rgba(204,0,0,0.2); }
.sig-p2 { background: rgba(245,166,35,0.10); color: var(--amber); border: 1px solid rgba(245,166,35,0.2); }
.market-note { font-size: 11px; color: var(--muted); font-style: italic; }
.pack-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.pack-chip { font-family: var(--mono); font-size: 10px; padding: 2px 8px;
             border-radius: 10px; background: rgba(0,174,239,0.08);
             color: var(--blue); border: 1px solid rgba(0,174,239,0.2); }
.pack-chip.fairness { background: rgba(245,166,35,0.08);
                       color: var(--amber); border-color: rgba(245,166,35,0.3); }
.pack-chip.negative { background: rgba(0,175,160,0.08);
                       color: var(--teal); border-color: rgba(0,175,160,0.3); }

/* Right panel */
.panel-section { display: flex; flex-direction: column; gap: 10px; }
.panel-title { font-size: 11px; font-weight: 700; letter-spacing: 2px;
               color: var(--blue); text-transform: uppercase;
               padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.chronicle-card { background: var(--card); border: 1px solid var(--border);
                  border-radius: 8px; padding: 12px 14px;
                  display: flex; flex-direction: column; gap: 5px; }
.chronicle-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chronicle-id { font-family: var(--mono); font-size: 11px; font-weight: 600; color: #8BBCCC; }
.chronicle-bank { font-size: 11px; font-weight: 600; color: #8BBCCC; flex: 1; }
.chronicle-date { font-size: 10px; color: var(--muted); font-family: var(--mono); }
.chronicle-type { font-size: 10px; color: #3A5A6F; }
.chronicle-impact { font-size: 11px; font-weight: 700; color: var(--amber); font-family: var(--mono); }
.chronicle-active { font-size: 9px; font-weight: 700; letter-spacing: 1px;
                    background: rgba(204,0,0,0.2); color: #FF6666;
                    padding: 1px 5px; border-radius: 8px; }
.chronicle-hold { font-size: 9px; font-weight: 700;
                  background: rgba(74,122,143,0.2); color: var(--text-3);
                  padding: 1px 5px; border-radius: 8px; }

.inference-card { background: var(--card); border: 1px solid var(--red);
                  border-radius: 12px; padding: 14px 16px;
                  display: flex; flex-direction: column; gap: 8px; }
.inference-header { display: flex; align-items: center; gap: 8px; }
.inference-label { font-size: 11px; font-weight: 800; letter-spacing: 2px;
                   color: var(--red); text-transform: uppercase; }
.severity-badge { font-size: 10px; font-weight: 700; padding: 1px 8px; border-radius: 12px; }
.severity-p0 { background: rgba(204,0,0,0.3); color: #FF4444; }
.severity-p1 { background: rgba(204,0,0,0.15); color: #FF6666; }
.severity-p2 { background: rgba(245,166,35,0.15); color: var(--amber); }
.inference-finding { font-size: 13px; font-weight: 700; color: var(--text); line-height: 1.5; }
.blind-spots { list-style: none; display: flex; flex-direction: column; gap: 4px; }
.blind-spot-item { font-size: 11px; color: #9AB0BA; line-height: 1.5;
                   padding-left: 12px; position: relative; }
.blind-spot-item::before { content: '·'; position: absolute; left: 4px;
                           color: var(--amber); font-weight: 700; }
.chronicle-anchor { font-family: var(--mono); font-size: 11px; color: var(--blue); }

.sources-grid { display: flex; flex-direction: column; gap: 4px; }
.source-item { display: flex; align-items: center; gap: 8px; padding: 5px 0;
               border-bottom: 1px solid var(--border); }
.source-item:last-child { border-bottom: none; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-green { background: var(--teal); box-shadow: 0 0 4px rgba(0,175,160,0.6); }
.dot-amber { background: var(--amber); box-shadow: 0 0 4px rgba(245,166,35,0.5); }
.dot-grey { background: var(--border); }
.source-name { font-size: 11px; font-weight: 500; color: var(--muted); flex: 1; }
.source-weight { font-family: var(--mono); font-size: 11px; color: var(--text-3); }

/* V3 below-fold layer */
.v3-divider { border: none; border-top: 2px solid #003A5C; margin: 32px 0 0; }
.v3-outer { max-width: 1200px; margin: 0 auto; padding: 24px 16px 60px; }
.v3-label { font-size: 10px; color: #3A6A7F; text-transform: uppercase;
            letter-spacing: 1px; margin-bottom: 24px; }
.churn-header { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.churn-score-block { text-align: center; min-width: 110px; }
.churn-score-num { font-family: var(--mono); font-size: 48px; font-weight: 800; line-height: 1; }
.churn-score-lbl { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
                   letter-spacing: 1px; margin-top: 4px; }
.churn-trend-block { display: flex; flex-direction: column; gap: 6px; }
.churn-trend-badge { display: inline-block; padding: 4px 10px; border-radius: 4px;
                     font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.churn-meta { font-size: 11px; color: #4A7A8F; }
.churn-over-list { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.churn-issue-pill { font-size: 10px; padding: 3px 8px; border-radius: 4px;
                    border: 1px solid #CC3333; color: #CC3333; background: #1A0810; }
.churn-issue-pill.strength { border-color: #00AFA0; color: #00AFA0; background: #00100E; }

.commentary-grid { display: flex; flex-direction: column; gap: 14px; }
.commentary-card { background: #001828; border: 1px solid #003A5C;
                   border-radius: 8px; padding: 16px 20px; }
.commentary-card.risk { border-left: 4px solid #CC3333; }
.commentary-card.strength { border-left: 4px solid #00AFA0; }
.commentary-card.negative { border-left: 4px solid var(--amber); }
.commentary-card-header { display: flex; align-items: center; gap: 10px;
                          margin-bottom: 10px; flex-wrap: wrap; }
.commentary-issue { font-size: 13px; font-weight: 700; color: #E8F4FA; }
.commentary-badge { font-size: 9px; padding: 2px 7px; border-radius: 3px;
                    font-weight: 700; letter-spacing: 0.5px; }
.commentary-badge.risk { background: #2A0808; color: #CC3333; border: 1px solid #CC3333; }
.commentary-badge.strength { background: #001810; color: #00AFA0; border: 1px solid #00AFA0; }
.commentary-badge.negative { background: #2A1200; color: var(--amber); border: 1px solid var(--amber); }
.commentary-stats { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }
.commentary-stat { font-size: 10px; color: #3A6A7F; }
.commentary-stat span { font-family: var(--mono); color: #7AACBF; }
.commentary-prose { font-size: 12px; color: #C5DDE8; line-height: 1.65; margin-bottom: 10px; }
.commentary-quote { font-size: 11px; color: #4A7A8F; font-style: italic;
                    border-left: 2px solid #003A5C; padding-left: 10px; }

.bench-table { width: 100%; border-collapse: separate; border-spacing: 0 4px; }
.bench-row-head { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
                  letter-spacing: 0.5px; padding: 4px 8px 8px; text-align: left; }
.bench-issue-row { background: #001828; }
.bench-issue-name { font-size: 11px; color: #C5DDE8; padding: 10px 8px 10px 12px;
                    min-width: 230px; }
.bench-bar-cell { padding: 6px 8px; min-width: 140px; }
.bench-bar-wrap { display: flex; align-items: center; gap: 6px; }
.bench-bar-bg { flex: 1; background: #002030; border-radius: 3px;
                height: 8px; max-width: 140px; }
.bench-bar-fill { height: 8px; border-radius: 3px; }
.bench-bar-pct { font-family: var(--mono); font-size: 10px; color: #7AACBF; min-width: 38px; }
.bench-gap-cell { font-family: var(--mono); font-size: 11px;
                  padding: 10px 8px; text-align: right; min-width: 60px; }
.bench-gap-positive { color: #CC3333; }
.bench-gap-negative { color: #00AFA0; }
.bench-gap-neutral { color: #4A7A8F; }
.bench-days-cell { font-size: 10px; color: #3A6A7F; padding: 10px 8px;
                   min-width: 70px; text-align: left; }

/* Clark Protocol tiles */
.clark-strip { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.clark-tile { flex: 1; min-width: 100px; background: #001828;
              border: 1px solid #003A5C; border-radius: 8px;
              padding: 12px; text-align: center; }
.clark-count { font-family: var(--mono); font-size: 24px; font-weight: 800; }
.clark-tier { font-size: 9px; color: #3A6A7F; text-transform: uppercase;
              letter-spacing: 1px; margin-top: 2px; }
.clark-label { font-size: 8px; color: #4A7A8F; }

/* footer */
.footer { background: var(--topbar-bg); border-top: 1px solid var(--border);
          padding: 16px 32px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.footer-item { font-size: 11px; color: #2A5A6F; font-family: var(--mono); letter-spacing: 1px; }
.footer-sep { color: var(--border); }
.footer-sovereign { font-size: 11px; font-weight: 700; letter-spacing: 1px;
                    color: var(--blue); background: rgba(0,174,239,0.08);
                    padding: 2px 8px; border-radius: 8px; }

/* ── BOX 0 — first column of the topbar (controls placeholder).
   Inherits .topbar-box chrome via .sidebar.topbar-box so it visually
   matches box1/2/3. Internal sections scroll if box0 content overflows. */
body { overflow-x: hidden; }
.sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-body { flex: 1; overflow-y: auto; }
.sidebar-head {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: #001828;
}
.sidebar-tag {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 1.5px;
  text-transform: uppercase;
}
.sidebar-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--blue);
  letter-spacing: 2px;
  text-transform: uppercase;
  margin-top: 4px;
}
.sidebar-sub {
  font-size: 9px;
  color: var(--text-3);
  margin-top: 4px;
  line-height: 1.4;
  font-style: italic;
}
.sidebar-section {
  padding: 8px 14px;
  border-bottom: 1px solid #001E30;
}
.sidebar-section-label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  color: var(--text-3);
  letter-spacing: 1.2px;
  text-transform: uppercase;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sidebar-section-label .badge {
  background: rgba(245,166,35,0.08);
  color: var(--amber);
  border: 1px solid rgba(245,166,35,0.3);
  padding: 1px 5px;
  border-radius: 8px;
  font-size: 8px;
  letter-spacing: 0.5px;
}
.sidebar-select {
  width: 100%;
  background: #001828;
  color: var(--text-2);
  border: 1px solid var(--border);
  padding: 6px 8px;
  font-family: var(--mono);
  font-size: 11px;
  border-radius: 4px;
  appearance: none;
  background-image: url("data:image/svg+xml;charset=utf-8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 14 8' fill='%234A7A8F'><path d='M0 0l7 8 7-8z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 8px center;
  background-size: 8px 6px;
  padding-right: 22px;
}
.sidebar-select:focus { outline: none; border-color: var(--blue); }
.sidebar-multiselect {
  background: #001828;
  border: 1px solid var(--border);
  border-radius: 4px;
  max-height: 120px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.sidebar-multi-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--text-2);
  border-bottom: 1px solid #001E30;
  cursor: pointer;
}
.sidebar-multi-item:last-child { border-bottom: none; }
.sidebar-multi-item:hover { background: #002A3F; color: var(--text); }
.sidebar-multi-item input {
  margin: 0;
  width: 11px;
  height: 11px;
  accent-color: var(--blue);
  cursor: pointer;
}
.sidebar-multi-item .cat-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  margin-left: auto;
  flex-shrink: 0;
}
.cat-choke_point { background: var(--red); }
.cat-context_loss { background: var(--amber); }
.cat-behavioural_noise { background: #B07A1F; }
.cat-regulator { background: var(--blue); }
.cat-infrastructure { background: var(--text-3); }

.sidebar-placeholder {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-3);
  background: #001828;
  border: 1px dashed var(--border);
  border-radius: 4px;
  padding: 10px 12px;
  text-align: center;
  font-style: italic;
}
.sidebar-actions {
  margin-top: auto;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  background: #001828;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sidebar-btn {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.6px;
  padding: 6px 8px;
  border-radius: 4px;
  text-align: center;
  text-transform: uppercase;
  cursor: pointer;
  border: 1px solid var(--border);
  background: #002030;
  color: var(--text-2);
}
.sidebar-btn.primary {
  background: rgba(0,174,239,0.12);
  border-color: var(--blue);
  color: var(--blue);
  font-weight: 700;
}
.sidebar-btn:hover { background: rgba(0,174,239,0.08); color: var(--text); }

@media (max-width: 1024px) {
  .topbar { grid-template-columns: 1fr; }
  .body-wrapper { grid-template-columns: 1fr; }
  .journey-row { flex-wrap: wrap; }
  .journey-cell { min-width: 45%; }
}
"""


def render_ticker(packs: list[dict]) -> str:
    """Scrolling ticker of pack lineage anchors."""
    items = []
    for p in packs:
        sig = (p["hypothesis"] or {}).get("signature_id", "—").replace("_", " ")
        cell = (p["hypothesis"] or {}).get("cell_id", "?")
        sha = short_hash(p["sha256"])
        gt = (p["hypothesis"] or {}).get("ground_truth_expectation", "positive")
        color = "#F5A623" if gt == "negative" else "#7AACBF"
        items.append(
            f'<span class="ticker-item">'
            f'<span class="ticker-name" style="color:{color};">CELL {cell:>2}</span>'
            f'<span class="ticker-score" style="font-size:11px;">{sig}</span>'
            f'<span class="mini-bar"><span class="mini-bar-fill" '
            f'style="width:{40 if gt!="negative" else 22}px;background:{color};"></span></span>'
            f'<span class="ticker-delta" style="color:#3A6A7F;">{sha}</span></span>'
            f'<span class="ticker-sep">·</span>'
        )
    track = "".join(items)
    return f'<div class="ticker-wrapper"><div class="ticker-track"><div class="ticker-inner">{track}{track}</div></div></div>'


def render_journey_row(screens: list[dict]) -> str:
    cells_html = ""
    for s in screens:
        score = 100 - (s["positives"] * 18)  # synthetic — higher positives = lower screen health
        cells_html += (
            f'<div class="journey-cell" style="border-top:3px solid {s["status_color"]};">'
            f'<div class="journey-cell-name">{s["short"]}</div>'
            f'<div class="journey-cell-score">{s["positives"]}/3</div>'
            f'<div class="journey-cell-meta">'
            f'<span class="journey-status-label" style="color:{s["status_color"]};">{s["status"]}</span>'
            f'</div>'
            f'<div class="journey-cell-submeta">{s["total"]} cells · '
            f'{s["positives"]} positive · {s["negatives"]} negative</div>'
            f'</div>'
        )
    header = (
        '<div class="journey-row-header">'
        '<span class="journey-row-title">FRICTION-TARGET SCREENS</span>'
        '<span class="journey-row-sub">FrictionBench v0.1 · 4 screens × 3 signatures</span>'
        '</div>'
    )
    return header + f'<div class="journey-row">{cells_html}</div>'


def render_journey_cards(packs: list[dict]) -> str:
    """Per-pack cards, ranked by ground-truth severity (negative first, then positive)."""
    sorted_packs = sorted(
        packs,
        key=lambda p: (
            0 if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative" else 1,
            (p["hypothesis"] or {}).get("cell_id", 99),
        ),
    )
    cards = ""
    for i, p in enumerate(sorted_packs, 1):
        meta = p["meta"]
        h = p["hypothesis"] or {}
        label, _, border = pack_severity(p)
        cell = h.get("cell_id", "?")
        screen = h.get("screen_id", "—")
        sig = h.get("signature_id", "—").replace("_", " ")
        analytic_method = (h.get("analytic") or {}).get("method", "—")
        fairness = (h.get("fairness") or {}).get("required_methods", [])
        chip_class = "negative" if "NEGATIVE" in label else ""
        chips = ""
        if fairness:
            chips += f'<span class="pack-chip fairness">FAIRNESS · {len(fairness)} methods</span>'
        chips += f'<span class="pack-chip">{analytic_method}</span>'
        if "NEGATIVE" in label:
            chips += '<span class="pack-chip negative">DISCRIMINATOR ACTIVE</span>'
        domain = screen.split(".")[0] if screen != "—" else ""
        authors = ",".join(meta.get("authors", []))
        gt = h.get("ground_truth_expectation", "")
        # HOL-9: per-pack Value + Risk + Action badges from the placement
        # scenario index. If unavailable (engine import failed), the badge
        # row degrades to nothing — base card still renders.
        cell_score = get_pack_cell(meta["pack_name"])
        badges_html = ""
        if cell_score is not None:
            badges_html = (
                f'<div class="pack-tier-badges" style="margin-top:6px;display:flex;flex-wrap:wrap;gap:4px;">'
                f'{_tier_badge_html("VALUE", cell_score.value.tier, _VALUE_COLORS)}'
                f'{_tier_badge_html("RISK", cell_score.risk.tier, _RISK_COLORS)}'
                f'{_tier_badge_html("ACTION", cell_score.action_tier, _ACTION_COLORS)}'
                f'</div>'
            )

        cards += f'''
<div class="journey-card pack-card"
     data-packname="{meta['pack_name']}"
     data-author="{authors}"
     data-domain="{domain}"
     data-screen="{screen}"
     data-signature="{h.get('signature_id', '')}"
     data-gt="{gt}"
     data-cell="{cell}"
     style="border-left:3px solid {border};">
  <div class="card-header">
    <span class="rank-num">#{i}</span>
    <span class="journey-name">Cell {cell} · {sig.title()}</span>
    <span class="badge" style="color:{border};background:{'#2a1500' if 'NEGATIVE' in label else '#2a0a0a'};">{label}</span>
  </div>
  <div class="derived-note">{screen}</div>
  {badges_html}
  <div class="verdict-label">Pack verdict</div>
  <div class="verdict-text">{meta.get("description","").strip().replace(chr(10), " ")[:220]}{"…" if len(meta.get("description","")) > 220 else ""}</div>
  <div class="version-delta-row">
    <span class="version-label">{meta["pack_name"]}</span>
    <code class="version-delta">v{meta["pack_version"]} · sha256:{short_hash(p["sha256"])}</code>
  </div>
  <div class="pack-chips">{chips}</div>
  <div class="market-note">Synthesis: {meta["synthesis_mode"]} · attestation: {(meta["compliance_attestations"] or [{}])[0].get("status", "—")} · {(meta["compliance_attestations"] or [{}])[0].get("name", "—")}</div>
</div>
'''
    return cards


def render_chronicle(packs: list[dict]) -> str:
    """HOL-9 evolution: render matched Chronicle precedents for the
    headline pack, not the static FrictionBench cell catalogue.

    For each verified Chronicle entry the Risk methodology matched on
    the headline pack's friction signature, render a card with
    institution + regulator + year + enforcement summary. If no
    verified matches (the seed-batch state — all Chronicle entries
    ship `pending_human_review` and the matcher fails closed), render
    an explanatory card pointing at the curator handoff.

    Never silent — the panel always renders content, never empty.
    """
    headline = headline_pack(packs)
    cell_score = get_pack_cell(headline["meta"]["pack_name"])

    # Header context — which pack this matcher result is for
    h = headline["hypothesis"] or {}
    cell_id = h.get("cell_id", "?")
    sig = h.get("signature_id", "—").replace("_", " ")
    context_card = f'''
<div class="chronicle-card" style="border-left:3px solid var(--blue);background:#001020;">
  <div class="chronicle-header">
    <span class="chronicle-id" style="color:var(--blue);">CONTEXT</span>
    <span class="chronicle-bank">Headline pack — cell {cell_id}</span>
  </div>
  <div class="chronicle-type">{sig.title()} on {h.get("screen_id", "—")}</div>
  <div class="chronicle-impact" style="font-size:10px;color:#5A7E92;">
    Matcher checks the seed Chronicle library for verified enforcement
    precedents sharing this signature × screen × severity.
  </div>
</div>'''

    # No-engine fallback
    if cell_score is None:
        return context_card + '''
<div class="chronicle-card" style="border-left:3px solid var(--amber);">
  <div class="chronicle-header">
    <span class="chronicle-id" style="color:var(--amber);">UNAVAILABLE</span>
    <span class="chronicle-bank">Chronicle matcher offline</span>
  </div>
  <div class="chronicle-type">PULSE-106 import failed</div>
  <div class="chronicle-impact" style="font-size:10px;color:#5A7E92;">
    Cannot run matcher — engine modules not loaded.
  </div>
</div>'''

    matches = cell_score.risk.chronicle_matches
    if not matches:
        # Empty-matches path: rendered honestly with the curator-handoff
        # note. This is the active state for the seed batch.
        return context_card + '''
<div class="chronicle-card" style="border-left:3px solid #7A7A7A;">
  <div class="chronicle-header">
    <span class="chronicle-id" style="color:#A8CDDE;">NO VERIFIED MATCHES</span>
    <span class="chronicle-bank">Matcher returned empty</span>
  </div>
  <div class="chronicle-type">Curator handoff pending</div>
  <div class="chronicle-impact" style="font-size:10px;color:#5A7E92;line-height:1.5;">
    The seed-batch Chronicle library (10 CHR-friction entries) ships with
    <code>verification_status: pending_human_review</code>. The matcher
    fails closed on pending entries — no entry influences production Risk
    scoring until a UK-banking-enforcement curator corroborates facts
    against the cited public sources and flips the status to
    <code>verified</code>. See <code>pulse/risk/chronicle/SCHEMA.md</code>
    § Two-stage trust model.
  </div>
</div>'''

    # Matches-exist path: load the full chronicle library to render the
    # ChronicleMatch details (institution / regulator / year / fine).
    # Re-runs match_signature — cheap; only fires when there are
    # verified entries to render.
    try:
        from pulse.risk.chronicle import load_chronicle_library, match_signature
        library = load_chronicle_library(REPO / "pulse" / "risk" / "chronicle" / "entries")
        full_matches = match_signature(
            library,
            signature_id=cell_score.value.tier,  # placeholder; see below
            screen_class=h.get("screen_id", "—"),
            severity="P0",
        )
    except Exception:  # pragma: no cover
        full_matches = []

    # If the matcher round-trip didn't produce full details (e.g. signature
    # mismatch), fall back to rendering IDs only.
    cards = context_card
    for match_id in matches:
        full = next((m for m in full_matches if m.chronicle_id == match_id), None)
        if full is None:
            cards += f'''
<div class="chronicle-card" style="border-left:3px solid var(--green);">
  <div class="chronicle-header">
    <span class="chronicle-id" style="color:var(--green);">{match_id}</span>
    <span class="chronicle-bank">Verified precedent</span>
  </div>
  <div class="chronicle-type">Details available in pulse/risk/chronicle/entries/</div>
</div>'''
            continue
        fine_str = (
            f"£{full.fine_gbp/1_000_000:.1f}M fine"
            if full.fine_gbp
            else (f"£{full.redress_gbp/1_000_000:.1f}M redress" if full.redress_gbp else full.enforcement_type)
        )
        cards += f'''
<div class="chronicle-card" style="border-left:3px solid var(--green);">
  <div class="chronicle-header">
    <span class="chronicle-id" style="color:var(--green);">{full.chronicle_id}</span>
    <span class="chronicle-bank">{full.institution}</span>
  </div>
  <div class="chronicle-type">{full.regulator} · {full.year} · {fine_str}</div>
  <div class="chronicle-impact" style="font-size:10px;color:#5A7E92;">
    {full.public_sources_count} public source{"s" if full.public_sources_count != 1 else ""} cited
  </div>
</div>'''
    return cards


def render_inference(pack: dict) -> str:
    """Currently-selected pack's hypothesis in the inference slot."""
    h = pack["hypothesis"] or {}
    analytic = h.get("analytic") or {}
    method = analytic.get("method", "—")
    trigger = analytic.get("trigger") or {}
    cohort_axes = h.get("cohort_axes") or []
    fairness = (h.get("fairness") or {}).get("required_methods", [])
    gt = h.get("ground_truth_expectation", "positive")
    sev = "P0" if gt == "negative" else "P1"
    sev_cls = "severity-p0" if gt == "negative" else "severity-p1"
    blind_spots_html = ""
    for cls in fairness:
        blind_spots_html += f'<li class="blind-spot-item">Fairness method enforced: {cls}</li>'
    if gt == "negative":
        blind_spots_html += '<li class="blind-spot-item">Discriminator MUST suppress fire — false positives are the failure mode</li>'
    return f'''
<div class="inference-card">
  <div class="inference-header">
    <span class="inference-label">ACTIVE HYPOTHESIS</span>
    <span class="severity-badge {sev_cls}">{sev}</span>
  </div>
  <div class="inference-finding">{method} · {h.get("question_class", "—")}</div>
  <ul class="blind-spots">
    {blind_spots_html}
    <li class="blind-spot-item">Cohort axes: {", ".join(cohort_axes) or "—"}</li>
  </ul>
  <div class="chronicle-anchor">CELL: {h.get("cell_id", "?")} · sha256:{short_hash(pack["sha256"])}</div>
</div>
'''


def render_sources(pack: dict) -> str:
    """Cohort axes in the signal sources slot."""
    h = pack["hypothesis"] or {}
    axes = h.get("cohort_axes") or []
    items = ""
    for a in axes:
        items += (
            f'<div class="source-item">'
            f'<span class="dot dot-green"></span>'
            f'<span class="source-name">{a}</span>'
            f'<span class="source-weight">enforced</span>'
            f'</div>'
        )
    if not items:
        items = '<div class="source-item"><span class="dot dot-grey"></span><span class="source-name">No cohort axes declared</span></div>'
    return items


def render_intelligence_brief(pack: dict, all_packs: list[dict]) -> str:
    """Box 3 — selected pack's Bank altitude rendered in MIL exec-alert format."""
    h = pack["hypothesis"] or {}
    meta = pack["meta"]
    cell = h.get("cell_id", "?")
    sig = h.get("signature_id", "—").replace("_", " ")
    screen = h.get("screen_id", "—")
    gt = h.get("ground_truth_expectation", "positive")
    is_negative = gt == "negative"

    # Strip markdown headings and code fences — box3 needs to stay compact.
    raw = pack["bank_md"]
    cleaned = " ".join(
        ln.strip().lstrip("#").strip()
        for ln in raw.split("\n")
        if ln.strip() and not ln.startswith("```")
    )
    bank_excerpt = cleaned[:280] + ("…" if len(cleaned) > 280 else "")

    # Synthetic volume strip metrics derived from the pack
    n_packs = len(all_packs)
    n_positive = sum(1 for p in all_packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
    n_negative = n_packs - n_positive

    # HOL-9: replace the hand-typed CLARK tier with the engine-computed
    # Action tier from the placement scenario. Falls back to the legacy
    # CLARK label if the engine isn't loaded (preserves old behaviour
    # when PULSE-106 unavailable).
    cell_score = get_pack_cell(meta["pack_name"])
    if cell_score is not None:
        tier = cell_score.action_tier
        tier_action = cell_score.placement_recommendation
        badge_color = _ACTION_COLORS.get(cell_score.action_tier, "#7A7A7A")
    else:
        badge_color = "var(--amber)" if is_negative else "#F5A623"
        tier = "PULSE-0 — DISCRIMINATOR REQUIRED" if is_negative else "PULSE-1 — DETECTOR ACTIVE"
        tier_action = "engineering · fairness review · before-fire suppression" if is_negative else "investigation routing · remediation · cohort review"

    return f'''
<div class="topbar-box exec-alert-panel{' nominal' if not is_negative else ''}">
  <div class="topbar-box-header" style="background:#001828;border-bottom:1px solid #003A5C;">
    <span class="topbar-box-title">INTELLIGENCE BRIEF</span>
    <span style="font-size:10px;color:#3A6A7F;">Pulse · cell {cell} · {sig.title()}</span>
  </div>
  <div class="topbar-box-body">
    <div class="preamble">
      <div><strong>{sig.title()}</strong> on {screen} is the active hypothesis — {"NEGATIVE ground truth (detector MUST NOT fire)" if is_negative else "POSITIVE ground truth, detector active"}, cell {cell} of 12 in FrictionBench v0.1.</div>
      <div class="preamble-sub">{n_positive} positive · {n_negative} negative · {n_packs} cells total · synthesis layer pending PULSE-93</div>
    </div>
    <div class="volume-strip">
      <div class="volume-card">
        <div class="volume-num" style="color:var(--blue);">CELL {cell}</div>
        <div class="volume-lbl">FrictionBench</div>
        <div class="volume-sub">v0.1 · frozen</div>
      </div>
      <div class="volume-card">
        <div class="volume-num" style="color:{'var(--amber)' if is_negative else 'var(--teal)'};">{gt.upper()}</div>
        <div class="volume-lbl">Ground truth</div>
        <div class="volume-sub">{"discriminator active" if is_negative else "detector active"}</div>
      </div>
      <div class="volume-card">
        <div class="volume-num" style="color:var(--text-2);">{(h.get("analytic") or {}).get("method", "—").split("_")[0]}</div>
        <div class="volume-lbl">Method family</div>
        <div class="volume-sub" style="font-size:9px;">{(h.get("analytic") or {}).get("method", "—")}</div>
      </div>
      <div class="volume-card">
        <div class="volume-num" style="color:var(--amber);font-size:14px;line-height:1.4;">sha256</div>
        <div class="volume-lbl">Lineage anchor</div>
        <div class="volume-sub">{short_hash(pack["sha256"])}</div>
      </div>
    </div>
    <div class="alert-section">
      <div class="alert-section-label">The Situation</div>
      <div class="alert-section-text">{meta.get("description", "").strip().replace(chr(10), " ")[:500]}</div>
    </div>
    <div class="alert-section">
      <div class="alert-section-label">Bank altitude (preview)</div>
      <div class="alert-section-text">{bank_excerpt}…</div>
    </div>
    <div class="clark-badge-wrap">
      <span class="clark-badge" style="background:{badge_color}22;border:1px solid {badge_color};">
        <span class="clark-badge-tier" style="color:{badge_color};">{tier}</span>
        <span class="clark-badge-action">{tier_action}</span>
      </span>
    </div>
  </div>
</div>
'''


def render_volume_brief_for_box1(packs: list[dict]) -> str:
    """Box 1: 2 sample quote cards from headline packs."""
    quote_packs = [p for p in packs if (p["hypothesis"] or {}).get("cell_id") in (9, 10)]
    if not quote_packs:
        quote_packs = packs[:2]
    cards = ""
    for p in quote_packs[:2]:
        h = p["hypothesis"] or {}
        sig = h.get("signature_id", "—").replace("_", " ")
        cell = h.get("cell_id", "?")
        # First line of bank.md, minus the heading
        lines = [ln for ln in p["bank_md"].split("\n") if ln.strip() and not ln.startswith("#")][:2]
        excerpt = " ".join(lines)[:200] + "…"
        gt = h.get("ground_truth_expectation", "positive")
        cards += (
            f'<div style="border:1px solid #003A5C;border-radius:8px;padding:10px 12px;'
            f'background:#001E2E;">'
            f'<div style="font-size:12px;color:#B8D4E0;font-style:italic;line-height:1.5;">'
            f'"{excerpt}"</div>'
            f'<div style="font-size:11px;color:#4A7A8F;margin-top:6px;letter-spacing:0.03em;">'
            f'CELL {cell} · {sig} · {gt.upper()}</div>'
            f'</div>'
        )
    return cards


def render_volume_brief_for_box2(packs: list[dict], screens: list[dict]) -> str:
    """Box 2 issues status with cell counts + screen list."""
    n_positive = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
    n_negative = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative")

    list_items = ""
    for s in screens:
        list_items += (
            f'<div class="journey-list-item">'
            f'<span class="journey-list-name">{s["short"]}</span>'
            f'<span class="journey-list-right">'
            f'<span class="journey-list-score" style="color:{s["status_color"]};">{s["positives"]}/3</span>'
            f'<span class="journey-list-meta">{s["total"]} cells</span>'
            f'<span class="journey-list-status" style="color:{s["status_color"]};">{s["status"]}</span>'
            f'</span></div>'
        )
    return f'''
<div class="topbar-box">
  <div class="topbar-box-header">
    <span class="topbar-box-title">PACK STATUS</span>
    <span style="font-size:10px;color:#3A6A7F;">FrictionBench v0.1 cell coverage</span>
  </div>
  <div class="topbar-box-body">
    <div class="issues-stat-row">
      <span class="issues-stat-num" style="color:var(--teal);" data-count="positive">{n_positive}</span>
      <div><div class="issues-stat-label">Positive</div><div class="issues-stat-sub">DETECTOR ACTIVE cells</div></div>
    </div>
    <div class="issues-stat-row">
      <span class="issues-stat-num" style="color:var(--amber);" data-count="negative">{n_negative}</span>
      <div><div class="issues-stat-label">Negative</div><div class="issues-stat-sub">LOAD-BEARING · discriminator MUST suppress</div></div>
    </div>
    <div class="issues-stat-row">
      <span class="issues-stat-num" style="color:var(--blue);" data-count="total">{len(packs)}</span>
      <div><div class="issues-stat-label">Total</div><div class="issues-stat-sub">cells covered</div></div>
    </div>
    <div class="issues-divider"></div>
    {list_items}
  </div>
</div>'''


def render_metrics_strip(packs: list[dict]) -> str:
    n_packs = len(packs)
    n_negative = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative")
    fairness_enforced = sum(1 for p in packs if p["meta"].get("fairness_methods_required"))
    return f'''
<div class="metrics-strip">
  <div class="metric-card">
    <div class="metric-value" style="color:var(--teal);" data-count="metric-total">{n_packs}</div>
    <div class="metric-label">Cells covered</div>
    <div class="metric-sub" data-count="metric-total-sub">of 12 FrictionBench v0.1</div>
  </div>
  <div class="metric-card">
    <div class="metric-value" style="color:var(--amber);" data-count="metric-negative">{n_negative}</div>
    <div class="metric-label">Load-bearing negative</div>
    <div class="metric-sub">discriminator required</div>
  </div>
  <div class="metric-card">
    <div class="metric-value" style="color:var(--blue);" data-count="metric-fairness">{fairness_enforced}</div>
    <div class="metric-label">Fairness enforced</div>
    <div class="metric-sub">all packs (regulator-defensible)</div>
  </div>
</div>'''


def render_churn_block(packs: list[dict]) -> str:
    """V3 churn-risk-style block — adapt to friction risk score."""
    risk = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
    discriminators = sum(1 for p in packs if (p["hypothesis"] or {}).get("negative_class_discriminator"))
    score = f"{risk * 6.5:.1f}"
    pos_pills = "".join(
        f'<span class="churn-issue-pill" data-packname="{p["meta"]["pack_name"]}" data-pill-class="positive">{(p["hypothesis"] or {}).get("signature_id","—").replace("_"," ")} · cell {(p["hypothesis"] or {}).get("cell_id","?")}</span>'
        for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative"
    )
    neg_pills = "".join(
        f'<span class="churn-issue-pill strength" data-packname="{p["meta"]["pack_name"]}" data-pill-class="discriminator">{(p["hypothesis"] or {}).get("signature_id","—").replace("_"," ")} · cell {(p["hypothesis"] or {}).get("cell_id","?")} · discriminator</span>'
        for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative"
    )
    return f'''
<div class="topbar-box">
  <div class="topbar-box-header">
    <span class="topbar-box-title">FRICTION RISK SCORE</span>
    <span style="font-size:10px;color:#3A6A7F;">Pulse · FrictionBench cell coverage · risk-weighted</span>
  </div>
  <div class="topbar-box-body">
    <div class="churn-header">
      <div class="churn-score-block">
        <div class="churn-score-num" style="color:var(--amber);" data-aggregate="churn-score">{score}</div>
        <div class="churn-score-lbl">Cell Risk Score</div>
      </div>
      <div class="churn-trend-block">
        <span class="churn-trend-badge" style="background:#002030;color:#7AACBF;border:1px solid #3A6A7F;" data-aggregate="churn-coverage">12-CELL COVERAGE</span>
        <div class="churn-meta">
          <span data-aggregate="churn-positive-count">{risk}</span> positive detector cells · <span data-aggregate="churn-discriminator-count">{discriminators}</span> negative-class discriminator cells
        </div>
      </div>
    </div>
    <div style="margin-top:12px;">
      <div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">
        Positive cells — detector active
      </div>
      <div class="churn-over-list">{pos_pills}</div>
    </div>
    <div style="margin-top:10px;">
      <div style="font-size:9px;color:#3A6A7F;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">
        Negative cells — discriminator suppresses
      </div>
      <div class="churn-over-list">{neg_pills}</div>
    </div>
  </div>
</div>'''


def render_commentary_block(packs: list[dict]) -> str:
    """V3 analyst-commentary-style: one card per pack."""
    cards_html = ""
    sorted_packs = sorted(packs, key=lambda p: (p["hypothesis"] or {}).get("cell_id", 99))
    for p in sorted_packs:
        h = p["hypothesis"] or {}
        m = p["meta"]
        gt = h.get("ground_truth_expectation", "positive")
        cell = h.get("cell_id", "?")
        sig = h.get("signature_id", "—").replace("_", " ")
        screen = h.get("screen_id", "—")
        is_neg = gt == "negative"
        cls = "negative" if is_neg else "risk"
        badge_cls = "negative" if is_neg else "risk"
        badge_text = "NEGATIVE · LOAD-BEARING" if is_neg else "POSITIVE · DETECTOR ACTIVE"
        cards_html += f'''
<div class="commentary-card {cls}" data-packname="{p['meta']['pack_name']}">
  <div class="commentary-card-header">
    <span class="commentary-issue">Cell {cell} · {sig.title()}</span>
    <span class="commentary-badge {badge_cls}">{badge_text}</span>
    <span class="commentary-badge sev-p{('0' if is_neg else '1')}">SIG · {(h.get("analytic") or {}).get("method","").split("_")[0].upper()}</span>
    <span style="font-size:9px;color:#3A6A7F;">{screen}</span>
  </div>
  <div class="commentary-stats">
    <div class="commentary-stat">Cohort axes <span>{len(h.get("cohort_axes") or [])}</span></div>
    <div class="commentary-stat">Fairness methods <span>{len((h.get("fairness") or {}).get("required_methods", []))}</span></div>
    <div class="commentary-stat">Evidence fields <span>{len(h.get("evidence_required") or [])}</span></div>
    <div class="commentary-stat">Remediation <span>{len(h.get("remediation_categories") or [])}</span></div>
  </div>
  <div class="commentary-prose">{m.get("description","").strip().replace(chr(10), " ")[:400]}</div>
</div>'''
    return f'''
<div class="topbar-box">
  <div class="topbar-box-header">
    <span class="topbar-box-title">PACK COMMENTARY</span>
    <span style="font-size:10px;color:#3A6A7F;">
      Per-cell hypothesis summary · {len(packs)} packs
    </span>
  </div>
  <div class="topbar-box-body">
    <div class="commentary-grid">{cards_html}</div>
  </div>
</div>'''


def render_bench_block(packs: list[dict]) -> str:
    """Pack benchmark table (mirror MIL benchmark)."""
    rows = ""
    sorted_packs = sorted(packs, key=lambda p: (p["hypothesis"] or {}).get("cell_id", 99))
    for p in sorted_packs:
        h = p["hypothesis"] or {}
        cell = h.get("cell_id", "?")
        sig = h.get("signature_id", "—").replace("_", " ")
        screen_s = screen_short(h.get("screen_id", "—"))
        gt = h.get("ground_truth_expectation", "positive")
        is_neg = gt == "negative"
        cohort_n = len(h.get("cohort_axes") or [])
        evidence_n = len(h.get("evidence_required") or [])
        # synthetic "rate" — count of fields as a proxy for hypothesis density
        density = min((cohort_n + evidence_n) * 6, 100)
        bar_color = "var(--amber)" if is_neg else "var(--blue)"
        rows += f'''
<tr class="bench-issue-row" data-packname="{p['meta']['pack_name']}">
  <td class="bench-issue-name"><span style="color:{'#F5A623' if is_neg else '#CC0000'};font-size:8px;margin-right:2px;">●</span>Cell {cell} · {sig.title()}</td>
  <td class="bench-bar-cell">
    <div style="margin-bottom:3px;">
      <div style="font-size:8px;color:#3A6A7F;margin-bottom:2px;">Hypothesis density</div>
      <div class="bench-bar-wrap">
        <div class="bench-bar-bg">
          <div class="bench-bar-fill" style="width:{density}%;background:{bar_color};"></div>
        </div>
        <span class="bench-bar-pct" style="color:{bar_color};">{density}%</span>
      </div>
    </div>
  </td>
  <td class="bench-gap-cell {'bench-gap-positive' if is_neg else 'bench-gap-neutral'}">
    {gt.upper()}
  </td>
  <td class="bench-days-cell">{screen_s}</td>
</tr>'''
    return f'''
<div class="topbar-box">
  <div class="topbar-box-header">
    <span class="topbar-box-title">⚠ FRICTIONBENCH CELL BENCHMARK</span>
    <span style="font-size:10px;color:#3A6A7F;">All 12 cells · hypothesis density by cohort + evidence field count</span>
  </div>
  <div class="topbar-box-body">
    <table class="bench-table">
      <thead>
        <tr>
          <th class="bench-row-head">Cell</th>
          <th class="bench-row-head">Density</th>
          <th class="bench-row-head" style="text-align:right;">Ground Truth</th>
          <th class="bench-row-head">Screen</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>'''


SEARCH_MODAL_HTML = """
<div class="search-overlay" id="search-overlay" role="dialog" aria-label="Search packs" aria-hidden="true">
  <div class="search-modal" role="document">
    <div class="search-modal-head">
      <input type="text" class="search-input" id="search-input"
             placeholder="search packs · signatures · screens · authors"
             autocomplete="off" spellcheck="false" aria-label="Search query">
      <div class="search-meta">
        <span><span class="search-hint-keys">↑↓</span>navigate</span>
        <span><span class="search-hint-keys">↵</span>jump</span>
        <span><span class="search-hint-keys">Esc</span>close</span>
        <span style="margin-left:auto;"><span id="search-count">12</span> packs · pack-name · signature · screen · author</span>
      </div>
    </div>
    <div class="search-results" id="search-results"></div>
  </div>
</div>
"""


SEARCH_JS = """
<script>
/* HOL-10 phase 2 — search overlay.
 * Open via topnav search icon or `/` keypress (when not focused in an input).
 * Fuzzy substring match across pack_name + signature + screen + author + cell.
 * Arrow keys navigate results; Enter jumps to the pack card (closes the modal,
 * scrolls into view, flashes a blue outline). If the target pack is filtered
 * out, clears the filters first so the card is visible. */
(function () {
  const $overlay = document.getElementById('search-overlay');
  const $input   = document.getElementById('search-input');
  const $results = document.getElementById('search-results');
  const $count   = document.getElementById('search-count');
  const $icon    = document.querySelector('.topnav-icon[title^="Search"]');
  let activeIndex = 0;
  let currentResults = [];

  function getAllPacks() {
    return Array.from(document.querySelectorAll('.pack-card')).map(card => ({
      el: card,
      name: card.dataset.packname || '',
      author: card.dataset.author || '',
      domain: card.dataset.domain || '',
      screen: card.dataset.screen || '',
      signature: (card.dataset.signature || '').replace(/_/g, ' '),
      gt: card.dataset.gt || '',
      cell: card.dataset.cell || '?',
    }));
  }

  function searchPacks(q) {
    const all = getAllPacks();
    if (!q) return all;
    const needle = q.toLowerCase();
    return all.filter(p =>
      p.name.toLowerCase().includes(needle) ||
      p.signature.toLowerCase().includes(needle) ||
      p.screen.toLowerCase().includes(needle) ||
      p.author.toLowerCase().includes(needle) ||
      ('cell ' + p.cell).toLowerCase().includes(needle) ||
      p.domain.toLowerCase().includes(needle)
    );
  }

  function escape(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function highlight(text, q) {
    if (!q) return escape(text);
    const t = text;
    const needle = q.toLowerCase();
    const idx = t.toLowerCase().indexOf(needle);
    if (idx < 0) return escape(t);
    return escape(t.substring(0, idx)) +
           '<mark>' + escape(t.substring(idx, idx + needle.length)) + '</mark>' +
           escape(t.substring(idx + needle.length));
  }

  function renderResults() {
    const query = $input.value.trim();
    currentResults = searchPacks(query);
    $count.textContent = currentResults.length;
    if (currentResults.length === 0) {
      $results.innerHTML = '<div class="search-no-results">no packs match \\u201C' + escape(query) + '\\u201D</div>';
      return;
    }
    if (activeIndex >= currentResults.length) activeIndex = 0;
    $results.innerHTML = currentResults.map((p, i) => {
      const badgeCls = p.gt === 'negative' ? 'negative' : 'positive';
      const badgeText = p.gt === 'negative' ? 'NEG' : 'POS';
      return '<div class="search-result' + (i === activeIndex ? ' active' : '') + '" data-idx="' + i + '">' +
        '<div class="search-result-cell">CELL ' + p.cell + '</div>' +
        '<div>' +
          '<div class="search-result-title">' + highlight(p.signature, query) + '</div>' +
          '<div class="search-result-screen">' + highlight(p.screen, query) + '</div>' +
        '</div>' +
        '<div class="search-result-badge ' + badgeCls + '">' + badgeText + '</div>' +
      '</div>';
    }).join('');
    Array.from($results.querySelectorAll('.search-result')).forEach(el => {
      el.addEventListener('click', () => {
        activeIndex = parseInt(el.dataset.idx, 10);
        selectResult();
      });
    });
  }

  function selectResult() {
    const r = currentResults[activeIndex];
    if (!r) return;
    close();
    // If target is filtered out, clear filters first so card is visible.
    if (r.el.style.display === 'none') {
      const filterSelects = document.querySelectorAll('.topnav-select.active');
      filterSelects.forEach(s => { s.value = ''; });
      // trigger one change event so filter JS recomputes
      const trigger = document.getElementById('filter-domain');
      if (trigger) trigger.dispatchEvent(new Event('change'));
    }
    setTimeout(() => {
      r.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // restart flash even if already applied
      r.el.classList.remove('flash');
      void r.el.offsetWidth;
      r.el.classList.add('flash');
    }, 60);
  }

  function moveActive(delta) {
    activeIndex = Math.max(0, Math.min(currentResults.length - 1, activeIndex + delta));
    renderResults();
    const active = $results.querySelector('.search-result.active');
    if (active) active.scrollIntoView({ block: 'nearest' });
  }

  function open() {
    $overlay.classList.add('open');
    $overlay.setAttribute('aria-hidden', 'false');
    $input.value = '';
    activeIndex = 0;
    renderResults();
    setTimeout(() => $input.focus(), 0);
  }

  function close() {
    $overlay.classList.remove('open');
    $overlay.setAttribute('aria-hidden', 'true');
  }

  // wire
  if ($icon) {
    $icon.style.cursor = 'pointer';
    $icon.addEventListener('click', open);
  }
  $overlay.addEventListener('click', e => {
    if (e.target === $overlay) close();
  });
  $input.addEventListener('input', () => { activeIndex = 0; renderResults(); });
  $input.addEventListener('keydown', e => {
    if (e.key === 'Escape')        { close(); e.preventDefault(); }
    else if (e.key === 'ArrowDown'){ moveActive(1); e.preventDefault(); }
    else if (e.key === 'ArrowUp')  { moveActive(-1); e.preventDefault(); }
    else if (e.key === 'Enter')    { selectResult(); e.preventDefault(); }
  });
  // global `/` shortcut — only when not already typing in an input
  document.addEventListener('keydown', e => {
    if (e.key !== '/') return;
    const ae = document.activeElement;
    if (ae && /^(INPUT|SELECT|TEXTAREA)$/.test(ae.tagName)) return;
    if ($overlay.classList.contains('open')) return;
    open();
    e.preventDefault();
  });
})();
</script>
"""


PANEL_JS = """
<script>
/* HOL-10 phase 3 — utility-cluster panels.
 * Wires buttons with data-panel to toggle the matching panel element.
 * Search button (data-panel="search-overlay") is handled by SEARCH_JS;
 * we skip it here so the two systems don't fight.
 *
 * Behaviour:
 *  - click button → close other panels, toggle target
 *  - click outside any panel/button → close all
 *  - Esc → close all
 *  - Settings toggles add/remove body classes (data-toggle-class)
 *  - Popover right-anchors to its trigger button's right edge
 */
(function () {
  const $buttons = document.querySelectorAll('[data-panel]');
  const $panels  = document.querySelectorAll('.topnav-popover, .topnav-drawer');

  function closeAll() {
    $panels.forEach(p => p.setAttribute('hidden', ''));
    $buttons.forEach(b => b.classList.remove('panel-open'));
  }

  function anchorPopover(panel, button) {
    if (!panel.classList.contains('topnav-popover')) return; // drawer is right:0
    const rect = button.getBoundingClientRect();
    // Right-anchor the popover to the right edge of the viewport offset by
    // (viewport-width minus button's right edge).
    const rightEdge = window.innerWidth - rect.right;
    panel.style.right = Math.max(8, rightEdge) + 'px';
  }

  $buttons.forEach(btn => {
    const panelId = btn.getAttribute('data-panel');
    if (panelId === 'search-overlay') return; // owned by SEARCH_JS
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const panel = document.getElementById(panelId);
      if (!panel) return;
      const isOpen = !panel.hasAttribute('hidden');
      closeAll();
      if (!isOpen) {
        anchorPopover(panel, btn);
        panel.removeAttribute('hidden');
        btn.classList.add('panel-open');
      }
    });
  });

  // click outside → close
  document.addEventListener('click', e => {
    if (e.target.closest('[data-panel]')) return;
    if (e.target.closest('.topnav-popover, .topnav-drawer')) return;
    closeAll();
  });

  // Esc → close (SEARCH_JS already handles its own Esc; harmless redundancy)
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeAll();
  });

  // Settings toggles drive body classes (cosmetic show/hide).
  document.querySelectorAll('[data-toggle-class]').forEach(cb => {
    const cls = cb.getAttribute('data-toggle-class');
    cb.addEventListener('change', () => {
      document.body.classList.toggle(cls, cb.checked);
    });
  });
})();
</script>
"""



FILTER_JS = """
<script>
/* HOL-10 phase 1 — top-nav filtering.
 * Reads Product / Owner / Domain dropdowns, hides non-matching .pack-card
 * elements, recomputes counts in box1 / box2 / metrics-strip, syncs URL
 * query params, and toggles the Reset button + dropdown styling.
 * No backend; pure client-side. State shareable via URL. */
(function () {
  const FILTERS = ['product', 'owner', 'domain'];
  const FILTER_TO_DATA = {
    product: 'packname',
    owner:   'author',
    domain:  'domain',
  };

  const $selects = FILTERS.map(f => document.getElementById('filter-' + f));
  const $resetBtn = document.getElementById('filter-reset');
  const $cards = Array.from(document.querySelectorAll('.pack-card'));

  function readURLState() {
    const params = new URLSearchParams(window.location.search);
    FILTERS.forEach((f, i) => {
      const v = params.get(f) || '';
      if ($selects[i]) $selects[i].value = v;
    });
  }

  function writeURLState() {
    const params = new URLSearchParams();
    FILTERS.forEach((f, i) => {
      const v = $selects[i] && $selects[i].value;
      if (v) params.set(f, v);
    });
    const qs = params.toString();
    const url = window.location.pathname + (qs ? '?' + qs : '');
    history.replaceState(null, '', url);
  }

  function matches(card) {
    for (let i = 0; i < FILTERS.length; i++) {
      const sel = $selects[i];
      if (!sel || !sel.value) continue;
      const dataKey = FILTER_TO_DATA[FILTERS[i]];
      const cardVal = card.dataset[dataKey] || '';
      if (FILTERS[i] === 'owner') {
        // multi-value field — comma-separated authors
        const authors = cardVal.split(',').map(s => s.trim());
        if (!authors.includes(sel.value)) return false;
      } else if (cardVal !== sel.value) {
        return false;
      }
    }
    return true;
  }

  function recomputeCounts(visibleCards) {
    let positive = 0, negative = 0, fairness = 0;
    visibleCards.forEach(c => {
      if (c.dataset.gt === 'negative') negative++;
      else positive++;
      // every pack in this dataset declares fairness_methods_required:true
      // we proxy via presence of the FAIRNESS chip on the card
      if (c.querySelector('.pack-chip.fairness')) fairness++;
    });
    const total = visibleCards.length;

    function setText(selector, value) {
      document.querySelectorAll(selector).forEach(el => { el.textContent = value; });
    }

    setText('[data-count="positive"]', positive);
    setText('[data-count="negative"]', negative);
    setText('[data-count="total"]', total);
    setText('[data-count="metric-total"]', total);
    setText('[data-count="metric-total-sub"]',
            total === 12 ? 'of 12 FrictionBench v0.1'
                         : 'of 12 FrictionBench v0.1 · ' + (12 - total) + ' filtered out');
    setText('[data-count="metric-negative"]', negative);
    setText('[data-count="metric-fairness"]', fairness);
    setText('[data-count="coverage-score"]', total + '/12');
    setText('[data-count="coverage-delta"]',
            total === 12 ? '+9 vs showcase'
                         : (total === 0 ? '— no packs in scope'
                                        : 'filtered (' + total + ' of 12)'));
  }

  function recomputeJourneyRow(visibleCards) {
    // Recompute journey-row scores: count visible cards per screen.
    const byScreen = {};
    visibleCards.forEach(c => {
      const dom = c.dataset.domain;
      if (!dom) return;
      if (!byScreen[dom]) byScreen[dom] = { positive: 0, negative: 0 };
      if (c.dataset.gt === 'negative') byScreen[dom].negative++;
      else byScreen[dom].positive++;
    });
    document.querySelectorAll('.journey-cell').forEach(cell => {
      const nameEl = cell.querySelector('.journey-cell-name');
      if (!nameEl) return;
      const dom = nameEl.textContent.trim().split(' ')[0];
      const counts = byScreen[dom] || { positive: 0, negative: 0 };
      const total = counts.positive + counts.negative;
      const scoreEl = cell.querySelector('.journey-cell-score');
      const submetaEl = cell.querySelector('.journey-cell-submeta');
      if (scoreEl) scoreEl.textContent = counts.positive + '/3';
      if (submetaEl) submetaEl.textContent =
        total + ' cells · ' + counts.positive + ' positive · ' + counts.negative + ' negative';
      cell.style.opacity = total === 0 ? '0.35' : '1';
    });
  }

  /* HOL-10 phase 4 — V3-layer recompute.
   * Visible pack-name set drives:
   *  - show/hide per-pack rows in commentary cards, bench rows,
   *    Value/Risk scoring rows, placement matrix rows, churn pills
   *  - aggregates: friction risk score, clark-protocol tiles,
   *    placement matrix 2x2, Value/Risk tier-count chips
   */
  function recomputeV3(visibleCards) {
    const visibleNames = new Set(visibleCards.map(c => c.dataset.packname));

    // 1. Show/hide every per-pack V3 element (excluding pack-cards
    //    themselves; those are owned by applyFilters above).
    document.querySelectorAll('[data-packname]').forEach(el => {
      if (el.classList.contains('pack-card')) return;
      const visible = visibleNames.has(el.dataset.packname);
      el.style.display = visible ? '' : 'none';
    });

    // 2. Friction risk score: count visible positive pills + score.
    const visiblePills = document.querySelectorAll('.churn-issue-pill[data-pill-class]:not([style*="display: none"])');
    let posCount = 0, discCount = 0;
    visiblePills.forEach(p => {
      if (p.dataset.pillClass === 'positive') posCount++;
      else if (p.dataset.pillClass === 'discriminator') discCount++;
    });
    const elScore = document.querySelector('[data-aggregate="churn-score"]');
    if (elScore) elScore.textContent = (posCount * 6.5).toFixed(1);
    const elPos = document.querySelector('[data-aggregate="churn-positive-count"]');
    if (elPos) elPos.textContent = posCount;
    const elDisc = document.querySelector('[data-aggregate="churn-discriminator-count"]');
    if (elDisc) elDisc.textContent = discCount;

    // 3. Clark protocol tiles — counts derived from visible pack cards.
    let clarkPos = 0, clarkNeg = 0;
    visibleCards.forEach(c => {
      if (c.dataset.gt === 'negative') clarkNeg++;
      else clarkPos++;
    });
    const elClarkPos = document.querySelector('[data-aggregate="clark-positive"]');
    if (elClarkPos) elClarkPos.textContent = clarkPos;
    const elClarkNeg = document.querySelector('[data-aggregate="clark-negative"]');
    if (elClarkNeg) elClarkNeg.textContent = clarkNeg;
    const elClarkTotal = document.querySelector('[data-aggregate="clark-total"]');
    if (elClarkTotal) elClarkTotal.textContent = visibleCards.length;

    // 4. Placement matrix 2x2 aggregates — count visible rows by
    //    (action-tier × non-INCONCLUSIVE) / INCONCLUSIVE.
    const highValue = new Set(['SIGNIFICANT', 'COMMERCIAL-OPPORTUNITY']);
    const highRisk  = new Set(['ESCALATE', 'REGULATORY-FLAG']);
    let nAcute = 0, nRegFlag = 0, nCommercial = 0, nNominalWatch = 0, nIncon = 0;
    document.querySelectorAll('[data-panel-id="placement-matrix"] tbody tr[data-action-tier]').forEach(row => {
      if (row.style.display === 'none') return;
      const diag = row.dataset.diagnosis;
      if (diag === 'INCONCLUSIVE') { nIncon++; return; }
      // Re-derive risk and value from the displayed text. Simpler: use
      // the action tier directly since it's the composed signal.
      const act = row.dataset.actionTier;
      if (act === 'ACUTE') nAcute++;
      else if (act === 'REGULATORY-FLAG') nRegFlag++;
      else if (act === 'COMMERCIAL-OPPORTUNITY') nCommercial++;
      else nNominalWatch++;
    });
    [
      ['action-acute', nAcute],
      ['action-regflag', nRegFlag],
      ['action-commercial', nCommercial],
      ['action-nominal-watch', nNominalWatch],
      ['action-inconclusive', nIncon],
    ].forEach(([key, val]) => {
      const el = document.querySelector(`[data-aggregate="${key}"]`);
      if (el) el.textContent = val;
    });

    // 5. Value / Risk tier-count chips — recompute from visible rows.
    recomputeTierChips('value-scoring', 'data-value-tier', 'value');
    recomputeTierChips('risk-scoring',  'data-risk-tier',  'risk');
  }

  function recomputeTierChips(panelId, rowAttr, chipPrefix) {
    const tierCounts = {};
    document.querySelectorAll(
      `[data-panel-id="${panelId}"] tbody tr[${rowAttr}]`
    ).forEach(row => {
      if (row.style.display === 'none') return;
      const t = row.getAttribute(rowAttr);
      tierCounts[t] = (tierCounts[t] || 0) + 1;
    });
    document.querySelectorAll(
      `[data-tier-chip^="${chipPrefix}:"]`
    ).forEach(chip => {
      const tier = chip.dataset.tierChip.split(':')[1];
      const count = tierCounts[tier] || 0;
      const countEl = chip.querySelector('[data-tier-count]');
      if (countEl) countEl.textContent = count;
      chip.style.display = count === 0 ? 'none' : 'inline-block';
    });
  }

  function applyFilters() {
    const visibleCards = [];
    $cards.forEach(card => {
      if (matches(card)) {
        card.style.display = '';
        visibleCards.push(card);
      } else {
        card.style.display = 'none';
      }
    });
    recomputeCounts(visibleCards);
    recomputeJourneyRow(visibleCards);
    recomputeV3(visibleCards);

    // toggle visual on dropdowns + reset btn
    let anyActive = false;
    $selects.forEach(sel => {
      if (!sel) return;
      if (sel.value) { sel.classList.add('filter-on'); anyActive = true; }
      else sel.classList.remove('filter-on');
    });
    if ($resetBtn) {
      if (anyActive) {
        $resetBtn.classList.add('active');
        $resetBtn.removeAttribute('hidden');
      } else {
        $resetBtn.classList.remove('active');
        $resetBtn.setAttribute('hidden', '');
      }
    }

    writeURLState();
  }

  function reset() {
    $selects.forEach(sel => { if (sel) sel.value = ''; });
    applyFilters();
  }

  // wire events
  $selects.forEach(sel => sel && sel.addEventListener('change', applyFilters));
  if ($resetBtn) $resetBtn.addEventListener('click', reset);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') reset();
  });

  // on load: read URL state and apply
  readURLState();
  applyFilters();
})();
</script>
"""


def render_topnav(packs: list[dict]) -> str:
    """Global top nav — CJI Pulse brand + canvas-header dropdowns + utility cluster.

    HOL-10 phase 1: Product / Owner / Domain dropdowns functional (filter JS).
    HOL-10 phase 2: Search overlay wired ("/" keypress or click).
    HOL-10 phase 3: Notifications dropdown · Canvas-guide drawer · Settings
    panel · Avatar menu — all four panels behind interactive buttons with
    data-panel attributes, opened/closed by PANEL_JS.

    Date filter still cosmetic (packs don't carry detection timestamps —
    blocked on PULSE-93).
    """
    domains = sorted({(p["hypothesis"] or {}).get("screen_id", "").split(".")[0]
                       for p in packs if (p["hypothesis"] or {}).get("screen_id")})
    owners = sorted({a for p in packs for a in p["meta"].get("authors", [])})

    # Dimension name lives INSIDE the option label so we don't need an
    # external <label> next to each <select>. Self-describing dropdowns.
    product_opts = f'<option value="">Product · all packs · {len(packs)}</option>\n'
    sorted_packs = sorted(packs, key=lambda p: (p["hypothesis"] or {}).get("cell_id", 99))
    for p in sorted_packs:
        h = p["hypothesis"] or {}
        cell = h.get("cell_id", "?")
        sig = h.get("signature_id", "—").replace("_", " ")
        product_opts += (
            f'<option value="{p["meta"]["pack_name"]}">'
            f'Product · cell {cell} · {sig}</option>\n'
        )

    owner_opts = f'<option value="">Owner · all teams · {len(owners)}</option>\n'
    for o in owners:
        owner_opts += f'<option value="{o}">Owner · {o}</option>\n'

    domain_opts = f'<option value="">Domain · all journeys · {len(domains)}</option>\n'
    for d in domains:
        domain_opts += f'<option value="{d}">Domain · {d}</option>\n'

    # Notification count — synthesized from observable engine state below in
    # render_notif_panel(); we count unread events here so the badge stays in sync.
    notif_count = len(_synthesise_notifications(packs))
    notif_badge = (
        f'<span class="topnav-icon-badge">{notif_count}</span>' if notif_count else ""
    )

    return f'''
<header class="app-topnav">
  <div class="topnav-brand">
    <span class="brand-logo">CJI&nbsp;PULSE</span>
  </div>
  <div class="topnav-controls">
    <select class="topnav-select active" id="filter-product" data-filter="packname">
      {product_opts}
    </select>
    <select class="topnav-select active" id="filter-owner" data-filter="author">
      {owner_opts}
    </select>
    <select class="topnav-select active" id="filter-domain" data-filter="domain">
      {domain_opts}
    </select>
    <select class="topnav-select" disabled title="Date — packs don't yet carry detection timestamps (blocked on PULSE-93)">
      <option>Date · last 7 days</option>
    </select>
    <button class="topnav-reset" id="filter-reset" type="button" title="Reset filters (Esc)" hidden>Reset</button>
  </div>
  <div class="topnav-utility">
    <button class="topnav-icon" id="btn-search" data-panel="search-overlay" type="button" title="Search packs (click or press /)">⌕</button>
    <button class="topnav-icon" id="btn-notif" data-panel="panel-notif" type="button" title="Notifications · {notif_count} unread">🔔{notif_badge}</button>
    <button class="topnav-icon" id="btn-guide" data-panel="panel-guide" type="button" title="Canvas guide — slot architecture + decision flow">?</button>
    <button class="topnav-icon" id="btn-settings" data-panel="panel-settings" type="button" title="Settings — display preferences + methodology versions">⚙</button>
    <button class="topnav-avatar" id="btn-avatar" data-panel="panel-avatar" type="button" title="Hussain Ahmed — project links + about">HA</button>
  </div>
</header>
'''


def _synthesise_notifications(packs: list[dict]) -> list[dict]:
    """Surface observable engine-state events as notifications.

    For the dev preview these aren't pushed events — they're derived from
    state the engine can observe at render time. Production would pull from
    an event log; for now this teaches the user what kinds of events the
    notifications surface will carry.
    """
    cell_score_sample = get_pack_cell(packs[0]["meta"]["pack_name"]) if packs else None
    events: list[dict] = []

    events.append({
        "type": "system",
        "color": "var(--green)",
        "title": "Pulse v2 design spine shipped",
        "detail": "10 tickets closed today (PULSE-99 through 106 + HOL-9 + HOL-11)",
        "ago": "just now",
    })
    events.append({
        "type": "curator",
        "color": "var(--amber)",
        "title": "Chronicle library awaiting curator review",
        "detail": "10 CHR-friction entries pending_human_review — Risk matcher fails closed until verified",
        "ago": "today",
    })
    if cell_score_sample is not None:
        events.append({
            "type": "engine",
            "color": "var(--blue)",
            "title": "Placement matrix online",
            "detail": (
                f"Diagnosis v{cell_score_sample.diagnosis.methodology_version} · "
                f"Risk v{cell_score_sample.risk.methodology_version} · "
                f"Value v{cell_score_sample.value.methodology_version}"
            ),
            "ago": "today",
        })
    events.append({
        "type": "registry",
        "color": "var(--teal)",
        "title": f"{len(packs)} packs canvas-complete",
        "detail": "PULSE-104 backfill — every pack declares actors / value_inputs / risk_inputs",
        "ago": "today",
    })

    return events


def render_notif_panel(packs: list[dict]) -> str:
    """🔔 Notifications popover — engine-state events."""
    events = _synthesise_notifications(packs)
    items = ""
    for e in events:
        items += f'''
<div class="topnav-panel-item">
  <span class="topnav-panel-dot" style="background:{e["color"]};"></span>
  <div class="topnav-panel-item-body">
    <div class="topnav-panel-item-title">{e["title"]}</div>
    <div class="topnav-panel-item-detail">{e["detail"]}</div>
  </div>
  <span class="topnav-panel-item-ago">{e["ago"]}</span>
</div>'''
    return f'''
<div class="topnav-popover" id="panel-notif" data-anchor="btn-notif" hidden role="dialog" aria-label="Notifications">
  <div class="topnav-panel-header">
    <span class="topnav-panel-title">NOTIFICATIONS</span>
    <span class="topnav-panel-sub">{len(events)} unread · engine-state events</span>
  </div>
  <div class="topnav-panel-body">{items}</div>
  <div class="topnav-panel-footer">
    Notifications surface engine-observable events. Production would
    pull from an event log; this dev preview synthesises from current state.
  </div>
</div>'''


def render_guide_drawer() -> str:
    """? Canvas-guide right-side drawer — explains canvas slot architecture."""
    return '''
<aside class="topnav-drawer" id="panel-guide" data-anchor="btn-guide" hidden role="dialog" aria-label="Canvas guide">
  <div class="topnav-panel-header">
    <span class="topnav-panel-title">CANVAS — three slot classes</span>
    <span class="topnav-panel-sub">Holter understands canvas; speaks in briefing form</span>
  </div>
  <div class="topnav-panel-body">

    <div class="guide-section">
      <div class="guide-label" style="color:var(--blue);">DECLARED</div>
      <div class="guide-meta">Author writes · validator checks</div>
      <ul class="guide-list">
        <li><code>actors</code> — investigation_consumer / ml_engineer / mrm_reviewer / compliance_reviewer</li>
        <li><code>value_inputs</code> — severity_class · vulnerable_cohort_sensitivity · population_segment_addressed</li>
        <li><code>risk_inputs</code> — regulatory_taxonomies · policy_areas · chronicle_precedents</li>
        <li><code>signature_id</code> · <code>screen_id</code> · <code>cell_id</code></li>
        <li><code>analytic</code> · <code>cohort_axes</code> · <code>evidence_required</code> · <code>fairness</code></li>
      </ul>
    </div>

    <div class="guide-section">
      <div class="guide-label" style="color:var(--green);">COMPUTED</div>
      <div class="guide-meta">Engine derives at runtime · reproducible</div>
      <ul class="guide-list">
        <li><code>Diagnosis</code> — SUPPORT_PROBLEM / JOURNEY_PROBLEM / BOTH / INCONCLUSIVE (PULSE-105)</li>
        <li><code>Risk tier</code> — NOMINAL / WATCH / ESCALATE / REGULATORY-FLAG (PULSE-99)</li>
        <li><code>Value tier</code> — NOMINAL / WATCH / SIGNIFICANT / COMMERCIAL-OPPORTUNITY (PULSE-101)</li>
        <li><code>Action tier</code> — ACUTE / REGULATORY-FLAG / COMMERCIAL-OPPORTUNITY / WATCH / NOMINAL / NEEDS_MORE_DATA</li>
        <li><code>methodology_version</code> + <code>inputs_hash</code> — pinned in every output for audit reproducibility</li>
      </ul>
    </div>

    <div class="guide-section">
      <div class="guide-label" style="color:var(--amber);">ATTACHED</div>
      <div class="guide-meta">Organisational fact · lives outside pack</div>
      <ul class="guide-list">
        <li><code>bank_policy.escalation_thresholds</code> — affected_customers_7d_window · vulnerable_cohort_overrep_floor (PULSE-102)</li>
        <li><code>bank_policy.policy_areas</code> — bank-internal policy register mapped to regulatory taxonomies</li>
        <li><code>bank_policy.deployment_id</code> — opaque token, never the bank's name</li>
        <li><code>chronicle_library</code> — curator-pending until <code>verification_status: verified</code></li>
      </ul>
    </div>

    <div class="guide-section" style="border-top:1px solid var(--border);padding-top:14px;">
      <div class="guide-label" style="color:var(--text-2);">DECISION FLOW</div>
      <div class="guide-meta" style="margin-bottom:8px;">Order matters — Diagnosis can override the 2×2</div>
      <div class="guide-flow">
        <span class="guide-flow-step" style="border-color:var(--green);color:var(--green);">DIAGNOSIS</span>
        <span class="guide-flow-arrow">→</span>
        <span class="guide-flow-step" style="border-color:var(--red);color:var(--red);">RISK</span>
        <span class="guide-flow-arrow">→</span>
        <span class="guide-flow-step" style="border-color:var(--amber);color:var(--amber);">VALUE</span>
        <span class="guide-flow-arrow">→</span>
        <span class="guide-flow-step" style="border-color:var(--blue);color:var(--blue);">ACTION TIER</span>
      </div>
      <div class="guide-meta" style="margin-top:8px;">
        JOURNEY_PROBLEM → "fix the journey" verb regardless of Action tier.
        INCONCLUSIVE → NEEDS_MORE_DATA regardless of how appealing the cell looks.
      </div>
    </div>

  </div>
  <div class="topnav-panel-footer">
    Methodology design docs:
    <code>pulse/diagnosis/DIAGNOSIS_DESIGN.md</code> ·
    <code>pulse/risk/RISK_DESIGN.md</code> ·
    <code>pulse/value/VALUE_DESIGN.md</code>
  </div>
</aside>'''


def render_settings_panel(packs: list[dict]) -> str:
    """⚙ Settings popover — display preferences + methodology versions."""
    # Pull real methodology versions from a sample pack's cell score
    cell = get_pack_cell(packs[0]["meta"]["pack_name"]) if packs else None
    if cell is not None:
        d_ver = cell.diagnosis.methodology_version
        r_ver = cell.risk.methodology_version
        v_ver = cell.value.methodology_version
    else:
        d_ver = r_ver = v_ver = "unavailable"

    now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d %H:%M UTC")

    return f'''
<div class="topnav-popover" id="panel-settings" data-anchor="btn-settings" hidden role="dialog" aria-label="Settings">
  <div class="topnav-panel-header">
    <span class="topnav-panel-title">SETTINGS</span>
    <span class="topnav-panel-sub">Display preferences · build info</span>
  </div>
  <div class="topnav-panel-body">

    <div class="settings-section">
      <div class="settings-label">DISPLAY PREFERENCES</div>
      <label class="settings-toggle">
        <input type="checkbox" class="settings-toggle-input" data-toggle-class="hide-v3-scoring" id="toggle-scoring">
        <span class="settings-toggle-label">Hide Value/Risk scoring panels (V3)</span>
      </label>
      <label class="settings-toggle">
        <input type="checkbox" class="settings-toggle-input" data-toggle-class="hide-pack-badges" id="toggle-badges">
        <span class="settings-toggle-label">Hide per-pack tier badges</span>
      </label>
      <label class="settings-toggle">
        <input type="checkbox" class="settings-toggle-input" data-toggle-class="hide-placement-matrix" id="toggle-matrix">
        <span class="settings-toggle-label">Hide placement matrix (V3)</span>
      </label>
    </div>

    <div class="settings-section">
      <div class="settings-label">METHODOLOGY VERSIONS</div>
      <div class="settings-row"><span>Diagnosis</span><code>v{d_ver}</code></div>
      <div class="settings-row"><span>Risk</span><code>v{r_ver}</code></div>
      <div class="settings-row"><span>Value</span><code>v{v_ver}</code></div>
    </div>

    <div class="settings-section">
      <div class="settings-label">BUILD INFO</div>
      <div class="settings-row"><span>Packs registered</span><code>{len(packs)}</code></div>
      <div class="settings-row"><span>Briefing rendered</span><code>{now}</code></div>
      <div class="settings-row"><span>Engine version</span><code>pulse v1.0.0</code></div>
    </div>

  </div>
  <div class="topnav-panel-footer">
    Toggles persist for this session only — refresh clears.
    Design doc: <code>CLAUDE.md</code> § HOL-1 identity lock.
  </div>
</div>'''


def render_avatar_menu() -> str:
    """HA Avatar menu — user info + project links + about."""
    return '''
<div class="topnav-popover topnav-popover-narrow" id="panel-avatar" data-anchor="btn-avatar" hidden role="menu" aria-label="User menu">
  <div class="topnav-panel-header">
    <span class="topnav-panel-title">HUSSAIN AHMED</span>
    <span class="topnav-panel-sub">CJI · Holter / Pulse</span>
  </div>
  <div class="topnav-panel-body">

    <div class="avatar-section">
      <div class="avatar-label">PROJECT BOARDS</div>
      <a class="avatar-link" href="https://cjipro.atlassian.net/jira/software/projects/PULSE" target="_blank" rel="noopener">
        <span class="avatar-link-bullet" style="background:var(--blue);"></span>
        <span>PULSE — engine (Scrum)</span>
        <span class="avatar-link-arrow">↗</span>
      </a>
      <a class="avatar-link" href="https://cjipro.atlassian.net/jira/software/projects/HOL/boards/134" target="_blank" rel="noopener">
        <span class="avatar-link-bullet" style="background:var(--amber);"></span>
        <span>HOL — Holter (Kanban)</span>
        <span class="avatar-link-arrow">↗</span>
      </a>
    </div>

    <div class="avatar-section">
      <div class="avatar-label">SISTER REPOS</div>
      <div class="avatar-row"><code>cjipro/holter</code><span>this repo</span></div>
      <div class="avatar-row"><code>cjipro/mil_streamlit</code><span>MIL · while-sleeping</span></div>
      <div class="avatar-row"><code>cjipro/taq-app</code><span>TAQ synthetic env</span></div>
    </div>

    <div class="avatar-section">
      <div class="avatar-label">ABOUT</div>
      <div class="avatar-row" style="font-size:10px;color:#5A7E92;line-height:1.5;">
        Holter = the bundle. Pulse = the engine. Briefing = the voice
        (HOL-1 identity lock). Project-split rule: framework → PULSE,
        surface → HOL.
      </div>
    </div>

  </div>
</div>'''


def render_sidebar(packs: list[dict]) -> str:
    """Box 0 — left vertical sidebar with placeholder controls."""
    taxonomy = load_journey_taxonomy()  # {journey_id: category}
    # journeys present in at least one pack — pre-tick them in the multi-select
    covered_screens = {(p["hypothesis"] or {}).get("screen_id", "") for p in packs}
    covered_journeys = {s.split(".")[0] for s in covered_screens if s}

    # category dot legend order matches journey_taxonomy.yaml
    journey_items = ""
    for jid, cat in taxonomy.items():
        checked = "checked" if jid in covered_journeys else ""
        journey_items += (
            f'<label class="sidebar-multi-item" title="{cat}">'
            f'<input type="checkbox" {checked} disabled>'
            f'<span>{jid}</span>'
            f'<span class="cat-dot cat-{cat}"></span>'
            f'</label>'
        )

    return f'''
<aside class="topbar-box sidebar">
  <div class="topbar-box-header" style="background:#001828;">
    <span class="topbar-box-title" style="color:#7AACBF;">BOX 0 · CONTROLS</span>
    <span style="font-size:9px;color:#3A6A7F;">placeholder</span>
  </div>
  <div class="sidebar-body">
    <div class="sidebar-section">
      <div class="sidebar-section-label">
        Journey <span class="badge">{len(covered_journeys)} of {len(taxonomy)}</span>
      </div>
      <div class="sidebar-multiselect">{journey_items}</div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-section-label">Time period</div>
      <select class="sidebar-select" disabled>
        <option>Last 24 hours</option>
        <option selected>Last 7 days</option>
        <option>Last 30 days</option>
        <option>Last quarter</option>
        <option>Custom range…</option>
      </select>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-section-label">ML model</div>
      <select class="sidebar-select" disabled>
        <option selected>deterministic · v1</option>
        <option disabled>llm_augmented · v2 (gated)</option>
      </select>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-section-label">Reserved <span class="badge">future</span></div>
      <div style="display:flex;flex-direction:column;gap:4px;font-family:var(--mono);font-size:10px;color:var(--text-3);">
        <span>· cohort axis</span>
        <span>· confidence floor</span>
        <span>· fairness gate</span>
      </div>
    </div>
  </div>
  <div class="sidebar-actions">
    <button class="sidebar-btn primary" disabled>Apply</button>
    <button class="sidebar-btn" disabled>Reset</button>
  </div>
</aside>
'''


_DIAGNOSIS_COLORS = {
    "SUPPORT_PROBLEM": "var(--green)",     # AI deployment is the right intervention
    "JOURNEY_PROBLEM": "var(--amber)",     # fix the journey itself
    "BOTH": "var(--blue)",                 # combination
    "INCONCLUSIVE": "#7A7A7A",             # insufficient control-arm data
}

_ACTION_COLORS = {
    "ACUTE": "var(--red)",                 # high value × high risk — guardrails
    "REGULATORY-FLAG": "var(--amber)",     # high risk × low value — don't deploy
    "COMMERCIAL-OPPORTUNITY": "var(--green)",  # high value × low risk — deploy first
    "WATCH": "var(--teal)",                # mid both
    "NOMINAL": "#5A6E7A",                  # low both
    "NEEDS_MORE_DATA": "#7A7A7A",          # diagnosis override
}

# Severity-ascending palette per tier-word for Risk and Value. Tier-words
# the two methodologies share (NOMINAL, WATCH) carry identical colours
# across both axes so the visual language stays consistent. Top-tier
# colours diverge by meaning: Risk's REGULATORY-FLAG is red (precautionary),
# Value's COMMERCIAL-OPPORTUNITY is green (opportunity).
_RISK_COLORS = {
    "NOMINAL": "#5A6E7A",
    "WATCH": "var(--teal)",
    "ESCALATE": "var(--amber)",
    "REGULATORY-FLAG": "var(--red)",
}

_VALUE_COLORS = {
    "NOMINAL": "#5A6E7A",
    "WATCH": "var(--teal)",
    "SIGNIFICANT": "var(--amber)",
    "COMMERCIAL-OPPORTUNITY": "var(--green)",
}


def _build_pack_cell_index() -> dict[str, "Any"]:
    """Run the placement scenario once and index its cells by pack_name
    (which matches the pack directory name and the on-disk pack_name in
    metadata.yaml). Returns {} on import failure — callers degrade
    gracefully rather than raising. lru_cached per process: one engine
    run per briefing render."""
    try:
        from pulse.scenarios.agentic_ai_placement import run_placement_scenario
        import yaml as _yaml
        scenario_path = REPO / "pulse" / "scenarios" / "agentic_ai_placement" / "scenario.yaml"
        with scenario_path.open("r", encoding="utf-8") as f:
            scenario = _yaml.safe_load(f)
        # pack_dir per scenario cell, in the same order as matrix.cells
        pack_dirs = [c["pack_dir"] for c in scenario["cells"]]
        matrix = run_placement_scenario()
        return {pack_dir: cell for pack_dir, cell in zip(pack_dirs, matrix.cells)}
    except Exception:  # pragma: no cover — diagnostic fallback
        return {}


_PACK_CELL_INDEX: dict[str, Any] | None = None


def get_pack_cell(pack_name: str) -> Any:
    """Return the PlacementCell for a pack, or None if unavailable.
    Cached at module level so the engine runs once per render."""
    global _PACK_CELL_INDEX
    if _PACK_CELL_INDEX is None:
        _PACK_CELL_INDEX = _build_pack_cell_index()
    return _PACK_CELL_INDEX.get(pack_name)


def _tier_badge_html(label: str, tier_word: str, color_map: dict[str, str]) -> str:
    """Compact inline tier badge: '<label> · <tier>' with colour from map."""
    color = color_map.get(tier_word, "#7A7A7A")
    return (
        f'<span style="display:inline-block;padding:2px 6px;margin-right:4px;'
        f'font-size:9px;font-weight:700;letter-spacing:0.5px;background:#001828;'
        f'color:{color};border:1px solid {color};border-radius:2px;">'
        f'{label} · {tier_word}</span>'
    )


def render_placement_matrix(packs: list[dict]) -> str:
    """V3 — Agentic AI placement matrix (PULSE-106 worked example).

    Runs the full v0 engine spine (Diagnosis → Risk → Value → Action tier)
    against the scenario.yaml fixtures and renders the placement matrix as a
    briefing block. Fails closed with a banner if PULSE-106 is unavailable
    so the rest of the briefing still renders.

    Filed under HOL-11.
    """
    try:
        from pulse.scenarios.agentic_ai_placement import run_placement_scenario
        matrix = run_placement_scenario()
    except Exception as e:  # pragma: no cover — diagnostic fallback
        return f'''
<div class="topbar-box">
  <div class="topbar-box-header">
    <span class="topbar-box-title">AGENTIC AI PLACEMENT MATRIX</span>
    <span style="font-size:10px;color:var(--amber);">PULSE-106 unavailable</span>
  </div>
  <div class="topbar-box-body">
    <div style="padding:14px;color:var(--amber);font-size:12px;">
      Worked-example scenario could not be loaded: {str(e)[:200]}
      <br/><br/>
      The placement matrix renders here when
      <code>pulse.scenarios.agentic_ai_placement</code> is importable. Run
      <code>py -m pulse.scenarios.agentic_ai_placement.run</code> to see the
      Markdown form independently.
    </div>
  </div>
</div>'''

    # 2x2 aggregate counts (Risk × Value bands)
    high_value = {"SIGNIFICANT", "COMMERCIAL-OPPORTUNITY"}
    high_risk = {"ESCALATE", "REGULATORY-FLAG"}

    n_acute = sum(
        1 for c in matrix.cells
        if c.value.tier in high_value and c.risk.tier in high_risk
        and c.diagnosis.diagnosis != "INCONCLUSIVE"
    )
    n_regflag = sum(
        1 for c in matrix.cells
        if c.value.tier not in high_value and c.risk.tier in high_risk
        and c.diagnosis.diagnosis != "INCONCLUSIVE"
    )
    n_commercial = sum(
        1 for c in matrix.cells
        if c.value.tier in high_value and c.risk.tier not in high_risk
        and c.diagnosis.diagnosis != "INCONCLUSIVE"
    )
    n_nominal_watch = sum(
        1 for c in matrix.cells
        if c.value.tier not in high_value and c.risk.tier not in high_risk
        and c.diagnosis.diagnosis != "INCONCLUSIVE"
    )
    n_inconclusive = sum(
        1 for c in matrix.cells if c.diagnosis.diagnosis == "INCONCLUSIVE"
    )

    # Per-cell row list. pack_name is reconstructed as "<journey>__<signature>"
    # to match the seed pack directory naming convention; rows are filterable
    # via data-packname when the topnav filters fire (HOL-10 phase 4).
    rows_html = ""
    for c in matrix.cells:
        d_color = _DIAGNOSIS_COLORS.get(c.diagnosis.diagnosis, "#7A7A7A")
        a_color = _ACTION_COLORS.get(c.action_tier, "#7A7A7A")
        hash_short = c.risk.inputs_hash[:7]
        pack_name = f"{c.journey_id}__{c.signature_id}"
        rows_html += f'''
<tr data-packname="{pack_name}" data-action-tier="{c.action_tier}" data-diagnosis="{c.diagnosis.diagnosis}">
  <td style="padding:6px 10px;font-family:'DM Mono',monospace;font-size:10px;color:#7AACBF;">{c.journey_id}</td>
  <td style="padding:6px 10px;font-family:'DM Mono',monospace;font-size:10px;color:#7AACBF;">{c.signature_id.replace("_", " ")}</td>
  <td style="padding:6px 8px;"><span style="display:inline-block;padding:3px 8px;font-size:9px;font-weight:700;letter-spacing:0.5px;background:#001828;color:{d_color};border:1px solid {d_color};border-radius:2px;">{c.diagnosis.diagnosis}</span></td>
  <td style="padding:6px 8px;text-align:center;font-size:10px;color:#7AACBF;">{c.risk.tier}</td>
  <td style="padding:6px 8px;text-align:center;font-size:10px;color:#7AACBF;">{c.value.tier}</td>
  <td style="padding:6px 8px;"><span style="display:inline-block;padding:3px 8px;font-size:9px;font-weight:700;letter-spacing:0.5px;background:{a_color};color:#001828;border-radius:2px;">{c.action_tier}</span></td>
  <td style="padding:6px 10px;font-size:11px;color:#A8CDDE;">{c.placement_recommendation}</td>
  <td style="padding:6px 10px;font-family:'DM Mono',monospace;font-size:9px;color:#3A6A7F;">{hash_short}</td>
</tr>'''

    return f'''
<div class="topbar-box" data-panel-id="placement-matrix">
  <div class="topbar-box-header">
    <span class="topbar-box-title">AGENTIC AI PLACEMENT MATRIX</span>
    <span style="font-size:10px;color:#3A6A7F;">
      Pulse v0 engine spine · Diagnosis → Risk → Value → CLARK-style Action tier · {len(matrix.cells)} cells
    </span>
  </div>
  <div class="topbar-box-body">
    <!-- 2x2 aggregate -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px;">
      <div style="border:1px solid var(--border);border-top:3px solid var(--red);padding:10px;background:#001020;">
        <div style="font-size:9px;color:#7AACBF;letter-spacing:0.5px;text-transform:uppercase;">High Risk · High Value</div>
        <div style="font-size:28px;font-weight:700;color:var(--red);margin:4px 0;" data-aggregate="action-acute">{n_acute}</div>
        <div style="font-size:10px;color:#A8CDDE;font-weight:600;">ACUTE</div>
        <div style="font-size:9px;color:#5A7E92;">Deploy AI with heavy guardrails</div>
      </div>
      <div style="border:1px solid var(--border);border-top:3px solid var(--amber);padding:10px;background:#001020;">
        <div style="font-size:9px;color:#7AACBF;letter-spacing:0.5px;text-transform:uppercase;">High Risk · Low Value</div>
        <div style="font-size:28px;font-weight:700;color:var(--amber);margin:4px 0;" data-aggregate="action-regflag">{n_regflag}</div>
        <div style="font-size:10px;color:#A8CDDE;font-weight:600;">REGULATORY-FLAG</div>
        <div style="font-size:9px;color:#5A7E92;">Don't deploy AI here</div>
      </div>
      <div style="border:1px solid var(--border);border-top:3px solid var(--green);padding:10px;background:#001020;">
        <div style="font-size:9px;color:#7AACBF;letter-spacing:0.5px;text-transform:uppercase;">Low Risk · High Value</div>
        <div style="font-size:28px;font-weight:700;color:var(--green);margin:4px 0;" data-aggregate="action-commercial">{n_commercial}</div>
        <div style="font-size:10px;color:#A8CDDE;font-weight:600;">COMMERCIAL-OPPORTUNITY</div>
        <div style="font-size:9px;color:#5A7E92;">Deploy AI here first</div>
      </div>
      <div style="border:1px solid var(--border);border-top:3px solid #5A6E7A;padding:10px;background:#001020;">
        <div style="font-size:9px;color:#7AACBF;letter-spacing:0.5px;text-transform:uppercase;">Low Risk · Low Value</div>
        <div style="font-size:28px;font-weight:700;color:#A8CDDE;margin:4px 0;" data-aggregate="action-nominal-watch">{n_nominal_watch}</div>
        <div style="font-size:10px;color:#A8CDDE;font-weight:600;">NOMINAL / WATCH</div>
        <div style="font-size:9px;color:#5A7E92;">Not worth deploying</div>
      </div>
    </div>
    <div style="font-size:11px;color:#5A7E92;margin-bottom:10px;">
      <span style="display:inline-block;width:8px;height:8px;background:#7A7A7A;border-radius:50%;margin-right:4px;vertical-align:middle;"></span>
      <span data-aggregate="action-inconclusive">{n_inconclusive}</span> cells diagnosed INCONCLUSIVE — control-arm data too thin to call (Diagnosis overrides the 2x2)
    </div>

    <!-- Per-cell row table -->
    <table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead>
        <tr style="border-bottom:1px solid var(--border);">
          <th style="padding:6px 10px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">JOURNEY</th>
          <th style="padding:6px 10px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">SIGNATURE</th>
          <th style="padding:6px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">DIAGNOSIS</th>
          <th style="padding:6px 8px;text-align:center;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">RISK</th>
          <th style="padding:6px 8px;text-align:center;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">VALUE</th>
          <th style="padding:6px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">ACTION</th>
          <th style="padding:6px 10px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">PLACEMENT</th>
          <th style="padding:6px 10px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">HASH</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>

    <!-- Lineage footer -->
    <div style="margin-top:14px;padding-top:10px;border-top:1px solid var(--border);font-size:10px;color:#5A7E92;">
      <span style="color:#7AACBF;">LINEAGE:</span>
      Diagnosis v{matrix.diagnosis_methodology_version}
      · Risk v{matrix.risk_methodology_version}
      · Value v{matrix.value_methodology_version}
      · deployment <span style="font-family:'DM Mono',monospace;color:#7AACBF;">{matrix.deployment_id}</span>
      · per-cell inputs_hash above (first 7 chars; full SHA-256 in audit bundle)
    </div>
  </div>
</div>'''


def render_value_scoring_panel(packs: list[dict]) -> str:
    """V3 — per-pack Value tier breakdown (PULSE-101).

    Mirrors the Friction Risk Score panel shape. Shows tier counts + per-
    pack rows with the adjustments that fired (large_affected_population /
    high_frequency_per_user / vulnerable_cohort_concentrated /
    large_counterfactual_baseline).
    """
    sorted_packs = sorted(
        packs, key=lambda p: (p["hypothesis"] or {}).get("cell_id", 99)
    )
    rows_html = ""
    tier_counts: dict[str, int] = {}
    for p in sorted_packs:
        cell_score = get_pack_cell(p["meta"]["pack_name"])
        if cell_score is None:
            continue
        v = cell_score.value
        tier_counts[v.tier] = tier_counts.get(v.tier, 0) + 1
        adjustments = ", ".join(
            a.replace("_", " ") for a in v.adjustments_applied
        ) or "—"
        h = p["hypothesis"] or {}
        rows_html += f'''
<tr data-packname="{p["meta"]["pack_name"]}" data-value-tier="{v.tier}">
  <td style="padding:5px 8px;font-size:10px;color:#7AACBF;font-family:'DM Mono',monospace;">cell {h.get("cell_id", "?")}</td>
  <td style="padding:5px 8px;font-size:10px;color:#A8CDDE;">{p["meta"]["pack_name"]}</td>
  <td style="padding:5px 8px;">{_tier_badge_html("VALUE", v.tier, _VALUE_COLORS)}</td>
  <td style="padding:5px 8px;font-size:10px;color:#5A7E92;">base: {v.base_tier} · adjustments: {adjustments}</td>
</tr>'''

    if not rows_html:
        return _empty_scoring_panel(
            "VALUE SCORING",
            "Per-pack value tier requires PULSE-101 + PULSE-104 + PULSE-106",
        )

    counts_html = "".join(
        f'<span data-tier-chip="value:{t}" style="display:inline-block;margin-right:14px;font-size:11px;">'
        f'<span style="display:inline-block;width:8px;height:8px;background:{_VALUE_COLORS[t]};vertical-align:middle;margin-right:4px;border-radius:1px;"></span>'
        f'<span style="color:#A8CDDE;">{t}</span> '
        f'<span style="color:#7AACBF;font-weight:700;" data-tier-count>{c}</span></span>'
        for t, c in sorted(tier_counts.items())
    )

    return f'''
<div class="topbar-box" data-panel-id="value-scoring">
  <div class="topbar-box-header">
    <span class="topbar-box-title">VALUE SCORING</span>
    <span style="font-size:10px;color:#3A6A7F;">
      Pulse Value methodology v0 · per-pack tier · severity / population / frequency / cohort / counterfactual
    </span>
  </div>
  <div class="topbar-box-body">
    <div style="padding-bottom:10px;" data-tier-counts-band>{counts_html}</div>
    <table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead>
        <tr style="border-bottom:1px solid var(--border);">
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">CELL</th>
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">PACK</th>
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">TIER</th>
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">BREAKDOWN</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>'''


def render_risk_scoring_panel(packs: list[dict]) -> str:
    """V3 — per-pack Risk tier breakdown (PULSE-99).

    Shows tier counts + per-pack rows with regulatory taxonomies matched,
    adjustments fired, and Chronicle precedent matches. Mirrors the
    Value Scoring panel shape.
    """
    sorted_packs = sorted(
        packs, key=lambda p: (p["hypothesis"] or {}).get("cell_id", 99)
    )
    rows_html = ""
    tier_counts: dict[str, int] = {}
    for p in sorted_packs:
        cell_score = get_pack_cell(p["meta"]["pack_name"])
        if cell_score is None:
            continue
        r = cell_score.risk
        tier_counts[r.tier] = tier_counts.get(r.tier, 0) + 1
        # Trim regulatory taxonomy codes to last segment for readability.
        regs = ", ".join(
            code.split(".")[-1] for code in r.regulatory_matches
        ) or "—"
        adjustments = ", ".join(
            a.replace("_", " ") for a in r.adjustments_applied
        ) or "—"
        chronicle = (
            f'{len(r.chronicle_matches)} matched' if r.chronicle_matches
            else "no verified matches"
        )
        h = p["hypothesis"] or {}
        rows_html += f'''
<tr data-packname="{p["meta"]["pack_name"]}" data-risk-tier="{r.tier}">
  <td style="padding:5px 8px;font-size:10px;color:#7AACBF;font-family:'DM Mono',monospace;">cell {h.get("cell_id", "?")}</td>
  <td style="padding:5px 8px;">{_tier_badge_html("RISK", r.tier, _RISK_COLORS)}</td>
  <td style="padding:5px 8px;font-size:10px;color:#A8CDDE;">{regs}</td>
  <td style="padding:5px 8px;font-size:10px;color:#5A7E92;">{adjustments}</td>
  <td style="padding:5px 8px;font-size:10px;color:#5A7E92;">{chronicle}</td>
</tr>'''

    if not rows_html:
        return _empty_scoring_panel(
            "RISK SCORING",
            "Per-pack risk tier requires PULSE-99 + PULSE-104 + PULSE-106",
        )

    counts_html = "".join(
        f'<span data-tier-chip="risk:{t}" style="display:inline-block;margin-right:14px;font-size:11px;">'
        f'<span style="display:inline-block;width:8px;height:8px;background:{_RISK_COLORS[t]};vertical-align:middle;margin-right:4px;border-radius:1px;"></span>'
        f'<span style="color:#A8CDDE;">{t}</span> '
        f'<span style="color:#7AACBF;font-weight:700;" data-tier-count>{c}</span></span>'
        for t, c in sorted(tier_counts.items())
    )

    return f'''
<div class="topbar-box" data-panel-id="risk-scoring">
  <div class="topbar-box-header">
    <span class="topbar-box-title">RISK SCORING</span>
    <span style="font-size:10px;color:#3A6A7F;">
      Pulse Risk methodology v0 · per-pack tier · regulatory taxonomies / policy thresholds / chronicle precedents
    </span>
  </div>
  <div class="topbar-box-body">
    <div style="padding-bottom:10px;" data-tier-counts-band>{counts_html}</div>
    <table style="width:100%;border-collapse:collapse;font-size:11px;">
      <thead>
        <tr style="border-bottom:1px solid var(--border);">
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">CELL</th>
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">TIER</th>
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">REGULATORY MATCHES</th>
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">ADJUSTMENTS FIRED</th>
          <th style="padding:5px 8px;text-align:left;font-size:9px;color:#3A6A7F;letter-spacing:0.5px;">CHRONICLE</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>'''


def _empty_scoring_panel(title: str, hint: str) -> str:
    """Fallback shape when the engine isn't loaded — keeps page layout intact."""
    return f'''
<div class="topbar-box">
  <div class="topbar-box-header">
    <span class="topbar-box-title">{title}</span>
    <span style="font-size:10px;color:var(--amber);">engine unavailable</span>
  </div>
  <div class="topbar-box-body">
    <div style="padding:14px;color:var(--amber);font-size:12px;">
      {hint}. The scenario import path is set in
      <code>holter/preview/render_mil_briefing.py</code> at module top.
    </div>
  </div>
</div>'''


def render_clark_protocol(packs: list[dict]) -> str:
    n_positive = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") != "negative")
    n_negative = sum(1 for p in packs if (p["hypothesis"] or {}).get("ground_truth_expectation") == "negative")
    return f'''
<div class="topbar-box">
  <div class="topbar-box-header">
    <span class="topbar-box-title">CONFIDENCE PROTOCOL</span>
    <span style="font-size:10px;color:#3A6A7F;">Pulse synthesis tier · 4-level escalation</span>
  </div>
  <div class="topbar-box-body">
    <div class="clark-strip">
      <div class="clark-tile" style="border-top-color:#CC3333;">
        <div class="clark-count" style="color:#CC3333;" data-aggregate="clark-calibration-fail">0</div>
        <div class="clark-tier">PULSE-3</div>
        <div class="clark-label">CALIBRATION FAIL</div>
      </div>
      <div class="clark-tile" style="border-top-color:var(--amber);">
        <div class="clark-count" style="color:var(--amber);" data-aggregate="clark-negative">{n_negative}</div>
        <div class="clark-tier">PULSE-2</div>
        <div class="clark-label">DISCRIMINATOR ACTIVE</div>
      </div>
      <div class="clark-tile" style="border-top-color:var(--teal);">
        <div class="clark-count" style="color:var(--teal);" data-aggregate="clark-positive">{n_positive}</div>
        <div class="clark-tier">PULSE-1</div>
        <div class="clark-label">DETECTOR ACTIVE</div>
      </div>
      <div class="clark-tile" style="border-top-color:var(--blue);">
        <div class="clark-count" style="color:var(--blue);" data-aggregate="clark-total">{len(packs)}</div>
        <div class="clark-tier">PULSE-0</div>
        <div class="clark-label">REGISTRY-VALID</div>
      </div>
    </div>
    <div style="font-size:11px;color:#4A7A8F;padding:8px 0;">
      All {len(packs)} packs pass v1 metadata validator · all declare fairness_methods_required · attestation: self_declared · awaiting PULSE-93 synthesis hydration.
    </div>
  </div>
</div>'''


# ─────────────────────────────────────────────────────────────────────────────
# Page assembly
# ─────────────────────────────────────────────────────────────────────────────

def render_page(packs: list[dict]) -> str:
    headline = headline_pack(packs)
    screens = cell_screens_with_counts(packs)
    now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Box 1 — brand + sentiment-style "coverage" card + quote cards + footnote
    coverage_pct = int(len(packs) / 12 * 100)
    box1_html = f'''
<div class="topbar-box topbar-left">
  <div class="topbar-box-header" style="background:#001828;">
    <span class="topbar-logo">PULSE — DECISION INTELLIGENCE</span>
  </div>
  <div class="topbar-box-body" style="gap:8px;">
    <div class="topbar-sent-card">
      <div class="sent-card-bar"></div>
      <div class="sent-card-inner">
        <div class="sent-row-1">
          <span class="sent-card-label">CELL COVERAGE</span>
          <span class="sent-card-score" style="margin-left:auto;" data-count="coverage-score">{len(packs)}/12</span>
          <span class="sent-card-delta" style="color:var(--green);" data-count="coverage-delta">+{len(packs)-3} vs showcase</span>
          <span class="sent-card-traj" style="color:var(--green);" data-count="coverage-traj">↗ COMPLETE</span>
        </div>
        <div class="sent-row-2">
          <span class="sent-card-baseline">Baseline: 3 showcase packs</span>
          <span class="sent-card-ts">{now}</span>
        </div>
        <div class="sent-card-progress">
          <div class="sent-progress-fill" style="width:{coverage_pct}%;"></div>
        </div>
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      {render_volume_brief_for_box1(packs)}
    </div>
    <div class="brand-line">
      <span class="brand-dot brand-dot-blue"></span>
      <span>FrictionBench v0.1 · 12-cell matrix · 4 screens × 3 signatures</span>
    </div>
    <div class="brand-line">
      <span class="brand-dot brand-dot-teal"></span>
      <span>Lineage-anchored, fairness-enforced, regulator-defensible decision packs</span>
    </div>
    <div class="topbar-pills" style="margin-top:auto;">
      <span class="version-pill">pulse v1.0.0</span>
      <span class="version-pill">{now}</span>
      <div class="live-dot">LIVE</div>
    </div>
    <div style="font-size:10px;color:#3A6A7F;line-height:1.4;">
      Decision packs · canonical lineage anchors · synthesis layer pending PULSE-93 hydration
    </div>
  </div>
</div>'''

    # Box 2 — pack status
    box2_html = render_volume_brief_for_box2(packs, screens)

    # Box 3 — intelligence brief for the headline pack
    box3_html = render_intelligence_brief(headline, packs)

    # Body
    body_html = f'''
{render_metrics_strip(packs)}
{render_journey_cards(packs)}
'''

    # Right panel
    right_html = f'''
<div class="panel-section">
  <div class="panel-title">CHRONICLE — matched precedents</div>
  {render_chronicle(packs)}
</div>
<div class="panel-section">
  <div class="panel-title">ACTIVE HYPOTHESIS</div>
  {render_inference(headline)}
</div>
<div class="panel-section">
  <div class="panel-title">Cohort Axes — {headline["meta"]["pack_name"][:32]}…</div>
  <div class="sources-grid">
    {render_sources(headline)}
  </div>
</div>'''

    # V3 below-fold intelligence layer
    v3_html = f'''
<hr class="v3-divider">
<div class="v3-outer">
  <div class="v3-label">
    Pulse Intelligence Layer &nbsp;·&nbsp; {now}
  </div>
  {render_churn_block(packs)}
  {render_value_scoring_panel(packs)}
  {render_risk_scoring_panel(packs)}
  {render_placement_matrix(packs)}
  {render_commentary_block(packs)}
  {render_bench_block(packs)}
  {render_clark_protocol(packs)}
</div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pulse — Decision-pack briefing (MIL-template-style)</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
{render_topnav(packs)}
{render_notif_panel(packs)}
{render_guide_drawer()}
{render_settings_panel(packs)}
{render_avatar_menu()}
<div class="topbar">
  {render_sidebar(packs)}
  {box1_html}
  {box2_html}
  {box3_html}
</div>
{render_ticker(packs)}
{render_journey_row(screens)}
<div class="body-wrapper">
  <div class="left-col">{body_html}</div>
  <div class="right-col">{right_html}</div>
</div>
{v3_html}
<div class="footer">
  <span class="footer-item">INFERENCE LOCAL</span>
  <span class="footer-sep">·</span>
  <span class="footer-item">PUBLISHED OUTPUT ONLY</span>
  <span class="footer-sep">·</span>
  <span class="footer-item">dist/preview/index.html</span>
  <span class="footer-sep">·</span>
  <span class="footer-item">pulse v1.0.0</span>
  <span class="footer-sep">·</span>
  <span class="footer-sovereign">SOVEREIGN</span>
  <span class="footer-sep">·</span>
  <span class="footer-item">Article Zero</span>
  <span class="footer-sep">·</span>
  <span class="footer-item">Generated {now}</span>
</div>
{SEARCH_MODAL_HTML}
{FILTER_JS}
{SEARCH_JS}
{PANEL_JS}
</body>
</html>
'''


def main() -> None:
    packs = discover_packs()
    print(f"Discovered {len(packs)} packs")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html = render_page(packs)
    out_path = OUT_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}  ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
