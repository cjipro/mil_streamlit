"""Compose Diagnosis + Risk + Value onto the pipeline's fired detections (PULSE-99/101/105).

Aggregates the pipeline session-friction mart (pulse.pipeline.detect_sessions) into
one finding per (screen x signature), measures the Risk/Value input metrics from the
real MA_S sessions, scores both axes, and composes the CLARK-style Action tier
(Value x Risk 2x2): ACUTE / REGULATORY-FLAG / COMMERCIAL-OPPORTUNITY / WATCH / NOMINAL.

Diagnosis (problem-locus / AI-deployability) needs an assistance-vs-control arm
comparison. The synthetic pipeline runs control-only (no Lever/AI assistance arm),
so Diagnosis reports NOT_ASSESSED unless the caller supplies assistance arms — at
which point the real `diagnose_problem_locus` is run. The friction Action tier is
driven by Risk x Value regardless, so a finding is decided even when AI-placement
isn't yet assessable.

Run:  py -m pulse.decision.score_findings
"""

from __future__ import annotations

import argparse
import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from pulse.convergence.fairness import assess_fairness
from pulse.decision.chronicle import (
    chronicle_library,
    is_chronicle_candidate,
    propose_chronicle_candidates,
)
from pulse.decision.lineage import build_decision_lineage
from pulse.diagnosis import (
    DiagnosisResult,
    JourneyArmObservation,
    JourneyIdentity,
    diagnose_problem_locus,
)
from pulse.risk import FrictionShape, ImpactMetrics, score_risk
from pulse.serving.marts import MARTS_DIR, PIPELINE_SESSION_FRICTION_PARQUET
from pulse.value import ValueMetrics, ValueShape, score_value

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_MA_S = _REPO / "dist" / "ma_s"
_BANK_POLICY_PATH = Path(__file__).parent / "synthetic_deployment.yaml"
_PACKS_DIR = _REPO / "pulse" / "decision_packs"
DECISIONS_PARQUET = MARTS_DIR / "decisions.parquet"

# Friction-target screen -> regulatory screen_class (vocabulary from
# pulse/risk/regulatory_taxonomy.yaml). journey_category comes from MA_S.
_SCREEN_CLASS = {
    "loans.apply.step3": "credit_application",
    "cards.credit.apply.eligibility": "credit_application",
    "international.beneficiary.setup": "payment_initiation",
    "investments.premier.portfolio.overview": "account_management",
}
_SEVERITY_CLASS_TO_P = {"high": "P0", "medium": "P1", "low": "P2"}

# CLARK-style Action tier (canvas-as-discipline lock) — Value x Risk 2x2.
_HIGH_VALUE = {"SIGNIFICANT", "COMMERCIAL-OPPORTUNITY"}
_HIGH_RISK = {"ESCALATE", "REGULATORY-FLAG"}

# Per-(screen x signature) metrics, aggregated from the friction mart joined to MA_S.
_FINDINGS_SQL = """
WITH fr AS (
    SELECT session_id, screen_id, target_signature, fired, cohort_tags
    FROM read_parquet($friction)
),
s AS (
    SELECT session_id, journey_id, journey_category, outcome, n_events,
           list_contains(cohort_tags, 'vulnerable_flag') AS is_vuln
    FROM read_parquet($ma_s, hive_partitioning = true)
),
j AS (
    SELECT fr.screen_id, fr.target_signature, fr.fired,
           s.journey_id, s.journey_category, s.outcome, s.n_events, s.is_vuln
    FROM fr JOIN s USING (session_id)
)
SELECT
    screen_id,
    target_signature,
    any_value(journey_id)                                              AS journey_id,
    any_value(journey_category)                                        AS journey_category,
    count(*)                                                           AS total_sessions,
    sum(fired::INT)                                                    AS affected_sessions,
    coalesce(avg(n_events) FILTER (WHERE fired), 0.0)                  AS avg_events_affected,
    coalesce(avg(CASE WHEN outcome = 'abandoned' THEN 1.0 ELSE 0.0 END)
             FILTER (WHERE fired), 0.0)                                AS abandon_share_affected,
    coalesce(avg(CASE WHEN is_vuln THEN 1.0 ELSE 0.0 END)
             FILTER (WHERE fired), 0.0)                                AS vuln_share_affected,
    coalesce(avg(CASE WHEN is_vuln THEN 1.0 ELSE 0.0 END), 0.0)        AS baseline_vuln_share,
    sum(CASE WHEN is_vuln AND fired THEN 1 ELSE 0 END)                 AS vuln_fired,
    sum(CASE WHEN is_vuln THEN 1 ELSE 0 END)                           AS vuln_total,
    sum(CASE WHEN (NOT is_vuln) AND fired THEN 1 ELSE 0 END)           AS nonvuln_fired,
    sum(CASE WHEN NOT is_vuln THEN 1 ELSE 0 END)                       AS nonvuln_total
FROM j
GROUP BY screen_id, target_signature
HAVING sum(fired::INT) > 0
ORDER BY affected_sessions DESC
"""


@dataclass(frozen=True)
class DecisionRecord:
    """One scored finding: Risk + Value + composed Action tier + Diagnosis state."""

    screen_id: str
    signature: str
    journey_id: str
    journey_category: str
    screen_class: str
    severity: str
    affected_sessions: int
    total_sessions: int
    fire_rate: float
    vulnerable_cohort_share: float
    counterfactual_baseline_pct: float
    risk_tier: str
    risk_numeric: int
    regulatory_matches: tuple[str, ...]
    value_tier: str
    value_numeric: int
    recoverable_sessions_per_week: int | None
    recoverable_sessions_per_month: int | None
    estimated_monthly_lift_gbp: float | None
    action_tier: str
    diagnosis: str
    diagnosis_reason: str
    recommendation: str
    fairness_assessed: bool
    fairness_disparity_ratio: float | None
    fairness_parity_difference: float | None
    fairness_chi2_p: float | None
    fairness_disparate_impact: bool
    fairness_independent_review: bool
    fairness_note: str
    chronicle_matches: tuple[str, ...]
    chronicle_candidate: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "signature": self.signature,
            "journey_id": self.journey_id,
            "journey_category": self.journey_category,
            "screen_class": self.screen_class,
            "severity": self.severity,
            "affected_sessions": self.affected_sessions,
            "total_sessions": self.total_sessions,
            "fire_rate": self.fire_rate,
            "vulnerable_cohort_share": self.vulnerable_cohort_share,
            "counterfactual_baseline_pct": self.counterfactual_baseline_pct,
            "risk_tier": self.risk_tier,
            "risk_numeric": self.risk_numeric,
            "regulatory_matches": list(self.regulatory_matches),
            "value_tier": self.value_tier,
            "value_numeric": self.value_numeric,
            "recoverable_sessions_per_week": self.recoverable_sessions_per_week,
            "recoverable_sessions_per_month": self.recoverable_sessions_per_month,
            "estimated_monthly_lift_gbp": self.estimated_monthly_lift_gbp,
            "action_tier": self.action_tier,
            "diagnosis": self.diagnosis,
            "diagnosis_reason": self.diagnosis_reason,
            "recommendation": self.recommendation,
            "fairness_assessed": self.fairness_assessed,
            "fairness_disparity_ratio": self.fairness_disparity_ratio,
            "fairness_parity_difference": self.fairness_parity_difference,
            "fairness_chi2_p": self.fairness_chi2_p,
            "fairness_disparate_impact": self.fairness_disparate_impact,
            "fairness_independent_review": self.fairness_independent_review,
            "fairness_note": self.fairness_note,
            "chronicle_matches": list(self.chronicle_matches),
            "chronicle_candidate": self.chronicle_candidate,
        }


@functools.lru_cache(maxsize=1)
def load_bank_policy() -> dict[str, Any]:
    with _BANK_POLICY_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=None)
def _severity_for(screen_id: str, signature: str) -> str:
    """Read severity_class from the decision pack's hypothesis.yaml (high/medium/low
    -> P0/P1/P2) — the production engine consumes the methodology-vocabulary P-level."""
    pack_dir = f"{screen_id.replace('.', '_')}__{signature}"
    hyp_path = _PACKS_DIR / pack_dir / "hypothesis.yaml"
    if not hyp_path.exists():
        return "P2"
    with hyp_path.open("r", encoding="utf-8") as f:
        hyp = yaml.safe_load(f)
    sev_class = (hyp.get("value_inputs") or {}).get("severity_class", "low")
    return _SEVERITY_CLASS_TO_P.get(sev_class, "P2")


@functools.lru_cache(maxsize=None)
def _fairness_threshold(screen_id: str, signature: str) -> float:
    """Independent-review trigger threshold from the pack's fairness block
    (cohort_recall_disparity_above); default 0.15."""
    pack_dir = f"{screen_id.replace('.', '_')}__{signature}"
    hyp_path = _PACKS_DIR / pack_dir / "hypothesis.yaml"
    if not hyp_path.exists():
        return 0.15
    with hyp_path.open("r", encoding="utf-8") as f:
        hyp = yaml.safe_load(f)
    trig = (hyp.get("fairness") or {}).get("trigger_independent_review_if") or {}
    return float(trig.get("cohort_recall_disparity_above", 0.15))


def _compose_action_tier(risk_tier: str, value_tier: str) -> str:
    """Value x Risk 2x2 -> CLARK-style friction Action tier."""
    high_value = value_tier in _HIGH_VALUE
    high_risk = risk_tier in _HIGH_RISK
    if high_value and high_risk:
        return "ACUTE"
    if high_risk:
        return "REGULATORY-FLAG"
    if high_value:
        return "COMMERCIAL-OPPORTUNITY"
    if risk_tier == "NOMINAL" and value_tier == "NOMINAL":
        return "NOMINAL"
    return "WATCH"


def _recommendation(action_tier: str, recoverable_month: int | None) -> str:
    vol = f" ~{recoverable_month} recoverable sessions/mo" if recoverable_month else ""
    return {
        "ACUTE": f"Act now — high commercial value + high regulatory exposure.{vol}",
        "REGULATORY-FLAG": "Escalate to compliance — regulatory exposure outweighs commercial upside.",
        "COMMERCIAL-OPPORTUNITY": f"Prioritise — strong recoverable value, low regulatory risk.{vol}",
        "WATCH": "Monitor — modest signal on both axes.",
        "NOMINAL": "No action — low value, low risk.",
    }[action_tier]


def score_findings(
    *,
    ma_s_dir: str | Path = _DEFAULT_MA_S,
    friction_parquet: Path = PIPELINE_SESSION_FRICTION_PARQUET,
    assistance_arms: dict[str, JourneyArmObservation] | None = None,
) -> list[DecisionRecord]:
    """Aggregate fired detections into findings and score each (Risk/Value/Diagnosis).

    `assistance_arms` maps journey_id -> the AI-assistance arm observation. When a
    finding's journey has one, Diagnosis is computed against the journey's real
    control sessions; otherwise it reports NOT_ASSESSED."""
    bank_policy = load_bank_policy()
    glob = str(Path(ma_s_dir) / "**" / "*.parquet")

    con = duckdb.connect()
    try:
        rows = con.execute(
            _FINDINGS_SQL, {"friction": str(friction_parquet), "ma_s": glob}
        ).fetchall()
        cols = [c[0] for c in con.description]
        # control-arm (no-AI) success rate per journey — completed share — for Diagnosis
        control = {
            r[0]: (int(r[1]), float(r[2]))
            for r in con.execute(
                "SELECT journey_id, count(*), "
                "avg(CASE WHEN outcome = 'completed' THEN 1.0 ELSE 0.0 END) "
                "FROM read_parquet($ma_s, hive_partitioning = true) GROUP BY journey_id",
                {"ma_s": glob},
            ).fetchall()
        }
    finally:
        con.close()

    decisions: list[DecisionRecord] = []
    for row in rows:
        m = dict(zip(cols, row))
        screen_id = m["screen_id"]
        signature = m["target_signature"]
        journey_id = m["journey_id"]
        journey_category = m["journey_category"]
        screen_class = _SCREEN_CLASS.get(screen_id, "account_management")
        severity = _severity_for(screen_id, signature)

        affected = int(m["affected_sessions"])
        total = int(m["total_sessions"])
        vuln_share = float(m["vuln_share_affected"])
        baseline_vuln = float(m["baseline_vuln_share"])
        overrep = round(vuln_share / baseline_vuln, 4) if baseline_vuln > 0 else 1.0
        counterfactual = round(float(m["abandon_share_affected"]), 4)

        risk = score_risk(
            shape=FrictionShape(signature, journey_category, screen_class, severity),
            impact=ImpactMetrics(
                affected_customers_7d=affected,
                vulnerable_cohort_overrep_ratio=overrep,
            ),
            bank_policy=bank_policy,
            chronicle_library=chronicle_library(),
        )
        value = score_value(
            shape=ValueShape(signature, journey_category, screen_class, severity),
            metrics=ValueMetrics(
                affected_customers_7d=affected,
                avg_events_per_affected_user=round(float(m["avg_events_affected"]), 2),
                vulnerable_cohort_share=vuln_share,
                counterfactual_baseline_pct=counterfactual,
            ),
            bank_policy=bank_policy,
        )
        action_tier = _compose_action_tier(risk.tier, value.tier)
        diagnosis, reason = _diagnose(journey_id, screen_class, control, assistance_arms)

        # Fairness lens — only on high-stakes (escalated Risk) findings, per the
        # convergence design (don't run on every low-stakes investigation).
        fairness = None
        if risk.tier in _HIGH_RISK:
            fairness = assess_fairness(
                protected_fired=int(m["vuln_fired"]),
                protected_total=int(m["vuln_total"]),
                reference_fired=int(m["nonvuln_fired"]),
                reference_total=int(m["nonvuln_total"]),
            )
        assessed = bool(fairness and fairness.assessed)
        indep_review = bool(
            assessed
            and fairness.statistically_significant
            and fairness.parity_difference is not None
            and abs(fairness.parity_difference) >= _fairness_threshold(screen_id, signature)
        )
        recommendation = _recommendation(action_tier, value.recoverable_sessions_per_month)
        if indep_review:
            recommendation += (
                " — vulnerable-cohort disparity flagged: independent fairness review triggered."
            )
        chronicle_candidate = is_chronicle_candidate(
            risk_tier=risk.tier, fairness_independent_review=indep_review
        )

        decisions.append(DecisionRecord(
            screen_id=screen_id,
            signature=signature,
            journey_id=journey_id,
            journey_category=journey_category,
            screen_class=screen_class,
            severity=severity,
            affected_sessions=affected,
            total_sessions=total,
            fire_rate=round(affected / total, 4) if total else 0.0,
            vulnerable_cohort_share=round(vuln_share, 4),
            counterfactual_baseline_pct=counterfactual,
            risk_tier=risk.tier,
            risk_numeric=risk.numeric_tier,
            regulatory_matches=risk.regulatory_matches,
            value_tier=value.tier,
            value_numeric=value.numeric_tier,
            recoverable_sessions_per_week=value.recoverable_sessions_per_week,
            recoverable_sessions_per_month=value.recoverable_sessions_per_month,
            estimated_monthly_lift_gbp=value.estimated_monthly_lift_gbp,
            action_tier=action_tier,
            diagnosis=diagnosis,
            diagnosis_reason=reason,
            recommendation=recommendation,
            fairness_assessed=assessed,
            fairness_disparity_ratio=fairness.disparity_ratio if assessed else None,
            fairness_parity_difference=fairness.parity_difference if assessed else None,
            fairness_chi2_p=fairness.chi2_p_value if assessed else None,
            fairness_disparate_impact=bool(fairness and fairness.disparate_impact),
            fairness_independent_review=indep_review,
            fairness_note=(fairness.reason if fairness else "not assessed — low-stakes (Risk not escalated)"),
            chronicle_matches=risk.chronicle_matches,
            chronicle_candidate=chronicle_candidate,
        ))

    # ACUTE first, then by recoverable volume
    order = {"ACUTE": 0, "REGULATORY-FLAG": 1, "COMMERCIAL-OPPORTUNITY": 2, "WATCH": 3, "NOMINAL": 4}
    decisions.sort(key=lambda d: (order[d.action_tier], -(d.recoverable_sessions_per_month or 0)))
    return decisions


def _diagnose(
    journey_id: str,
    screen_class: str,
    control: dict[str, tuple[int, float]],
    assistance_arms: dict[str, JourneyArmObservation] | None,
) -> tuple[str, str]:
    """Run problem-locus diagnosis when an assistance arm is available; else honest
    NOT_ASSESSED (the synthetic pipeline is control-only — no Lever assistance arm)."""
    if not assistance_arms or journey_id not in assistance_arms:
        return ("NOT_ASSESSED",
                "no assistance arm — synthetic pipeline is control-only; "
                "AI-placement diagnosis activates when a Lever assistance experiment exists")
    ctrl_n, ctrl_success = control.get(journey_id, (0, 0.0))
    result: DiagnosisResult = diagnose_problem_locus(
        journey=JourneyIdentity(journey_id=journey_id, screen_class=screen_class),
        assistance_arm=assistance_arms[journey_id],
        no_assistance_arm=JourneyArmObservation(n_sessions=ctrl_n, success_rate=round(ctrl_success, 4)),
    )
    return (result.diagnosis, f"gap={result.gap}")


_DECISIONS_SCHEMA = pa.schema([
    ("screen_id", pa.string()), ("signature", pa.string()),
    ("journey_id", pa.string()), ("journey_category", pa.string()),
    ("screen_class", pa.string()), ("severity", pa.string()),
    ("affected_sessions", pa.int64()), ("total_sessions", pa.int64()),
    ("fire_rate", pa.float64()), ("vulnerable_cohort_share", pa.float64()),
    ("counterfactual_baseline_pct", pa.float64()),
    ("risk_tier", pa.string()), ("risk_numeric", pa.int64()),
    ("regulatory_matches", pa.list_(pa.string())),
    ("value_tier", pa.string()), ("value_numeric", pa.int64()),
    ("recoverable_sessions_per_week", pa.int64()),
    ("recoverable_sessions_per_month", pa.int64()),
    ("estimated_monthly_lift_gbp", pa.float64()),
    ("action_tier", pa.string()), ("diagnosis", pa.string()),
    ("diagnosis_reason", pa.string()), ("recommendation", pa.string()),
    ("fairness_assessed", pa.bool_()),
    ("fairness_disparity_ratio", pa.float64()),
    ("fairness_parity_difference", pa.float64()),
    ("fairness_chi2_p", pa.float64()),
    ("fairness_disparate_impact", pa.bool_()),
    ("fairness_independent_review", pa.bool_()),
    ("fairness_note", pa.string()),
    ("chronicle_matches", pa.list_(pa.string())),
    ("chronicle_candidate", pa.bool_()),
    ("lineage_id", pa.string()), ("lineage_row_hash", pa.string()),
])


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def build_decisions(
    *,
    ma_s_dir: str | Path = _DEFAULT_MA_S,
    friction_parquet: Path = PIPELINE_SESSION_FRICTION_PARQUET,
) -> dict[str, Any]:
    """Score findings, hash-chain them into the lineage log, write the decisions mart."""
    decisions = score_findings(ma_s_dir=ma_s_dir, friction_parquet=friction_parquet)

    lineage = build_decision_lineage(
        decisions,
        ma_s_manifest=_read_manifest(Path(ma_s_dir) / "_MANIFEST.json"),
        friction_manifest=_read_manifest(
            friction_parquet.parent / "session_friction_pipeline._MANIFEST.json"
        ),
        bank_policy=load_bank_policy(),
    )
    anchor = lineage["decision_anchor"]

    rows: list[dict[str, Any]] = []
    for d in decisions:
        row = d.as_dict()
        lineage_id, row_hash = anchor[(d.screen_id, d.signature)]
        row["lineage_id"] = lineage_id
        row["lineage_row_hash"] = row_hash
        rows.append(row)

    MARTS_DIR.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=_DECISIONS_SCHEMA)
    pq.write_table(table, DECISIONS_PARQUET)

    chronicle = propose_chronicle_candidates(
        rows, deployment_id=load_bank_policy().get("deployment_id", "unknown")
    )

    tiers: dict[str, int] = {}
    for d in decisions:
        tiers[d.action_tier] = tiers.get(d.action_tier, 0) + 1
    manifest = {
        "mart": "decisions",
        "grain": "one row per (screen x signature) fired finding",
        "row_count": len(decisions),
        "action_tier_counts": tiers,
        "deployment_id": load_bank_policy().get("deployment_id"),
        "parquet": str(DECISIONS_PARQUET),
        "lineage_log": lineage["log_path"],
        "lineage_head_row_hash": lineage["head_row_hash"],
        "lineage_verified": lineage["chain_verified"],
        "chronicle_candidates": chronicle["candidates"],
        "chronicle_candidates_log": chronicle["log_path"],
    }
    (MARTS_DIR / "decisions._MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def read_decisions() -> list[dict]:
    """Read the decisions mart as JSON-serialisable rows (FastAPI-facing)."""
    if not DECISIONS_PARQUET.exists():
        build_decisions()
    con = duckdb.connect(database=":memory:")
    try:
        cur = con.execute(
            "SELECT * FROM read_parquet(?) "
            "ORDER BY array_position(['ACUTE','REGULATORY-FLAG','COMMERCIAL-OPPORTUNITY',"
            "'WATCH','NOMINAL'], action_tier), recoverable_sessions_per_month DESC",
            [str(DECISIONS_PARQUET)],
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Score fired detections into decisions")
    p.add_argument("--ma-s", type=str, default=str(_DEFAULT_MA_S))
    p.parse_args()
    print(json.dumps(build_decisions(), indent=2))


if __name__ == "__main__":
    main()
