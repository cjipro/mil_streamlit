"""
mil/chat/retrievers/structured.py — MIL-41.

Direct lookup against the structured MIL artefacts — CHRONICLE entries
and findings JSON. No ranking, no text search: entity-keyed fetches
with exact filters on competitor / journey / chronicle_id.

Use this retriever when the query carries concrete handles (chronicle_id,
competitor, finding_id). Broad text search belongs in bm25/embedding.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from mil.chat.retrievers.base import Evidence, EvidenceBundle, Retriever
from mil.inference.chronicle_loader import load_chronicle_entries

logger = logging.getLogger(__name__)

_MIL_ROOT       = Path(__file__).parent.parent.parent
_FINDINGS_PATH  = _MIL_ROOT / "outputs" / "mil_findings.json"


@lru_cache(maxsize=1)
def _load_findings() -> list[dict]:
    if not _FINDINGS_PATH.exists():
        logger.warning("[structured] findings file missing: %s", _FINDINGS_PATH)
        return []
    with _FINDINGS_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("findings", []) if isinstance(payload, dict) else []


def _chronicle_to_text(entry: dict) -> str:
    lines = [
        f"{entry.get('chronicle_id')} | {entry.get('bank')} | "
        f"incident_type={entry.get('incident_type', 'unknown')}",
    ]
    if entry.get("pattern_description"):
        lines.append(entry["pattern_description"])
    if entry.get("journey_tags"):
        lines.append(f"journeys: {', '.join(entry['journey_tags'])}")
    return "\n".join(lines)


def _finding_to_text(entry: dict) -> str:
    lines = [
        f"{entry.get('finding_id')} | {entry.get('competitor')} | "
        f"journey={entry.get('journey_id')} | tier={entry.get('finding_tier')}",
    ]
    if entry.get("finding_summary"):
        lines.append(entry["finding_summary"])
    sc = entry.get("signal_counts") or {}
    if sc:
        lines.append(f"signals: P0={sc.get('P0', 0)} P1={sc.get('P1', 0)} P2={sc.get('P2', 0)}")
    cac = entry.get("cac_components") or {}
    if isinstance(cac, dict) and cac.get("total") is not None:
        lines.append(f"CAC={cac['total']:.3f}")
    if entry.get("chronicle_match"):
        lines.append(f"chronicle_match={entry['chronicle_match']}")
    return "\n".join(lines)


class StructuredRetriever(Retriever):
    name = "structured"

    def retrieve(
        self,
        query: str,
        entities: Optional[dict[str, Any]] = None,
        k: int = 10,
    ) -> EvidenceBundle:
        entities = entities or {}
        bundle = EvidenceBundle(query=query, retriever_chain=[self.name])

        self._retrieve_chronicle(entities, bundle)
        self._retrieve_findings(entities, bundle)

        bundle.total_candidates = len(bundle.items)
        bundle.items = bundle.top_k(k)
        return bundle

    def _retrieve_chronicle(self, entities: dict[str, Any], bundle: EvidenceBundle) -> None:
        entries = load_chronicle_entries()
        competitors = self._competitors(entities)
        chronicle_id = entities.get("chronicle_id")
        chronicle_event = (entities.get("chronicle_event") or "").lower()
        journey_id = entities.get("journey_id")

        for entry in entries:
            score = 0.0

            if chronicle_id and entry.get("chronicle_id") == chronicle_id:
                score = 1.0

            if competitors:
                bank_lc = (entry.get("bank") or "").lower()
                if any(c in bank_lc for c in competitors):
                    score = max(score, 0.85)

            if chronicle_event:
                blob = f"{entry.get('bank', '')} {entry.get('incident_type', '')}".lower()
                tokens = [t for t in chronicle_event.split() if len(t) >= 3]
                if tokens:
                    hits = sum(1 for t in tokens if t in blob)
                    ratio = hits / len(tokens)
                    if ratio > 0:
                        score = max(score, 0.7 + 0.2 * ratio)

            if journey_id and journey_id in (entry.get("journey_tags") or []):
                score = max(score, 0.6)

            if score > 0:
                bundle.add(Evidence(
                    source="chronicle",
                    id=entry.get("chronicle_id", "CHR-?"),
                    text=_chronicle_to_text(entry),
                    score=score,
                    metadata={
                        "bank":          entry.get("bank"),
                        "incident_type": entry.get("incident_type"),
                        "journey_tags":  entry.get("journey_tags", []),
                    },
                ))

    def _retrieve_findings(self, entities: dict[str, Any], bundle: EvidenceBundle) -> None:
        competitors = self._competitors(entities)
        journey_id = entities.get("journey_id")
        issue_type = entities.get("issue_type")
        finding_id = entities.get("finding_id")
        severity   = entities.get("severity") or entities.get("severity_class")

        # A severity-only query ("any active P0 signals?") is valid — scan all
        # findings, otherwise require at least one concrete filter to avoid
        # dumping the full 142-row findings set.
        has_filter = bool(
            competitors or journey_id or issue_type or finding_id or severity
        )
        if not has_filter:
            return

        findings = _load_findings()
        tier_score = {"CLARK-3": 1.0, "CLARK-2": 0.9, "CLARK-1": 0.8}
        severity_rank = {"P0": 3, "P1": 2, "P2": 1}

        for entry in findings:
            if finding_id and entry.get("finding_id") != finding_id:
                continue
            if competitors and (entry.get("competitor") or "").lower() not in competitors:
                continue
            if journey_id and entry.get("journey_id") != journey_id:
                continue
            if issue_type and entry.get("dominant_issue_type") != issue_type:
                continue

            sig_counts = entry.get("signal_counts") or {}
            finding_sev = entry.get("signal_severity") or ""

            # Severity filter: keep finding if it reports at least one signal at
            # the requested severity (e.g. P0 → sig_counts.P0 >= 1 or
            # signal_severity is P0). Otherwise drop.
            if severity:
                req_rank = severity_rank.get(severity, 3)
                has_matching = False
                for sev_key, rank in severity_rank.items():
                    if rank >= req_rank and sig_counts.get(sev_key, 0) > 0:
                        has_matching = True
                        break
                if not has_matching and severity_rank.get(finding_sev, 0) < req_rank:
                    continue

            # Boost findings where the requested severity dominates
            sev_boost = 0.0
            if severity and sig_counts.get(severity, 0) > 0:
                sev_boost = min(0.2, 0.02 * sig_counts[severity])

            bundle.add(Evidence(
                source="findings",
                id=entry.get("finding_id") or f"finding_{len(bundle.items)}",
                text=_finding_to_text(entry),
                score=min(1.0, tier_score.get(entry.get("finding_tier") or "", 0.7) + sev_boost),
                metadata={
                    "competitor":     entry.get("competitor"),
                    "journey_id":     entry.get("journey_id"),
                    "finding_tier":   entry.get("finding_tier"),
                    "signal_severity": finding_sev,
                    "p0_count":       sig_counts.get("P0", 0),
                    "p1_count":       sig_counts.get("P1", 0),
                    "issue_type":     entry.get("dominant_issue_type"),
                    "chronicle_match": entry.get("chronicle_match"),
                },
            ))

    @staticmethod
    def _competitors(entities: dict[str, Any]) -> set[str]:
        out: set[str] = set()
        if entities.get("competitor"):
            out.add(str(entities["competitor"]).lower())
        for c in entities.get("competitors") or []:
            if isinstance(c, str):
                out.add(c.lower())
        return out
