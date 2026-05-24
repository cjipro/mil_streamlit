"""Cause-class analytics layer (PULSE-96).

Produces the investigation-grain `AnalyticOutputs` the synthesis layer renders
into a brief, for the **Cause** question class (the v1 class — the 12-cell
detection answers "why is this screen failing"; the other six question classes
are v2). Classical, deterministic, non-LLM — per the locked runtime.

How it works (mirrors `pulse.serving.marts`, which is the single synthetic-corpus
definition): run the detection runtime over the pack's own FrictionBench corpus
cell — a **labelled** set (`generate_corpus` carries ground-truth `should_fire`,
so Brier calibration is honest) — harvest each `Detection`'s evidence
(`dwell_time_seconds`, `p_value`, `error_type`, baseline) + cohort + ground truth,
then aggregate to exactly the keys the journey-altitude template expects.

The `payload` key set is the contract with the templates — it is locked against
`pulse/decision_packs/<pack>/templates/journey.md.j2`. Do NOT add or rename keys
here without updating the template (and vice versa).

Run:  py -m pulse.analytics.cause --pack loans_apply_step3__dwell_after_error
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any

import yaml

from pulse.convergence.fairness import assess_fairness
from pulse.detection.detect import normal_cdf, run_detection
from pulse.detection.frictionbench_run import _baseline_for, _hypothesis_for, generate_corpus
from pulse.synthesis.base import AnalyticOutputs

_REPO = Path(__file__).resolve().parents[2]
_PACKS_DIR = _REPO / "pulse" / "decision_packs"

# Below this per-cohort session count a rate is too noisy to claim a disparity.
_MIN_COHORT_SESSIONS = 5
# Empirical-percentile confidence band (deterministic; the pack declares
# bootstrap_ci_95 — v1 uses the percentile interval, a seeded bootstrap is a refinement).
_CI_LOW_PCT, _CI_HIGH_PCT = 2.5, 97.5

QUESTION_CLASS = "cause"

# Signal-altitude provenance: the runtime stamp (matches DETECTION_RUNTIME_VERSION).
ENGINE_VERSION = "0.1.0"
# Per-session evidence rows the signal altitude shows.
_EVIDENCE_SAMPLE_SIZE = 3


# ── pack config ────────────────────────────────────────────────────────────────


def _load_pack(pack_name: str) -> tuple[dict, dict]:
    """Return (hypothesis.yaml, metadata.yaml) dicts for a pack."""
    pack_dir = _PACKS_DIR / pack_name
    hyp = yaml.safe_load((pack_dir / "hypothesis.yaml").read_text(encoding="utf-8"))
    meta_path = pack_dir / "metadata.yaml"
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return hyp, meta


def _baseline_window_days(hyp: dict) -> int:
    """Parse '28' from analytic.baseline_source 'rolling_28d_same_screen'."""
    src = str(hyp.get("analytic", {}).get("baseline_source", ""))
    m = re.search(r"(\d+)\s*d", src)
    return int(m.group(1)) if m else 28


def _cohort_label(tags: tuple[str, ...]) -> str:
    return " · ".join(tags) if tags else "(no cohort tag)"


# ── aggregation helpers ──────────────────────────────────────────────────────────


def _cohort_breakdown(records: list[dict], overall_rate: float) -> list[dict[str, Any]]:
    """Per-cohort affected count / share / recall-vs-overall, sorted by affected desc."""
    by_cohort: dict[str, dict[str, int]] = {}
    for r in records:
        c = by_cohort.setdefault(r["cohort"], {"total": 0, "affected": 0})
        c["total"] += 1
        c["affected"] += int(r["fired"])
    total_affected = sum(c["affected"] for c in by_cohort.values())
    rows = []
    for label, c in by_cohort.items():
        if c["affected"] == 0:
            continue
        cohort_rate = c["affected"] / c["total"]
        rows.append({
            "label": label,
            "affected": c["affected"],
            "share_pct": round(100 * c["affected"] / total_affected, 1) if total_affected else 0.0,
            "recall_x": round(cohort_rate / overall_rate, 2) if overall_rate > 0 else 0.0,
        })
    rows.sort(key=lambda x: (-x["affected"], x["label"]))
    return rows


def _fairness_flag(records: list[dict], threshold: float) -> dict[str, Any] | None:
    """Recall disparity = max−min affected-rate across cohorts with enough sessions.
    Returns the flag dict only when it exceeds the pack's configured trigger."""
    by_cohort: dict[str, dict[str, int]] = {}
    for r in records:
        c = by_cohort.setdefault(r["cohort"], {"total": 0, "affected": 0})
        c["total"] += 1
        c["affected"] += int(r["fired"])
    rates = [c["affected"] / c["total"] for c in by_cohort.values()
             if c["total"] >= _MIN_COHORT_SESSIONS]
    if len(rates) < 2:
        return None
    disparity = round(max(rates) - min(rates), 4)
    if disparity > threshold:
        return {"disparity": disparity, "threshold": threshold}
    return None


# The protected attribute for the demographic-parity assessment. In the synthetic
# corpus the vulnerability-relevant axis is age — the `over_50` cohort tag — which is
# a recognised UK-banking vulnerability indicator. A real deployment configures the
# protected characteristic per pack; v1 uses this single, well-populated axis.
_PROTECTED_TAG = "over_50"


def _fairness_assessment(
    records: list[dict], protected_tag: str = _PROTECTED_TAG,
    min_cohort: int = _MIN_COHORT_SESSIONS,
) -> dict[str, Any] | None:
    """Real fairness-aware verdict via convergence.assess_fairness (demographic_parity
    ratio + chi² significance + 4/5ths disparate-impact flag).

    Split on a single protected attribute: sessions carrying `protected_tag` (protected)
    vs those without (reference). A binary, well-populated split — NOT a fragmenting
    breakdown over full cohort-tag tuples — so the demographic-parity question that
    actually matters here (age-vulnerability disparity in detection) is answerable.
    Returns the full convergence verdict (PULSE-89 registry); None when either arm is
    below min_cohort. Deterministic."""
    prot_fired = prot_total = ref_fired = ref_total = 0
    for r in records:
        fired = int(r["fired"])
        if protected_tag in (r.get("cohort_tags") or []):
            prot_total += 1
            prot_fired += fired
        else:
            ref_total += 1
            ref_fired += fired
    if prot_total < min_cohort or ref_total < min_cohort:
        return None
    return assess_fairness(
        protected_fired=prot_fired, protected_total=prot_total,
        reference_fired=ref_fired, reference_total=ref_total,
        protected_group=protected_tag, min_cohort=min_cohort,
    ).as_dict()


def _error_breakdown(records: list[dict]) -> list[dict[str, Any]]:
    """Aggregate error_type across all sessions' error events → code/count/share."""
    counts: dict[str, int] = {}
    for r in records:
        for code in r["error_codes"]:
            counts[code] = counts.get(code, 0) + 1
    total = sum(counts.values())
    rows = [
        {"code": code, "count": n, "share_pct": round(100 * n / total, 1) if total else 0.0}
        for code, n in counts.items()
    ]
    rows.sort(key=lambda x: (-x["count"], x["code"]))
    return rows


def _confidence_band(median_conf: float) -> str:
    return "high" if median_conf >= 0.8 else "medium" if median_conf >= 0.6 else "low"


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile (deterministic, stdlib-only)."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct / 100.0
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _remediation(error_rows: list[dict], categories: list[str]) -> tuple[str, str]:
    """Deterministic, data-grounded remediation (category from the pack's allowed
    list + a templated rationale citing the dominant error). NOT free prose."""
    category = categories[0] if categories else "template_fix"
    if not error_rows:
        return category, "No dominant error type was isolated in the affected sessions."
    top = error_rows[0]
    rationale = (
        f"{top['code']} dominates the error mix ({top['share_pct']}% of errors) and is "
        f"upstream of the dwell signature; addressing it via {category} clears the largest "
        f"share of affected sessions with one change."
    )
    return category, rationale


# ── public API ────────────────────────────────────────────────────────────────


def _primary_cohort(cohort_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The most-affected cohort, for the bank-altitude headline. None if none fired."""
    if not cohort_rows:
        return None
    top = cohort_rows[0]  # _cohort_breakdown sorts by affected desc
    return {"label": top["label"], "share_pct": top["share_pct"], "recall_disparity_x": top["recall_x"]}


def _recommendation_summary(category: str, error_rows: list[dict[str, Any]], screen_id: str) -> str:
    """One-line exec recommendation for the bank altitude — deterministic, data-grounded."""
    if not error_rows:
        return f"Investigate the dwell-after-error pattern on {screen_id}"
    top = error_rows[0]
    return f"Apply {category} to {top['code']} on {screen_id} ({top['share_pct']}% of errors)"


def _analytic_block(hyp: dict) -> dict[str, Any]:
    """The pack's analytic config the signal altitude prints (straight from hypothesis.yaml)."""
    a = hyp.get("analytic", {})
    t = a.get("trigger", {})
    return {
        "method": a.get("method"),
        "baseline_source": a.get("baseline_source"),
        "trigger": {
            "requires_prior_event": t.get("requires_prior_event"),
            "dwell_window_seconds": t.get("dwell_window_seconds"),
            "p_value_threshold": t.get("p_value_threshold"),
        },
    }


def _evidence_sample(records: list[dict[str, Any]], n: int = _EVIDENCE_SAMPLE_SIZE) -> list[dict[str, Any]]:
    """First n fired sessions (by session_id) as per-session evidence for the signal altitude."""
    fired = sorted((r for r in records if r["fired"]), key=lambda r: r["session_id"])[:n]
    return [
        {
            "session_id": r["session_id"],
            "dwell_seconds": round(r["dwell"]) if r["dwell"] is not None else None,
            "error_code": r["error_type"] or (r["error_codes"][0] if r["error_codes"] else "none"),
            "cohort_tags": r["cohort_tags"],
            "p_value": r["p_value"],
        }
        for r in fired
    ]


def build_analytic_outputs(pack_name: str, *, sessions_per_cell: int = 200) -> AnalyticOutputs:
    """Aggregate the pack's labelled corpus cell into the Cause-class AnalyticOutputs.

    Deterministic for a given pack + sessions_per_cell. `payload` keys cover all three
    altitude templates (journey / bank / signal). Signal-altitude provenance stamps
    (engine_version / detection_emitted_at / lineage_anchor) are deterministic analytics
    defaults; the live pipeline overrides emitted_at + lineage_anchor with real run values."""
    hyp, meta = _load_pack(pack_name)
    cell_id = int(hyp["cell_id"])
    screen_id = hyp["screen_id"]
    signature_id = hyp["signature_id"]
    analytic = hyp.get("analytic", {})
    p_threshold = float(analytic.get("trigger", {}).get("p_value_threshold", 0.01))
    rem_categories = list(hyp.get("remediation_categories", []))
    fairness_threshold = float(
        hyp.get("fairness", {}).get("trigger_independent_review_if", {})
        .get("cohort_recall_disparity_above", 0.15)
    )

    hypothesis = _hypothesis_for(cell_id, screen_id, signature_id)
    baseline = _baseline_for(signature_id, screen_id)
    cell_sessions, _ = generate_corpus(sessions_per_cell, 0)

    # Run detection; harvest each session's detection + evidence + ground truth.
    records: list[dict[str, Any]] = []
    latest_event_ts: str | None = None
    for session, gt in cell_sessions[cell_id]:
        det = run_detection(hypothesis=hypothesis, session=session, baseline=baseline)
        ev = det.evidence or {}
        error_codes: list[str] = []
        for e in session.events:
            evt = e.get("event", {})
            if evt.get("event_type") == "error":
                code = (evt.get("payload", {}) or {}).get("error_type")
                if code:
                    error_codes.append(code)
            ts = evt.get("event_ts")
            if ts and (latest_event_ts is None or ts > latest_event_ts):
                latest_event_ts = ts  # deterministic: max event_ts across the corpus cell
        records.append({
            "session_id": session.session_id,
            "fired": bool(det.fired),
            "confidence": float(det.confidence) if det.confidence is not None else 0.0,
            "should_fire": bool(gt.get("should_fire", False)),
            "cohort": _cohort_label(tuple(session.cohort_tags)),
            "cohort_tags": list(session.cohort_tags),
            "dwell": ev.get("dwell_time_seconds"),
            "p_value": ev.get("p_value"),
            "error_type": ev.get("error_type"),
            "error_codes": error_codes,
        })

    total = len(records)
    fired = [r for r in records if r["fired"]]
    affected = len(fired)
    overall_rate = affected / total if total else 0.0
    dwells = [r["dwell"] for r in fired if r["dwell"] is not None]
    dwell_p50 = statistics.median(dwells) if dwells else 0.0

    # Investigation-level significance: z-test of the affected sessions' mean dwell
    # vs the rolling screen baseline (population test, distinct from the per-session z).
    if dwells and baseline.std > 0:
        se = baseline.std / math.sqrt(len(dwells))
        z = (statistics.fmean(dwells) - baseline.mean) / se if se > 0 else 0.0
        p_value = round(1.0 - normal_cdf(z), 6)
    else:
        p_value = None

    error_rows = _error_breakdown(records)
    cohort_rows = _cohort_breakdown(records, overall_rate)
    rem_category, rem_rationale = _remediation(error_rows, rem_categories)
    conf_values = [r["confidence"] for r in fired]
    median_conf = statistics.median(conf_values) if conf_values else 0.0
    brier = round(statistics.fmean([(r["confidence"] - r["should_fire"]) ** 2 for r in records]), 4) \
        if total else None
    evidence_sample = _evidence_sample(records)

    # Signal-altitude provenance. detection_emitted_at = latest corpus event_ts (deterministic);
    # lineage_anchor = content hash of the analytic facts (honest analytic-content anchor). The
    # live pipeline overrides emitted_at + lineage_anchor with the real run ts + lineage row hash.
    analytic_facts = {
        "screen_id": screen_id, "signature_id": signature_id,
        "affected_sessions": affected, "total_sessions": total,
        "dwell_seconds_p50": round(dwell_p50), "p_value": p_value,
        "cohort_breakdown": cohort_rows, "error_breakdown": error_rows,
    }
    lineage_anchor = hashlib.sha256(
        json.dumps(analytic_facts, sort_keys=True).encode("utf-8")
    ).hexdigest()
    detection_emitted_at = latest_event_ts or "1970-01-01T00:00:00Z"

    payload: dict[str, Any] = {
        # shared / journey altitude
        "pack": {
            "pack_name": meta.get("pack_name", pack_name),
            "pack_version": str(meta.get("pack_version", "0.0.0")),
            "synthesis_mode": meta.get("synthesis_mode", "deterministic"),
        },
        "screen_id": screen_id,
        "signature_id": signature_id,
        "window": {"label": "FrictionBench v0.1 calibration set"},
        "affected_sessions": affected,
        "total_sessions": total,
        "affected_pct": round(100 * overall_rate, 1),
        "dwell_seconds_p50": round(dwell_p50),
        "dwell_uplift_pct": round(100 * (dwell_p50 - baseline.mean) / baseline.mean)
        if baseline.mean > 0 else 0,
        "baseline_window_days": _baseline_window_days(hyp),
        "p_value": p_value,
        "baseline_n": baseline.n_sessions,
        "p_value_threshold": p_threshold,
        "cohort_breakdown": cohort_rows,
        "fairness_flag": _fairness_flag(records, fairness_threshold),
        "fairness": _fairness_assessment(records),
        "error_breakdown": error_rows,
        "remediation_category": rem_category,
        "remediation_rationale": rem_rationale,
        "confidence_band": _confidence_band(median_conf),
        "confidence_low": round(_percentile(conf_values, _CI_LOW_PCT), 2),
        "confidence_high": round(_percentile(conf_values, _CI_HIGH_PCT), 2),
        "brier_score": brier,
        # bank altitude
        "primary_cohort": _primary_cohort(cohort_rows),
        "recommendation_summary": _recommendation_summary(rem_category, error_rows, screen_id),
        # signal altitude — analytic config + per-session evidence + provenance stamps
        "analytic": _analytic_block(hyp),
        "evidence_sample": evidence_sample,
        "evidence_sample_size": len(evidence_sample),
        "audit": {"bundle_required_fields": list(hyp.get("audit", {}).get("bundle_required_fields", []))},
        "engine_version": ENGINE_VERSION,
        "detection_emitted_at": detection_emitted_at,
        "lineage_anchor": lineage_anchor,
    }
    return AnalyticOutputs(question_class=QUESTION_CLASS, payload=payload)


def main() -> None:
    p = argparse.ArgumentParser(description="Cause-class analytics layer (PULSE-96)")
    p.add_argument("--pack", default="loans_apply_step3__dwell_after_error")
    p.add_argument("--sessions-per-cell", type=int, default=200)
    args = p.parse_args()
    out = build_analytic_outputs(args.pack, sessions_per_cell=args.sessions_per_cell)
    print(json.dumps({"question_class": out.question_class, "payload": out.payload}, indent=2))


if __name__ == "__main__":
    main()
