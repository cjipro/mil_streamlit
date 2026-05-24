"""PULSE-137 — tests for the real TAQ taxonomy loader + committed artifacts.

Verifies the 24 / 107 / 697 cardinality, the orphan/coverage handling, and that no
op-code is silently dropped from the roll-ups.
"""
from pulse import taxonomy as tx


def test_counts_match_manifest():
    c = tx.manifest()["counts"]
    assert c["op_codes"] == 697
    assert c["journeys"] == 24
    assert c["customer_journeys"] == 107
    assert c["orphans"] == 97


def test_loader_cardinality_matches_manifest():
    c = tx.manifest()["counts"]
    assert len(tx.op_codes()) == c["op_codes"]
    assert len(tx.journeys()) == c["journeys"]
    assert len(tx.customer_journeys()) == c["customer_journeys"]
    assert len(tx.orphans()) == c["orphans"]


def test_op_code_ids_unique():
    ids = tx.op_codes()
    assert len(ids) == len(set(ids)) == 697


def test_known_op_code_mapping():
    # A001C is the canonical first op-screen in screens.yaml v2.
    row = tx.lookup("a001c")
    assert row is not None
    assert row["journey"] == "core_app_web"
    assert row["customer_journey"] == "Terms & Conditions"


def test_orphans_have_no_customer_journey():
    for oid in tx.orphans():
        assert tx.lookup(oid)["customer_journey"] == ""


def test_coverage_matches_manifest():
    assert tx.coverage() == tx.manifest()["counts"]["customer_journey_coverage_pct"]


def test_rollups_drop_nothing():
    cj_rollup = tx.rollup_by_customer_journey()
    j_rollup = tx.rollup_by_journey()
    # CustomerJourney rollup + orphan bucket == every op-code (nothing silently dropped).
    in_cj = sum(len(v) for v in cj_rollup.values())
    assert in_cj + len(tx.orphans()) == len(tx.op_codes()) == 697
    # Journey tier covers every op-code (all 697 carry a journey).
    assert sum(len(v) for v in j_rollup.values()) == 697
    assert len(cj_rollup) == 107
    assert len(j_rollup) == 24


def test_lookup_unknown_returns_none():
    assert tx.lookup("no-such-op-code") is None
