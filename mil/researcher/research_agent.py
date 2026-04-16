"""
research_agent.py — MIL Research Agent (Option A)

Processes mil/data/research_queue.jsonl, clusters findings by competitor +
journey, and drafts proposed CHRONICLE entries for Hussain to approve.

Output: mil/data/chr_proposals/<competitor>_<journey>_<timestamp>.md
         mil/data/chr_proposals/summary_<timestamp>.md

Usage:
    py mil/researcher/research_agent.py
    py mil/researcher/research_agent.py --dry-run   # cluster report only, no LLM
    py mil/researcher/research_agent.py --competitor barclays

MIL Import Rule: no imports from pulse/, poc/, app/, dags/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import anthropic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
MIL_ROOT     = Path(__file__).parent.parent
REPO_ROOT    = MIL_ROOT.parent
QUEUE_FILE   = MIL_ROOT / "data" / "research_queue.jsonl"
PROPOSALS_DIR = MIL_ROOT / "data" / "chr_proposals"
CHRONICLE_MD  = MIL_ROOT / "CHRONICLE.md"

# Add mil/ to path so get_model works when called directly
if str(MIL_ROOT) not in sys.path:
    sys.path.insert(0, str(MIL_ROOT))

from config.get_model import get_model

# Load .env so ANTHROPIC_API_KEY is available when run directly
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

# ── Chronicle ID registry (read existing entries to determine next ID) ────────
KNOWN_CHR_IDS = [
    "CHR-001", "CHR-002", "CHR-003", "CHR-004",
    "CHR-005", "CHR-006", "CHR-007", "CHR-008",
    "CHR-009", "CHR-010", "CHR-011", "CHR-012",
    "CHR-013", "CHR-014", "CHR-015", "CHR-016",
    "CHR-017", "CHR-018", "CHR-019",
]

JOURNEY_LABELS = {
    "J_LOGIN_01":   "Log In / Account Access",
    "J_PAY_01":     "Make a Payment / Transfer",
    "J_SERVICE_01": "Account / Service Access",
    "J_CARD_01":    "Manage Card",
    "J_SUPPORT_01": "Get Support",
    "J_ONBOARD_01": "Onboarding / Registration",
}

COMP_LABELS = {
    "barclays": "Barclays",
    "natwest":  "NatWest",
    "lloyds":   "Lloyds",
    "monzo":    "Monzo",
    "revolut":  "Revolut",
    "hsbc":     "HSBC UK",
}

# Clusters that are already anchored to an approved CHR entry with good coverage
# Don't propose a new CHR if the cluster is already well-served
CHR_COVERAGE = {
    # (competitor, journey_id): existing CHR that covers it
    ("barclays", "J_SERVICE_01"): "CHR-017",
    ("barclays", "J_PAY_01"):     "CHR-018",
    ("barclays", "J_LOGIN_01"):   "CHR-019",
}


# ── Load queue ────────────────────────────────────────────────────────────────

def load_queue(competitor_filter: str | None = None) -> list[dict]:
    if not QUEUE_FILE.exists():
        logger.error("[research_agent] Queue file not found: %s", QUEUE_FILE)
        return []
    items = []
    with open(QUEUE_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if item.get("status") == "PENDING":
                    if competitor_filter is None or item.get("competitor") == competitor_filter:
                        items.append(item)
            except json.JSONDecodeError:
                continue
    return items


# ── Cluster ───────────────────────────────────────────────────────────────────

def cluster_queue(items: list[dict]) -> dict[tuple, list[dict]]:
    """Group PENDING items by (competitor, journey_id)."""
    clusters: dict[tuple, list[dict]] = defaultdict(list)
    for item in items:
        key = (item.get("competitor", "unknown"), item.get("journey_id", "unknown"))
        clusters[key].append(item)
    # Sort by size descending
    return dict(sorted(clusters.items(), key=lambda x: -len(x[1])))


# ── Print cluster report ──────────────────────────────────────────────────────

def print_cluster_report(clusters: dict[tuple, list[dict]]) -> None:
    total = sum(len(v) for v in clusters.values())
    print(f"\n{'='*60}")
    print(f"RESEARCH QUEUE — {total} PENDING items, {len(clusters)} clusters")
    print(f"{'='*60}")
    for (comp, journey), group in clusters.items():
        sevs = [i.get("signal_severity", "?") for i in group]
        p0 = sevs.count("P0")
        p1 = sevs.count("P1")
        kw_all = [k for i in group for k in i.get("top_3_keywords", [])]
        top_kw = [k for k, _ in Counter(kw_all).most_common(5)]
        chr_ids = list({i.get("chronicle_id", "") for i in group if i.get("chronicle_id")})
        avg_sim = sum(i.get("sim_hist_score", 0) for i in group) / len(group)
        existing = CHR_COVERAGE.get((comp, journey))
        flag = f"  [COVERED BY {existing}]" if existing else ""
        print(
            f"  {COMP_LABELS.get(comp, comp):<14} {JOURNEY_LABELS.get(journey, journey):<30}"
            f"  n={len(group):>2}  P0={p0} P1={p1}  sim={avg_sim:.2f}"
            f"  anchor={','.join(chr_ids) or 'none'}  kw={top_kw}{flag}"
        )
    print()


# ── Draft CHR proposal via Opus (ARCH-003 Tier 1) ────────────────────────────

def draft_chr_proposal(
    comp: str,
    journey: str,
    group: list[dict],
    next_chr_id: str,
    client: anthropic.Anthropic,
) -> str:
    """Call Opus to draft a proposed CHRONICLE entry for this cluster."""
    cfg = get_model("chr_proposal")   # Opus — ARCH-003 Tier 1

    comp_label   = COMP_LABELS.get(comp, comp)
    journey_label = JOURNEY_LABELS.get(journey, journey)

    kw_all   = [k for i in group for k in i.get("top_3_keywords", [])]
    top_kw   = [k for k, _ in Counter(kw_all).most_common(8)]
    finding_ids = [i.get("finding_id", "") for i in group]
    severities  = [i.get("signal_severity", "") for i in group]
    p0 = severities.count("P0")
    p1 = severities.count("P1")
    avg_cac  = sum(i.get("cac_score", 0) for i in group) / len(group)
    avg_sim  = sum(i.get("sim_hist_score", 0) for i in group) / len(group)
    chr_refs = list({i.get("chronicle_id", "") for i in group if i.get("chronicle_id")})

    # Sample research prompts for context
    sample_prompts = [i.get("research_prompt", "") for i in group[:3]]

    prompt = f"""You are a banking intelligence analyst drafting a CHRONICLE entry proposal.

A cluster of MIL research queue items requires a new CHRONICLE entry.
The CHRONICLE is an immutable banking failure ledger — entries trace to verified PUBLIC sources only.

CLUSTER DETAILS:
- Competitor: {comp_label}
- Journey affected: {journey_label}
- Signal count: {len(group)} findings ({p0} P0, {p1} P1)
- Average CAC score: {avg_cac:.3f}
- Average chronicle similarity: {avg_sim:.3f} (below 0.4 threshold — no strong existing anchor)
- Existing partial anchors: {', '.join(chr_refs) if chr_refs else 'none'}
- Top keywords across cluster: {', '.join(top_kw)}
- Sample finding IDs: {', '.join(finding_ids[:5])}

Sample research prompts from the queue:
{chr(10).join(f'- {p}' for p in sample_prompts)}

TASK:
Draft a proposed CHRONICLE entry in YAML format following this schema:

```yaml
chronicle_id: {next_chr_id}  # PROPOSED — Hussain assigns final ID
date: "YYYY-MM-DD"           # date of incident or start of pattern window
bank: "{comp_label}"
incident_type: "<tag>"       # e.g. app_friction_pattern, payment_failure_cluster, login_regression
inference_approved: false    # PROPOSED — requires Hussain sign-off
confidence_score: 0.0        # 0.0–1.0 — be conservative, mark what is unverified
date_window: "YYYY-MM-DD to YYYY-MM-DD"

summary: >
  One paragraph describing what the cluster of signals suggests is happening.
  Be precise. Do not overstate. Flag uncertainty.

signal_summary:
  finding_count: {len(group)}
  p0_count: {p0}
  p1_count: {p1}
  avg_cac: {avg_cac:.3f}
  top_keywords: {top_kw}

verified_facts:
  - "Only include facts traceable to verified public sources."
  - "Mark anything unverified as [UNVERIFIED — REVIEW REQUIRED]"

causal_chain:
  - "Step 1 of what may have happened (note if speculative)"
  - "Step 2 ..."

mil_relevance:
  - "Why this matters for MIL inference"
  - "Which journey tags it anchors"

confidence:
  dates: LOW/MEDIUM/HIGH
  impact_figures: LOW/MEDIUM/HIGH
  root_cause: LOW/MEDIUM/HIGH
  regulatory_outcome: N/A or LOW/MEDIUM/HIGH

review_flags:
  - "What Hussain needs to verify before inference_approved can be set to true"

public_sources:
  - source: "Name of source"
    date: "YYYY or YYYY-MM-DD"
```

RULES:
1. Be conservative — this is a PROPOSAL not a finding. Hussain must verify before it goes live.
2. If you cannot identify a specific public incident, say so in the summary and set confidence LOW across the board.
3. Do not fabricate source names. Use placeholder format: "Search required: <suggested query>" if no source is known.
4. Keep verified_facts honest — only what public record would support.

Output ONLY the YAML block. No preamble, no explanation after."""

    response = client.messages.create(
        model=cfg["model"],
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Write proposal file ───────────────────────────────────────────────────────

def write_proposal(
    comp: str,
    journey: str,
    group: list[dict],
    chr_yaml: str,
    next_chr_id: str,
    timestamp: str,
) -> Path:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{comp}_{journey.lower()}_{timestamp}.md"
    path = PROPOSALS_DIR / fname

    comp_label    = COMP_LABELS.get(comp, comp)
    journey_label = JOURNEY_LABELS.get(journey, journey)
    finding_ids   = [i.get("finding_id", "") for i in group]

    content = f"""# CHR PROPOSAL — {comp_label} / {journey_label}

**Proposed ID:** {next_chr_id} (Hussain assigns final ID)
**Generated:** {timestamp}
**Status:** DRAFT — requires Hussain review and sign-off before inference use

## Source Findings ({len(group)} items)

{chr(10).join(f'- {fid}' for fid in finding_ids)}

## Proposed CHRONICLE Entry

{chr_yaml}

---

## HUSSAIN REVIEW ACTIONS

- [ ] Verify facts against public sources
- [ ] Confirm or update `date` and `date_window`
- [ ] Confirm `confidence_score` is appropriate
- [ ] Set `inference_approved: true` if satisfied
- [ ] Append to `mil/CHRONICLE.md` (immutability rule: append only)
- [ ] Update RAG in `mil/inference/mil_agent.py` with new entry
- [ ] Mark resolved findings in `research_queue.jsonl` (status: RESOLVED)
"""
    path.write_text(content, encoding="utf-8")
    return path


# ── Summary report ────────────────────────────────────────────────────────────

def write_summary(
    proposals: list[dict],
    skipped: list[dict],
    timestamp: str,
) -> Path:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROPOSALS_DIR / f"summary_{timestamp}.md"

    lines = [
        f"# Research Agent Run — {timestamp}",
        f"\n## Proposals Generated ({len(proposals)})\n",
    ]
    for p in proposals:
        lines.append(
            f"- **{p['chr_id']}** — {COMP_LABELS.get(p['comp'], p['comp'])} / "
            f"{JOURNEY_LABELS.get(p['journey'], p['journey'])} "
            f"({p['n']} findings) → `{p['file'].name}`"
        )

    if skipped:
        lines.append(f"\n## Skipped — Already Covered ({len(skipped)})\n")
        for s in skipped:
            lines.append(
                f"- {COMP_LABELS.get(s['comp'], s['comp'])} / "
                f"{JOURNEY_LABELS.get(s['journey'], s['journey'])} "
                f"({s['n']} findings) — covered by {s['reason']}"
            )

    lines.append("\n## Next Steps\n")
    lines.append("1. Review each proposal file in `mil/data/chr_proposals/`")
    lines.append("2. Verify facts against public sources")
    lines.append("3. Append approved entries to `mil/CHRONICLE.md`")
    lines.append("4. Update RAG in `mil/inference/mil_agent.py`")
    lines.append("5. Re-run inference: `py run_daily.py --skip-fetch`")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="MIL Research Agent — draft CHR proposals")
    parser.add_argument("--dry-run",    action="store_true", help="Cluster report only — no LLM calls")
    parser.add_argument("--competitor", type=str, default=None, help="Filter to one competitor")
    parser.add_argument("--force",      action="store_true", help="Bypass CHR_COVERAGE skip — draft proposals even for covered competitors")
    args = parser.parse_args()

    items = load_queue(competitor_filter=args.competitor)
    if not items:
        print("No PENDING items in research queue.")
        return

    clusters = cluster_queue(items)
    print_cluster_report(clusters)

    if args.dry_run:
        print("[dry-run] Skipping LLM proposals.")
        return

    cfg    = get_model("chr_proposal")   # Opus — ARCH-003 Tier 1
    client = anthropic.Anthropic()

    timestamp  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    next_id_n  = len(KNOWN_CHR_IDS) + 1   # next proposed number

    proposals: list[dict] = []
    skipped:   list[dict] = []

    for (comp, journey), group in clusters.items():
        existing = CHR_COVERAGE.get((comp, journey))
        if existing and not args.force:
            logger.info("[research_agent] Skipping %s/%s — already covered by %s", comp, journey, existing)
            skipped.append({"comp": comp, "journey": journey, "n": len(group), "reason": existing})
            continue
        elif existing and args.force:
            logger.info("[research_agent] --force: overriding coverage skip for %s/%s (was: %s)", comp, journey, existing)

        next_chr_id = f"CHR-{next_id_n:03d} (PROPOSED)"
        logger.info(
            "[research_agent] Drafting %s for %s / %s (%d findings)...",
            next_chr_id, comp, journey, len(group)
        )

        try:
            chr_yaml = draft_chr_proposal(comp, journey, group, next_chr_id, client)
            file_path = write_proposal(comp, journey, group, chr_yaml, next_chr_id, timestamp)
            proposals.append({
                "chr_id": next_chr_id,
                "comp": comp,
                "journey": journey,
                "n": len(group),
                "file": file_path,
            })
            next_id_n += 1
            logger.info("[research_agent] Written → %s", file_path.name)
        except Exception as exc:
            logger.error("[research_agent] Failed %s/%s: %s", comp, journey, exc)

    summary_path = write_summary(proposals, skipped, timestamp)

    print(f"\n{'='*60}")
    print(f"RESEARCH AGENT COMPLETE")
    print(f"  Proposals:  {len(proposals)}")
    print(f"  Skipped:    {len(skipped)} (already covered)")
    print(f"  Output dir: {PROPOSALS_DIR}")
    print(f"  Summary:    {summary_path.name}")
    print(f"{'='*60}\n")
    print("Next: review proposals, verify facts, append approved entries to mil/CHRONICLE.md")


if __name__ == "__main__":
    main()
