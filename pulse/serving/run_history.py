"""Run-history persistence for the MLOps drift monitor (PULSE-133).

The detection engine is single-snapshot, so each benchmark/pipeline run is ONE
data point. This module records per-run, per-cell detection metrics — keyed by run
timestamp — to an append-only mart, and reads them back as a time-series so the
drift pane can render a real trend instead of a fabricated one.

`compute_cell_metrics` runs the detection runtime over the FrictionBench corpus
(`generate_corpus`) and aggregates per cell:
  - detection_rate      = fired / should_fire population (recall on positives)
  - false_positive_rate = fired / should-NOT-fire population
  - accuracy_gap        = max(0, expected_recall - detection_rate)  (0 = perfect)

`drift_pct` (PULSE-133) degrades a fraction of true positives → recall drops →
detection_rate falls + accuracy_gap grows. `backfill_demo_history` ramps drift_pct
across N days to seed a synthetic-but-real drift SCENARIO for the OSS preview (like
FrictionBench's engineered cell-10 negative); production accumulates real runs.

Run:  py -m pulse.serving.run_history --backfill 14
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from pulse.convergence.fairness import assess_fairness
from pulse.detection.detect import run_detection
from pulse.detection.frictionbench_run import (
    CELLS,
    _baseline_for,
    _hypothesis_for,
    generate_corpus,
)
from pulse.serving.marts import MARTS_DIR

CELL_METRICS_HISTORY_LOG = MARTS_DIR / "cell_metrics_history.jsonl"
FAIRNESS_HISTORY_LOG = MARTS_DIR / "fairness_history.jsonl"
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).strftime(_TS_FMT)


def compute_cell_metrics(
    *, sessions_per_cell: int = 200, seed: int | None = None, drift_pct: float = 0.0,
) -> list[dict[str, Any]]:
    """Per-cell detection metrics over one corpus run. Deterministic per inputs."""
    cell_sessions, _ = generate_corpus(sessions_per_cell, 0, seed=seed, drift_pct=drift_pct)
    rows: list[dict[str, Any]] = []
    for cell_id, screen, signature, expect in CELLS:
        hyp = _hypothesis_for(cell_id, screen, signature)
        baseline = _baseline_for(signature, screen)
        should = fired_pos = should_not = fired_neg = 0
        for session, gt in cell_sessions[cell_id]:
            fired = bool(run_detection(hypothesis=hyp, session=session, baseline=baseline).fired)
            if gt["should_fire"]:
                should += 1
                fired_pos += int(fired)
            else:
                should_not += 1
                fired_neg += int(fired)
        detection_rate = round(fired_pos / should, 4) if should else 0.0
        fp_rate = round(fired_neg / should_not, 4) if should_not else 0.0
        expected = 1.0 if expect == "positive" else 0.0  # clean-run recall target
        rows.append({
            "cell_id": cell_id,
            "screen_id": screen,
            "signature_id": signature,
            "ground_truth_class": expect,
            "n_sessions": should + should_not,
            "detection_rate": detection_rate,
            "false_positive_rate": fp_rate,
            "accuracy_gap": round(max(0.0, expected - detection_rate), 4),
        })
    return rows


def compute_fairness_metrics(
    *, sessions_per_cell: int = 200, seed: int | None = None, cohort_disparity: float = 0.0,
) -> list[dict[str, Any]]:
    """Per-cell fairness verdict over a MIXED-cohort corpus (PULSE-134): protected =
    over_50 sessions, reference = the rest; runs convergence.assess_fairness on the
    detection outcomes. `cohort_disparity>0` lowers the protected cohort's recall →
    a real disparate-impact signal. Deterministic per inputs."""
    cell_sessions, _ = generate_corpus(
        sessions_per_cell, 0, seed=seed, mixed_cohorts=True, cohort_disparity=cohort_disparity,
    )
    rows: list[dict[str, Any]] = []
    for cell_id, screen, signature, expect in CELLS:
        hyp = _hypothesis_for(cell_id, screen, signature)
        baseline = _baseline_for(signature, screen)
        prot_fired = prot_total = ref_fired = ref_total = 0
        for session, _gt in cell_sessions[cell_id]:
            fired = bool(run_detection(hypothesis=hyp, session=session, baseline=baseline).fired)
            if "over_50" in session.cohort_tags:
                prot_total += 1
                prot_fired += int(fired)
            else:
                ref_total += 1
                ref_fired += int(fired)
        v = assess_fairness(
            protected_fired=prot_fired, protected_total=prot_total,
            reference_fired=ref_fired, reference_total=ref_total,
            protected_group="over_50",
        )
        rows.append({
            "cell_id": cell_id,
            "screen_id": screen,
            "signature_id": signature,
            "ground_truth_class": expect,
            "assessed": v.assessed,
            "demographic_parity_ratio": v.disparity_ratio,
            "disparate_impact": v.disparate_impact,
            "chi2_p_value": v.chi2_p_value,
            "protected_rate": v.protected_rate,
            "reference_rate": v.reference_rate,
        })
    return rows


def record_run(
    run_ts: str, rows: list[dict[str, Any]], *,
    log_path: Path = CELL_METRICS_HISTORY_LOG,
) -> int:
    """Append per-cell metric rows for one run, stamped with run_ts. Returns count."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"run_ts": run_ts, **r}) + "\n")
    return len(rows)


def read_cell_metrics_history(
    *, cell_id: int | None = None, signature: str | None = None,
    days: int | None = None, log_path: Path = CELL_METRICS_HISTORY_LOG,
) -> list[dict[str, Any]]:
    """Read history rows (chronological), filtered by cell / signature / last-N-days.
    Empty list when no run has been recorded (honest — never fabricated)."""
    if not log_path.exists():
        return []
    rows = [
        json.loads(ln)
        for ln in log_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if cell_id is not None:
        rows = [r for r in rows if r.get("cell_id") == cell_id]
    if signature is not None:
        rows = [r for r in rows if r.get("signature_id") == signature]
    if days is not None:
        cutoff = _iso(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days))
        rows = [r for r in rows if r.get("run_ts", "") >= cutoff]
    rows.sort(key=lambda r: (r.get("run_ts", ""), r.get("cell_id", 0)))
    return rows


def read_fairness_history(
    *, cell_id: int | None = None, signature: str | None = None, days: int | None = None,
) -> list[dict[str, Any]]:
    """Per-run fairness-verdict history (PULSE-134) — same filters as
    read_cell_metrics_history. Empty until a fairness run is recorded."""
    return read_cell_metrics_history(
        cell_id=cell_id, signature=signature, days=days, log_path=FAIRNESS_HISTORY_LOG,
    )


def backfill_demo_history(
    days: int = 14, *, sessions_per_cell: int = 200,
    log_path: Path = CELL_METRICS_HISTORY_LOG,
    fairness_log_path: Path = FAIRNESS_HISTORY_LOG, fresh: bool = True,
) -> int:
    """Seed synthetic SCENARIOS for the OSS preview: `days` runs (oldest first).
    Detection history gets `drift_pct` ramping 0 → ~0.45 (declining recall = drift);
    fairness history gets `cohort_disparity` ramping 0 → ~0.35 (worsening protected-
    cohort disparity). Each run seeded by its day index. Returns detection rows
    written. Production accumulates real per-run history instead."""
    if fresh:
        for lp in (log_path, fairness_log_path):
            if lp.exists():
                lp.unlink()
    today = dt.datetime.now(dt.timezone.utc)
    total = 0
    span = max(days - 1, 1)
    for d in range(days):
        run_ts = _iso(today - dt.timedelta(days=span - d))  # oldest → newest
        frac = d / span
        total += record_run(
            run_ts,
            compute_cell_metrics(sessions_per_cell=sessions_per_cell, seed=d,
                                 drift_pct=round(0.45 * frac, 4)),
            log_path=log_path,
        )
        record_run(
            run_ts,
            compute_fairness_metrics(sessions_per_cell=sessions_per_cell, seed=d,
                                     cohort_disparity=round(0.35 * frac, 4)),
            log_path=fairness_log_path,
        )
    return total


def main() -> None:
    p = argparse.ArgumentParser(description="Run-history persistence (PULSE-133)")
    p.add_argument("--backfill", type=int, metavar="DAYS",
                   help="seed a synthetic drift scenario over DAYS runs")
    p.add_argument("--record", action="store_true", help="record one clean run now")
    args = p.parse_args()
    if args.backfill:
        n = backfill_demo_history(args.backfill)
        print(f"backfilled {n} rows over {args.backfill} runs → {CELL_METRICS_HISTORY_LOG}")
    elif args.record:
        n = record_run(_iso(dt.datetime.now(dt.timezone.utc)), compute_cell_metrics())
        print(f"recorded {n} cell rows → {CELL_METRICS_HISTORY_LOG}")
    else:
        p.print_help()


if __name__ == "__main__":
    main()
