#!/usr/bin/env python3
"""
mil/chronicle/migrate_to_yaml.py — MIL-34

One-shot migration: extracts every ```yaml ... ``` block from mil/CHRONICLE.md
and writes each as a standalone YAML file at mil/chronicle/entries/CHR-XXX.yaml.

After migration, chronicle_loader.py reads the directory directly — no regex,
no CRLF fragility, no startup assertion needed.

Re-running is safe (idempotent): overwrites existing entry files with the
current canonical content from CHRONICLE.md.
"""
import re
import sys
from pathlib import Path

MIL_ROOT     = Path(__file__).parent.parent
CHRONICLE_MD = MIL_ROOT / "CHRONICLE.md"
ENTRIES_DIR  = MIL_ROOT / "chronicle" / "entries"


def main() -> int:
    if not CHRONICLE_MD.exists():
        print(f"ERROR: {CHRONICLE_MD} not found", file=sys.stderr)
        return 1

    text = CHRONICLE_MD.read_text(encoding="utf-8")
    # Grab each yaml code block body (CRLF safe)
    blocks = re.findall(r"```yaml\r?\n(.*?)\r?\n```", text, re.DOTALL)
    print(f"Found {len(blocks)} YAML blocks in CHRONICLE.md")

    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for block in blocks:
        # Extract chronicle_id from first line that matches
        m = re.search(r"^chronicle_id:\s*(CHR-\d+)", block, re.MULTILINE)
        if not m:
            print("  skip: block has no chronicle_id")
            continue
        cid = m.group(1)
        out = ENTRIES_DIR / f"{cid}.yaml"
        out.write_text(block.rstrip() + "\n", encoding="utf-8")
        print(f"  wrote {out.name}")
        written += 1

    print(f"\nMigrated {written} entries -> {ENTRIES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
