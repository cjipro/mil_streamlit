"""Parser-level checks that the memory layer holds its required structure.

STATE.md       — required H2 sections present
DECISIONS.md   — D-NNN regex; IDs strictly increasing from 1; required
                 fields per entry; `Implemented by:` references at least
                 one file path
CONVENTIONS.md — required H2 sections present
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

STATE_PATH = REPO_ROOT / "STATE.md"
DECISIONS_PATH = REPO_ROOT / "docs" / "decisions" / "DECISIONS.md"
CONVENTIONS_PATH = REPO_ROOT / "docs" / "CONVENTIONS.md"

REQUIRED_STATE_SECTIONS = (
    "Phase",
    "Latest decisions",
    "Latest findings",
    "Open questions",
    "Next step",
)
REQUIRED_CONVENTIONS_SECTIONS = (
    "Runtime",
    "Bindings",
    "Primitives",
    "Patterns",
    "Engine-per-stage",
)
REQUIRED_DECISION_FIELDS = (
    "Status",
    "Context",
    "Decision",
    "Consequences",
    "Implemented by",
)

# Matches headers like: "## D-001 — 2026-05-30 — Title"
# em-dash (—) is U+2014.
DECISION_HEADER_RE = re.compile(
    r"^##\s+D-(\d{3})\s+—\s+(\d{4}-\d{2}-\d{2})\s+—\s+(.+)$",
    re.MULTILINE,
)


def _read(path: Path) -> str:
    assert path.exists(), f"memory file missing: {path}"
    return path.read_text(encoding="utf-8")


# ── STATE.md ─────────────────────────────────────────────────────────


def test_state_md_has_required_sections() -> None:
    content = _read(STATE_PATH)
    for section in REQUIRED_STATE_SECTIONS:
        pattern = rf"^##\s+{re.escape(section)}\b"
        assert re.search(pattern, content, re.MULTILINE), (
            f"STATE.md missing H2 section: '{section}'"
        )


# ── DECISIONS.md ─────────────────────────────────────────────────────


def test_decisions_md_has_at_least_one_entry() -> None:
    content = _read(DECISIONS_PATH)
    headers = DECISION_HEADER_RE.findall(content)
    assert len(headers) >= 1, "DECISIONS.md has no D-NNN entries"


def test_decisions_md_ids_form_strict_sequence_from_one() -> None:
    content = _read(DECISIONS_PATH)
    headers = DECISION_HEADER_RE.findall(content)
    ids = sorted(int(h[0]) for h in headers)
    expected = list(range(1, len(ids) + 1))
    assert ids == expected, (
        f"DECISIONS.md IDs must form 1..N with no gaps; got {ids}"
    )


def test_decisions_md_entries_have_required_fields() -> None:
    content = _read(DECISIONS_PATH)
    headers = DECISION_HEADER_RE.findall(content)
    n_entries = len(headers)
    for field in REQUIRED_DECISION_FIELDS:
        # Each `**Field:**` should appear at least n_entries times.
        occurrences = len(re.findall(rf"\*\*{re.escape(field)}:\*\*", content))
        assert occurrences >= n_entries, (
            f"DECISIONS.md field '**{field}:**' appears {occurrences} times; "
            f"expected at least {n_entries} (one per entry)"
        )


def test_decisions_md_implemented_by_references_code_or_tbd() -> None:
    content = _read(DECISIONS_PATH)
    # Split on D-NNN headers; first chunk is preamble, skip it.
    chunks = re.split(r"^## D-\d{3}", content, flags=re.MULTILINE)
    entry_bodies = chunks[1:]
    assert entry_bodies, "no entry bodies parsed"
    for body in entry_bodies:
        has_code_ref = ".py" in body or ".yml" in body or ".yaml" in body or ".md" in body
        has_tbd = "TBD" in body
        assert has_code_ref or has_tbd, (
            "every decision entry must reference at least one file (.py/.yml/"
            ".yaml/.md) or be marked TBD; body starts: " + body[:120]
        )


# ── CONVENTIONS.md ───────────────────────────────────────────────────


def test_conventions_md_has_required_sections() -> None:
    content = _read(CONVENTIONS_PATH)
    for section in REQUIRED_CONVENTIONS_SECTIONS:
        pattern = rf"^##\s+{re.escape(section)}\b"
        assert re.search(pattern, content, re.MULTILINE), (
            f"CONVENTIONS.md missing H2 section: '{section}'"
        )
