"""Tests for the Pulse Risk methodology v0 (PULSE-99).

Key invariants:
- tier-words enum is a closed set (no accidental new tier-word slips in)
- score_risk() is pure: same inputs → identical RiskScore (incl. hash)
- methodology_version is stamped in every output
- adjustments are monotonic (only push tier up, never down)
- Chronicle library is a soft dep: absent library degrades to base-tier
  + non-chronicle adjustments without raising
- Risk methodology consumes ONLY verified Chronicle entries (pending-review
  entries do not influence tier)
- Risk methodology + bank_policy + Chronicle integrate end-to-end against
  the shipped TSB CHR-friction-001 case
"""

from __future__ import annotations

import copy

import pytest

from pulse.contracts import validate_bank_policy
from pulse.risk import (
    FrictionShape,
    ImpactMetrics,
    RiskScore,
    load_rubric,
    load_taxonomy,
    score_risk,
)
from pulse.risk.chronicle import load_chronicle_library
from pulse.risk.score import _RUBRIC_PATH  # used by version-pin test
from pathlib import Path


_ENTRIES_DIR = Path(__file__).parent.parent / "risk" / "chronicle" / "entries"


def _good_bank_policy() -> dict:
    cfg = {
        "version": "0.1.0",
        "deployment_id": "deploy-test-001",
        "escalation_thresholds": {
            "affected_customers_7d_window": 500,
            "vulnerable_cohort_overrep_floor": 1.25,
        },
        "policy_areas": [],
        "vulnerable_cohort_extensions": [],
    }
    validate_bank_policy(cfg)  # sanity: tests must use a valid config
    return cfg


def _nominal_shape() -> FrictionShape:
    return FrictionShape(
        signature_id="lazy_scroll",
        journey_category="behavioural_noise",
        screen_class="marketing_page",
        severity="P2",
    )


def _quiet_impact() -> ImpactMetrics:
    return ImpactMetrics(affected_customers_7d=15, vulnerable_cohort_overrep_ratio=1.0)


# --- tier-words closure ------------------------------------------------------


def test_tier_words_is_closed_enum_of_four() -> None:
    """The rubric ships exactly four tier-words. Adding/removing one is a
    methodology-version change — this test guards the enum at the rubric
    file level so a stray edit doesn't slip through."""
    rubric = load_rubric()
    assert rubric["tier_words"] == [
        "NOMINAL",
        "WATCH",
        "ESCALATE",
        "REGULATORY-FLAG",
    ]


def test_max_tier_matches_tier_words_length() -> None:
    rubric = load_rubric()
    assert rubric["max_tier"] == len(rubric["tier_words"]) - 1


def test_every_returned_tier_is_in_the_enum() -> None:
    """Sweep every reachable combination — base + each adjustment subset —
    and assert the returned tier is always in the closed enum."""
    rubric = load_rubric()
    valid_words = set(rubric["tier_words"])
    for severity in ("P0", "P1", "P2"):
        shape = FrictionShape(
            signature_id="any",
            journey_category="behavioural_noise",
            screen_class="any",
            severity=severity,
        )
        for affected in (0, 9999):
            for overrep in (1.0, 99.0):
                impact = ImpactMetrics(
                    affected_customers_7d=affected,
                    vulnerable_cohort_overrep_ratio=overrep,
                )
                score = score_risk(
                    shape=shape, impact=impact, bank_policy=_good_bank_policy()
                )
                assert score.tier in valid_words


# --- base tier from severity -------------------------------------------------


@pytest.mark.parametrize(
    "severity,expected_tier",
    [
        ("P0", "ESCALATE"),
        ("P1", "WATCH"),
        ("P2", "NOMINAL"),
    ],
)
def test_base_tier_from_severity_alone(severity: str, expected_tier: str) -> None:
    """No adjustments fire → tier is the base tier for the severity."""
    shape = FrictionShape(
        signature_id="any",
        journey_category="behavioural_noise",
        screen_class="never_matches_any_taxonomy",
        severity=severity,
    )
    impact = ImpactMetrics(
        affected_customers_7d=0, vulnerable_cohort_overrep_ratio=1.0
    )
    score = score_risk(shape=shape, impact=impact, bank_policy=_good_bank_policy())
    assert score.tier == expected_tier
    assert score.adjustments_applied == ()


def test_unknown_severity_raises() -> None:
    shape = FrictionShape(
        signature_id="any",
        journey_category="behavioural_noise",
        screen_class="any",
        severity="P9",
    )
    with pytest.raises(ValueError, match="severity"):
        score_risk(shape=shape, impact=_quiet_impact(), bank_policy=_good_bank_policy())


# --- individual adjustments fire correctly -----------------------------------


def test_regulatory_match_escalates_one_tier() -> None:
    """credit_application + context_loss hits FCA Consumer Duty Outcome 3."""
    shape = FrictionShape(
        signature_id="unclear_validation_message",
        journey_category="context_loss",
        screen_class="credit_application",
        severity="P1",
    )
    impact = ImpactMetrics(affected_customers_7d=10, vulnerable_cohort_overrep_ratio=1.0)
    score = score_risk(shape=shape, impact=impact, bank_policy=_good_bank_policy())
    assert "regulatory_match" in score.adjustments_applied
    assert score.tier == "ESCALATE"
    assert "fca_consumer_duty.outcome_3_consumer_understanding" in score.regulatory_matches


def test_affected_customers_threshold_fires() -> None:
    shape = FrictionShape(
        signature_id="any",
        journey_category="behavioural_noise",
        screen_class="never_matches",
        severity="P2",
    )
    impact = ImpactMetrics(affected_customers_7d=500, vulnerable_cohort_overrep_ratio=1.0)
    score = score_risk(shape=shape, impact=impact, bank_policy=_good_bank_policy())
    assert "affected_customers_threshold" in score.adjustments_applied
    assert score.tier == "WATCH"  # P2 base (0) + 1 = WATCH (1)


def test_affected_customers_at_exact_threshold_fires() -> None:
    """Equality with the threshold is inclusive — defensible default."""
    shape = FrictionShape(
        signature_id="any",
        journey_category="behavioural_noise",
        screen_class="never_matches",
        severity="P2",
    )
    impact = ImpactMetrics(affected_customers_7d=500, vulnerable_cohort_overrep_ratio=1.0)
    assert score_risk(
        shape=shape, impact=impact, bank_policy=_good_bank_policy()
    ).numeric_tier == 1


def test_vulnerable_cohort_overrep_fires() -> None:
    shape = FrictionShape(
        signature_id="any",
        journey_category="behavioural_noise",
        screen_class="never_matches",
        severity="P2",
    )
    impact = ImpactMetrics(affected_customers_7d=0, vulnerable_cohort_overrep_ratio=1.5)
    score = score_risk(shape=shape, impact=impact, bank_policy=_good_bank_policy())
    assert "vulnerable_cohort_overrep" in score.adjustments_applied


def test_chronicle_precedent_excluded_when_only_pending_entries() -> None:
    """All shipped Chronicle entries are pending_human_review. They MUST
    NOT influence Risk tier — matcher fails closed."""
    library = load_chronicle_library(_ENTRIES_DIR)
    # The TSB shape — would match CHR-friction-001 if it were verified.
    shape = FrictionShape(
        signature_id="account_access_locked_out",
        journey_category="choke_point",
        screen_class="account_login",
        severity="P0",
    )
    impact = ImpactMetrics(affected_customers_7d=0, vulnerable_cohort_overrep_ratio=1.0)
    score = score_risk(
        shape=shape,
        impact=impact,
        bank_policy=_good_bank_policy(),
        chronicle_library=library,
    )
    assert "chronicle_precedent_match" not in score.adjustments_applied
    assert score.chronicle_matches == ()


def test_chronicle_precedent_fires_for_verified_entry() -> None:
    """Flip the CHR-friction-001 entry to verified (in-memory only) and
    confirm the adjustment fires."""
    library = load_chronicle_library(_ENTRIES_DIR)
    verified_lib = copy.deepcopy(library)
    for entry in verified_lib:
        if entry["chronicle_id"] == "CHR-friction-001":
            entry["verification_status"] = "verified"
    shape = FrictionShape(
        signature_id="account_access_locked_out",
        journey_category="choke_point",
        screen_class="account_login",
        severity="P0",
    )
    impact = ImpactMetrics(affected_customers_7d=0, vulnerable_cohort_overrep_ratio=1.0)
    score = score_risk(
        shape=shape,
        impact=impact,
        bank_policy=_good_bank_policy(),
        chronicle_library=verified_lib,
    )
    assert "chronicle_precedent_match" in score.adjustments_applied
    assert "CHR-friction-001" in score.chronicle_matches


# --- monotonicity + clamping -------------------------------------------------


def test_p0_with_all_adjustments_clamps_at_top_tier() -> None:
    """The load-bearing REGULATORY-FLAG case: P0 + every adjustment fires."""
    library = load_chronicle_library(_ENTRIES_DIR)
    verified = copy.deepcopy(library)
    for entry in verified:
        if entry["chronicle_id"] == "CHR-friction-001":
            entry["verification_status"] = "verified"
    shape = FrictionShape(
        signature_id="account_access_locked_out",
        journey_category="choke_point",
        screen_class="account_login",
        severity="P0",
    )
    impact = ImpactMetrics(
        affected_customers_7d=12500, vulnerable_cohort_overrep_ratio=1.45
    )
    score = score_risk(
        shape=shape,
        impact=impact,
        bank_policy=_good_bank_policy(),
        chronicle_library=verified,
    )
    # P0 base (2) + 4 adjustments = 6, clamped to max_tier (3).
    assert score.tier == "REGULATORY-FLAG"
    assert score.numeric_tier == 3
    assert set(score.adjustments_applied) == {
        "regulatory_match",
        "affected_customers_threshold",
        "vulnerable_cohort_overrep",
        "chronicle_precedent_match",
    }


def test_adjustments_are_monotonic() -> None:
    """Adding an adjustment can only push the tier up, never down."""
    shape = FrictionShape(
        signature_id="unclear_validation_message",
        journey_category="context_loss",
        screen_class="credit_application",
        severity="P1",
    )
    weak = ImpactMetrics(affected_customers_7d=0, vulnerable_cohort_overrep_ratio=1.0)
    strong = ImpactMetrics(affected_customers_7d=99999, vulnerable_cohort_overrep_ratio=99.0)
    weak_score = score_risk(shape=shape, impact=weak, bank_policy=_good_bank_policy())
    strong_score = score_risk(shape=shape, impact=strong, bank_policy=_good_bank_policy())
    assert strong_score.numeric_tier >= weak_score.numeric_tier


# --- soft Chronicle dep ------------------------------------------------------


def test_chronicle_library_is_optional_soft_dep() -> None:
    """The methodology must work with chronicle_library=None — Chronicle
    is documented as a soft dependency per the ticket."""
    shape = FrictionShape(
        signature_id="account_access_locked_out",
        journey_category="choke_point",
        screen_class="account_login",
        severity="P0",
    )
    impact = ImpactMetrics(affected_customers_7d=600, vulnerable_cohort_overrep_ratio=1.5)
    score = score_risk(
        shape=shape, impact=impact, bank_policy=_good_bank_policy(), chronicle_library=None
    )
    # All three non-chronicle adjustments fire — tier clamps to REGULATORY-FLAG.
    assert score.tier == "REGULATORY-FLAG"
    assert "chronicle_precedent_match" not in score.adjustments_applied
    assert score.chronicle_matches == ()


def test_chronicle_library_empty_list_is_allowed() -> None:
    """An empty library is structurally distinct from None — both must work."""
    shape = _nominal_shape()
    score = score_risk(
        shape=shape,
        impact=_quiet_impact(),
        bank_policy=_good_bank_policy(),
        chronicle_library=[],
    )
    assert score.tier == "NOMINAL"


# --- determinism + audit footprint -------------------------------------------


def test_same_inputs_produce_identical_risk_score() -> None:
    """Pure-function invariant. Same inputs → identical RiskScore in every
    field, including inputs_hash."""
    shape = FrictionShape(
        signature_id="unclear_validation_message",
        journey_category="context_loss",
        screen_class="credit_application",
        severity="P1",
    )
    impact = ImpactMetrics(affected_customers_7d=600, vulnerable_cohort_overrep_ratio=1.3)
    policy = _good_bank_policy()
    a = score_risk(shape=shape, impact=impact, bank_policy=policy)
    b = score_risk(shape=shape, impact=impact, bank_policy=policy)
    assert a == b
    assert a.inputs_hash == b.inputs_hash


def test_changing_severity_changes_inputs_hash() -> None:
    shape_p2 = FrictionShape("any", "behavioural_noise", "x", "P2")
    shape_p0 = FrictionShape("any", "behavioural_noise", "x", "P0")
    a = score_risk(shape=shape_p2, impact=_quiet_impact(), bank_policy=_good_bank_policy())
    b = score_risk(shape=shape_p0, impact=_quiet_impact(), bank_policy=_good_bank_policy())
    assert a.inputs_hash != b.inputs_hash


def test_changing_deployment_id_changes_inputs_hash() -> None:
    """Different deployments running the same shape produce different
    audit-trail hashes — keeps deployment provenance in the lineage."""
    policy_a = _good_bank_policy()
    policy_b = _good_bank_policy()
    policy_b["deployment_id"] = "deploy-test-002"
    a = score_risk(shape=_nominal_shape(), impact=_quiet_impact(), bank_policy=policy_a)
    b = score_risk(shape=_nominal_shape(), impact=_quiet_impact(), bank_policy=policy_b)
    assert a.inputs_hash != b.inputs_hash


def test_cosmetic_bank_policy_edit_does_not_change_hash() -> None:
    """Editing policy_areas (informational) should NOT bust the audit
    hash — the score only depends on escalation_thresholds + deployment_id."""
    policy_a = _good_bank_policy()
    policy_b = _good_bank_policy()
    policy_b["policy_areas"] = [
        {
            "internal_name": "Cosmetic",
            "regulatory_taxonomy": "fca_consumer_duty_2.0",
            "regulatory_section": "PRIN 12",
        }
    ]
    a = score_risk(shape=_nominal_shape(), impact=_quiet_impact(), bank_policy=policy_a)
    b = score_risk(shape=_nominal_shape(), impact=_quiet_impact(), bank_policy=policy_b)
    assert a.inputs_hash == b.inputs_hash


def test_methodology_version_pinned_in_output() -> None:
    score = score_risk(
        shape=_nominal_shape(), impact=_quiet_impact(), bank_policy=_good_bank_policy()
    )
    assert score.methodology_version == str(load_rubric()["methodology_version"])
    assert score.methodology_version == "0.1.0"


def test_riskscore_as_dict_round_trip() -> None:
    score = score_risk(
        shape=_nominal_shape(), impact=_quiet_impact(), bank_policy=_good_bank_policy()
    )
    d = score.as_dict()
    assert d["tier"] == score.tier
    assert d["methodology_version"] == score.methodology_version
    assert d["inputs_hash"] == score.inputs_hash


# --- regulatory taxonomy structural invariants -------------------------------


def test_taxonomy_loads_and_has_entries() -> None:
    tax = load_taxonomy()
    assert tax["version"] == "0.1.0"
    assert len(tax["taxonomies"]) >= 5


def test_every_taxonomy_entry_has_public_source() -> None:
    """Mirrors the Chronicle library discipline: no entry without a
    public-source citation."""
    tax = load_taxonomy()
    for entry in tax["taxonomies"]:
        assert "public_source" in entry
        assert entry["public_source"]["title"]
        assert entry["public_source"]["date"]


def test_taxonomy_codes_are_unique() -> None:
    tax = load_taxonomy()
    codes = [e["taxonomy_code"] for e in tax["taxonomies"]]
    assert len(codes) == len(set(codes))
