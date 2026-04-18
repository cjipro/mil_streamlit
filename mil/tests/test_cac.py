"""
test_cac.py — Unit tests for mil/inference/cac.py and severity gate logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.inference.cac import compute_cac, compute_vol_sig


class TestComputeCAC:
    def test_zero_inputs(self):
        assert compute_cac(0.0, 0.0) == 0.0

    def test_no_telemetry_denominator_is_one(self):
        # delta_tel=0 → denominator=1 → CAC = alpha*vol + beta*sim = 0.4+0.4 = 0.8
        assert compute_cac(1.0, 1.0, delta_tel=0.0) == 0.8

    def test_telemetry_lowers_score(self):
        without = compute_cac(0.8, 0.8, delta_tel=0.0)
        with_tel = compute_cac(0.8, 0.8, delta_tel=1.0)
        assert with_tel < without

    def test_clark3_threshold_achievable(self):
        assert compute_cac(0.9, 0.9) >= 0.65

    def test_alpha_beta_symmetry(self):
        # alpha == beta so swapping vol_sig/sim_hist gives same result
        assert compute_cac(0.7, 0.3) == compute_cac(0.3, 0.7)

    def test_result_rounded_to_4dp(self):
        result = compute_cac(0.333, 0.333)
        assert result == round(result, 4)

    def test_designed_ceiling_triggerable(self):
        # CAC > 0.45 with no telemetry — ceiling rule should fire downstream
        assert compute_cac(0.6, 0.6) > 0.45

    def test_below_ceiling_threshold(self):
        assert compute_cac(0.2, 0.2) <= 0.45


class TestComputeVolSig:
    def test_zero_total_records(self):
        assert compute_vol_sig([], 0) == 0.0

    def test_all_p0_cluster(self):
        cluster = [{"severity_class": "P0"}] * 5
        result = compute_vol_sig(cluster, 100)
        assert 0.0 < result <= 1.0

    def test_enrichment_failed_contributes_zero(self):
        cluster = [{"severity_class": "ENRICHMENT_FAILED"}] * 10
        assert compute_vol_sig(cluster, 100) == 0.0

    def test_p0_outweighs_p2_same_count(self):
        cluster_p0 = [{"severity_class": "P0"}] * 3
        cluster_p2 = [{"severity_class": "P2"}] * 3
        assert compute_vol_sig(cluster_p0, 50) > compute_vol_sig(cluster_p2, 50)

    def test_capped_at_one(self):
        cluster = [{"severity_class": "P0"}] * 1000
        assert compute_vol_sig(cluster, 10) == 1.0


class TestSeverityGate:
    """Severity gate logic from enrich_sonnet._normalise()."""

    def _gate(self, severity: str, issue_type: str) -> str:
        BLOCKING = {
            "App Not Opening", "Login Failed", "Payment Failed",
            "Transfer Failed", "Account Locked", "App Crashing",
        }
        if severity in ("P0", "P1") and issue_type not in BLOCKING:
            return "P2"
        if issue_type == "Positive Feedback":
            return "P2"
        return severity

    def test_p0_blocking_kept(self):
        assert self._gate("P0", "Login Failed") == "P0"

    def test_p0_non_blocking_downgraded(self):
        assert self._gate("P0", "Slow Performance") == "P2"

    def test_p1_blocking_kept(self):
        assert self._gate("P1", "Payment Failed") == "P1"

    def test_p1_non_blocking_downgraded(self):
        assert self._gate("P1", "Notification Issue") == "P2"

    def test_positive_feedback_always_p2(self):
        assert self._gate("P0", "Positive Feedback") == "P2"
        assert self._gate("P1", "Positive Feedback") == "P2"

    def test_p2_unchanged(self):
        assert self._gate("P2", "Login Failed") == "P2"
        assert self._gate("P2", "Slow Performance") == "P2"
