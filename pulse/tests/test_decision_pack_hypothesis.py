"""Tests for the hypothesis.yaml canvas-completeness validator (PULSE-103).

Key invariants:
- canvas-completeness gate: actors / value_inputs / risk_inputs all required
- computed-slot immutability gate: no value_output / no risk_output
- cross-validation: regulatory_taxonomies references real codes from
  pulse/risk/regulatory_taxonomy.yaml
- the 12 existing seed-batch hypothesis.yaml files all FAIL under this
  new validator (expected — PULSE-104 backfill is the follow-up)
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pulse.decision_packs import (
    DecisionPackHypothesisError,
    load_hypothesis,
    validate_hypothesis,
)

_DECISION_PACKS_DIR = Path(__file__).parent.parent / "decision_packs"


def _good_hypothesis() -> dict:
    return {
        "actors": ["investigation_consumer", "compliance_reviewer"],
        "value_inputs": {
            "severity_class": "high",
            "vulnerable_cohort_sensitivity": True,
            "population_segment_addressed": "uk_retail_credit_applicants",
        },
        "risk_inputs": {
            "regulatory_taxonomies": [
                "fca_consumer_duty.outcome_3_consumer_understanding",
                "fca_consumer_duty.outcome_4_consumer_support",
            ],
            "policy_areas": ["vulnerable_customer_handling"],
            "chronicle_precedents": ["CHR-friction-005"],
        },
    }


def test_good_hypothesis_passes() -> None:
    validate_hypothesis(_good_hypothesis())


def test_minimal_hypothesis_passes() -> None:
    """Empty lists for policy_areas + regulatory_taxonomies + omitted
    chronicle_precedents must all pass — they're valid declarations."""
    minimal = {
        "actors": ["ml_engineer"],
        "value_inputs": {
            "severity_class": "low",
            "vulnerable_cohort_sensitivity": False,
            "population_segment_addressed": "any",
        },
        "risk_inputs": {
            "regulatory_taxonomies": [],
            "policy_areas": [],
        },
    }
    validate_hypothesis(minimal)


# --- Gate 1: canvas-completeness --------------------------------------------


@pytest.mark.parametrize(
    "missing_field", ["actors", "value_inputs", "risk_inputs"]
)
def test_missing_canvas_slot_rejected(missing_field: str) -> None:
    bad = _good_hypothesis()
    del bad[missing_field]
    with pytest.raises(DecisionPackHypothesisError, match="missing required canvas slots"):
        validate_hypothesis(bad)


def test_actors_must_be_non_empty_list() -> None:
    bad = _good_hypothesis()
    bad["actors"] = []
    with pytest.raises(DecisionPackHypothesisError, match="actors"):
        validate_hypothesis(bad)


def test_actor_outside_enum_rejected() -> None:
    bad = _good_hypothesis()
    bad["actors"] = ["product_manager"]  # not in the closed enum
    with pytest.raises(DecisionPackHypothesisError, match="actors"):
        validate_hypothesis(bad)


def test_value_inputs_missing_key_rejected() -> None:
    bad = _good_hypothesis()
    del bad["value_inputs"]["severity_class"]
    with pytest.raises(DecisionPackHypothesisError, match="value_inputs missing"):
        validate_hypothesis(bad)


def test_value_inputs_severity_class_outside_enum_rejected() -> None:
    bad = _good_hypothesis()
    bad["value_inputs"]["severity_class"] = "extreme"
    with pytest.raises(DecisionPackHypothesisError, match="severity_class"):
        validate_hypothesis(bad)


def test_value_inputs_sensitivity_must_be_bool() -> None:
    bad = _good_hypothesis()
    bad["value_inputs"]["vulnerable_cohort_sensitivity"] = "yes"  # str, not bool
    with pytest.raises(DecisionPackHypothesisError, match="vulnerable_cohort_sensitivity"):
        validate_hypothesis(bad)


def test_value_inputs_segment_must_be_non_empty_string() -> None:
    bad = _good_hypothesis()
    bad["value_inputs"]["population_segment_addressed"] = ""
    with pytest.raises(DecisionPackHypothesisError, match="population_segment_addressed"):
        validate_hypothesis(bad)


def test_risk_inputs_missing_key_rejected() -> None:
    bad = _good_hypothesis()
    del bad["risk_inputs"]["policy_areas"]
    with pytest.raises(DecisionPackHypothesisError, match="risk_inputs missing"):
        validate_hypothesis(bad)


def test_risk_inputs_unknown_regulatory_code_rejected() -> None:
    """Cross-validation: a taxonomy code not in regulatory_taxonomy.yaml
    is rejected with a message pointing at the taxonomy file."""
    bad = _good_hypothesis()
    bad["risk_inputs"]["regulatory_taxonomies"] = ["made_up_taxonomy_v999"]
    with pytest.raises(
        DecisionPackHypothesisError,
        match="not a registered taxonomy code",
    ):
        validate_hypothesis(bad)


def test_risk_inputs_chronicle_precedent_bad_format_rejected() -> None:
    bad = _good_hypothesis()
    bad["risk_inputs"]["chronicle_precedents"] = ["CHR-001"]  # MIL-style, not Pulse
    with pytest.raises(DecisionPackHypothesisError, match="CHR-friction-NNN"):
        validate_hypothesis(bad)


def test_risk_inputs_chronicle_precedents_optional() -> None:
    """Omitting chronicle_precedents must be allowed (optional field)."""
    good = _good_hypothesis()
    del good["risk_inputs"]["chronicle_precedents"]
    validate_hypothesis(good)


def test_risk_inputs_policy_areas_not_cross_validated() -> None:
    """policy_areas accepts any string — bank_policy is per-deployment, so
    pack-registration time cannot cross-check against the registered
    policy_areas in bank_policy.yaml."""
    good = _good_hypothesis()
    good["risk_inputs"]["policy_areas"] = ["any_string_at_all"]
    validate_hypothesis(good)


# --- Gate 2: computed-slot immutability --------------------------------------


def test_declared_value_output_rejected_with_methodology_pointer() -> None:
    bad = _good_hypothesis()
    bad["value_output"] = "COMMERCIAL-OPPORTUNITY"
    with pytest.raises(
        DecisionPackHypothesisError,
        match="Value methodology",
    ):
        validate_hypothesis(bad)


def test_declared_risk_output_rejected_with_methodology_pointer() -> None:
    bad = _good_hypothesis()
    bad["risk_output"] = "REGULATORY-FLAG"
    with pytest.raises(
        DecisionPackHypothesisError,
        match="Risk methodology",
    ):
        validate_hypothesis(bad)


def test_computed_slot_check_runs_before_completeness_check() -> None:
    """Even a structurally-incomplete pack that ALSO declares a computed
    slot must surface the computed-slot violation — clearer signal for
    the author."""
    bad = {
        "value_output": "COMMERCIAL-OPPORTUNITY",
        "risk_output": "REGULATORY-FLAG",
        # missing actors / value_inputs / risk_inputs
    }
    with pytest.raises(DecisionPackHypothesisError, match="value_output"):
        validate_hypothesis(bad)


# --- Non-mutation invariant --------------------------------------------------


def test_validate_does_not_mutate_input() -> None:
    hyp = _good_hypothesis()
    snapshot = copy.deepcopy(hyp)
    validate_hypothesis(hyp)
    assert hyp == snapshot


# --- Acceptance: 12 existing packs all PASS post-PULSE-104 backfill ----------


def _existing_hypothesis_files() -> list[Path]:
    return sorted(_DECISION_PACKS_DIR.glob("*/hypothesis.yaml"))


def test_seed_batch_hypothesis_files_exist() -> None:
    """Sanity: the seed-batch packs are present so the next test has
    something to assert against."""
    files = _existing_hypothesis_files()
    assert len(files) >= 12, (
        f"expected ≥12 seed-batch hypothesis.yaml files, found {len(files)}"
    )


@pytest.mark.parametrize(
    "hyp_path", _existing_hypothesis_files(),
    ids=lambda p: p.parent.name,
)
def test_seed_batch_pack_passes_new_validator(hyp_path: Path) -> None:
    """PULSE-104 backfilled all 12 seed packs with product-meaningful
    actors / value_inputs / risk_inputs declarations — they all now
    PASS the canvas-completeness validator.

    This test inverts the PULSE-103-era negative check (which asserted
    all 12 FAIL pre-backfill). The inversion IS the acceptance signal:
    PULSE-103 + PULSE-104 together complete the canvas-completeness
    discipline across the seed batch."""
    hyp = load_hypothesis(hyp_path)
    # spot-check the canvas slots actually landed (not just that the
    # validator was lenient)
    assert "actors" in hyp and hyp["actors"]
    assert "value_inputs" in hyp
    assert "risk_inputs" in hyp


def test_seed_batch_severity_classes_distribute_across_enum() -> None:
    """PULSE-104 backfill should produce a mix of severity_class values
    across the 12 seed packs (not all high, not all low). Confirms the
    backfill was product-meaningful, not placeholder."""
    library = [load_hypothesis(p) for p in _existing_hypothesis_files()]
    severities = {h["value_inputs"]["severity_class"] for h in library}
    assert len(severities) >= 2, (
        f"all 12 packs share the same severity_class — likely placeholder backfill: {severities}"
    )


# --- Load API ----------------------------------------------------------------


def test_load_hypothesis_returns_parsed_dict(tmp_path) -> None:
    """A valid hypothesis.yaml loads and returns the parsed dict."""
    import yaml as _yaml

    hyp = _good_hypothesis()
    p = tmp_path / "hypothesis.yaml"
    p.write_text(_yaml.safe_dump(hyp, sort_keys=False), encoding="utf-8")
    loaded = load_hypothesis(p)
    assert loaded == hyp


def test_load_hypothesis_raises_on_malformed(tmp_path) -> None:
    """load_hypothesis() composes load + validate — malformed file raises."""
    p = tmp_path / "hypothesis.yaml"
    p.write_text("not_a_canvas_field: 1\n", encoding="utf-8")
    with pytest.raises(DecisionPackHypothesisError):
        load_hypothesis(p)
