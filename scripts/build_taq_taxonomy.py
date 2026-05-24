"""Build-time extractor: TAQ screens.yaml -> committed Pulse taxonomy artifacts (PULSE-137).

Reads the taq-app inventory (sister repo, read ONCE at build time) and emits the
committed, self-contained Pulse taxonomy snapshot:

  - pulse/contracts/taq_taxonomy.yaml    manifest: counts, vocabularies, coverage
  - pulse/contracts/taq_op_code_map.csv  the op_code -> journey, customer_journey mapping

This script is the *documented crossing point*. The pulse package never imports or
reads taq-app at runtime — it consumes only the committed artifacts, so pulse stays
self-contained (same principle as pulse/synthetic/generate_ma_d.py). Re-run this
whenever taq-app/inventory/screens.yaml changes.

Taxonomy (screens.yaml v2):
  Journey (24)           = `journey` field   — coarse/technical grouping, NOT customer journeys
  Customer Journey (107) = `feature` field   — CJ01..CJ107, the canonical roll-up
  Op-code (697)          = screen entries     — the grain (600 op + 57 api + 40 extras)

`feature` exists only on the 600 op-screens, so 97 op-codes have no Customer Journey:
they are recorded as ORPHANS (empty customer_journey) with a coverage metric — never
silently dropped (else roll-ups undercount and "verify every claim" breaks).

Run:
    py scripts/build_taq_taxonomy.py
    py scripts/build_taq_taxonomy.py --screens C:/Users/hussa/taq-app/inventory/screens.yaml
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
DEFAULT_SCREENS = _REPO.parent / "taq-app" / "inventory" / "screens.yaml"
CONTRACTS = _REPO / "pulse" / "contracts"
MANIFEST_OUT = CONTRACTS / "taq_taxonomy.yaml"
MAP_OUT = CONTRACTS / "taq_op_code_map.csv"


def _resolve_op_code(screen: dict) -> str:
    """Stable op-code identifier. op screens carry `code` (A001C); api screens carry
    `op_code`/`handle`; everything has `id`. `id` is the unique PK across all 697."""
    return str(screen.get("code") or screen.get("op_code") or screen.get("handle") or screen["id"])


def extract(screens_path: Path) -> dict:
    data = yaml.safe_load(screens_path.read_text(encoding="utf-8"))
    screens = data["screens"]

    rows = []
    seen_ids = set()
    for s in screens:
        sid = str(s["id"])
        if sid in seen_ids:
            raise ValueError(f"duplicate screen id {sid!r} in {screens_path}")
        seen_ids.add(sid)
        rows.append({
            "id": sid,
            "op_code": _resolve_op_code(s),
            "journey": s.get("journey") or "",            # 24-tier (backend grouping)
            "customer_journey": s.get("feature") or "",    # 107-tier (the roll-up); "" => orphan
        })
    rows.sort(key=lambda r: r["id"])

    journeys = sorted({r["journey"] for r in rows if r["journey"]})
    customer_journeys = sorted({r["customer_journey"] for r in rows if r["customer_journey"]})
    orphans = [r["id"] for r in rows if not r["customer_journey"]]
    mapped = len(rows) - len(orphans)

    manifest = {
        "_generated_by": "scripts/build_taq_taxonomy.py (PULSE-137)",
        "_do_not_edit": "regenerate from taq-app/inventory/screens.yaml; do not hand-edit",
        "source": "taq-app/inventory/screens.yaml",
        "source_meta": data.get("meta", {}).get("version", "unknown"),
        "generated": dt.date.today().isoformat(),
        "counts": {
            "op_codes": len(rows),
            "journeys": len(journeys),
            "customer_journeys": len(customer_journeys),
            "orphans": len(orphans),
            "customer_journey_coverage_pct": round(100.0 * mapped / len(rows), 2) if rows else 0.0,
        },
        "journeys": journeys,
        "customer_journeys": customer_journeys,
    }
    return {"rows": rows, "manifest": manifest}


def write_artifacts(result: dict) -> None:
    CONTRACTS.mkdir(parents=True, exist_ok=True)
    # Manifest YAML — block style, keys unsorted (preserve our order), LF line endings.
    text = yaml.safe_dump(result["manifest"], sort_keys=False, allow_unicode=True, width=100)
    MANIFEST_OUT.write_text(text, encoding="utf-8", newline="\n")
    # Mapping CSV — sorted by id, LF line endings.
    with MAP_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "op_code", "journey", "customer_journey"])
        w.writeheader()
        w.writerows(result["rows"])


def main() -> None:
    p = argparse.ArgumentParser(description="Build Pulse taxonomy artifacts from TAQ screens.yaml (PULSE-137)")
    p.add_argument("--screens", type=Path, default=DEFAULT_SCREENS)
    args = p.parse_args()
    if not args.screens.exists():
        raise SystemExit(f"screens.yaml not found: {args.screens}\n(pass --screens <path>)")

    result = extract(args.screens)
    write_artifacts(result)
    c = result["manifest"]["counts"]
    print(f"wrote {MANIFEST_OUT.relative_to(_REPO)} + {MAP_OUT.relative_to(_REPO)}")
    print(f"  op_codes={c['op_codes']} journeys={c['journeys']} "
          f"customer_journeys={c['customer_journeys']} orphans={c['orphans']} "
          f"coverage={c['customer_journey_coverage_pct']}%")


if __name__ == "__main__":
    main()
