"""
hodos_kernel.decision — the DECISION as a first-class object (HODOS-4 spike).

The core thesis: "Decisions, not dashboards." Following the Palantir-ontology /
DMN pattern, a Decision is an explicit object — inputs → verdict →
recommended_action → outcome (write-back) — not a chart a human has to read.

DecisionLog is a hash-chained, tamper-evident ledger of decisions (lineage by
design — the shape EU AI Act Art. 12 requires: logging in the core, not bolted
on). The verdict + score are computed DETERMINISTICALLY from the evidence and do
NOT depend on the synthesis runtime — the runtime toggle changes the
explanation, never the decision.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from hodos_kernel.detectors import Signal

GENESIS = "0" * 64


@dataclass
class Decision:
    product: str
    subject: str                     # the group decided about (journey / segment)
    verdict: str                     # ACT | WATCH | IGNORE
    score: float
    inputs: dict[str, Any]           # the evidence the verdict was computed from
    recommended_action: str
    narrative: str = ""              # filled by the SynthesisProvider (runtime-dependent)
    outcome: str = "pending"         # write-back slot (Palantir loop): pending|accepted|…

    def core(self) -> dict[str, Any]:
        """The runtime-independent decision content (excludes narrative)."""
        return {
            "product": self.product, "subject": self.subject, "verdict": self.verdict,
            "score": round(self.score, 4), "inputs": self.inputs,
            "recommended_action": self.recommended_action, "outcome": self.outcome,
        }


def decide(product: str, signals: list[Signal], spec: dict[str, Any]) -> list[Decision]:
    """Group signals → score → verdict → recommended action. Pure + deterministic."""
    weights = spec.get("score", {}).get("weights", {"high": 3, "medium": 2, "low": 1})
    act = spec["thresholds"]["act"]
    watch = spec["thresholds"]["watch"]
    entity_noun = spec.get("entity_noun", "records")
    action_tmpl = spec["action_template"]

    by_group: dict[str, list[Signal]] = defaultdict(list)
    for s in signals:
        by_group[s.group].append(s)

    decisions: list[Decision] = []
    for group, sigs in by_group.items():
        score = sum(weights.get(s.severity, 1) for s in sigs)
        entities = {s.entity_id for s in sigs}
        by_detector = Counter(s.label for s in sigs)
        top_signal = by_detector.most_common(1)[0][0]
        verdict = "ACT" if score >= act else ("WATCH" if score >= watch else "IGNORE")
        inputs = {
            "signal_count": len(sigs),
            "entity_count": len(entities),
            "signals_by_type": dict(by_detector),
            "top_signal": top_signal,
            "sample_verbatim": next((s.text for s in sigs if s.text), ""),
        }
        action = action_tmpl.format(
            group=group, score=score, signal_count=len(sigs),
            entity_count=len(entities), entity_noun=entity_noun, top_signal=top_signal,
        )
        decisions.append(Decision(
            product=product, subject=group, verdict=verdict, score=float(score),
            inputs=inputs, recommended_action=action,
        ))

    # Rank: ACT > WATCH > IGNORE, then by score desc.
    order = {"ACT": 0, "WATCH": 1, "IGNORE": 2}
    decisions.sort(key=lambda d: (order[d.verdict], -d.score))
    return decisions


@dataclass
class DecisionLog:
    """Hash-chained ledger of decisions (tamper-evident lineage)."""
    rows: list[dict[str, Any]] = field(default_factory=list)

    def append(self, decision: Decision) -> str:
        prev = self.rows[-1]["row_hash"] if self.rows else GENESIS
        payload = json.dumps(decision.core(), sort_keys=True, ensure_ascii=False)
        row_hash = hashlib.sha256((payload + "|" + prev).encode("utf-8")).hexdigest()
        self.rows.append({"prev_hash": prev, "row_hash": row_hash, "decision": decision.core()})
        return row_hash

    def verify(self) -> bool:
        prev = GENESIS
        for row in self.rows:
            if row["prev_hash"] != prev:
                return False
            payload = json.dumps(row["decision"], sort_keys=True, ensure_ascii=False)
            expect = hashlib.sha256((payload + "|" + prev).encode("utf-8")).hexdigest()
            if expect != row["row_hash"]:
                return False
            prev = row["row_hash"]
        return True
