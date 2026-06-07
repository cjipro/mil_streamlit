"""Build-time extractor: TAQ screens.yaml -> committed Pulse taxonomy artifacts (PULSE-137, PULSE-141).

Reads the taq-app inventory (sister repo, read ONCE at build time) and emits the
committed, self-contained Pulse taxonomy snapshot:

  - pulse/contracts/taq_taxonomy.yaml    manifest: counts, kinds, vocabularies, coverage
  - pulse/contracts/taq_op_code_map.csv  faithful per-screen table:
        id, op_code, kind, journey, customer_journey,
        op_class, name, handle, friendly_name,
        friction_class, friction_target, friction_patterns_supported

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

PULSE-141 widened the CSV from {id, op_code, journey, customer_journey} to the faithful
column set above (non-breaking: the original four columns are retained, so the
pulse/taxonomy.py loader + tests are unaffected). The three discriminator field-keys
`feature` / `op_code` / `friction_target` partition the 697 screens exactly into
op (600) / api (57) / extra (40) — recorded as the `kind` column. API op_code stays the
source placeholder `spro1`; the unique API identity lives in `handle`/`friendly_name`.
The 40 extras carry the friction-injection metadata used to drive MA_D error injection.

Note: NO error-code table here yet — the ~50 error codes are supplied separately and
land as pulse/contracts/taq_error_codes.csv (pending). op-codes + APIs are the two
token sources captured by this script.

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

CSV_FIELDS = [
    "id", "op_code", "kind", "journey", "customer_journey",
    "op_class", "name", "handle", "friendly_name",
    "friction_class", "friction_target", "friction_patterns_supported",
]


def _resolve_op_code(screen: dict) -> str:
    """Stable op-code identifier. op screens carry `code` (A001C); api screens carry
    `op_code`/`handle`; everything has `id`. `id` is the unique PK across all 697."""
    return str(screen.get("code") or screen.get("op_code") or screen.get("handle") or screen["id"])


def _flat(v) -> str:
    """Flatten a screens.yaml value to a CSV cell: lists -> 'a|b', None -> '', else str."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "|".join(str(x) for x in v)
    return str(v)


def _kind(screen: dict) -> str:
    """op (has `feature`, 600) / api (has `op_code`, 57) / extra (has `friction_target`, 40).
    These three field-keys partition the 697 screens exactly."""
    if "feature" in screen:
        return "op"
    if "op_code" in screen:
        return "api"
    if "friction_target" in screen:
        return "extra"
    return "unknown"


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
            "kind": _kind(s),                               # op (600) / api (57) / extra (40)
            "journey": s.get("journey") or "",              # 24-tier (backend grouping)
            "customer_journey": s.get("feature") or "",     # 107-tier (the roll-up); "" => orphan
            "op_class": _flat(s.get("op_class")),           # op-screens; terminal/cancel detection
            "name": _flat(s.get("name")),                   # human-readable screen name
            "handle": _flat(s.get("handle")),               # api-screens unique identity
            "friendly_name": _flat(s.get("friendly_name")), # api-screens label
            "friction_class": _flat(s.get("friction_class")),                           # extras
            "friction_target": _flat(s.get("friction_target")),                         # extras
            "friction_patterns_supported": _flat(s.get("friction_patterns_supported")), # extras
        })
    rows.sort(key=lambda r: r["id"])

    journeys = sorted({r["journey"] for r in rows if r["journey"]})
    customer_journeys = sorted({r["customer_journey"] for r in rows if r["customer_journey"]})
    orphans = [r["id"] for r in rows if not r["customer_journey"]]
    mapped = len(rows) - len(orphans)

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1

    manifest = {
        "_generated_by": "scripts/build_taq_taxonomy.py (PULSE-137, PULSE-141)",
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
        "kinds": dict(sorted(kinds.items())),
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
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(result["rows"])


def main() -> None:
    p = argparse.ArgumentParser(description="Build Pulse taxonomy artifacts from TAQ screens.yaml (PULSE-137, PULSE-141)")
    p.add_argument("--screens", type=Path, default=DEFAULT_SCREENS)
    args = p.parse_args()
    if not args.screens.exists():
        raise SystemExit(f"screens.yaml not found: {args.screens}\n(pass --screens <path>)")

    result = extract(args.screens)
    write_artifacts(result)
    c = result["manifest"]["counts"]
    k = result["manifest"]["kinds"]
    print(f"wrote {MANIFEST_OUT.relative_to(_REPO)} + {MAP_OUT.relative_to(_REPO)}")
    print(f"  op_codes={c['op_codes']} journeys={c['journeys']} "
          f"customer_journeys={c['customer_journeys']} orphans={c['orphans']} "
          f"coverage={c['customer_journey_coverage_pct']}%")
    print(f"  kinds={k}")


if __name__ == "__main__":
    main()
