"""Chronicle matcher — signature × screen × severity lookup.

The Pulse Risk methodology calls match_signature() with a detected friction
shape and gets back the verified Chronicle entries that share the same
friction_pattern coordinates. Pending-review entries are excluded — they do
not influence Risk tier escalation until a curator marks them verified.

Filed under PULSE-100.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChronicleMatch:
    """A Chronicle entry that matches a detected friction shape."""

    chronicle_id: str
    institution: str
    regulator: str
    year: int
    enforcement_type: str
    fine_gbp: float | None
    redress_gbp: float | None
    public_sources_count: int


def match_signature(
    library: list[dict[str, Any]],
    *,
    signature_id: str,
    screen_class: str,
    severity: str,
    include_pending: bool = False,
) -> list[ChronicleMatch]:
    """Return Chronicle entries whose friction_pattern matches the given
    coordinates. Fails closed: only `verified` entries are returned by
    default. Pass include_pending=True to also include pending-review
    entries (Pulse Risk methodology never sets this in production)."""
    matches: list[ChronicleMatch] = []
    for entry in library:
        if not include_pending and entry["verification_status"] != "verified":
            continue
        pattern = entry["friction_pattern"]
        if (
            pattern["signature_id"] != signature_id
            or pattern["screen_class"] != screen_class
            or pattern["severity"] != severity
        ):
            continue
        action = entry["enforcement_action"]
        year = entry["year"]
        if isinstance(year, str):
            year = int(year)
        matches.append(
            ChronicleMatch(
                chronicle_id=entry["chronicle_id"],
                institution=entry["institution"],
                regulator=entry["regulator"],
                year=year,
                enforcement_type=action["type"],
                fine_gbp=action.get("fine_gbp"),
                redress_gbp=action.get("redress_gbp"),
                public_sources_count=len(entry["public_sources"]),
            )
        )
    return matches
