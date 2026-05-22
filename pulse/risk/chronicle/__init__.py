"""Chronicle precedent library — curated friction-pattern enforcement registry.

Pulse Risk methodology matches detection signatures against this library to
compute a reputation-exposure component: "this signature is what triggered
enforcement at peer institution X in year Y."

Mirrors the MIL Sonar Chronicle pattern (CHR-001..) but adapted from
outage-incident framing to friction-pattern framing. Every entry pins a
regulator, year, institution, friction pattern, enforcement action,
and at least one public source.

Two-stage trust model (mirrors MIL):
- Entries ship with `verification_status: pending_human_review`. The
  matcher excludes them from Risk tier escalation until reviewed.
- A curator (Pulse maintainer with UK-banking expertise) flips entries
  to `verification_status: verified` after corroborating facts against
  the cited public sources. Only verified entries influence Risk scoring.

Filed under PULSE-100.
"""

from pulse.risk.chronicle.validate import (
    ChronicleEntryError,
    load_chronicle_entry,
    load_chronicle_library,
    validate_chronicle_entry,
)
from pulse.risk.chronicle.match import (
    ChronicleMatch,
    match_signature,
)

__all__ = [
    "ChronicleEntryError",
    "ChronicleMatch",
    "load_chronicle_entry",
    "load_chronicle_library",
    "match_signature",
    "validate_chronicle_entry",
]
