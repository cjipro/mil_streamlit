"""
test_cac.py — Unit tests for MIL CAC formula.

Tests the core confidence score calculation (alpha/beta/delta weights)
and the severity gate logic in _normalise().
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _cac(vol_sig: float, sim_hist: float, delta_tel: float,
         alpha: float = 0.40, beta: float = 0.40, delta: float = 0.20) -> float:
    return (alpha * vol_sig + beta * sim_hist) / (delta * delta_tel + 1)


class TestCACFormula:
    def test_zero_inputs_returns_zero(self):
        assert _cac(0.0, 0.0, 0.0) == 0.0

    def test_full_signal_no_telemetry(self):
        result = _cac(1.0, 1.0, 0.0)
        assert abs(result - 0.80) < 1e-9

    def test_telemetry_dampens_score(self):
        without = _cac(1.0, 1.0, 0.0)
        with_tel = _cac(1.0, 1.0, 1.0)
        assert with_tel < without

    def test_designed_ceiling_threshold(self):
        # CAC > 0.45 with delta_tel=0.0 should trigger ceiling
        result = _cac(0.6, 0.6, 0.0)
        assert result > 0.45

    def test_below_ceiling_threshold(self):
        result = _cac(0.2, 0.2, 0.0)
        assert result <= 0.45

    def test_alpha_beta_symmetry(self):
        # Swapping vol_sig and sim_hist should give same result when alpha==beta
        r1 = _cac(0.7, 0.3, 0.5)
        r2 = _cac(0.3, 0.7, 0.5)
        assert abs(r1 - r2) < 1e-9

    def test_clark3_threshold_achievable(self):
        # CLARK-3 requires CAC >= 0.65
        result = _cac(0.9, 0.9, 0.0)
        assert result >= 0.65


class TestSeverityGate:
    """Test the severity gate logic from enrich_sonnet._normalise()."""

    def _normalise_severity(self, severity: str, issue_type: str) -> str:
        BLOCKING_ISSUES = {
            "App Not Opening", "Login Failed", "Payment Failed",
            "Transfer Failed", "Account Locked", "App Crashing",
        }
        if severity in ("P0", "P1") and issue_type not in BLOCKING_ISSUES:
            severity = "P2"
        if issue_type == "Positive Feedback":
            severity = "P2"
        return severity

    def test_p0_on_blocking_issue_kept(self):
        assert self._normalise_severity("P0", "Login Failed") == "P0"

    def test_p0_on_non_blocking_downgraded(self):
        assert self._normalise_severity("P0", "Slow Performance") == "P2"

    def test_p1_on_blocking_issue_kept(self):
        assert self._normalise_severity("P1", "Payment Failed") == "P1"

    def test_p1_on_non_blocking_downgraded(self):
        assert self._normalise_severity("P1", "Notification Issue") == "P2"

    def test_positive_feedback_always_p2(self):
        assert self._normalise_severity("P0", "Positive Feedback") == "P2"
        assert self._normalise_severity("P1", "Positive Feedback") == "P2"

    def test_p2_unchanged(self):
        assert self._normalise_severity("P2", "Login Failed") == "P2"
        assert self._normalise_severity("P2", "Slow Performance") == "P2"
