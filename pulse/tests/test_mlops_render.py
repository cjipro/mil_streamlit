"""Tests for the MLOps Console pure classifier functions (HOL-49).

Beck PR-panel rationale: classifier composition chain runs
  classify_drift_severity(delta) → severity string → CSS class
    → JS filter selector → THRESHOLD_RULES tooltip lookup

If any link in that chain shifts (e.g. NOMINAL vs NEUTRAL token mismatch),
the entire signal breaks silently — HTML still renders, but the filter
won't match, the tooltip lookup returns None, etc.

These tests pin the contract.
"""

from __future__ import annotations

import pytest

from holter.preview.render_mlops import (
    THRESHOLD_RULES,
    attestation_severity,
    classify_drift_severity,
    classify_fairness_severity,
    classify_lineage_severity,
    classify_synthesis_severity,
)


class TestClassifyDriftSeverity:
    """|delta| boundaries: <2 NOMINAL · 2-5 WATCH · 5-10 ESCALATE · >10 ACUTE."""

    @pytest.mark.parametrize("delta, expected", [
        (0,    "NOMINAL"),
        (1,    "NOMINAL"),
        (-1,   "NOMINAL"),
        (2,    "WATCH"),
        (-3,   "WATCH"),
        (5,    "WATCH"),       # 5 is boundary — inclusive in WATCH
        (-5,   "WATCH"),
        (6,    "ESCALATE"),
        (-7,   "ESCALATE"),
        (10,   "ESCALATE"),    # 10 is boundary — inclusive in ESCALATE
        (-10,  "ESCALATE"),
        (11,   "ACUTE"),
        (-13,  "ACUTE"),
        (50,   "ACUTE"),
    ])
    def test_boundary(self, delta: int, expected: str) -> None:
        assert classify_drift_severity(delta) == expected


class TestClassifyFairnessSeverity:
    """n_deviations: 0 NOMINAL · 1 WATCH · 2-3 ESCALATE · 4+ ACUTE."""

    @pytest.mark.parametrize("n, expected", [
        (0, "NOMINAL"),
        (1, "WATCH"),
        (2, "ESCALATE"),
        (3, "ESCALATE"),
        (4, "ACUTE"),
        (12, "ACUTE"),
    ])
    def test_boundary(self, n: int, expected: str) -> None:
        assert classify_fairness_severity(n) == expected


class TestClassifyLineageSeverity:
    """n_broken: 0 NOMINAL · 1 ESCALATE · 2+ ACUTE (no WATCH band)."""

    @pytest.mark.parametrize("n, expected", [
        (0, "NOMINAL"),
        (1, "ESCALATE"),
        (2, "ACUTE"),
        (5, "ACUTE"),
    ])
    def test_boundary(self, n: int, expected: str) -> None:
        assert classify_lineage_severity(n) == expected


class TestClassifySynthesisSeverity:
    """n_llm in prod: 0 NOMINAL · 1 ESCALATE · 2+ ACUTE."""

    @pytest.mark.parametrize("n, expected", [
        (0, "NOMINAL"),
        (1, "ESCALATE"),
        (2, "ACUTE"),
        (7, "ACUTE"),
    ])
    def test_boundary(self, n: int, expected: str) -> None:
        assert classify_synthesis_severity(n) == expected


class TestAttestationSeverity:
    """HOL-45 row-level severity for the SYNTHESIS filter strip.
    PENDING covers both self_declared (LLM_AUGMENTED) and
    attestation_pending (newly-onboarded DETERMINISTIC)."""

    @pytest.mark.parametrize("att, expected", [
        ("self_declared",          "PENDING"),
        ("attestation_pending",    "PENDING"),
        ("certified",              "NOMINAL"),
        ("independently_assessed", "NOMINAL"),
        # Unknown values fall through to NOMINAL (graceful default)
        ("garbage",                "NOMINAL"),
        ("",                       "NOMINAL"),
    ])
    def test_attestation_to_severity(self, att: str, expected: str) -> None:
        assert attestation_severity(att) == expected


class TestThresholdRulesCompleteness:
    """Every severity / status / attestation token the renderer surfaces
    must have a corresponding plain-language rule in THRESHOLD_RULES, or
    Gigerenzer's threshold tooltip silently shows nothing."""

    DRIFT_KEYS = ["DRIFT_NOMINAL", "DRIFT_WATCH", "DRIFT_ESCALATE", "DRIFT_ACUTE"]
    LINEAGE_KEYS = ["LINEAGE_NOMINAL", "LINEAGE_ESCALATE", "LINEAGE_ACUTE"]
    SYNTHESIS_KEYS = ["SYNTHESIS_NOMINAL", "SYNTHESIS_ESCALATE", "SYNTHESIS_ACUTE"]
    STATUS_KEYS = ["VERIFIED", "BROKEN", "STABLE"]
    ATTESTATION_KEYS = [
        "self_declared", "attestation_pending",
        "independently_assessed", "certified",
    ]
    METRIC_KEYS = ["demographic_parity", "equalised_odds", "calibration_by_cohort"]

    @pytest.mark.parametrize("key", DRIFT_KEYS + LINEAGE_KEYS + SYNTHESIS_KEYS
                             + STATUS_KEYS + ATTESTATION_KEYS + METRIC_KEYS)
    def test_key_present(self, key: str) -> None:
        assert key in THRESHOLD_RULES, f"missing rule for token: {key}"
        assert isinstance(THRESHOLD_RULES[key], str)
        assert len(THRESHOLD_RULES[key]) > 10, (
            f"rule for {key!r} is too short to be useful: "
            f"{THRESHOLD_RULES[key]!r}"
        )

    def test_no_unused_severity_outputs(self) -> None:
        """Every value classify_drift_severity / etc. can return is keyed
        in THRESHOLD_RULES with the appropriate domain prefix."""
        drift_outputs = {classify_drift_severity(d) for d in range(-20, 20)}
        for sev in drift_outputs:
            assert f"DRIFT_{sev}" in THRESHOLD_RULES, (
                f"drift severity {sev!r} can be produced but has no rule"
            )
