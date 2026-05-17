"""Chain verifier — walks lineage rows in order, asserts integrity.

Does NOT throw on violations. Returns a structured report; the caller
decides whether to exit non-zero (verifier_cli does).

Filed under PULSE-89.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from pulse.lineage.chain import GENESIS, recompute_row_hash


@dataclass
class Violation:
    """One integrity violation detected during chain walk."""

    kind: str  # "row-hash-mismatch" | "chain-break" | "genesis-missing"
    lineage_id: str
    expected: str
    actual: str


@dataclass
class VerifyReport:
    total_rows: int
    violations: list[Violation] = field(default_factory=list)
    last_lineage_id: str | None = None
    last_row_hash: str | None = None

    @property
    def ok(self) -> bool:
        return not self.violations


def verify_chain(rows: Iterable[dict[str, Any]]) -> VerifyReport:
    """Walk rows in iteration order, recompute hashes, check chain integrity."""
    violations: list[Violation] = []
    expected_prev = GENESIS
    last_lineage_id: str | None = None
    last_row_hash: str | None = None
    total = 0

    for row in rows:
        total += 1
        lineage_id = row.get("lineage_id", "<missing>")

        if row["prev_row_hash"] != expected_prev:
            kind = "genesis-missing" if expected_prev == GENESIS else "chain-break"
            violations.append(
                Violation(
                    kind=kind,
                    lineage_id=lineage_id,
                    expected=expected_prev,
                    actual=row["prev_row_hash"],
                )
            )

        recomputed = recompute_row_hash(row)
        if recomputed != row["row_hash"]:
            violations.append(
                Violation(
                    kind="row-hash-mismatch",
                    lineage_id=lineage_id,
                    expected=recomputed,
                    actual=row["row_hash"],
                )
            )

        expected_prev = row["row_hash"]
        last_lineage_id = lineage_id
        last_row_hash = row["row_hash"]

    return VerifyReport(
        total_rows=total,
        violations=violations,
        last_lineage_id=last_lineage_id,
        last_row_hash=last_row_hash,
    )
