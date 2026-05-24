"""HOL-4 Pulse Home wiring — flagged/commercial cards carry the REAL lineage
anchor + REAL synthesis-analytics confidence band, not the metadata-file sha or a
fabricated single-point confidence score.

The genuinely contract-blocked stubs stay honest: time / change / velocity
(no feed-state contract), AWAITING REVIEW and MLOPS alert cards (no engine
review-state / Surface-4-alert contract). Those are out of scope by design, not
oversight.

Run:  python -m pytest holter/tests/test_home_wiring.py -q
"""

from __future__ import annotations

from holter.preview import render_home as H
from holter.preview._shared import (
    discover_packs,
    get_pack_analytics,
    lineage_anchor_short,
    short_hash,
)

_RUNNABLE = "loans_apply_step3__dwell_after_error"  # HYP + SAMPLES + META
_FIXTURE = "example_pack"                            # META only — not runnable


# ── real confidence (band + interval, not a fabricated point score) ───────────

def test_real_confidence_runnable_pack():
    rc = H._real_confidence(_RUNNABLE)
    assert rc is not None
    label, interval, color = rc
    assert label in ("HIGH", "MEDIUM", "LOW")
    assert "–" in interval                       # percentile interval, not a point
    assert color.startswith("var(--")


def test_real_confidence_none_for_non_runnable():
    assert H._real_confidence(_FIXTURE) is None
    assert H._real_confidence("does-not-exist-pack") is None


def test_card_delta_confidence_is_real_for_runnable_pack():
    d = H.card_delta(_RUNNABLE)
    # real → interval string; stub values in _DELTA_CONFIDENCE are point scores.
    assert "–" in d["conf_score"]
    assert d["conf_label"] in ("HIGH", "MEDIUM", "LOW")


def test_card_delta_confidence_is_stub_for_non_pack():
    # A synthetic MLOps-alert "name" is not a pack → stub confidence retained
    # (a point score from _DELTA_CONFIDENCE, no interval dash).
    d = H.card_delta("Diagnosis methodology drift alert (not a pack)")
    assert "–" not in d["conf_score"]


# ── lineage badge ─────────────────────────────────────────────────────────────

def test_lineage_meta_runnable_pack_uses_real_anchor():
    packs = discover_packs()
    pack = next(p for p in packs if p["meta"]["pack_name"] == _RUNNABLE)
    assert H._lineage_meta(pack) == f"lineage:{lineage_anchor_short(_RUNNABLE)}"


def test_lineage_meta_matches_engine_anchor():
    out = get_pack_analytics(_RUNNABLE)
    assert lineage_anchor_short(_RUNNABLE) == short_hash(out.payload["lineage_anchor"])


# ── rendered surface ──────────────────────────────────────────────────────────

def test_home_page_carries_real_lineage_and_confidence_interval():
    html = H.render_page()
    # real lineage badge present on the engine-backed cards
    assert "lineage:" in html
    # real confidence band + interval present (e.g. "CONF HIGH 0.93–0.93")
    import re
    assert re.search(r"CONF (HIGH|MEDIUM|LOW) \d\.\d\d–\d\.\d\d", html)


def test_home_page_negative_scope_holds():
    # HOL-4 negative scope: no KPI tiles. (Sanity that wiring didn't smuggle any in.)
    html = H.render_page()
    assert "kpi-tile" not in html.lower()
