"""Full FrictionBench run over the detection runtime (PULSE-126).

Runs the detector across the 12-cell FrictionBench v0.1 matrix + a negative-
screen false-positive substrate, scores every detection with the FrictionBench
reference scorer, and reports per-cell aggregates + the macro-average + the
false-positive penalty + the cell-10 acid test.

The session corpus here is a **deterministic synthetic stand-in**, generated
in-process (the real v0.1 corpus is TAQ-generated + contract-gated, not in this
repo). So the macro number is a *harness-validation* score on a clean synthetic
corpus — not the published benchmark figure. The harness is real and runs on
the TAQ corpus unchanged when it lands; the headline metric remains the
synthetic→real transfer gap (PULSE-124), which stays open until then.

Run:  py -m pulse.detection.frictionbench_run
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from pulse.detection.detect import (
    DETECTION_RUNTIME_VERSION,
    ScreenBaseline,
    Session,
    run_detection,
)
from pulse.frictionbench.scoring.score import (
    aggregate_cell,
    apply_false_positive_penalty,
    macro_average,
    score_detection,
)

# The 12-cell matrix (TEST_SET_SPEC.md): 3 signatures × 4 friction-target screens.
# Cell 10 is the engineered NEGATIVE (long dwell on a Premier portfolio = interest).
_SCREENS = [
    "loans.apply.step3",
    "international.beneficiary.setup",
    "cards.credit.apply.eligibility",
    "investments.premier.portfolio.overview",
]
_SIGNATURES = ["dwell_after_error", "multi_back_press", "abandon_before_submit"]

CELLS: list[tuple[int, str, str, str]] = []
_cid = 0
for _screen in _SCREENS:
    for _sig in _SIGNATURES:
        _cid += 1
        # cell 10 = investments × dwell_after_error → engineered negative
        _expect = "negative" if _cid == 10 else "positive"
        CELLS.append((_cid, _screen, _sig, _expect))

_NEGATIVE_SCREENS = [
    "dashboard.home", "accounts.summary", "spending.by_category",
    "insurance.travel.quote", "payments.standing_orders",
]


# ── per-cell hypothesis + baseline ─────────────────────────────────────────────


def _hypothesis_for(cell_id: int, screen_id: str, signature_id: str) -> dict:
    if signature_id == "dwell_after_error":
        hyp: dict[str, Any] = {
            "screen_id": screen_id,
            "signature_id": signature_id,
            "analytic": {
                "method": "dwell_z_score_vs_screen_baseline",
                "trigger": {"requires_prior_event": "validation_error", "p_value_threshold": 0.01},
            },
            "negative_class_discriminator": None,
        }
        if cell_id == 10:  # the load-bearing negative carries the suppression block
            hyp["negative_class_discriminator"] = {
                "suppression_signals": [
                    {"signal": "scroll_depth_pct", "threshold": 60, "direction": "above"},
                    {"signal": "chart_drilldowns_in_session", "threshold": 2, "direction": "above_or_equal"},
                    {"signal": "return_within_7_days", "threshold": True, "direction": "equals"},
                ],
            }
        return hyp
    if signature_id == "multi_back_press":
        return {
            "screen_id": screen_id,
            "signature_id": signature_id,
            "analytic": {
                "method": "back_press_burst_detection",
                "trigger": {"min_back_press_events": 3, "window_seconds": 300, "same_screen_required": True},
                "discriminator": {"rule": "inter_press_interval_under_seconds", "value": 20},
            },
            "negative_class_discriminator": None,
        }
    return {  # abandon_before_submit
        "screen_id": screen_id,
        "signature_id": signature_id,
        "analytic": {
            "method": "terminal_abandonment_detection",
            "trigger": {
                "requires_prior_step_completion": ["step1", "step2"],
                "requires_dwell_above_percentile": 90,
                "requires_exit_without_event": "submit_clicked",
            },
            "exclusions": [{"session_returned_within_seconds": 1800}],
        },
        "negative_class_discriminator": None,
    }


def _baseline_for(signature_id: str, screen_id: str) -> ScreenBaseline:
    if signature_id == "abandon_before_submit":
        return ScreenBaseline(screen_id, "dwell_seconds", mean=30.0, std=15.0, n_sessions=300)
    return ScreenBaseline(screen_id, "dwell_seconds", mean=20.0, std=5.0, n_sessions=300)


# ── deterministic synthetic corpus ──────────────────────────────────────────────


def _ev(seq: int, etype: str, screen: str, ts: str, payload: dict | None = None) -> dict:
    return {
        "context": {"sequence_no": seq, "screen_id": screen},
        "event": {"event_type": etype, "event_ts": ts, "payload": payload or {}},
    }


def _ts(sec: int) -> str:
    return f"2026-05-21T10:{(sec // 60) % 60:02d}:{sec % 60:02d}Z"


def _make_session(
    cell_id: int, screen: str, signature: str, kind: str, idx: int
) -> tuple[Session, dict]:
    """kind ∈ {positive, negative, noise}. Returns (Session, ground_truth_row).
    Sessions are constructed so the detector's fire/abstain matches should_fire."""
    sid = f"c{cell_id}-{kind}-{idx}"
    cohort = ("over_50",) if signature != "multi_back_press" else ("mobile",)

    # cell 10: the "positive-slot" is the engineered negative (interest, suppressed)
    is_neg_cell = cell_id == 10
    fires_positive = (kind == "positive") and not is_neg_cell

    def gt(should_fire: bool) -> dict:
        return {
            "session_id": sid,
            "cell_id": str(cell_id),
            "screen_id": screen,
            "signature_id": signature if should_fire else "none",
            "should_fire": should_fire,
            "root_cause": "template" if should_fire else "none",
            "cohort_tags": list(cohort) if should_fire else [],
        }

    if signature == "dwell_after_error":
        if kind == "positive" and is_neg_cell:
            # long dwell BUT engagement signals → suppressed → no fire
            ev = (_ev(1, "screen_view", screen, _ts(0)),
                  _ev(2, "error", screen, _ts(4), {"error_type": "validation_error"}),
                  _ev(3, "dwell", screen, _ts(10), {"duration_seconds": 70.0}))
            feats = {"scroll_depth_pct": 75, "chart_drilldowns_in_session": 3, "return_within_7_days": True}
            return Session(sid, screen, cohort, ev, feats), gt(False)
        if kind == "positive":
            ev = (_ev(1, "screen_view", screen, _ts(0)),
                  _ev(2, "error", screen, _ts(5), {"error_type": "validation_error"}),
                  _ev(3, "dwell", screen, _ts(13), {"duration_seconds": 60.0}))
            return Session(sid, screen, cohort, ev, {}), gt(True)
        if kind == "degraded_positive":  # PULSE-133 drift: friction occurred
            # (gt True) but dwell drifted below threshold → detector misses it
            ev = (_ev(1, "error", screen, _ts(0), {"error_type": "validation_error"}),
                  _ev(2, "dwell", screen, _ts(3), {"duration_seconds": 22.0}))
            return Session(sid, screen, cohort, ev, {}), gt(True)
        if kind == "negative":  # close-call: dwell near baseline → no fire
            ev = (_ev(1, "error", screen, _ts(0), {"error_type": "validation_error"}),
                  _ev(2, "dwell", screen, _ts(3), {"duration_seconds": 22.0}))
            return Session(sid, screen, cohort, ev, {}), gt(False)
        # noise: no error-then-dwell → abstain
        ev = (_ev(1, "back_press", screen, _ts(0)),)
        return Session(sid, screen, cohort, ev, {}), gt(False)

    if signature == "multi_back_press":
        if kind == "positive":  # tight burst → fires
            ev = tuple(_ev(1 + i, "back_press", screen, _ts(i * 8)) for i in range(4))
            return Session(sid, screen, cohort, ev, {}), gt(True)
        if kind == "degraded_positive":  # PULSE-133 drift: presses spaced out
            # (gt True) → burst no longer detected = missed detection
            ev = tuple(_ev(1 + i, "back_press", screen, _ts(i * 60)) for i in range(4))
            return Session(sid, screen, cohort, ev, {}), gt(True)
        if kind == "negative":  # spaced-out → deliberate review → no fire
            ev = tuple(_ev(1 + i, "back_press", screen, _ts(i * 60)) for i in range(4))
            return Session(sid, screen, cohort, ev, {}), gt(False)
        # noise: a single error/dwell, no back-presses → abstain
        ev = (_ev(1, "error", screen, _ts(0), {"error_type": "validation_error"}),
              _ev(2, "dwell", screen, _ts(3), {"duration_seconds": 18.0}))
        return Session(sid, screen, cohort, ev, {}), gt(False)

    # abandon_before_submit
    base_ev = (_ev(1, "screen_view", screen, _ts(0)),
               _ev(2, "nav_intent", screen, _ts(120), {"action": "exit"}))
    if kind == "positive":  # prior steps + long dwell + no submit + no return → fires
        feats = {"prior_steps_completed": ["step1", "step2"], "time_on_step_seconds": 120.0}
        return Session(sid, screen, cohort, base_ev, feats), gt(True)
    if kind == "degraded_positive":  # PULSE-133 drift: dwell drifted below the
        # percentile (gt True) → terminal-abandonment trigger missed
        feats = {"prior_steps_completed": ["step1", "step2"], "time_on_step_seconds": 35.0}
        return Session(sid, screen, cohort, base_ev, feats), gt(True)
    if kind == "negative":  # below the dwell percentile → no fire
        feats = {"prior_steps_completed": ["step1", "step2"], "time_on_step_seconds": 35.0}
        return Session(sid, screen, cohort, base_ev, feats), gt(False)
    # noise: prior steps incomplete → no fire
    feats = {"prior_steps_completed": ["step1"], "time_on_step_seconds": 120.0}
    return Session(sid, screen, cohort, base_ev, feats), gt(False)


def generate_corpus(
    sessions_per_cell: int = 100, negative_pool_size: int = 60,
    *, seed: int | None = None, drift_pct: float = 0.0,
) -> tuple[dict[int, list[tuple[Session, dict]]], list[tuple[Session, dict]]]:
    """Synthetic corpus. Per-cell mix follows TEST_SET_SPEC ratios (~65% positive-
    slot / 25% negative / 10% noise). Negative pool = sessions on non-target screens
    (false-positive substrate).

    PULSE-133 — `seed` / `drift_pct` are additive: `seed=None, drift_pct=0.0` (the
    defaults) reproduce the original byte-identical deterministic corpus. When
    `drift_pct > 0`, `round(n_pos * drift_pct)` true-positive sessions per positive
    cell are emitted as `degraded_positive` — ground-truth should_fire UNCHANGED, but
    sub-threshold events the detector misses (recall degradation = drift). `seed`
    jitters the degraded count ±1 for run-to-run noise. Cell 10 (engineered negative)
    is never degraded."""
    n_pos = round(sessions_per_cell * 0.65)
    n_neg = round(sessions_per_cell * 0.25)
    n_noise = sessions_per_cell - n_pos - n_neg
    rng = random.Random(seed) if seed is not None else None

    cell_sessions: dict[int, list[tuple[Session, dict]]] = {}
    for cell_id, screen, signature, _expect in CELLS:
        n_degraded = 0
        if drift_pct > 0 and cell_id != 10:
            base = n_pos * drift_pct
            if rng is not None:
                base += rng.uniform(-1.0, 1.0)
            n_degraded = max(0, min(n_pos, round(base)))
        items: list[tuple[Session, dict]] = []
        for i in range(n_pos):
            kind = "degraded_positive" if i < n_degraded else "positive"
            items.append(_make_session(cell_id, screen, signature, kind, i))
        for i in range(n_neg):
            items.append(_make_session(cell_id, screen, signature, "negative", i))
        for i in range(n_noise):
            items.append(_make_session(cell_id, screen, signature, "noise", i))
        cell_sessions[cell_id] = items

    negative_pool: list[tuple[Session, dict]] = []
    for i in range(negative_pool_size):
        screen = _NEGATIVE_SCREENS[i % len(_NEGATIVE_SCREENS)]
        # friction-looking session on a non-target screen — must NOT fire (screen-scoped)
        ev = (_ev(1, "screen_view", screen, _ts(0)),
              _ev(2, "error", screen, _ts(4), {"error_type": "validation_error"}),
              _ev(3, "dwell", screen, _ts(10), {"duration_seconds": 80.0}))
        gt = {"session_id": f"neg-{i}", "cell_id": "negative_screens", "screen_id": screen,
              "signature_id": "none", "should_fire": False, "root_cause": "none", "cohort_tags": []}
        negative_pool.append((Session(f"neg-{i}", screen, (), ev, {}), gt))
    return cell_sessions, negative_pool


# ── result + run ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FrictionBenchResult:
    per_cell_aggregate: dict[int, float]
    macro_average: float
    in_cell_false_positives: int
    negative_screen_false_positives: int
    penalised_score: float
    cell10_aggregate: float
    cell10_fired_count: int
    total_sessions: int
    runtime_version: str

    @property
    def cell10_passed(self) -> bool:
        return self.cell10_fired_count == 0 and self.cell10_aggregate > 0.9

    def render(self) -> str:
        lines = ["# FrictionBench v0.1 — detection-runtime run (synthetic corpus)\n"]
        lines.append(f"_Runtime {self.runtime_version} · {self.total_sessions} sessions · "
                     f"synthetic stand-in corpus (real corpus is TAQ-generated / contract-gated)._\n")
        lines.append("| Cell | Screen | Signature | Aggregate |")
        lines.append("|---|---|---|---|")
        for cell_id, screen, sig, expect in CELLS:
            mark = " (neg)" if expect == "negative" else ""
            lines.append(f"| {cell_id} | {screen} | {sig}{mark} | {self.per_cell_aggregate[cell_id]:.3f} |")
        lines.append("")
        lines.append(f"- **Macro-average:** {self.macro_average:.3f}")
        lines.append(f"- **In-cell false positives:** {self.in_cell_false_positives}")
        lines.append(f"- **Negative-screen false positives:** {self.negative_screen_false_positives} "
                     f"(detector is screen-scoped — packs cannot fire on screens they don't own)")
        lines.append(f"- **Penalised score (after FP penalty):** {self.penalised_score:.3f}")
        lines.append(f"- **Cell-10 acid test:** {'PASS' if self.cell10_passed else 'FAIL'} "
                     f"(aggregate {self.cell10_aggregate:.3f}, fired {self.cell10_fired_count})")
        lines.append("\n> Headline metric remains the synthetic-to-real transfer gap (PULSE-124) -- "
                     "this is a clean-synthetic harness-validation score, not the published figure.")
        return "\n".join(lines)


def run_frictionbench(
    sessions_per_cell: int = 100, negative_pool_size: int = 60
) -> FrictionBenchResult:
    cell_sessions, negative_pool = generate_corpus(sessions_per_cell, negative_pool_size)

    per_cell: dict[int, float] = {}
    in_cell_fp = 0
    cell10_fired = 0
    total = 0

    for cell_id, screen, signature, _expect in CELLS:
        hyp = _hypothesis_for(cell_id, screen, signature)
        baseline = _baseline_for(signature, screen)
        scores = []
        for session, gt in cell_sessions[cell_id]:
            total += 1
            det = run_detection(hypothesis=hyp, session=session, baseline=baseline)
            scores.append(score_detection(det.to_scoring_dict(), gt))
            if det.fired and not gt["should_fire"]:
                in_cell_fp += 1
                if cell_id == 10:
                    cell10_fired += 1
        per_cell[cell_id] = aggregate_cell(scores)

    # False-positive substrate: run every pack over the negative-screen pool.
    # Screen-scoping means every pack abstains (screen mismatch) → 0 FP.
    neg_fp = 0
    for cell_id, screen, signature, _expect in CELLS:
        hyp = _hypothesis_for(cell_id, screen, signature)
        baseline = _baseline_for(signature, screen)
        for session, gt in negative_pool:
            total += 1
            det = run_detection(hypothesis=hyp, session=session, baseline=baseline)
            if det.fired:
                neg_fp += 1

    macro = macro_average(list(per_cell.values()))
    penalised = apply_false_positive_penalty(macro, in_cell_fp + neg_fp)

    return FrictionBenchResult(
        per_cell_aggregate=per_cell,
        macro_average=macro,
        in_cell_false_positives=in_cell_fp,
        negative_screen_false_positives=neg_fp,
        penalised_score=penalised,
        cell10_aggregate=per_cell[10],
        cell10_fired_count=cell10_fired,
        total_sessions=total,
        runtime_version=DETECTION_RUNTIME_VERSION,
    )


def main() -> None:
    # Full-spec dimensions for the headline run.
    result = run_frictionbench(sessions_per_cell=1000, negative_pool_size=754)
    print(result.render())


if __name__ == "__main__":
    main()
