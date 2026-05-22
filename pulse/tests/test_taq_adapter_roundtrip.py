"""Round-trip test: TAQ source event → TAQAdapter.ingest() → canonical → validates."""

from __future__ import annotations

import re

from pulse.adapters.taq import TAQAdapter
from pulse.schema import validate


def _taq_source_event() -> dict:
    """Notional TAQ event shape per pulse/contracts/taq_contract.yaml.

    Wraps internal fields in a top-level `events` container, with
    synthetic_customer_id + synthetic_cohort_tags exposed at the envelope level
    (the crossing-contract shape TAQ will produce when it emits to Pulse —
    distinct from TAQ's internal events.yaml vocabulary).
    """
    return {
        "events": {
            "event_id": "taq-evt-00042",
            "session_id": "sess-uuid-abc",
            "synthetic_customer_id": "syn-cust-hash-001",
            "synthetic_cohort_tags": ["premier", "over_50"],
            "journey_id": "loans",
            "screen_id": "loans.apply.step3",
            "sequence_no": 7,
            "event_type": "dwell",
            "ts": "2026-05-17T14:29:58.000Z",
            "payload": {"duration_ms": 30000, "since_event": "error"},
        },
    }


def test_taq_event_round_trip_to_canonical() -> None:
    adapter = TAQAdapter()
    source = _taq_source_event()
    canonical = adapter.ingest(source, batch_hash="b" * 64)

    # Validates against canonical_schema.yaml.
    validate(canonical)

    # Field-level checks: every mapping resolved to the right value.
    assert canonical["identity"]["session_id"] == "sess-uuid-abc"
    assert canonical["identity"]["subject_id"] == "syn-cust-hash-001"
    assert canonical["identity"]["cohort_tags"] == ["premier", "over_50"]
    assert canonical["context"]["journey_id"] == "loans"
    assert canonical["context"]["journey_category"] == "choke_point"
    assert canonical["context"]["screen_id"] == "loans.apply.step3"
    assert canonical["context"]["sequence_no"] == 7
    assert canonical["event"]["event_type"] == "dwell"
    assert canonical["event"]["event_ts"] == "2026-05-17T14:29:58.000Z"
    assert canonical["event"]["payload"]["duration_ms"] == 30000


def test_taq_envelope_stamped() -> None:
    adapter = TAQAdapter()
    canonical = adapter.ingest(_taq_source_event(), batch_hash="c" * 64)
    env = canonical["envelope"]
    assert env["source"] == "taq"
    assert env["source_event_id"] == "taq-evt-00042"
    assert env["ingest_batch_hash"] == "c" * 64
    assert env["contract_version"] == "1.0.0"
    assert env["ingest_pipeline_version"] == "0.1.0"
    # ISO 8601 UTC, ms precision — same regex as the schema validator.
    assert re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", env["ingest_ts"]
    )
    # pulse_event_id is a UUID hex.
    assert re.match(r"^[0-9a-f]{32}$", env["pulse_event_id"])


def test_taq_journey_category_derived_for_each_friction_target() -> None:
    """The 4 v1 friction-target screens each land in the right journey_category."""
    adapter = TAQAdapter()
    cases = [
        ("loans", "loans.apply.step3", "choke_point"),
        ("international", "international.beneficiary.setup", "choke_point"),
        ("cards", "cards.credit.apply.eligibility", "context_loss"),
        ("investments", "investments.premier.portfolio.overview", "behavioural_noise"),
    ]
    for journey_id, screen_id, expected_category in cases:
        source = _taq_source_event()
        source["events"]["journey_id"] = journey_id
        source["events"]["screen_id"] = screen_id
        canonical = adapter.ingest(source, batch_hash="d" * 64)
        assert canonical["context"]["journey_category"] == expected_category, (
            f"{journey_id} -> expected {expected_category}, "
            f"got {canonical['context']['journey_category']}"
        )


def test_taq_unknown_journey_id_raises() -> None:
    adapter = TAQAdapter()
    source = _taq_source_event()
    source["events"]["journey_id"] = "not_a_journey"
    try:
        adapter.ingest(source, batch_hash="e" * 64)
    except ValueError as exc:
        assert "journey_taxonomy" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown journey_id")
