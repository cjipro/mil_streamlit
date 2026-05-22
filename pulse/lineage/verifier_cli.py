"""Verifier CLI — reads pulse_lineage_log.jsonl, prints structured report, exits non-zero on violations.

Mirrors the pattern from MIL-65's verify_cli.ts.

Usage:
    py -m pulse.lineage.verifier_cli path/to/pulse_lineage_log.jsonl

Exit codes:
    0 — chain intact
    1 — one or more violations detected
    2 — invocation error (file missing, malformed JSON)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pulse.lineage.verifier import verify_chain


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("usage: py -m pulse.lineage.verifier_cli <path-to-log.jsonl>", file=sys.stderr)
        return 2

    log_path = Path(argv[0])
    if not log_path.exists():
        print(f"error: log file not found: {log_path}", file=sys.stderr)
        return 2

    try:
        rows = []
        with log_path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"error: malformed JSON at line {line_no}: {e}", file=sys.stderr)
                    return 2
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    report = verify_chain(rows)

    print(f"total rows: {report.total_rows}")
    print(f"last lineage_id: {report.last_lineage_id}")
    print(f"last row_hash: {report.last_row_hash}")
    print(f"violations: {len(report.violations)}")
    for v in report.violations:
        print(f"  - {v.kind} at {v.lineage_id}: expected {v.expected!r}, got {v.actual!r}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
