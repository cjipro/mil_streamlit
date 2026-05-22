"""Tests for the bank_policy.yaml validator (PULSE-102).

Key invariants:
- the shipped template carries `<TBD>` placeholders and MUST fail strict
  validation (proves the no-silent-fallback discipline)
- a fully-resolved config passes
- the shipped template contains no string that looks like a real bank name
  (compliance lint)
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

from pulse.contracts import BankPolicyError, load_bank_policy, validate_bank_policy

_SHIPPED_TEMPLATE = (
    Path(__file__).parent.parent / "contracts" / "bank_policy.yaml"
)


def _good_cfg() -> dict:
    return {
        "version": "0.1.0",
        "deployment_id": "deploy-7f3a",
        "escalation_thresholds": {
            "affected_customers_7d_window": 500,
            "vulnerable_cohort_overrep_floor": 1.25,
        },
        "policy_areas": [
            {
                "internal_name": "Policy 4.7 — Affordability Review",
                "regulatory_taxonomy": "fca_consumer_duty_2.0",
                "regulatory_section": "PRIN 12",
            }
        ],
        "vulnerable_cohort_extensions": [
            {
                "cohort_id": "recent_bereavement",
                "description": "Customers within 6 months of registered bereavement event",
                "rationale": "Bank-internal commitment to enhanced support per ESG policy",
            }
        ],
    }


def test_good_cfg_passes() -> None:
    validate_bank_policy(_good_cfg())


def test_shipped_template_yaml_parses() -> None:
    """The shipped template must be valid YAML."""
    with _SHIPPED_TEMPLATE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert isinstance(cfg, dict)
    assert cfg["version"] == "0.1.0"


def test_shipped_template_fails_strict_validation() -> None:
    """The shipped template is a placeholder — it MUST fail strict
    validation so a deployment lifting it verbatim cannot start the engine."""
    with pytest.raises(BankPolicyError, match="placeholder"):
        load_bank_policy(_SHIPPED_TEMPLATE)


def test_missing_top_level_field_rejected() -> None:
    bad = _good_cfg()
    del bad["escalation_thresholds"]
    with pytest.raises(BankPolicyError, match="missing required"):
        validate_bank_policy(bad)


def test_deployment_id_placeholder_rejected() -> None:
    bad = _good_cfg()
    bad["deployment_id"] = "<TBD — set on deployment>"
    with pytest.raises(BankPolicyError, match="deployment_id is an unresolved placeholder"):
        validate_bank_policy(bad)


def test_deployment_id_empty_rejected() -> None:
    bad = _good_cfg()
    bad["deployment_id"] = ""
    with pytest.raises(BankPolicyError, match="deployment_id"):
        validate_bank_policy(bad)


def test_affected_customers_placeholder_rejected() -> None:
    bad = _good_cfg()
    bad["escalation_thresholds"]["affected_customers_7d_window"] = "<TBD>"
    with pytest.raises(BankPolicyError, match="affected_customers_7d_window is an unresolved placeholder"):
        validate_bank_policy(bad)


def test_affected_customers_non_integer_rejected() -> None:
    bad = _good_cfg()
    bad["escalation_thresholds"]["affected_customers_7d_window"] = 1.5
    with pytest.raises(BankPolicyError, match="non-negative integer"):
        validate_bank_policy(bad)


def test_affected_customers_negative_rejected() -> None:
    bad = _good_cfg()
    bad["escalation_thresholds"]["affected_customers_7d_window"] = -1
    with pytest.raises(BankPolicyError, match="non-negative integer"):
        validate_bank_policy(bad)


def test_affected_customers_bool_rejected() -> None:
    """Python `bool` is a subclass of `int`; explicitly reject it."""
    bad = _good_cfg()
    bad["escalation_thresholds"]["affected_customers_7d_window"] = True
    with pytest.raises(BankPolicyError, match="non-negative integer"):
        validate_bank_policy(bad)


def test_overrep_floor_placeholder_rejected() -> None:
    bad = _good_cfg()
    bad["escalation_thresholds"]["vulnerable_cohort_overrep_floor"] = "<TBD>"
    with pytest.raises(BankPolicyError, match="overrep_floor is an unresolved placeholder"):
        validate_bank_policy(bad)


def test_overrep_floor_below_one_rejected() -> None:
    """A ratio below 1.0 means under-represented, not over-represented."""
    bad = _good_cfg()
    bad["escalation_thresholds"]["vulnerable_cohort_overrep_floor"] = 0.9
    with pytest.raises(BankPolicyError, match=">= 1.0"):
        validate_bank_policy(bad)


def test_overrep_floor_int_accepted() -> None:
    """An integer 1 is a valid ratio (no over-representation)."""
    good = _good_cfg()
    good["escalation_thresholds"]["vulnerable_cohort_overrep_floor"] = 1
    validate_bank_policy(good)


def test_missing_threshold_key_rejected() -> None:
    bad = _good_cfg()
    del bad["escalation_thresholds"]["vulnerable_cohort_overrep_floor"]
    with pytest.raises(BankPolicyError, match="escalation_thresholds missing"):
        validate_bank_policy(bad)


def test_empty_policy_areas_accepted() -> None:
    good = _good_cfg()
    good["policy_areas"] = []
    validate_bank_policy(good)


def test_policy_area_missing_field_rejected() -> None:
    bad = _good_cfg()
    del bad["policy_areas"][0]["regulatory_section"]
    with pytest.raises(BankPolicyError, match="regulatory_section"):
        validate_bank_policy(bad)


def test_policy_area_unknown_taxonomy_rejected() -> None:
    bad = _good_cfg()
    bad["policy_areas"][0]["regulatory_taxonomy"] = "made_up_regulator_2.0"
    with pytest.raises(BankPolicyError, match="regulatory_taxonomy must be one of"):
        validate_bank_policy(bad)


def test_policy_area_placeholder_value_rejected() -> None:
    bad = _good_cfg()
    bad["policy_areas"][0]["internal_name"] = "<TBD — set on deployment>"
    with pytest.raises(BankPolicyError, match="internal_name is an unresolved placeholder"):
        validate_bank_policy(bad)


def test_empty_vulnerable_cohort_extensions_accepted() -> None:
    good = _good_cfg()
    good["vulnerable_cohort_extensions"] = []
    validate_bank_policy(good)


def test_vulnerable_cohort_extension_missing_field_rejected() -> None:
    bad = _good_cfg()
    del bad["vulnerable_cohort_extensions"][0]["rationale"]
    with pytest.raises(BankPolicyError, match="rationale"):
        validate_bank_policy(bad)


def test_vulnerable_cohort_extensions_duplicate_id_rejected() -> None:
    bad = _good_cfg()
    bad["vulnerable_cohort_extensions"].append(
        copy.deepcopy(bad["vulnerable_cohort_extensions"][0])
    )
    with pytest.raises(BankPolicyError, match="duplicate cohort_id"):
        validate_bank_policy(bad)


def test_validate_does_not_mutate_input() -> None:
    cfg = _good_cfg()
    snapshot = copy.deepcopy(cfg)
    validate_bank_policy(cfg)
    assert cfg == snapshot


# --- arpu_per_journey (v0.2 commercial-estimate framework — PULSE-107) ------


def test_arpu_block_omitted_is_valid() -> None:
    """Older deployments without arpu_per_journey stay valid — sized lift
    just returns None on every pack."""
    cfg = _good_cfg()
    assert "arpu_per_journey" not in cfg
    validate_bank_policy(cfg)


def test_arpu_empty_dict_is_valid() -> None:
    cfg = _good_cfg()
    cfg["arpu_per_journey"] = {}
    validate_bank_policy(cfg)


def test_arpu_with_journeys_is_valid() -> None:
    cfg = _good_cfg()
    cfg["arpu_per_journey"] = {
        "behavioural_noise": 8.50,
        "context_loss": 22.0,
        "choke_point": 0,  # zero is allowed
    }
    validate_bank_policy(cfg)


def test_arpu_not_mapping_rejected() -> None:
    bad = _good_cfg()
    bad["arpu_per_journey"] = [{"behavioural_noise": 10.0}]
    with pytest.raises(BankPolicyError, match="arpu_per_journey must be a mapping"):
        validate_bank_policy(bad)


def test_arpu_negative_value_rejected() -> None:
    bad = _good_cfg()
    bad["arpu_per_journey"] = {"behavioural_noise": -5.0}
    with pytest.raises(BankPolicyError, match="non-negative"):
        validate_bank_policy(bad)


def test_arpu_string_value_rejected() -> None:
    bad = _good_cfg()
    bad["arpu_per_journey"] = {"behavioural_noise": "10"}
    with pytest.raises(BankPolicyError, match="non-negative number"):
        validate_bank_policy(bad)


def test_arpu_bool_value_rejected() -> None:
    """Python bool is an int subclass; reject explicitly so True doesn't
    silently mean 1.0 ARPU."""
    bad = _good_cfg()
    bad["arpu_per_journey"] = {"behavioural_noise": True}
    with pytest.raises(BankPolicyError, match="non-negative number"):
        validate_bank_policy(bad)


def test_arpu_placeholder_rejected() -> None:
    bad = _good_cfg()
    bad["arpu_per_journey"] = {"behavioural_noise": "<TBD>"}
    with pytest.raises(BankPolicyError, match="unresolved placeholder"):
        validate_bank_policy(bad)


def test_arpu_empty_journey_key_rejected() -> None:
    bad = _good_cfg()
    bad["arpu_per_journey"] = {"": 10.0}
    with pytest.raises(BankPolicyError, match="non-empty strings"):
        validate_bank_policy(bad)


# --- Compliance lint: no real-bank name in the shipped template -------------


# Common UK high-street bank tokens. Curated, not exhaustive. The point is
# to catch accidental leaks at PR-review time, not to be a perfect filter.
_BANK_NAME_TOKENS = [
    "barclays",
    "hsbc",
    "natwest",
    "lloyds",
    "santander",
    "halifax",
    "monzo",
    "starling",
    "nationwide",
    "rbs",
]


def test_shipped_template_contains_no_real_bank_name() -> None:
    with _SHIPPED_TEMPLATE.open("r", encoding="utf-8") as f:
        text = f.read().lower()
    for token in _BANK_NAME_TOKENS:
        assert not re.search(rf"\b{re.escape(token)}\b", text), (
            f"shipped bank_policy.yaml contains banned bank-name token {token!r} — "
            "use opaque placeholder tokens instead (mirrors real_bank_contract.yaml "
            "discipline)"
        )
