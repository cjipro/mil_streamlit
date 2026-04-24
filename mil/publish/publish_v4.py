#!/usr/bin/env python3
"""
publish_v4.py — MIL Sonar Briefing V4, Jinja2-powered (MIL-39).

V4 is the FCA Consumer Duty 2.0 variant of V3. Same layout as V3 plus a
four-field Provenance Chain (chronicle_id / signal_ids / class_ver /
teacher_ver) rendered on every Inference Card.

V4 runs in parallel with V3 for the cutover window:
  V1 → cjipro.com/briefing       (actively maintained, f-string)
  V2 → cjipro.com/briefing-v2    (actively maintained, f-string + V1 extension)
  V3 → cjipro.com/briefing-v3    (actively maintained, f-string, MIL-29)
  V4 → cjipro.com/briefing-v4    (Jinja2 + FCA Provenance Chain, MIL-39)

Legacy publish_v3.py remains the source of truth for data-prep helpers
(V3_STYLES, _replace_box3, _load_env, benchmark/commentary pulls). V4's
generate_v4_html monkeypatches the six section builders in publish_v3 to
route through the Jinja2 template at mil/publish/templates/briefing_v4.html.j2,
then delegates to legacy.generate_v3_html. V3 output is untouched.

MIL Zero Entanglement: no imports from pulse/, poc/, app/, dags/

CLI:
  (no args)   Build V4 HTML, write mil/publish/output/index_v4.html, push
              briefing-v4/index.html to GitHub Pages.
  --diff-gate Fetch live data, render every section via legacy f-string AND
              Jinja paths, emit structural-diff + FCA-compliance report.
              Exits 0 if all sections pass. No publish.
  --render    Build V4 HTML and write mil/publish/output/index_v4.html
              only. No publish, no push.
"""

from __future__ import annotations

import difflib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR    = Path(__file__).resolve().parent
MIL_DIR       = SCRIPT_DIR.parent
REPO_ROOT     = MIL_DIR.parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"
OUTPUT_DIR    = SCRIPT_DIR / "output"

sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(MIL_DIR))
sys.path.insert(0, str(REPO_ROOT))

from adapters import write_text_lf  # LF-only HTML writes

from jinja2 import Environment, FileSystemLoader, StrictUndefined

import publish_v3 as legacy
from mil.publish.box3_selector import (
    CLARK_ACTION_DETAILS,
    build_preamble_html,
    select_box3_issue,
)

TEMPLATE_NAME = "briefing_v4.html.j2"


# ── Jinja environment ────────────────────────────────────────────────────────
def _env() -> Environment:
    # autoescape=False: parity with legacy f-string output (no HTML escaping).
    # StrictUndefined: fail loudly on missing context keys instead of silent blanks.
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=False,
    )


def _render_block(block_name: str, ctx: dict) -> str:
    """Render a single named block from briefing_v4.html.j2 with the given context."""
    tmpl = _env().get_template(TEMPLATE_NAME)
    render_ctx = tmpl.new_context(vars=ctx)
    return "".join(tmpl.blocks[block_name](render_ctx))


# ── Box 3 (Intelligence Brief) context builder ───────────────────────────────
def _box3_context(benchmark_result: dict, boxes: list[dict]) -> dict:
    """
    Shape Box 3 inputs from benchmark + commentary results. Mirrors the
    data-prep in legacy._build_exec_summary_box so diffs isolate to HTML
    shape, not data.
    """
    over  = benchmark_result.get("over_indexed", [])
    under = benchmark_result.get("under_indexed", [])

    try:
        clark_summary = legacy.active_clark_summary()
    except Exception:
        clark_summary = {"active": []}
    selected = select_box3_issue(over, clark_summary=clark_summary)
    # Persist the selected issue for MIL-49 briefing_email — decoupled from HTML.
    try:
        from mil.publish.box3_selector import write_priority_artifact
        write_priority_artifact(selected)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("box3 priority artifact write failed: %s", exc)

    risk_boxes = [b for b in boxes if b.get("type") == "risk" and b.get("prose")]
    matched_box = None
    if selected:
        matched_box = next(
            (b for b in risk_boxes if b.get("issue_type") == selected["issue_type"]),
            None,
        )
    top_box = matched_box or (risk_boxes[0] if risk_boxes else None)
    top_quote_raw = ""
    if top_box:
        situation = top_box["prose"]
        top_quote_raw = (top_box.get("top_quotes") or [""])[0]
    elif selected:
        issue_name = selected["issue_type"]
        sev  = selected.get("dominant_severity", "P1")
        days = selected.get("days_active", 0)
        days_str = f" for {days} consecutive days" if days > 1 else ""
        situation = (
            f"Barclays is showing elevated {issue_name} signals{days_str}. "
            f"The dominant severity is {sev}. "
            f"This is the leading complaint category in the current review corpus."
        )
    else:
        situation = "No significant over-indexed signals detected in the current review corpus."

    top_quote = top_quote_raw[:220] if top_quote_raw and len(top_quote_raw) > 20 else ""

    if selected:
        top = selected
        issue_name = top["issue_type"]
        gap    = top["gap_pp"]
        b_rate = top.get("barclays_rate", 0.0)
        p_rate = top.get("peer_avg_rate", 0.0)
        days   = top.get("days_active", 0)
        cat    = top.get("category", "technical")

        # Rank-of-6 prose (matches publish_v3.py style). Stat strip already carries the
        # absolute gap, so peer paragraph adds relative position + best-peer identity.
        benchmark_raw = benchmark_result.get("benchmark", {})
        all_rates: dict[str, float] = {legacy.COMP_LABELS.get("barclays", "Barclays"): b_rate}
        for comp in ["natwest", "lloyds", "hsbc", "monzo", "revolut"]:
            comp_data = benchmark_raw.get("competitors", {}).get(comp, {})
            rate = comp_data.get(cat, {}).get(issue_name)
            if rate is not None:
                all_rates[legacy.COMP_LABELS.get(comp, comp)] = rate

        if len(all_rates) > 1:
            ranked = sorted(all_rates.items(), key=lambda kv: kv[1])
            pos = next(
                (i + 1 for i, (name, _) in enumerate(ranked)
                 if name == legacy.COMP_LABELS.get("barclays", "Barclays")),
                len(ranked),
            )
            if 10 <= pos % 100 <= 20:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(pos % 10, "th")
            ordinal = f"{pos}{suffix}"
            best_peer, best_rate = ranked[0]
            peer_prose = (
                f"Barclays ranks {ordinal} of {len(ranked)} on {issue_name}. "
                f"Best in the cohort is {best_peer} at {best_rate:.1f}%."
            )
        else:
            peer_prose = f"Benchmark data unavailable for {issue_name}."

        if under:
            strength = under[0]
            peer_prose += (
                f" On {strength['issue_type']}, Barclays leads the cohort — "
                f"{abs(strength['gap_pp']):.1f}pp below average."
            )
    else:
        peer_prose = "Barclays complaint rates are broadly in line with the 5-bank peer cohort. No material over-indexed issues detected."

    top_tier = selected.get("clark_tier", "CLARK-0") if selected else "CLARK-0"
    if top_tier == "CLARK-0":
        try:
            active_clark = [e for e in clark_summary.get("active", [])
                            if e.get("competitor") == "barclays"]
            for t in ["CLARK-3", "CLARK-2", "CLARK-1"]:
                if any(e.get("clark_tier") == t for e in active_clark):
                    top_tier = t
                    break
        except Exception:
            pass
    clark_col = legacy.CLARK_COLOURS[top_tier]

    volume_strip_html = legacy._build_volume_strip(selected) if selected else ""
    vol_stats = legacy._compute_issue_volume_stats(selected["issue_type"]) if selected else None
    preamble_html = build_preamble_html(selected, vol_stats)

    return {
        "situation":         situation,
        "top_quote":         top_quote,
        "peer_prose":        peer_prose,
        "action_details":    CLARK_ACTION_DETAILS[top_tier],
        "top_tier":          top_tier,
        "clark_label":       legacy.CLARK_LABELS[top_tier],
        "clark_col":         clark_col,
        "volume_strip_html": volume_strip_html,
        "preamble_html":     preamble_html,
    }


def _build_exec_summary_box_jinja(benchmark_result: dict, boxes: list[dict]) -> str:
    return _render_block("box3_intelligence_brief", _box3_context(benchmark_result, boxes))


# ── Commentary context builder ───────────────────────────────────────────────
def _commentary_context(boxes: list[dict]) -> dict:
    cards = []
    for box in boxes:
        btype   = box["type"]
        gap     = box["gap_pp"]
        sev     = box["dominant_severity"]
        quotes  = box.get("top_quotes") or []
        chr_ctx = box.get("chr_resonance") or ""
        cards.append({
            "btype":     btype,
            "issue":     box["issue_type"],
            "cat_label": box["category"].upper(),
            "sev":       sev,
            "sev_cls":   f"sev-{sev.lower()}",
            "b_rate":    box["barclays_rate"],
            "p_rate":    box["peer_avg_rate"],
            "gap_str":   f"+{gap:.1f}pp" if gap > 0 else f"{gap:.1f}pp",
            "gap_col":   "#CC3333" if gap > 0 else "#00AFA0",
            "days":      box["days_active"],
            "first":     box.get("first_seen") or "",
            "cached":    bool(box.get("cached")),
            "prose":     box["prose"],
            "quote":     quotes[0] if quotes else "",
            "chr_line":  (f"{chr_ctx[:120]}..." if (chr_ctx and btype == "risk") else ""),
        })
    return {
        "commentary": {
            "cards":          cards,
            "risk_count":     sum(1 for b in boxes if b.get("type") == "risk"),
            "strength_count": sum(1 for b in boxes if b.get("type") == "strength"),
        }
    }


def _build_commentary_section_jinja(boxes: list[dict]) -> str:
    if not boxes:
        return ""
    return _render_block("analyst_commentary", _commentary_context(boxes))


# ── Benchmark (technical + service) context builder ──────────────────────────
_BENCH_SEV_COL = {"P0": "#CC0000", "P1": "#F5A623", "P2": "#4A9BD4"}


def _benchmark_context(category: str, category_label: str,
                       benchmark: dict, persistence_map: dict) -> dict:
    barcl_rates = benchmark.get("competitors", {}).get("barclays", {}).get(category, {})
    peer_avg    = benchmark.get("peer_avg", {}).get(category, {})

    rows = []
    for issue in sorted(barcl_rates.keys()):
        b_rate = barcl_rates.get(issue, 0.0)
        p_rate = peer_avg.get(issue, 0.0)
        gap    = b_rate - p_rate

        persist = persistence_map.get(issue, {})
        over    = persist.get("over_indexed", gap > 0)
        sev     = persist.get("dominant_severity", "P2")
        days    = persist.get("days_active", 0)

        max_val = max(b_rate, p_rate, 1.0)
        b_pct   = int((b_rate / max_val) * 100)
        p_pct   = int((p_rate / max_val) * 100)

        rows.append({
            "issue":       issue,
            "sev_col":     _BENCH_SEV_COL.get(sev, "#4A9BD4"),
            "b_rate":      b_rate,
            "p_rate":      p_rate,
            "b_pct":       b_pct,
            "p_pct":       p_pct,
            "b_col":       "#CC3333" if over else "#00AEEF",
            "gap_str":     f"+{gap:.1f}pp" if gap > 0 else f"{gap:.1f}pp",
            "gap_cls":     "bench-gap-positive" if gap > 2
                           else ("bench-gap-negative" if gap < -2 else "bench-gap-neutral"),
            "days_active": days,
        })

    comp_pills = []
    for comp in ["natwest", "lloyds", "hsbc", "monzo", "revolut"]:
        rates = benchmark.get("competitors", {}).get(comp, {}).get(category, {})
        avg   = sum(rates.values()) / max(len(rates), 1)
        comp_pills.append({
            "label": legacy.COMP_LABELS[comp],
            "col":   legacy.COMP_COLOURS.get(comp, "#7AACBF"),
            "rate":  avg,
        })

    icon = "&#9888;" if category == "technical" else "&#9998;"
    return {
        "icon":        icon,
        "label_upper": category_label.upper(),
        "comp_pills":  comp_pills,
        "rows":        rows,
    }


def _build_benchmark_section_jinja(category: str, category_label: str,
                                   benchmark: dict, persistence_map: dict) -> str:
    section_ctx = _benchmark_context(category, category_label, benchmark, persistence_map)
    if not section_ctx["rows"]:
        return ""
    if category == "technical":
        return _render_block("technical_benchmark", {"tech_bench": section_ctx})
    return _render_block("service_benchmark", {"svc_bench": section_ctx})


# ── Intelligence Findings context builder ────────────────────────────────────
def _format_signal_ids(sids: list) -> str:
    """Compact signal-id display for the FCA Provenance Chain."""
    n = len(sids)
    if n == 0:
        return "0 signals"
    head = ", ".join(sids[:2])
    return f"{n} signals ({head})" if n <= 2 else f"{n} signals ({head}, …)"


def _findings_context(findings: list[dict], render_provenance: bool) -> dict:
    cards = []
    for f in findings:
        tier     = f.get("finding_tier", "P3")
        sev      = f.get("signal_severity", "P2")
        cac      = f.get("confidence_score", 0.0)
        ceiling  = bool(f.get("designed_ceiling_reached"))
        summary  = (f.get("finding_summary") or "No summary.")[:120]
        kws      = f.get("top_3_keywords", []) or []
        chr_id   = (f.get("chronicle_match") or {}).get("chronicle_id", "")
        counts   = f.get("signal_counts", {}) or {}
        jid      = f.get("journey_id", "")
        prov     = f.get("provenance", {}) or {}

        cards.append({
            "fid":          f.get("finding_id", "—"),
            "tier":         tier,
            "tier_col":     legacy.TIER_COLOURS.get(tier, "#4A7A8F"),
            "sev":          sev,
            "ceiling":      ceiling,
            "chr_id":       chr_id,
            "summary_text": summary,
            "cac":          cac,
            "cac_pct":      min(int(cac * 100), 100),
            "cac_col":      "#CC0000" if cac >= 0.65 else ("#F5A623" if cac >= 0.45 else "#4A9BD4"),
            "journey":      legacy.JOURNEY_LABELS.get(jid, jid),
            "counts":       {"P0": counts.get("P0", 0), "P1": counts.get("P1", 0), "P2": counts.get("P2", 0)},
            "keywords":     kws,
            "provenance":   {
                "chronicle_id":       prov.get("chronicle_id") or "",
                "signal_ids_display": _format_signal_ids(prov.get("signal_ids") or []),
                "class_ver":          prov.get("classification_version") or "",
                "teacher_ver":        prov.get("teacher_model_version") or "",
            },
        })
    ceiling_count = sum(1 for f in findings if f.get("designed_ceiling_reached"))
    return {
        "findings": {
            "cards":             cards,
            "total":             len(findings),
            "ceiling_count":     ceiling_count,
            "render_provenance": render_provenance,
        }
    }


def _render_findings_block(render_provenance: bool) -> str:
    findings = legacy.load_findings(competitor="barclays", limit=8)
    if not findings:
        return ""
    return _render_block("intelligence_findings", _findings_context(findings, render_provenance))


def _build_findings_section_jinja() -> str:
    """Production renders always include the FCA four-field Provenance Chain."""
    return _render_findings_block(render_provenance=True)


# ── Clark Protocol context builder ───────────────────────────────────────────
_CLARK_TIER_STRIP = ["CLARK-3", "CLARK-2", "CLARK-1", "CLARK-0"]
_CLARK_ROW_ORDER  = {"CLARK-3": 0, "CLARK-2": 1, "CLARK-1": 2}


def _clark_context() -> dict:
    summary = legacy.active_clark_summary()
    active  = [e for e in summary.get("active", []) if e.get("competitor") == "barclays"]

    by_tier: dict[str, int] = {}
    for e in active:
        t = e.get("clark_tier", "CLARK-0")
        by_tier[t] = by_tier.get(t, 0) + 1

    tiles = [{
        "tier":   tier,
        "label":  legacy.CLARK_LABELS[tier],
        "count":  by_tier.get(tier, 0),
        "colour": legacy.CLARK_COLOURS[tier],
    } for tier in _CLARK_TIER_STRIP]

    rows = []
    for e in sorted(active, key=lambda x: _CLARK_ROW_ORDER.get(x.get("clark_tier", "CLARK-0"), 3)):
        ctier = e.get("clark_tier", "CLARK-0")
        rows.append({
            "fid":    e.get("finding_id", "—"),
            "tier":   ctier,
            "label":  legacy.CLARK_LABELS.get(ctier, "?"),
            "colour": legacy.CLARK_COLOURS.get(ctier, "#3A6A7F"),
            "cac":    e.get("cac_score", 0.0),
            "reason": (e.get("reason") or "")[:80],
            "ts":     (e.get("ts") or "")[:16].replace("T", " "),
        })

    return {"clark": {"tiles": tiles, "rows": rows}}


def _build_clark_section_jinja() -> str:
    return _render_block("clark_protocol", _clark_context())


# ── Full-page generator — monkeypatches legacy builders to Jinja renderers ───
_JINJA_OVERRIDES = {
    "_build_exec_summary_box":   _build_exec_summary_box_jinja,
    "_build_commentary_section": _build_commentary_section_jinja,
    "_build_benchmark_section":  _build_benchmark_section_jinja,
    "_build_findings_section":   _build_findings_section_jinja,
    "_build_clark_section":      _build_clark_section_jinja,
}


def generate_v4_html(v1_html: str) -> str:
    """
    Build V4 HTML by monkeypatching legacy's six section builders to render
    via the Jinja2 template, then delegating to legacy.generate_v3_html for
    non-section orchestration (V3_STYLES injection, _replace_box3, etc.).
    Patches are restored on exit — legacy V3 output is unaffected.
    """
    saved = {name: getattr(legacy, name) for name in _JINJA_OVERRIDES}
    for name, fn in _JINJA_OVERRIDES.items():
        setattr(legacy, name, fn)
    try:
        return legacy.generate_v3_html(v1_html)
    finally:
        for name, fn in saved.items():
            setattr(legacy, name, fn)


# ── Diff gate ────────────────────────────────────────────────────────────────
def _structural_whitespace_normalise(html: str) -> list[str]:
    """
    Tokenize HTML by tag boundaries, collapsing ALL whitespace (including
    line breaks) to single spaces. Makes diffs insensitive to where tags
    wrap across lines.
    """
    import re
    flat = re.sub(r"\s+", " ", html).strip()
    tokens = re.findall(r"<[^>]+>|[^<]+", flat)
    return [t.strip() for t in tokens if t.strip()]


def _fetch_live_data() -> tuple[dict, list[dict], dict]:
    """Pull benchmark + commentary + persistence_map once so legacy and Jinja render from identical inputs."""
    sys.path.insert(0, str(MIL_DIR / "data"))
    from benchmark_engine import run as benchmark_run
    benchmark_result = benchmark_run(mode="daily")

    try:
        from commentary_engine import generate_commentary
        boxes = generate_commentary()
    except Exception as exc:
        print(f"  [WARNING] commentary_engine failed: {exc}")
        boxes = []

    persistence_map: dict = {}
    persistence_log = MIL_DIR / "data" / "issue_persistence_log.jsonl"
    if persistence_log.exists():
        import json as _json
        all_entries = []
        for line in persistence_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    all_entries.append(_json.loads(line))
                except Exception:
                    pass
        if all_entries:
            latest_date = max(e["date"] for e in all_entries)
            persistence_map = {e["issue_type"]: e for e in all_entries if e["date"] == latest_date}

    return benchmark_result, boxes, persistence_map


def _diff_section(slug: str, legacy_html: str, jinja_html: str) -> bool:
    raw_diff = list(difflib.unified_diff(
        legacy_html.splitlines(keepends=True),
        jinja_html.splitlines(keepends=True),
        fromfile=f"{slug}_legacy.html", tofile=f"{slug}_jinja.html", n=2,
    ))
    struct_diff = list(difflib.unified_diff(
        _structural_whitespace_normalise(legacy_html),
        _structural_whitespace_normalise(jinja_html),
        fromfile=f"{slug}_legacy.struct", tofile=f"{slug}_jinja.struct", n=2,
    ))
    OUTPUT_DIR.mkdir(exist_ok=True)
    write_text_lf(OUTPUT_DIR / f"{slug}_legacy.html", legacy_html)
    write_text_lf(OUTPUT_DIR / f"{slug}_jinja.html", jinja_html)

    whitespace_only = sum(
        1 for l in raw_diff
        if l.startswith(('+','-')) and not l.startswith(('+++','---'))
    )
    print(f"  [{slug}] legacy={len(legacy_html):>5}B  jinja={len(jinja_html):>5}B  "
          f"struct-diff={len(struct_diff)}  whitespace-only={whitespace_only}")

    if struct_diff:
        print(f"  [FAIL {slug}] structural diff non-empty.")
        print("".join(struct_diff[:200]))
        return False
    print(f"  [PASS {slug}] structural diff clean.")
    return True


def _check_fca_provenance(findings_html: str) -> bool:
    """
    Validate FCA Consumer Duty 2.0: every Inference Card must render a
    Provenance Chain with chronicle_id, signal_ids, class_ver, teacher_ver.
    Missing data is "—" (visible audit gap); missing DOM elements are non-compliant.
    """
    import re
    n_cards = findings_html.count('class="inf-card"')
    n_prov_blocks = findings_html.count('class="inf-provenance"')
    required_fields = ["chronicle_id", "signal_ids", "class_ver", "teacher_ver"]
    missing_per_field = {
        k: n_cards - len(re.findall(rf'data-prov="{re.escape(k)}"', findings_html))
        for k in required_fields
    }
    ok = (n_prov_blocks == n_cards) and all(v == 0 for v in missing_per_field.values())
    status = "PASS" if ok else "FAIL"
    print(f"  [{status} fca_provenance] cards={n_cards} prov_blocks={n_prov_blocks}  "
          f"missing_fields={missing_per_field}")
    if not ok:
        print("  [FAIL fca_provenance] FCA Consumer Duty 2.0 requires all four "
              "provenance fields on every Inference Card.")
    return ok


def diff_gate() -> int:
    """V4 vs V3 structural equivalence + FCA compliance on every section."""
    print("[MIL-39] V4 diff gate — fetching live data once, rendering via both paths.")
    benchmark_result, boxes, persistence_map = _fetch_live_data()
    benchmark = benchmark_result.get("benchmark", {})
    print()

    results = [
        _diff_section("box3",
            legacy._build_exec_summary_box(benchmark_result, boxes),
            _build_exec_summary_box_jinja(benchmark_result, boxes)),
        _diff_section("commentary",
            legacy._build_commentary_section(boxes),
            _build_commentary_section_jinja(boxes)),
        _diff_section("tech_bench",
            legacy._build_benchmark_section("technical", "Technical Issues", benchmark, persistence_map),
            _build_benchmark_section_jinja("technical", "Technical Issues", benchmark, persistence_map)),
        _diff_section("svc_bench",
            legacy._build_benchmark_section("service", "Service Issues", benchmark, persistence_map),
            _build_benchmark_section_jinja("service", "Service Issues", benchmark, persistence_map)),
        # Findings: V3 has no Provenance Chain. Structural parity compares V4
        # with provenance OFF; FCA compliance is validated separately on ON.
        _diff_section("findings_noprov",
            legacy._build_findings_section(),
            _render_findings_block(render_provenance=False)),
        _check_fca_provenance(_render_findings_block(render_provenance=True)),
        _diff_section("clark",
            legacy._build_clark_section(),
            _build_clark_section_jinja()),
    ]

    if all(results):
        print("\n  [OK] V4 is structurally equivalent to V3 and FCA-compliant.")
        return 0
    print(f"\n  [FAIL] {results.count(False)}/{len(results)} check(s) failed.")
    return 1


# ── Publish (MIL-35 PublishAdapter) ──────────────────────────────────────────
def publish_v4(html_content: str) -> tuple[bool, str]:
    """
    Push briefing-v4/index.html via the configured PublishAdapter
    (mil/config/publish_config.yaml). Clone operators swap targets there
    without touching this file.
    """
    from adapters import get_adapter
    return get_adapter().publish("briefing-v4/index.html", html_content)


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    args = sys.argv[1:]

    if "--diff-gate" in args:
        return diff_gate()

    v1_path = OUTPUT_DIR / "index.html"
    if not v1_path.exists():
        print("  ERROR: V1 briefing not found at mil/publish/output/index.html")
        print("  Run publish.py first (or run_daily.py)")
        return 1
    v1_html = v1_path.read_text(encoding="utf-8")
    print("\n-- Sonar Briefing V4 Publisher --")
    print(f"  V1 source: {v1_path} ({len(v1_html)//1024}KB)")

    print("\n[1/3] Building V4 sections (Jinja2 + FCA Provenance Chain) ...")
    v4_html = generate_v4_html(v1_html)
    print(f"  V4 size: {len(v4_html)//1024}KB")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_v4 = OUTPUT_DIR / "index_v4.html"
    write_text_lf(local_v4, v4_html)
    print(f"  Local copy: {local_v4}")

    if "--render" in args:
        print("\n[2/3] --render: skipping publish.")
        return 0

    print("\n[2/3] Publishing to GitHub Pages ...")
    ok, msg = publish_v4(v4_html)
    print(f"  {'OK' if ok else 'FAIL'}: {msg}")

    print("\n[3/3] Report")
    print("-" * 56)
    print(f"  V1 (unchanged):  https://cjipro.com/briefing")
    print(f"  V2 (unchanged):  https://cjipro.com/briefing-v2")
    print(f"  V3 (unchanged):  https://cjipro.com/briefing-v3")
    print(f"  V4 (FCA Jinja):  https://cjipro.com/briefing-v4")
    print(f"  GitHub push:     {'SUCCESS' if ok else 'FAIL'}")
    print(f"  Local V4:        {local_v4}")
    print("-" * 56)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
