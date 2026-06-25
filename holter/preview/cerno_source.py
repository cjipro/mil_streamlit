"""Cerno data source — the Holter→Cerno bridge (HOL-90).

The ONLY module that knows the Cerno marts layout exists (mirrors the
"_shared.py is the only module that knows pulse/decision_packs/ exists"
discipline). Reads the Cerno pipeline output — the Stage-C marts +
the Step-4 D-014 shortlist — from CERNO_MARTS_DIR via DuckDB (LIVE), or a
deterministic synthetic fixture shaped like the real output (SAMPLE).

AIR-GAP: contains NO real data. The fixture uses generic role/shape labels
only. Real marts live on the work machine and are read at runtime there;
nothing real travels with this code. Real data flows in only via
CERNO_MARTS_DIR on the work machine.

render_cerno.py consumes this and renders through the Holter _shared component
library; this module never emits HTML.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb

# ── where the real marts live (work machine sets this) ──
MARTS_DIR = os.environ.get("CERNO_MARTS_DIR", "").strip()

# ── real-schema remaps (edit on the work machine if column names differ) ──
COLUMN_MAP: dict[str, str] = {
    "rank": "rank", "label": "label", "role_shape": "role_shape",
    "risk": "risk", "risk_abandon": "risk_abandon", "risk_error": "risk_error",
    "risk_loop": "risk_loop", "reach_customers": "reach_customers",
    "reach_sessions": "reach_sessions", "priority": "priority",
    "attribution": "attribution", "system_class": "system_class",
    "addressability": "addressability", "is_agentic": "is_agentic",
    "clark_tier": "clark_tier", "value_weight": "value_weight",
    "fairness_flag": "fairness_flag",
}

MART_MAPS: dict[str, dict[str, str]] = {
    "c_friction_matrix": {"step": "step", "error_code": "error_code",
                          "n_sessions": "n_sessions", "pct_of_friction": "pct_of_friction"},
    "c_weak_links": {"step": "step", "reach_customers": "reach_customers",
                     "fail_rate": "fail_rate", "score": "score"},
    "c_error_cascades": {"pattern": "pattern", "n_sessions": "n_sessions",
                         "n_distinct_errors": "n_distinct_errors", "abandon_rate": "abandon_rate"},
}


def _marts_path() -> Path | None:
    if not MARTS_DIR:
        return None
    p = Path(MARTS_DIR)
    return p if p.is_dir() else None


def _find(stem: str) -> Path | None:
    base = _marts_path()
    if base is None:
        return None
    for ext in (".parquet", ".csv"):
        cand = base / f"{stem}{ext}"
        if cand.exists():
            return cand
    return None


def _read_table(path: Path) -> list[dict]:
    con = duckdb.connect(database=":memory:")
    try:
        reader = "read_parquet" if path.suffix == ".parquet" else "read_csv_auto"
        return con.execute(
            f"SELECT * FROM {reader}('{path.as_posix()}')"
        ).fetch_arrow_table().to_pylist()
    finally:
        con.close()


# ──────────────────────────────────────────────────────────────────────────
# SYNTHETIC FIXTURE — shaped to the real Step-4 debrief (sanitised, generic).
# 13 candidates · 3 agentic · SEAM 7 / CASCADE 3 / SINGLE 3 · loop-driven tops.
# ──────────────────────────────────────────────────────────────────────────
_SAMPLE_SNAPSHOT = "sample-39ab8312a1b4431b"
_SAMPLE_MAP_VERSION = "sample-2026-06-08.1"

# rank, role_shape, risk, abandon, error, loop, reach_cust, reach_sess, attr, class, addr, clark
_SAMPLE_ROWS = [
    (1,  "loop-driven · main spine",          0.81, 0.62, 0.30, 0.92, 48200, 71500, "UNCLEAR", "SEAM",    "AGENTIC",     "CLARK_1"),
    (2,  "hybrid loop + systemic failure",     0.78, 0.70, 0.66, 0.74, 39100, 55300, "UNCLEAR", "SEAM",    "ENGINEERING", "CLARK_1"),
    (3,  "error-dominant hard failure",        0.72, 0.58, 0.88, 0.21, 22400, 28900, "UNCLEAR", "SINGLE",  "ENGINEERING", "CLARK_2"),
    (4,  "cascading failure node",             0.55, 0.49, 0.61, 0.34, 51800, 69200, "UNCLEAR", "CASCADE", "ENGINEERING", "CLARK_2"),
    (5,  "loop-heavy orchestration friction",  0.58, 0.44, 0.27, 0.81, 33600, 47100, "UNCLEAR", "SEAM",    "ENGINEERING", "CLARK_3"),
    (6,  "loop-driven hidden friction",        0.49, 0.41, 0.19, 0.77, 28900, 38400, "UNCLEAR", "SEAM",    "AGENTIC",     "CLARK_3"),
    (7,  "error-driven mid failure",           0.52, 0.40, 0.79, 0.24, 17300, 21100, "UNCLEAR", "SINGLE",  "ENGINEERING", "CLARK_3"),
    (8,  "cascade pattern · late stage",       0.47, 0.43, 0.55, 0.31, 24600, 31800, "UNCLEAR", "CASCADE", "ENGINEERING", "CLARK_3"),
    (9,  "loop friction · secondary path",     0.44, 0.37, 0.22, 0.70, 19800, 25400, "UNCLEAR", "SEAM",    "AGENTIC",     "CLARK_3"),
    (10, "error node · narrow reach",          0.51, 0.39, 0.82, 0.18,  9100, 10700, "UNCLEAR", "SINGLE",  "ENGINEERING", "CLARK_4"),
    (11, "cascade · upstream coupling",        0.40, 0.38, 0.49, 0.29, 14200, 17900, "UNCLEAR", "CASCADE", "ENGINEERING", "CLARK_4"),
    (12, "loop friction · low volume",         0.42, 0.33, 0.20, 0.68,  7600,  8800, "UNCLEAR", "SEAM",    "ENGINEERING", "CLARK_4"),
    (13, "seam stall · tail",                  0.38, 0.31, 0.24, 0.61,  6400,  7300, "UNCLEAR", "SEAM",    "ENGINEERING", "CLARK_4"),
]


def _sample_shortlist() -> list[dict]:
    rows: list[dict] = []
    raw = [(r[2] * r[6]) for r in _SAMPLE_ROWS]
    pmax = max(raw) or 1.0
    for r, praw in zip(_SAMPLE_ROWS, raw):
        rows.append({
            "rank": r[0], "label": f"State {chr(64 + r[0])}" if r[0] <= 26 else f"State {r[0]}",
            "role_shape": r[1], "risk": r[2], "risk_abandon": r[3], "risk_error": r[4],
            "risk_loop": r[5], "reach_customers": r[6], "reach_sessions": r[7],
            "priority": round(100.0 * praw / pmax, 1), "attribution": r[8],
            "system_class": r[9], "addressability": r[10], "is_agentic": r[10] == "AGENTIC",
            "clark_tier": r[11], "value_weight": "VALUE_DEFERRED", "fairness_flag": "FAIRNESS_DEFERRED",
        })
    return rows


def _sample_overview() -> dict:
    return {
        "total_sessions": 1_240_000, "total_customers": 890_000, "error_free_pct": 86.1,
        "concentration_states": 8, "concentration_pct": 80.0, "n_weak_links": 318,
        "n_candidates": 13, "n_agentic": 3, "risk_weights": "abandon 0.5 · error 0.3 · loop 0.2",
        "dominant_mode": "loop-driven", "snapshot_id": _SAMPLE_SNAPSHOT, "map_version": _SAMPLE_MAP_VERSION,
    }


# ── Public API ──────────────────────────────────────────────────────────────
def shortlist() -> tuple[list[dict], bool]:
    """Return (rows, is_live). is_live=False means synthetic sample."""
    path = _find("d014_shortlist")
    if path is None:
        return _sample_shortlist(), False
    rows = []
    for src in _read_table(path):
        row = {canon: src.get(real) for canon, real in COLUMN_MAP.items()}
        row["is_agentic"] = str(row.get("addressability", "")).upper() == "AGENTIC"
        rows.append(row)
    rows.sort(key=lambda x: (x.get("rank") or 1_000_000))
    return rows, True


def overview() -> tuple[dict, bool]:
    path = _marts_path()
    if path is not None:
        ov = path / "overview.json"
        if ov.exists():
            return json.loads(ov.read_text(encoding="utf-8")), True
    return _sample_overview(), False


# ── Stage-C marts ─────────────────────────────────────────────────────────
def _read_mart(stem: str) -> tuple[list[dict], bool]:
    path = _find(stem)
    if path is None:
        return [], False
    cmap = MART_MAPS[stem]
    return [{canon: src.get(real) for canon, real in cmap.items()}
            for src in _read_table(path)], True


_SAMPLE_FRICTION = [
    ("loop-driven · main spine", "—", 21800, 18.4), ("error-dominant hard failure", "E102", 18600, 15.7),
    ("hybrid loop + systemic failure", "E044", 14200, 12.0), ("cascading failure node", "E044", 11900, 10.1),
    ("error-driven mid failure", "E055", 9400, 7.9), ("loop-heavy orchestration", "—", 8700, 7.3),
    ("cascade pattern · late stage", "E061", 6800, 5.7), ("error node · narrow reach", "E102", 5200, 4.4),
    ("cascade · upstream coupling", "E001", 4600, 3.9), ("seam stall · tail", "—", 3900, 3.3),
    ("loop friction · secondary path", "—", 3400, 2.9), ("error node · auth boundary", "E118", 2700, 2.3),
]
_SAMPLE_WEAK_LINKS = [
    ("loop-driven · main spine", 48200, 0.34, 92.0), ("hybrid loop + systemic failure", 39100, 0.41, 86.0),
    ("cascading failure node", 51800, 0.22, 71.0), ("loop-heavy orchestration", 33600, 0.27, 64.0),
    ("error-dominant hard failure", 22400, 0.58, 61.0), ("loop-driven hidden friction", 28900, 0.19, 55.0),
    ("cascade pattern · late stage", 24600, 0.31, 49.0), ("error-driven mid failure", 17300, 0.44, 44.0),
    ("loop friction · secondary path", 19800, 0.22, 40.0), ("cascade · upstream coupling", 14200, 0.28, 33.0),
    ("error node · narrow reach", 9100, 0.61, 31.0), ("seam stall · tail", 6400, 0.24, 22.0),
]
_SAMPLE_CASCADES = [
    ("E001 → E044 → E044", 6900, 2, 0.72), ("E044 → E044 → E055", 4800, 2, 0.64),
    ("E102 → E102", 4100, 1, 0.81), ("E001 → E061 → E061", 3300, 2, 0.58),
    ("E055 → E044 → E118", 2600, 3, 0.69), ("E044 → E061", 2100, 2, 0.47),
    ("E118 → E118 → E102", 1700, 2, 0.66), ("E001 → E055 → E044 → E061", 1200, 4, 0.77),
]


def friction_matrix() -> tuple[list[dict], bool]:
    rows, live = _read_mart("c_friction_matrix")
    if live:
        rows.sort(key=lambda r: -(r.get("n_sessions") or 0))
        return rows, True
    return ([{"step": s, "error_code": e, "n_sessions": n, "pct_of_friction": p}
             for s, e, n, p in _SAMPLE_FRICTION], False)


def weak_links() -> tuple[list[dict], bool]:
    rows, live = _read_mart("c_weak_links")
    if live:
        rows.sort(key=lambda r: -(r.get("score") or 0))
        return rows, True
    return ([{"step": s, "reach_customers": c, "fail_rate": f, "score": sc}
             for s, c, f, sc in _SAMPLE_WEAK_LINKS], False)


def error_cascades() -> tuple[list[dict], bool]:
    rows, live = _read_mart("c_error_cascades")
    if live:
        rows.sort(key=lambda r: -(r.get("n_sessions") or 0))
        return rows, True
    return ([{"pattern": p, "n_sessions": n, "n_distinct_errors": d, "abandon_rate": a}
             for p, n, d, a in _SAMPLE_CASCADES], False)


# ── per-candidate drill-down dossier ──────────────────────────────────────
def _sample_detail(row: dict) -> dict:
    label, cls = row["label"], row.get("system_class")
    comps = {"abandon": row.get("risk_abandon", 0), "error": row.get("risk_error", 0),
             "loop": row.get("risk_loop", 0)}
    dominant = max(comps, key=comps.get)
    if cls == "SEAM":
        inbound = [("upstream spine state", 0.58, False), ("a secondary entry path", 0.27, False),
                   (label + " (self-loop)", 0.41, True)]
        outbound = [(label + " (self-loop)", 0.41), ("next spine state", 0.33),
                    ("<END:abandoned>", 0.18), ("recovery path", 0.08)]
        signature = ("Repeated self-transition with no explicit error — customers cycle on this "
                     "step (retry / hesitation / waiting), then a meaningful share abandon. "
                     "Loop-driven, platform-level friction, invisible to error-log monitoring.")
        examples = ["log_in[3] dashboard[7] " + label + "[14] " + label + "[22] " + label + "[31] <END:abandoned>[—]",
                    "log_in[4] " + label + "[18] " + label + "[27] next_step[9] <END:completed>[—]"]
    elif cls == "CASCADE":
        inbound = [("an upstream error state", 0.46, True), ("normal spine state", 0.39, False),
                   ("a prior retry", 0.15, True)]
        outbound = [("a further error state", 0.37), ("<END:abandoned>", 0.34),
                    (label + " (self-loop)", 0.16), ("recovery path", 0.13)]
        signature = ("Error accumulates across the arc — a fault upstream compounds into this state "
                     "and onward, several distinct error features within one session. The exit here "
                     "is often the tail of a cascade.")
        examples = ["log_in[3] step_a(E001-ERROR)[12] " + label + "(E044-ERROR)[20] later_step(E044-ERROR)[18] <END:abandoned>[—]",
                    "log_in[5] step_a[8] " + label + "(E044-ERROR)[16] retry[22] <END:abandoned>[—]"]
    else:
        inbound = [("clean spine state", 0.71, False), ("a secondary path", 0.21, False),
                   ("a prior step", 0.08, False)]
        outbound = [("<END:abandoned>", 0.52), ("retry of " + label, 0.29), ("next step", 0.19)]
        signature = ("A hard failure that originates at this state — clean inbound flow, an explicit "
                     "error fires here, and a majority abandon immediately after. Isolated functional "
                     "defect, not a cascade.")
        examples = ["log_in[3] dashboard[6] " + label + "(E102-ERROR)[28] <END:abandoned>[—]",
                    "log_in[4] " + label + "(E102-ERROR)[25] retry(E102-ERROR)[19] <END:abandoned>[—]"]
    addr = row.get("addressability")
    if addr == "AGENTIC":
        rationale = ("Looping/hesitation without an explicit failure — a guidance nudge, inline help, "
                     "or a proactive assist would likely unblock the customer. No code defect to fix; "
                     "this is a comprehension/guidance gap.")
        recommendation = "Prioritise for an agentic intervention (guided assist at this step)."
    elif addr == "DESIGN":
        rationale = ("The path itself is structurally awkward — friction is the flow, not a bug. "
                     "Resolution is a design change, not a fix or a nudge.")
        recommendation = "Route to design review of the journey flow."
    else:
        rationale = ("An explicit failure / functional defect is present. Resolution is an engineering "
                     "fix, not an assist.")
        recommendation = "Route to engineering triage with the error signature attached."
    return {
        **row, "inbound": inbound, "outbound": outbound, "signature": signature,
        "dominant_mode": dominant, "examples": examples,
        "action": {"addressability": addr, "rationale": rationale, "recommendation": recommendation},
        "attribution_note": ("Attribution (cause vs symptom) is currently a fallback (UNCLEAR) — the "
                             "inbound edges above are the raw material for it; the cause-vs-symptom pass "
                             "is deferred."),
    }


def candidate(rank: int) -> dict | None:
    rows, live = shortlist()
    match = next((r for r in rows if int(r.get("rank") or -1) == rank), None)
    if match is None:
        return None
    if live:
        path = _find("d014_candidate_detail")
        if path is not None:
            details = {int(d.get("rank")): d for d in _read_table(path)}
            if rank in details:
                return {**match, **details[rank]}
    return _sample_detail(match)


def lineage() -> dict:
    ov, _ = overview()
    return {
        "snapshot_id": ov.get("snapshot_id", "—"),
        "map_version": ov.get("map_version", "—"),
        "marts_dir": MARTS_DIR or "(none — sample fixture)",
    }


def data_mode() -> str:
    """LIVE if a real shortlist is present, else SAMPLE."""
    return "LIVE" if _find("d014_shortlist") is not None else "SAMPLE"
