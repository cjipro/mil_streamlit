"""HOL-90 — Cerno data source (the marts/D-014 adapter).

Pins the SAMPLE-mode contract the surface depends on: the shortlist shape +
sort + agentic derivation, the overview keys, the three marts, the per-candidate
dossier, and the LIVE/SAMPLE switch. No real data — the fixture is generic by
design; LIVE behaviour is exercised on the work machine via CERNO_MARTS_DIR.

Run:  python -m pytest holter/tests/test_cerno_source.py -q
"""
from __future__ import annotations

from holter.preview import cerno_source as src

_SHORTLIST_KEYS = {
    "rank", "label", "role_shape", "risk", "risk_abandon", "risk_error",
    "risk_loop", "reach_customers", "reach_sessions", "priority", "attribution",
    "system_class", "addressability", "is_agentic", "clark_tier",
    "value_weight", "fairness_flag",
}


def test_data_mode_sample_without_marts_dir():
    # No CERNO_MARTS_DIR in the test env → SAMPLE.
    assert src.data_mode() == "SAMPLE"


def test_shortlist_sample_shape_and_sort():
    rows, live = src.shortlist()
    assert live is False
    assert len(rows) == 13
    for r in rows:
        assert _SHORTLIST_KEYS <= set(r), f"missing keys on {r.get('rank')}"
    assert [r["rank"] for r in rows] == sorted(r["rank"] for r in rows)


def test_shortlist_agentic_derivation():
    rows, _ = src.shortlist()
    agentic = [r for r in rows if r["is_agentic"]]
    assert len(agentic) == 3
    assert all(r["addressability"] == "AGENTIC" for r in agentic)


def test_deferred_sentinels_present_not_fabricated():
    rows, _ = src.shortlist()
    assert all(r["value_weight"] == "VALUE_DEFERRED" for r in rows)
    assert all(r["fairness_flag"] == "FAIRNESS_DEFERRED" for r in rows)


def test_overview_keys():
    stats, live = src.overview()
    assert live is False
    for k in ("total_sessions", "total_customers", "n_candidates", "n_agentic",
              "concentration_pct", "snapshot_id", "map_version"):
        assert k in stats


def test_marts_sample_shapes():
    wl, wl_live = src.weak_links()
    fm, _ = src.friction_matrix()
    ec, _ = src.error_cascades()
    assert wl_live is False
    assert wl and {"step", "reach_customers", "fail_rate", "score"} <= set(wl[0])
    assert fm and {"step", "error_code", "n_sessions", "pct_of_friction"} <= set(fm[0])
    assert ec and {"pattern", "n_sessions", "n_distinct_errors", "abandon_rate"} <= set(ec[0])


def test_candidate_dossier_and_missing():
    c = src.candidate(1)
    assert c is not None
    for k in ("inbound", "outbound", "signature", "examples", "action", "dominant_mode"):
        assert k in c
    assert c["action"]["addressability"] == c["addressability"]
    assert src.candidate(999) is None


def test_lineage_keys():
    lin = src.lineage()
    assert {"snapshot_id", "map_version", "marts_dir"} <= set(lin)
