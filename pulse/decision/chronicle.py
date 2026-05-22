"""CHRONICLE candidate flow — propose ledger candidates from high-stakes findings (PULSE-100).

High-stakes findings are the CHRONICLE-candidate set: top regulatory exposure
(Risk = REGULATORY-FLAG) or a vulnerability-disparity claim the fairness lens
escalated to independent review. For each, this checks the verified precedent
library and proposes a CHRONICLE CANDIDATE for curator review.

Honesty boundary (Article Zero): a candidate is a CURATION WORK-ITEM, never a
fabricated enforcement entry. It carries the matchable friction_pattern + the
detection evidence + verification_status=pending_human_review, with
enforcement_action / public_sources left for a curator to research against real
UK-banking Final Notices. Synthetic detections never invent enforcement precedent —
that is exactly what the entry validator's public_sources requirement guards.

Run:  py -m pulse.decision.chronicle   (after a pipeline run)
"""

from __future__ import annotations

import datetime as dt
import functools
import json
from pathlib import Path
from typing import Any, Iterable

from pulse.risk.chronicle import load_chronicle_library, match_signature
from pulse.serving.marts import MARTS_DIR

_ENTRIES_DIR = Path(__file__).resolve().parents[1] / "risk" / "chronicle" / "entries"
CHRONICLE_CANDIDATES_LOG = MARTS_DIR / "chronicle_candidates.jsonl"


def _iso_now() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


@functools.lru_cache(maxsize=1)
def chronicle_library() -> list[dict[str, Any]]:
    """Verified+pending precedent entries. Empty list if the library can't load
    (the engine still scores; precedent contribution just degrades to nothing)."""
    try:
        return load_chronicle_library(_ENTRIES_DIR)
    except Exception:
        return []


def verified_precedents(*, signature_id: str, screen_class: str, severity: str) -> list[str]:
    """chronicle_ids of VERIFIED entries matching this friction shape (pending excluded)."""
    return [
        m.chronicle_id
        for m in match_signature(
            chronicle_library(),
            signature_id=signature_id,
            screen_class=screen_class,
            severity=severity,
            include_pending=False,
        )
    ]


def is_chronicle_candidate(*, risk_tier: str, fairness_independent_review: bool) -> bool:
    """High-stakes gate: top regulatory exposure OR a fairness-escalated disparity claim."""
    return risk_tier == "REGULATORY-FLAG" or bool(fairness_independent_review)


def _candidate(row: dict[str, Any], deployment_id: str) -> dict[str, Any]:
    precedents = verified_precedents(
        signature_id=row["signature"],
        screen_class=row["screen_class"],
        severity=row["severity"],
    )
    if row["risk_tier"] == "REGULATORY-FLAG" and row.get("fairness_independent_review"):
        trigger = "regulatory_flag+fairness_disparity"
    elif row["risk_tier"] == "REGULATORY-FLAG":
        trigger = "regulatory_flag"
    else:
        trigger = "fairness_disparity"
    return {
        "candidate_id": f"CHR-CAND-{row['screen_id'].replace('.', '_')}__{row['signature']}",
        "proposed_at": _iso_now(),
        "deployment_id": deployment_id,
        "trigger": trigger,
        "proposed_from": {
            "finding": f"{row['screen_id']}/{row['signature']}",
            "lineage_id": row.get("lineage_id"),
            "action_tier": row["action_tier"],
            "risk_tier": row["risk_tier"],
        },
        "friction_pattern": {
            "signature_id": row["signature"],
            "journey_category": row["journey_category"],
            "screen_class": row["screen_class"],
            "severity": row["severity"],
        },
        "detection_evidence": {
            "affected_sessions": row["affected_sessions"],
            "fire_rate": row["fire_rate"],
            "vulnerable_cohort_disparity_ratio": row.get("fairness_disparity_ratio"),
            "independent_review_triggered": bool(row.get("fairness_independent_review")),
            "regulatory_matches": row.get("regulatory_matches", []),
        },
        # Left for the curator — synthetic detection never invents enforcement precedent.
        "existing_verified_precedent": precedents,
        "enforcement_action": None,
        "public_sources": [],
        "verification_status": "pending_human_review",
        "curator_actions_required": [
            "Research whether a UK-banking enforcement precedent exists for this friction_pattern",
            "If yes, author a full CHR-friction-NNN entry (institution + public_sources)",
            "If no, retain as a forward-looking risk-watch candidate",
        ],
    }


def propose_chronicle_candidates(
    rows: Iterable[dict[str, Any]],
    *,
    deployment_id: str = "synthetic-taq",
    log_path: Path = CHRONICLE_CANDIDATES_LOG,
) -> dict[str, Any]:
    """Propose CHRONICLE candidates from the high-stakes decision rows; write the log."""
    candidates = [
        _candidate(r, deployment_id)
        for r in rows
        if is_chronicle_candidate(
            risk_tier=r["risk_tier"],
            fairness_independent_review=bool(r.get("fairness_independent_review")),
        )
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")

    with_precedent = sum(1 for c in candidates if c["existing_verified_precedent"])
    return {
        "candidates": len(candidates),
        "with_verified_precedent": with_precedent,
        "needs_research": len(candidates) - with_precedent,
        "log_path": str(log_path),
    }


def read_chronicle_candidates(log_path: Path = CHRONICLE_CANDIDATES_LOG) -> list[dict]:
    """Read the proposed CHRONICLE candidates (FastAPI-facing)."""
    if not Path(log_path).exists():
        return []
    return [
        json.loads(line)
        for line in Path(log_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
