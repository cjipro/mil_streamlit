"""
Unit tests for mil/publish/box3_selector.py — the 6-key tiebreaker + preamble.

Covers the panel-agreed ordering: Clark tier > trend > severity > days >
severity-weighted gap > alphabetical. Tests inject persistence entries,
findings, and clark_summary directly so they don't touch the filesystem.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mil.publish.box3_selector import (
    build_preamble_html,
    clark_tier_by_issue,
    compute_issue_trend,
    select_box3_issue,
)


def _issue(name, sev="P2", days=5, gap=2.0, cat="technical",
           b_rate=3.0, p_rate=1.0):
    return {
        "issue_type":        name,
        "category":          cat,
        "dominant_severity": sev,
        "days_active":       days,
        "gap_pp":             gap,
        "barclays_rate":     b_rate,
        "peer_avg_rate":     p_rate,
        "over_indexed":      True,
    }


def _clark(fid, tier, competitor="barclays"):
    return {"finding_id": fid, "clark_tier": tier, "competitor": competitor}


# ── Key #1: Clark tier dominates every other key ─────────────────────────────
def test_higher_clark_tier_wins_even_when_other_keys_lose():
    issues = [
        _issue("Login Failed",   sev="P0", days=30, gap=10.0),   # no Clark
        _issue("App Crashing",   sev="P2", days=1,  gap=0.5),    # CLARK-3
    ]
    findings = [
        {"finding_id": "F1", "competitor": "barclays", "dominant_issue_type": "App Crashing"},
    ]
    clark_summary = {"active": [_clark("F1", "CLARK-3")]}
    # no persistence data → trend falls back to STABLE for both
    selected = select_box3_issue(
        issues, clark_summary=clark_summary,
        persistence_entries=[], findings=findings,
    )
    assert selected["issue_type"] == "App Crashing"
    assert selected["clark_tier"] == "CLARK-3"


# ── Key #2: trend breaks a Clark-tier tie ────────────────────────────────────
def test_regression_beats_watch_within_same_clark_tier():
    issues = [
        _issue("App Crashing",   sev="P0", days=15, gap=7.0),    # WATCH trend
        _issue("Payment Failed", sev="P0", days=15, gap=0.7),    # REGRESSION trend
    ]
    findings = [
        {"finding_id": "F1", "competitor": "barclays", "dominant_issue_type": "App Crashing"},
        {"finding_id": "F2", "competitor": "barclays", "dominant_issue_type": "Payment Failed"},
    ]
    clark_summary = {"active": [_clark("F1", "CLARK-2"), _clark("F2", "CLARK-2")]}

    # Craft persistence so Payment Failed slopes up, App Crashing stays flat.
    entries = [
        {"date": "2026-04-15", "issue_type": "App Crashing",   "gap_pp": 7.0},
        {"date": "2026-04-21", "issue_type": "App Crashing",   "gap_pp": 7.05},
        {"date": "2026-04-15", "issue_type": "Payment Failed", "gap_pp": 0.1},
        {"date": "2026-04-21", "issue_type": "Payment Failed", "gap_pp": 3.0},
    ]
    selected = select_box3_issue(
        issues, clark_summary=clark_summary,
        persistence_entries=entries, findings=findings, today="2026-04-21",
    )
    assert selected["issue_type"] == "Payment Failed"
    assert selected["trend"] == "REGRESSION"


# ── Key #3: severity breaks a Clark+trend tie ────────────────────────────────
def test_p0_beats_p1_when_clark_tier_and_trend_match():
    issues = [
        _issue("A", sev="P1", days=15, gap=5.0),
        _issue("B", sev="P0", days=15, gap=5.0),
    ]
    # Both CLARK-2, both STABLE (no persistence)
    findings = [
        {"finding_id": "F1", "competitor": "barclays", "dominant_issue_type": "A"},
        {"finding_id": "F2", "competitor": "barclays", "dominant_issue_type": "B"},
    ]
    clark_summary = {"active": [_clark("F1", "CLARK-2"), _clark("F2", "CLARK-2")]}
    selected = select_box3_issue(
        issues, clark_summary=clark_summary,
        persistence_entries=[], findings=findings,
    )
    assert selected["issue_type"] == "B"


# ── Key #6: full tie resolves alphabetically ─────────────────────────────────
def test_full_tie_resolves_alphabetically():
    issues = [
        _issue("Zebra", sev="P2", days=5, gap=2.0),
        _issue("Alpha", sev="P2", days=5, gap=2.0),
    ]
    selected = select_box3_issue(
        issues, clark_summary={"active": []},
        persistence_entries=[], findings=[],
    )
    assert selected["issue_type"] == "Alpha"


# ── Empty input returns None ─────────────────────────────────────────────────
def test_empty_over_indexed_returns_none():
    assert select_box3_issue([], clark_summary={"active": []},
                             persistence_entries=[], findings=[]) is None


# ── compute_issue_trend thresholds ───────────────────────────────────────────
def test_trend_regression_on_steep_upward_slope():
    entries = [
        {"date": "2026-04-14", "issue_type": "X", "gap_pp": 1.0},
        {"date": "2026-04-21", "issue_type": "X", "gap_pp": 4.0},  # +0.43/d
    ]
    assert compute_issue_trend("X", today="2026-04-21", entries=entries) == "REGRESSION"


def test_trend_improving_on_steep_downward_slope():
    entries = [
        {"date": "2026-04-14", "issue_type": "X", "gap_pp": 5.0},
        {"date": "2026-04-21", "issue_type": "X", "gap_pp": 1.0},  # -0.57/d
    ]
    assert compute_issue_trend("X", today="2026-04-21", entries=entries) == "IMPROVING"


def test_trend_stable_on_flat_history():
    entries = [
        {"date": "2026-04-14", "issue_type": "X", "gap_pp": 2.0},
        {"date": "2026-04-21", "issue_type": "X", "gap_pp": 2.0},
    ]
    assert compute_issue_trend("X", today="2026-04-21", entries=entries) == "STABLE"


def test_trend_falls_back_to_stable_when_history_too_thin():
    assert compute_issue_trend("X", today="2026-04-21", entries=[]) == "STABLE"


# ── clark_tier_by_issue: only barclays findings map through ──────────────────
def test_clark_tier_by_issue_ignores_non_barclays():
    findings = [
        {"finding_id": "F1", "competitor": "natwest", "dominant_issue_type": "Login Failed"},
        {"finding_id": "F2", "competitor": "barclays", "dominant_issue_type": "App Crashing"},
    ]
    clark_summary = {"active": [
        _clark("F1", "CLARK-3", competitor="natwest"),
        _clark("F2", "CLARK-2", competitor="barclays"),
    ]}
    mapping = clark_tier_by_issue(clark_summary, findings=findings)
    assert mapping == {"App Crashing": "CLARK-2"}


def test_clark_tier_by_issue_keeps_highest_tier_per_issue():
    findings = [
        {"finding_id": "F1", "competitor": "barclays", "dominant_issue_type": "App Crashing"},
        {"finding_id": "F2", "competitor": "barclays", "dominant_issue_type": "App Crashing"},
    ]
    clark_summary = {"active": [
        _clark("F1", "CLARK-1"),
        _clark("F2", "CLARK-3"),
    ]}
    mapping = clark_tier_by_issue(clark_summary, findings=findings)
    assert mapping == {"App Crashing": "CLARK-3"}


# ── build_preamble_html: low-volume/high-severity justification ──────────────
def test_preamble_low_volume_high_severity_reads_volume_is_low_by_design():
    selected = {
        "issue_type":        "App Crashing",
        "dominant_severity": "P0",
        "trend":             "WATCH",
        "days_active":       15,
        "gap_pp":            6.9,
        "barclays_rate":     7.5,
        "peer_avg_rate":     0.6,
    }
    html = build_preamble_html(selected, vol_stats={"count_7d": 6, "total_7d": 219})
    assert "App Crashing" in html
    assert "P0" in html
    assert "6 of 219" in html
    assert "Volume is low by design" in html


def test_preamble_high_gap_reads_peer_gap_line():
    selected = {
        "issue_type":        "Feature Broken",
        "dominant_severity": "P2",
        "trend":             "STABLE",
        "days_active":       15,
        "gap_pp":            5.2,
        "barclays_rate":     8.5,
        "peer_avg_rate":     3.3,
    }
    html = build_preamble_html(selected, vol_stats={"count_7d": 22, "total_7d": 219})
    assert "Feature Broken" in html
    assert "+5.2pp gap" in html
    assert "Volume is low by design" not in html


def test_preamble_empty_when_no_selection():
    assert build_preamble_html(None, vol_stats=None) == ""
