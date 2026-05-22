"""Agentic AI placement scenario — orchestrator (PULSE-106).

Runs the v0 engine spine end-to-end across the cells declared in
scenario.yaml:

    Diagnosis (PULSE-105)  →  is this an AI-deployable problem?
        ↓
    Risk      (PULSE-99)   →  how exposed if we deploy / don't?
        ↓
    Value     (PULSE-101)  →  how big is the prize if we deploy?
        ↓
    Action tier            →  CLARK-style placement decision

Output is a `PlacementMatrix` (one `PlacementCell` per scenario cell).
A Markdown renderer prints the matrix to stdout when run as
`py -m pulse.scenarios.agentic_ai_placement.run`.

Filed under PULSE-106.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pulse.diagnosis import (
    DiagnosisResult,
    JourneyArmObservation,
    JourneyIdentity,
    diagnose_problem_locus,
)
from pulse.risk import (
    FrictionShape,
    ImpactMetrics,
    RiskScore,
    score_risk,
)
from pulse.value import (
    ValueMetrics,
    ValueScore,
    ValueShape,
    score_value,
)

_SCENARIO_PATH = Path(__file__).parent / "scenario.yaml"


# CLARK-style Action tier (canvas-as-discipline lock 2026-05-18).
# Composes the Value × Risk 2x2 into one of five placement decisions.
_HIGH_VALUE = {"SIGNIFICANT", "COMMERCIAL-OPPORTUNITY"}
_HIGH_RISK = {"ESCALATE", "REGULATORY-FLAG"}


@dataclass(frozen=True)
class PlacementCell:
    """One cell in the Agentic AI placement matrix — composed from
    Diagnosis + Risk + Value + the CLARK-style Action tier."""

    journey_id: str
    screen_class: str
    signature_id: str
    diagnosis: DiagnosisResult
    risk: RiskScore
    value: ValueScore
    action_tier: str           # CLARK-style: ACUTE / REGULATORY-FLAG /
                               # COMMERCIAL-OPPORTUNITY / WATCH / NOMINAL
    placement_recommendation: str  # plain-product sentence

    def as_dict(self) -> dict[str, Any]:
        return {
            "journey_id": self.journey_id,
            "screen_class": self.screen_class,
            "signature_id": self.signature_id,
            "diagnosis": self.diagnosis.diagnosis,
            "risk": self.risk.tier,
            "value": self.value.tier,
            "action_tier": self.action_tier,
            "placement_recommendation": self.placement_recommendation,
        }


@dataclass(frozen=True)
class PlacementMatrix:
    """The full placement matrix output — list of cells + the bank_policy
    + methodology version trail for the audit footer."""

    cells: tuple[PlacementCell, ...]
    deployment_id: str
    diagnosis_methodology_version: str
    risk_methodology_version: str
    value_methodology_version: str

    def render_markdown(self) -> str:
        """Markdown rendering suitable for screenshot / paste into briefing."""
        lines: list[str] = []
        lines.append(f"# Agentic AI placement matrix — `{self.deployment_id}`\n")
        lines.append(
            f"_Methodology versions: Diagnosis {self.diagnosis_methodology_version} · "
            f"Risk {self.risk_methodology_version} · "
            f"Value {self.value_methodology_version}_\n"
        )
        lines.append(
            "| Journey | Signature | Diagnosis | Risk | Value | "
            "Action tier | Placement |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for c in self.cells:
            lines.append(
                f"| `{c.journey_id}` | `{c.signature_id}` | {c.diagnosis.diagnosis} "
                f"| {c.risk.tier} | {c.value.tier} | **{c.action_tier}** | "
                f"{c.placement_recommendation} |"
            )
        return "\n".join(lines) + "\n"


def run_placement_scenario(
    scenario_path: Path | str | None = None,
) -> PlacementMatrix:
    """Run the placement scenario end-to-end. Returns the PlacementMatrix.
    Pure function over the scenario file — same scenario.yaml input
    always produces the same matrix."""
    path = Path(scenario_path) if scenario_path else _SCENARIO_PATH
    with path.open("r", encoding="utf-8") as f:
        scenario = yaml.safe_load(f)

    bank_policy = scenario["bank_policy"]
    cells: list[PlacementCell] = []

    for cell_cfg in scenario["cells"]:
        diagnosis = _run_diagnosis(cell_cfg)
        risk = _run_risk(cell_cfg, bank_policy)
        value = _run_value(cell_cfg, bank_policy)
        action_tier = _compose_action_tier(diagnosis, risk, value)
        placement = _placement_recommendation(diagnosis, action_tier)
        cells.append(
            PlacementCell(
                journey_id=cell_cfg["journey_id"],
                screen_class=cell_cfg["screen_class"],
                signature_id=cell_cfg["signature_id"],
                diagnosis=diagnosis,
                risk=risk,
                value=value,
                action_tier=action_tier,
                placement_recommendation=placement,
            )
        )

    return PlacementMatrix(
        cells=tuple(cells),
        deployment_id=bank_policy["deployment_id"],
        diagnosis_methodology_version=cells[0].diagnosis.methodology_version,
        risk_methodology_version=cells[0].risk.methodology_version,
        value_methodology_version=cells[0].value.methodology_version,
    )


# ── per-stage helpers ────────────────────────────────────────────────────────


def _run_diagnosis(cell_cfg: dict[str, Any]) -> DiagnosisResult:
    inputs = cell_cfg["diagnosis_inputs"]
    return diagnose_problem_locus(
        journey=JourneyIdentity(
            journey_id=cell_cfg["journey_id"],
            screen_class=cell_cfg["screen_class"],
        ),
        assistance_arm=JourneyArmObservation(
            n_sessions=inputs["assistance_arm"]["n_sessions"],
            success_rate=inputs["assistance_arm"]["success_rate"],
        ),
        no_assistance_arm=JourneyArmObservation(
            n_sessions=inputs["no_assistance_arm"]["n_sessions"],
            success_rate=inputs["no_assistance_arm"]["success_rate"],
        ),
    )


def _run_risk(
    cell_cfg: dict[str, Any], bank_policy: dict[str, Any]
) -> RiskScore:
    return score_risk(
        shape=FrictionShape(
            signature_id=cell_cfg["signature_id"],
            # Map screen_class to journey_category via the regulatory
            # taxonomy expectation: credit_application + payment_initiation
            # sit under choke_point/infrastructure depending on the
            # taxonomy entry. For this scenario we pick the journey_category
            # the regulatory taxonomy's most-specific match would imply.
            journey_category=_journey_category_for(cell_cfg["screen_class"]),
            screen_class=cell_cfg["screen_class"],
            severity=_severity_for(cell_cfg["pack_dir"]),
        ),
        impact=ImpactMetrics(
            affected_customers_7d=cell_cfg["risk_impact"]["affected_customers_7d"],
            vulnerable_cohort_overrep_ratio=cell_cfg["risk_impact"][
                "vulnerable_cohort_overrep_ratio"
            ],
        ),
        bank_policy=bank_policy,
        # Chronicle library deliberately not wired here at v0 — seed-batch
        # Chronicle entries ship pending_human_review, matcher fails closed.
        # PULSE-106 worked example consumes Diagnosis + Risk + Value only.
        chronicle_library=None,
    )


def _run_value(
    cell_cfg: dict[str, Any], bank_policy: dict[str, Any]
) -> ValueScore:
    return score_value(
        shape=ValueShape(
            signature_id=cell_cfg["signature_id"],
            journey_category=_journey_category_for(cell_cfg["screen_class"]),
            screen_class=cell_cfg["screen_class"],
            severity=_severity_for(cell_cfg["pack_dir"]),
        ),
        metrics=ValueMetrics(
            affected_customers_7d=cell_cfg["value_metrics"]["affected_customers_7d"],
            avg_events_per_affected_user=cell_cfg["value_metrics"][
                "avg_events_per_affected_user"
            ],
            vulnerable_cohort_share=cell_cfg["value_metrics"]["vulnerable_cohort_share"],
            counterfactual_baseline_pct=cell_cfg["value_metrics"][
                "counterfactual_baseline_pct"
            ],
        ),
        bank_policy=bank_policy,
    )


def _journey_category_for(screen_class: str) -> str:
    """Pick a journey_category that the regulatory_taxonomy supports for
    the given screen_class. Conservative mapping for the v0 worked
    example — real engine consumption derives this from the pack's
    declared journey_category instead."""
    mapping = {
        "credit_application": "choke_point",
        "payment_initiation": "infrastructure",
        "account_management": "context_loss",
    }
    return mapping.get(screen_class, "behavioural_noise")


_SEVERITY_CLASS_TO_P = {"high": "P0", "medium": "P1", "low": "P2"}
_DECISION_PACKS_DIR = Path(__file__).parent.parent.parent / "decision_packs"


def _severity_for(pack_dir: str) -> str:
    """Read severity_class from the pack's hypothesis.yaml value_inputs
    and map high→P0 / medium→P1 / low→P2. This is what the production
    engine does — packs declare severity_class, the methodology consumes
    the methodology-vocabulary P0/P1/P2."""
    hyp_path = _DECISION_PACKS_DIR / pack_dir / "hypothesis.yaml"
    with hyp_path.open("r", encoding="utf-8") as f:
        hyp = yaml.safe_load(f)
    sev_class = hyp["value_inputs"]["severity_class"]
    return _SEVERITY_CLASS_TO_P[sev_class]


# ── CLARK-style Action tier composition ──────────────────────────────────────


def _compose_action_tier(
    diagnosis: DiagnosisResult, risk: RiskScore, value: ValueScore
) -> str:
    """Compose Risk × Value into the CLARK-style Action tier per the
    canvas-as-discipline lock (CLAUDE.md 2026-05-18).

    Diagnosis is allowed to OVERRIDE — an INCONCLUSIVE diagnosis short-
    circuits to NEEDS_MORE_DATA regardless of Risk/Value; otherwise the
    2x2 fires normally."""
    if diagnosis.diagnosis == "INCONCLUSIVE":
        return "NEEDS_MORE_DATA"

    high_value = value.tier in _HIGH_VALUE
    high_risk = risk.tier in _HIGH_RISK

    if high_value and high_risk:
        return "ACUTE"
    if high_risk and not high_value:
        return "REGULATORY-FLAG"
    if high_value and not high_risk:
        return "COMMERCIAL-OPPORTUNITY"
    if risk.tier == "NOMINAL" and value.tier == "NOMINAL":
        return "NOMINAL"
    return "WATCH"


def _placement_recommendation(
    diagnosis: DiagnosisResult, action_tier: str
) -> str:
    """Plain-product placement sentence per (Diagnosis × Action) cell.
    The Diagnosis label dominates the verb (don't deploy AI where the
    journey itself is broken) — Action tier shapes the modifier."""
    if action_tier == "NEEDS_MORE_DATA":
        return "Insufficient control-arm data — collect more sessions before deciding"
    if diagnosis.diagnosis == "JOURNEY_PROBLEM":
        return "Fix the journey itself — AI assistance is symptomatic relief here"
    if diagnosis.diagnosis == "BOTH":
        return "Fix the journey first, then deploy AI to the support layer"

    # SUPPORT_PROBLEM diagnoses: AI deployment is the right intervention;
    # Action tier modulates urgency / guardrails.
    if action_tier == "ACUTE":
        return "Deploy AI assistance with heavy guardrails — high value + high regulatory exposure"
    if action_tier == "REGULATORY-FLAG":
        return "Do not deploy AI assistance — regulatory exposure outweighs benefit"
    if action_tier == "COMMERCIAL-OPPORTUNITY":
        return "Deploy AI assistance here first — high commercial unlock, low regulatory risk"
    if action_tier == "WATCH":
        return "Monitor — modest signal on both axes; not a priority for AI deployment"
    return "Not worth deploying AI assistance — low value, low risk"


if __name__ == "__main__":
    matrix = run_placement_scenario()
    print(matrix.render_markdown())
