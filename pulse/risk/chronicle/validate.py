"""Chronicle entry validator + library loader.

Strict validation by default. Every shipped entry must carry:
- a chronicle_id matching the CHR-friction-NNN convention
- an institution name (regulator publishes it, citing it is not a PII breach)
- a regulator from a known set
- a friction_pattern carrying signature_id + journey_category + screen_class + severity
- an enforcement_action with a verified type
- at least one public_sources entry with a source string and a date
- a verification_status from a known set

A PII deny-list pattern (mirrors real_bank_contract.yaml) scans every
string field for keys that would indicate leakage of individual customer
data into the Chronicle text. Public Final Notices never name customers
by personal details, so any such leak is a curation error.

Filed under PULSE-100.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Any

import yaml


class ChronicleEntryError(ValueError):
    """Raised when a Chronicle entry does not conform to the schema."""


_CHR_ID_RE = re.compile(r"^CHR-friction-\d{3,}$")
_YEAR_RE = re.compile(r"^\d{4}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_KNOWN_REGULATORS = {
    "FCA",            # UK Financial Conduct Authority
    "PRA",            # UK Prudential Regulation Authority
    "ICO",            # UK Information Commissioner's Office
    "EBA",            # European Banking Authority
    "ECB",            # European Central Bank
    "BAFIN",          # German federal financial supervisor
    "AMF",            # French financial markets authority
    "CSSF",           # Luxembourg financial sector supervisor
}

_KNOWN_JOURNEY_CATEGORIES = {
    "choke_point",
    "context_loss",
    "behavioural_noise",
    "regulator",
    "infrastructure",
}

_KNOWN_SEVERITIES = {"P0", "P1", "P2"}

_KNOWN_ENFORCEMENT_TYPES = {
    "fine",
    "redress",
    "restriction",
    "individual_sanction",
    "s166_review",   # FCA skilled-person review
    "voluntary_undertaking",
}

_KNOWN_VERIFICATION_STATUSES = {
    "pending_human_review",
    "verified",
    "rejected",
}

# PII deny-list. Mirrors the real_bank_contract.yaml pattern. Public
# enforcement notices never carry these — if a Chronicle entry does, the
# curator copy-pasted from the wrong source.
_PII_DENY_TOKENS = [
    "@",                       # email pattern
    "sort code",
    "sort-code",
    "account number",
    "date of birth",
    "national insurance number",
]

_REQUIRED_TOP_LEVEL = {
    "chronicle_id",
    "institution",
    "regulator",
    "year",
    "friction_pattern",
    "enforcement_action",
    "public_sources",
    "verification_status",
}

_REQUIRED_FRICTION_PATTERN = {
    "signature_id",
    "journey_category",
    "screen_class",
    "severity",
}


def load_chronicle_entry(path: Path | str) -> dict[str, Any]:
    """Load a single CHR-friction-NNN.yaml entry and strictly validate it.
    Returns the parsed dict on success."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        entry = yaml.safe_load(f)
    validate_chronicle_entry(entry)
    return entry


def load_chronicle_library(entries_dir: Path | str) -> list[dict[str, Any]]:
    """Load every CHR-friction-NNN.yaml entry under entries_dir and
    validate each. Returns the list in chronicle_id-sorted order.
    Raises ChronicleEntryError on any malformed entry — fails closed.
    Raises ChronicleEntryError if the directory yields zero entries."""
    d = Path(entries_dir)
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for path in sorted(d.glob("CHR-friction-*.yaml")):
        entry = load_chronicle_entry(path)
        if entry["chronicle_id"] in seen_ids:
            raise ChronicleEntryError(
                f"duplicate chronicle_id {entry['chronicle_id']!r} "
                f"(found in {path.name})"
            )
        seen_ids.add(entry["chronicle_id"])
        entries.append(entry)
    if not entries:
        raise ChronicleEntryError(
            f"no CHR-friction-*.yaml entries found under {d}"
        )
    return entries


def validate_chronicle_entry(entry: Any) -> None:
    """Strictly validate a parsed Chronicle entry. Raises
    ChronicleEntryError on any violation."""
    if not isinstance(entry, dict):
        raise ChronicleEntryError(
            f"entry must be a mapping, got {type(entry).__name__}"
        )

    missing = _REQUIRED_TOP_LEVEL - set(entry.keys())
    if missing:
        raise ChronicleEntryError(f"missing required fields: {sorted(missing)}")

    _validate_chronicle_id(entry["chronicle_id"])
    _validate_institution(entry["institution"])
    _validate_regulator(entry["regulator"])
    _validate_year(entry["year"])
    _validate_friction_pattern(entry["friction_pattern"])
    _validate_enforcement_action(entry["enforcement_action"])
    _validate_public_sources(entry["public_sources"])
    _validate_verification_status(entry["verification_status"])

    _check_pii_deny_list(entry)


def _validate_chronicle_id(chronicle_id: Any) -> None:
    if not isinstance(chronicle_id, str) or not _CHR_ID_RE.match(chronicle_id):
        raise ChronicleEntryError(
            f"chronicle_id must match CHR-friction-NNN convention, got {chronicle_id!r}"
        )


def _validate_institution(institution: Any) -> None:
    if not isinstance(institution, str) or not institution.strip():
        raise ChronicleEntryError(
            "institution must be a non-empty string (as named in the cited public source)"
        )


def _validate_regulator(regulator: Any) -> None:
    if regulator not in _KNOWN_REGULATORS:
        raise ChronicleEntryError(
            f"regulator must be one of {sorted(_KNOWN_REGULATORS)}, got {regulator!r}"
        )


def _validate_year(year: Any) -> None:
    """Year of enforcement action (not incident). int or YYYY string."""
    if isinstance(year, bool):
        raise ChronicleEntryError("year must be an integer year, not a bool")
    if isinstance(year, int):
        if year < 2000 or year > 2100:
            raise ChronicleEntryError(
                f"year must be a plausible enforcement year, got {year}"
            )
        return
    if isinstance(year, str) and _YEAR_RE.match(year):
        return
    raise ChronicleEntryError(f"year must be a four-digit year, got {year!r}")


def _validate_friction_pattern(pattern: Any) -> None:
    if not isinstance(pattern, dict):
        raise ChronicleEntryError("friction_pattern must be a mapping")
    missing = _REQUIRED_FRICTION_PATTERN - set(pattern.keys())
    if missing:
        raise ChronicleEntryError(
            f"friction_pattern missing required keys: {sorted(missing)}"
        )
    if not isinstance(pattern["signature_id"], str) or not pattern["signature_id"]:
        raise ChronicleEntryError(
            "friction_pattern.signature_id must be a non-empty string"
        )
    if pattern["journey_category"] not in _KNOWN_JOURNEY_CATEGORIES:
        raise ChronicleEntryError(
            "friction_pattern.journey_category must be one of "
            f"{sorted(_KNOWN_JOURNEY_CATEGORIES)}, got "
            f"{pattern['journey_category']!r}"
        )
    if not isinstance(pattern["screen_class"], str) or not pattern["screen_class"]:
        raise ChronicleEntryError(
            "friction_pattern.screen_class must be a non-empty string"
        )
    if pattern["severity"] not in _KNOWN_SEVERITIES:
        raise ChronicleEntryError(
            "friction_pattern.severity must be one of "
            f"{sorted(_KNOWN_SEVERITIES)}, got {pattern['severity']!r}"
        )


def _validate_enforcement_action(action: Any) -> None:
    if not isinstance(action, dict):
        raise ChronicleEntryError("enforcement_action must be a mapping")
    if "type" not in action:
        raise ChronicleEntryError("enforcement_action missing 'type'")
    if action["type"] not in _KNOWN_ENFORCEMENT_TYPES:
        raise ChronicleEntryError(
            "enforcement_action.type must be one of "
            f"{sorted(_KNOWN_ENFORCEMENT_TYPES)}, got {action['type']!r}"
        )
    for amount_key in ("fine_gbp", "redress_gbp"):
        if amount_key in action and action[amount_key] is not None:
            value = action[amount_key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ChronicleEntryError(
                    f"enforcement_action.{amount_key} must be a non-negative "
                    f"number or null, got {value!r}"
                )


def _validate_public_sources(sources: Any) -> None:
    if not isinstance(sources, list) or not sources:
        raise ChronicleEntryError(
            "public_sources must be a non-empty list — every entry requires "
            "at least one verifiable public-source citation"
        )
    for i, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ChronicleEntryError(f"public_sources[{i}] must be a mapping")
        if "source" not in source or not isinstance(source["source"], str) or not source["source"].strip():
            raise ChronicleEntryError(
                f"public_sources[{i}].source must be a non-empty string"
            )
        if "date" not in source:
            raise ChronicleEntryError(f"public_sources[{i}] missing 'date'")
        date = source["date"]
        # Accept full ISO date, YYYY-MM, or PyYAML-parsed datetime.date.
        if isinstance(date, _dt.date) and not isinstance(date, _dt.datetime):
            continue
        if not isinstance(date, str) or not (
            _ISO_DATE_RE.match(date) or _ISO_YEAR_MONTH_RE.match(date)
        ):
            raise ChronicleEntryError(
                f"public_sources[{i}].date must be YYYY-MM-DD or YYYY-MM, "
                f"got {date!r}"
            )


def _validate_verification_status(status: Any) -> None:
    if status not in _KNOWN_VERIFICATION_STATUSES:
        raise ChronicleEntryError(
            "verification_status must be one of "
            f"{sorted(_KNOWN_VERIFICATION_STATUSES)}, got {status!r}"
        )


def _check_pii_deny_list(entry: Any) -> None:
    """Walk the entry and assert no string contains a PII deny-list token.
    Public enforcement notices never carry these — a hit means the curator
    copy-pasted from the wrong source."""
    for path, value in _walk_strings(entry, prefix=""):
        lowered = value.lower()
        for token in _PII_DENY_TOKENS:
            if token in lowered:
                raise ChronicleEntryError(
                    f"PII deny-list token {token!r} found at {path!r} — "
                    "public enforcement notices do not carry customer PII; "
                    "remove this content or recheck source"
                )


def _walk_strings(node: Any, prefix: str):
    """Yield (dotted_path, string_value) for every string in a nested dict/list."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, prefix=f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, prefix=f"{prefix}[{i}]")
    elif isinstance(node, str):
        yield prefix, node
