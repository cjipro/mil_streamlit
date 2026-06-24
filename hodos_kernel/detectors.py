"""
hodos_kernel.detectors — declarative, deterministic signal detection (HODOS-4 spike).

Detectors are declared in the manifest, not coded per product. Each is a simple
comparison on a canonical metric (the deterministic / classical path — the
"validate against a rule" half of the neuro-symbolic pattern). A detector that
fires on a record emits a Signal. This is intentionally classical + explainable:
the rule IS the explanation.
"""
from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any

from hodos_kernel.canonical import CanonicalRecord

_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt,
        "<=": operator.le, "==": operator.eq, "!=": operator.ne}


@dataclass
class Signal:
    entity_id: str
    group: str
    detector_id: str
    label: str
    severity: str          # high | medium | low
    evidence: str          # human-readable "why it fired"
    text: str = ""         # verbatim carried from the record (unedited)


def run_detectors(records: list[CanonicalRecord], detector_specs: list[dict[str, Any]]) -> list[Signal]:
    signals: list[Signal] = []
    for spec in detector_specs:
        metric = spec["metric"]
        op = _OPS[spec["op"]]
        threshold = spec["threshold"]
        for rec in records:
            if metric not in rec.metrics:
                continue
            val = rec.metrics[metric]
            if op(val, threshold):
                signals.append(Signal(
                    entity_id=rec.entity_id,
                    group=rec.group,
                    detector_id=spec["id"],
                    label=spec.get("label", spec["id"]),
                    severity=spec.get("severity", "low"),
                    evidence=f"{metric}={val:g} {spec['op']} {threshold:g}",
                    text=rec.text,
                ))
    return signals
