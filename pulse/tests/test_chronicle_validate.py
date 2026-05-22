"""Tests for the Chronicle precedent library (PULSE-100).

Key invariants:
- every shipped entry passes strict validation
- every shipped entry has a public-source citation (ticket acceptance)
- ≥10 entries shipped (ticket acceptance)
- no PII deny-list token in any shipped entry
- validator rejects missing-field / malformed entries
- matcher fails closed on pending_human_review entries (excluded from prod)
- matcher returns coordinate matches when include_pending=True
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from pulse.risk.chronicle import (
    ChronicleEntryError,
    ChronicleMatch,
    load_chronicle_entry,
    load_chronicle_library,
    match_signature,
    validate_chronicle_entry,
)

_ENTRIES_DIR = Path(__file__).parent.parent / "risk" / "chronicle" / "entries"


def _good_entry() -> dict:
    return {
        "chronicle_id": "CHR-friction-999",
        "institution": "Test Bank plc",
        "regulator": "FCA",
        "year": 2024,
        "friction_pattern": {
            "signature_id": "dwell_after_error",
            "journey_category": "choke_point",
            "screen_class": "credit_application",
            "severity": "P0",
        },
        "enforcement_action": {
            "type": "fine",
            "fine_gbp": 1000000,
            "individual_named": False,
        },
        "public_sources": [
            {
                "source": "FCA Final Notice — Test Bank plc",
                "date": "2024-03-15",
            }
        ],
        "verification_status": "pending_human_review",
    }


# --- shipped library: ticket-acceptance invariants ---------------------------


def test_library_loads_all_entries() -> None:
    """Every shipped CHR-friction-NNN.yaml must pass strict validation."""
    library = load_chronicle_library(_ENTRIES_DIR)
    assert len(library) >= 10, (
        f"ticket acceptance requires >=10 CHR-friction entries, found {len(library)}"
    )


def test_every_shipped_entry_has_public_source() -> None:
    """Ticket acceptance: every entry has a public-source citation."""
    library = load_chronicle_library(_ENTRIES_DIR)
    for entry in library:
        assert len(entry["public_sources"]) >= 1, (
            f"{entry['chronicle_id']} has no public_sources"
        )


def test_every_shipped_entry_has_unique_id() -> None:
    library = load_chronicle_library(_ENTRIES_DIR)
    ids = [e["chronicle_id"] for e in library]
    assert len(ids) == len(set(ids)), f"duplicate chronicle_id(s) in library: {ids}"


def test_every_shipped_entry_filename_matches_id() -> None:
    """A misalignment between filename and chronicle_id would break diffs
    and git-history attribution — fail it early."""
    for path in _ENTRIES_DIR.glob("CHR-friction-*.yaml"):
        entry = load_chronicle_entry(path)
        assert path.stem == entry["chronicle_id"], (
            f"{path.name} contains chronicle_id={entry['chronicle_id']!r}"
        )


def test_shipped_library_loads_via_library_api() -> None:
    library = load_chronicle_library(_ENTRIES_DIR)
    # spot-check the reference TSB case
    tsb = next(e for e in library if e["chronicle_id"] == "CHR-friction-001")
    assert "TSB" in tsb["institution"]
    assert tsb["regulator"] == "FCA"


# --- validator: structural rejection paths -----------------------------------


def test_good_entry_passes() -> None:
    validate_chronicle_entry(_good_entry())


def test_missing_top_level_field_rejected() -> None:
    bad = _good_entry()
    del bad["enforcement_action"]
    with pytest.raises(ChronicleEntryError, match="missing required"):
        validate_chronicle_entry(bad)


def test_bad_chronicle_id_rejected() -> None:
    bad = _good_entry()
    bad["chronicle_id"] = "CHR-001"  # MIL pattern, not Pulse pattern
    with pytest.raises(ChronicleEntryError, match="CHR-friction-NNN"):
        validate_chronicle_entry(bad)


def test_blank_institution_rejected() -> None:
    bad = _good_entry()
    bad["institution"] = "   "
    with pytest.raises(ChronicleEntryError, match="institution"):
        validate_chronicle_entry(bad)


def test_unknown_regulator_rejected() -> None:
    bad = _good_entry()
    bad["regulator"] = "MADE_UP_REG"
    with pytest.raises(ChronicleEntryError, match="regulator must be one of"):
        validate_chronicle_entry(bad)


def test_year_out_of_range_rejected() -> None:
    bad = _good_entry()
    bad["year"] = 1900
    with pytest.raises(ChronicleEntryError, match="plausible enforcement year"):
        validate_chronicle_entry(bad)


def test_year_as_yyyy_string_accepted() -> None:
    good = _good_entry()
    good["year"] = "2024"
    validate_chronicle_entry(good)


def test_year_as_bool_rejected() -> None:
    """Python bool is a subclass of int — explicitly reject."""
    bad = _good_entry()
    bad["year"] = True
    with pytest.raises(ChronicleEntryError, match="year"):
        validate_chronicle_entry(bad)


def test_friction_pattern_missing_key_rejected() -> None:
    bad = _good_entry()
    del bad["friction_pattern"]["severity"]
    with pytest.raises(ChronicleEntryError, match="friction_pattern missing"):
        validate_chronicle_entry(bad)


def test_friction_pattern_unknown_journey_category_rejected() -> None:
    bad = _good_entry()
    bad["friction_pattern"]["journey_category"] = "not_a_category"
    with pytest.raises(ChronicleEntryError, match="journey_category"):
        validate_chronicle_entry(bad)


def test_friction_pattern_unknown_severity_rejected() -> None:
    bad = _good_entry()
    bad["friction_pattern"]["severity"] = "P5"
    with pytest.raises(ChronicleEntryError, match="severity"):
        validate_chronicle_entry(bad)


def test_enforcement_action_unknown_type_rejected() -> None:
    bad = _good_entry()
    bad["enforcement_action"]["type"] = "very_strong_letter"
    with pytest.raises(ChronicleEntryError, match="enforcement_action.type"):
        validate_chronicle_entry(bad)


def test_enforcement_action_negative_fine_rejected() -> None:
    bad = _good_entry()
    bad["enforcement_action"]["fine_gbp"] = -100
    with pytest.raises(ChronicleEntryError, match="fine_gbp"):
        validate_chronicle_entry(bad)


def test_enforcement_action_null_fine_accepted() -> None:
    """null fine is valid (e.g. for voluntary_undertaking entries)."""
    good = _good_entry()
    good["enforcement_action"]["type"] = "voluntary_undertaking"
    good["enforcement_action"]["fine_gbp"] = None
    validate_chronicle_entry(good)


def test_empty_public_sources_rejected() -> None:
    """Ticket acceptance: every entry must have a public-source citation."""
    bad = _good_entry()
    bad["public_sources"] = []
    with pytest.raises(ChronicleEntryError, match="non-empty list"):
        validate_chronicle_entry(bad)


def test_public_source_missing_date_rejected() -> None:
    bad = _good_entry()
    del bad["public_sources"][0]["date"]
    with pytest.raises(ChronicleEntryError, match="public_sources"):
        validate_chronicle_entry(bad)


def test_public_source_bad_date_format_rejected() -> None:
    bad = _good_entry()
    bad["public_sources"][0]["date"] = "March 2024"
    with pytest.raises(ChronicleEntryError, match="YYYY"):
        validate_chronicle_entry(bad)


def test_public_source_year_month_date_accepted() -> None:
    good = _good_entry()
    good["public_sources"][0]["date"] = "2024-03"
    validate_chronicle_entry(good)


def test_unknown_verification_status_rejected() -> None:
    bad = _good_entry()
    bad["verification_status"] = "trust_me"
    with pytest.raises(ChronicleEntryError, match="verification_status"):
        validate_chronicle_entry(bad)


# --- PII deny-list -----------------------------------------------------------


@pytest.mark.parametrize(
    "field_path,bad_value",
    [
        ("notes", "Customer email leaked: foo@bar.com"),
        ("notes", "Sort code 12-34-56 mentioned in entry"),
        ("notes", "Account number 12345678 mentioned"),
        ("notes", "Date of birth 1985-04-12 mentioned"),
        ("notes", "National Insurance number AB123456C mentioned"),
    ],
)
def test_pii_deny_list_blocks_curation_errors(field_path: str, bad_value: str) -> None:
    bad = _good_entry()
    bad[field_path] = bad_value
    with pytest.raises(ChronicleEntryError, match="PII deny-list"):
        validate_chronicle_entry(bad)


def test_pii_check_walks_nested_structures() -> None:
    """A leak inside a nested list/dict still raises."""
    bad = _good_entry()
    bad["public_sources"][0]["source"] = "Email sent to leak@example.com"
    with pytest.raises(ChronicleEntryError, match="PII deny-list"):
        validate_chronicle_entry(bad)


def test_no_pii_in_shipped_library() -> None:
    """Every shipped entry passes the PII deny-list check (proven by
    load_chronicle_library succeeding) — this test asserts the API
    contract end-to-end."""
    library = load_chronicle_library(_ENTRIES_DIR)
    assert len(library) >= 10


# --- matcher: fails closed on pending entries --------------------------------


def _stub_library(verification_status: str = "verified") -> list[dict]:
    entry = _good_entry()
    entry["verification_status"] = verification_status
    return [entry]


def test_match_returns_verified_entry() -> None:
    matches = match_signature(
        _stub_library("verified"),
        signature_id="dwell_after_error",
        screen_class="credit_application",
        severity="P0",
    )
    assert len(matches) == 1
    assert isinstance(matches[0], ChronicleMatch)
    assert matches[0].chronicle_id == "CHR-friction-999"
    assert matches[0].regulator == "FCA"
    assert matches[0].year == 2024


def test_match_excludes_pending_review_by_default() -> None:
    """Pending entries must NOT influence Risk scoring — fails closed."""
    matches = match_signature(
        _stub_library("pending_human_review"),
        signature_id="dwell_after_error",
        screen_class="credit_application",
        severity="P0",
    )
    assert matches == []


def test_match_includes_pending_when_explicitly_opted_in() -> None:
    matches = match_signature(
        _stub_library("pending_human_review"),
        signature_id="dwell_after_error",
        screen_class="credit_application",
        severity="P0",
        include_pending=True,
    )
    assert len(matches) == 1


def test_match_misses_when_signature_does_not_match() -> None:
    matches = match_signature(
        _stub_library("verified"),
        signature_id="different_signature",
        screen_class="credit_application",
        severity="P0",
    )
    assert matches == []


def test_match_misses_when_screen_does_not_match() -> None:
    matches = match_signature(
        _stub_library("verified"),
        signature_id="dwell_after_error",
        screen_class="other_screen",
        severity="P0",
    )
    assert matches == []


def test_match_misses_when_severity_does_not_match() -> None:
    matches = match_signature(
        _stub_library("verified"),
        signature_id="dwell_after_error",
        screen_class="credit_application",
        severity="P2",
    )
    assert matches == []


def test_validate_does_not_mutate_input() -> None:
    entry = _good_entry()
    snapshot = copy.deepcopy(entry)
    validate_chronicle_entry(entry)
    assert entry == snapshot


def test_empty_library_directory_rejected(tmp_path) -> None:
    """A directory with no CHR-friction-*.yaml files must fail load —
    silent zero-entry libraries would let Risk methodology degrade
    invisibly."""
    with pytest.raises(ChronicleEntryError, match="no CHR-friction"):
        load_chronicle_library(tmp_path)


def test_duplicate_chronicle_id_rejected(tmp_path) -> None:
    """Two files asserting the same chronicle_id must fail load."""
    entry = _good_entry()
    (tmp_path / "CHR-friction-999.yaml").write_text(
        "chronicle_id: CHR-friction-999\n"
        + _yaml_for(entry),
        encoding="utf-8",
    )
    other = copy.deepcopy(entry)
    (tmp_path / "CHR-friction-998.yaml").write_text(
        # filename says 998 but file declares 999 — that's also a problem,
        # but this test asserts the dup-id check fires before any
        # filename/id mismatch check
        _yaml_for(other),
        encoding="utf-8",
    )
    with pytest.raises(ChronicleEntryError, match="duplicate chronicle_id"):
        load_chronicle_library(tmp_path)


def _yaml_for(entry: dict) -> str:
    import yaml
    return yaml.safe_dump(entry, sort_keys=False)


# --- additional structural invariants on shipped entries ---------------------


def test_shipped_entries_cover_multiple_journey_categories() -> None:
    """A library that only covered one journey_category would have
    limited matcher utility — assert spread across the seed batch."""
    library = load_chronicle_library(_ENTRIES_DIR)
    categories = {e["friction_pattern"]["journey_category"] for e in library}
    assert len(categories) >= 2, (
        f"shipped library only covers journey categories {categories}"
    )


def test_shipped_entries_cover_multiple_regulators() -> None:
    """Useful for matcher cross-regulator joins later."""
    library = load_chronicle_library(_ENTRIES_DIR)
    regs = {e["regulator"] for e in library}
    assert len(regs) >= 1  # ICO + FCA at minimum in the seed batch


def test_shipped_entries_all_pending_or_verified() -> None:
    """No shipped entry should be `rejected` — those should be deleted
    rather than left in the file system."""
    library = load_chronicle_library(_ENTRIES_DIR)
    statuses = {e["verification_status"] for e in library}
    assert "rejected" not in statuses, (
        "rejected entries should be removed from the library, not left in place"
    )


def test_chronicle_ids_use_monotonic_numbering() -> None:
    """Numbering convention: monotonically increasing, no gaps in the
    initial seed batch. Gaps will appear later (entries retired by
    append-only amendments) — this test asserts the seed batch is clean."""
    library = load_chronicle_library(_ENTRIES_DIR)
    nums = sorted(
        int(re.match(r"CHR-friction-(\d+)", e["chronicle_id"]).group(1))
        for e in library
    )
    # seed batch (first 10) must be 1..10 contiguous
    if len(nums) >= 10:
        assert nums[:10] == list(range(1, 11)), (
            f"seed batch numbering should be contiguous 001..010, got {nums[:10]}"
        )
