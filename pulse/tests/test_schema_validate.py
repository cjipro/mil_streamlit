"""Tests for pulse.schema.validate against canonical_schema.yaml."""

from __future__ import annotations

import copy

import pytest

from pulse.schema import SchemaValidationError, validate


def _good_event() -> dict:
    return {
        "envelope": {
            "pulse_event_id": "evt-001",
            "source": "taq",
            "source_event_id": "src-123",
            "ingest_ts": "2026-05-17T14:30:00.123Z",
            "ingest_pipeline_version": "0.1.0",
            "ingest_batch_hash": "a" * 64,
            "contract_version": "1.0.0",
        },
        "identity": {
            "session_id": "sess-abc",
            "subject_id": "subj-hash-xyz",
            "cohort_tags": ["premier", "over_50"],
        },
        "context": {
            "journey_id": "loans",
            "journey_category": "choke_point",
            "screen_id": "loans.apply.step3",
            "sequence_no": 42,
        },
        "event": {
            "event_type": "dwell",
            "event_ts": "2026-05-17T14:29:58.000Z",
            "payload": {"duration_ms": 30000, "since_event": "error"},
        },
    }


def test_good_event_passes() -> None:
    validate(_good_event())


def test_missing_top_level_section() -> None:
    bad = _good_event()
    del bad["context"]
    with pytest.raises(SchemaValidationError, match="missing top-level"):
        validate(bad)


def test_unexpected_top_level_section() -> None:
    bad = _good_event()
    bad["unexpected"] = {}
    with pytest.raises(SchemaValidationError, match="unexpected top-level"):
        validate(bad)


def test_missing_required_field() -> None:
    bad = _good_event()
    del bad["identity"]["session_id"]
    with pytest.raises(SchemaValidationError, match="identity.session_id.*required"):
        validate(bad)


def test_optional_field_can_be_omitted() -> None:
    good = _good_event()
    del good["identity"]["cohort_tags"]
    validate(good)


def test_string_type_rejects_int() -> None:
    bad = _good_event()
    bad["identity"]["session_id"] = 123
    with pytest.raises(SchemaValidationError, match="expected string"):
        validate(bad)


def test_integer_type_rejects_bool() -> None:
    bad = _good_event()
    bad["context"]["sequence_no"] = True  # bool is int subclass — must be rejected
    with pytest.raises(SchemaValidationError, match="expected integer"):
        validate(bad)


def test_integer_type_rejects_string() -> None:
    bad = _good_event()
    bad["context"]["sequence_no"] = "42"
    with pytest.raises(SchemaValidationError, match="expected integer"):
        validate(bad)


def test_enum_rejects_unknown_value() -> None:
    bad = _good_event()
    bad["event"]["event_type"] = "explosion"
    with pytest.raises(SchemaValidationError, match="not in allowed enum"):
        validate(bad)


def test_enum_rejects_unknown_source() -> None:
    bad = _good_event()
    bad["envelope"]["source"] = "third_party"
    with pytest.raises(SchemaValidationError, match="not in allowed enum"):
        validate(bad)


def test_enum_rejects_unknown_journey_category() -> None:
    bad = _good_event()
    bad["context"]["journey_category"] = "miscellaneous"
    with pytest.raises(SchemaValidationError, match="not in allowed enum"):
        validate(bad)


def test_timestamp_rejects_non_iso() -> None:
    bad = _good_event()
    bad["envelope"]["ingest_ts"] = "yesterday"
    with pytest.raises(SchemaValidationError, match="ISO 8601"):
        validate(bad)


def test_timestamp_accepts_offset_variant() -> None:
    good = _good_event()
    good["envelope"]["ingest_ts"] = "2026-05-17T14:30:00.123+00:00"
    validate(good)


def test_list_of_strings_rejects_mixed() -> None:
    bad = _good_event()
    bad["identity"]["cohort_tags"] = ["premier", 42]
    with pytest.raises(SchemaValidationError, match="expected list of strings"):
        validate(bad)


def test_object_type_rejects_string() -> None:
    bad = _good_event()
    bad["event"]["payload"] = "not a dict"
    with pytest.raises(SchemaValidationError, match="expected object"):
        validate(bad)


def test_unexpected_field_within_section() -> None:
    bad = _good_event()
    bad["identity"]["surprise"] = "value"
    with pytest.raises(SchemaValidationError, match="unexpected fields"):
        validate(bad)


def test_validate_does_not_mutate_input() -> None:
    good = _good_event()
    snapshot = copy.deepcopy(good)
    validate(good)
    assert good == snapshot
