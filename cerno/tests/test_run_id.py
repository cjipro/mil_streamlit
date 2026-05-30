"""Tests for cerno.run_id — deterministic run identifiers."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from cerno.run_id import make_run_id


def test_deterministic_for_same_input() -> None:
    a = make_run_id("2026-05-30", {"x": 1, "y": 2})
    b = make_run_id("2026-05-30", {"x": 1, "y": 2})
    assert a == b


def test_key_order_does_not_affect_hash() -> None:
    a = make_run_id("2026-05-30", {"x": 1, "y": 2})
    b = make_run_id("2026-05-30", {"y": 2, "x": 1})
    assert a == b


def test_different_params_yield_different_hash() -> None:
    a = make_run_id("2026-05-30", {"x": 1})
    b = make_run_id("2026-05-30", {"x": 2})
    assert a != b


def test_format_matches_spec() -> None:
    rid = make_run_id("2026-05-30", {"k": "v"})
    # YYYY-MM-DD-XXXXXXXX
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{8}", rid)


def test_default_date_is_today_utc() -> None:
    rid = make_run_id(None, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert rid.startswith(today + "-")


def test_handles_non_json_serialisable_via_default_str() -> None:
    # Pass an object that isn't natively JSON-serialisable to confirm the
    # default=str fallback covers it without raising.
    class Marker:
        def __str__(self) -> str:
            return "marker"

    rid = make_run_id("2026-05-30", {"obj": Marker()})
    assert rid.startswith("2026-05-30-")
