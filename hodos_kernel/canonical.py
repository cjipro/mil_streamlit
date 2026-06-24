"""
hodos_kernel.canonical — one schema the engine reasons over (HODOS-4 spike).

Raw rows from any adapter are mapped to a CanonicalRecord via the manifest's
`canonical:` block. This is what lets two completely different sources (journey
events vs telco accounts) flow through the SAME detectors/decision logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CanonicalRecord:
    entity_id: str                       # the unit (session, account, …)
    group: str                           # the grouping dim (journey, segment, …)
    metrics: dict[str, float] = field(default_factory=dict)
    dims: dict[str, Any] = field(default_factory=dict)
    text: str = ""                       # optional verbatim (never paraphrased)


def canonicalize(raw_rows: list[dict[str, Any]], mapping: dict[str, Any]) -> list[CanonicalRecord]:
    """Map raw source rows to CanonicalRecords using a manifest `canonical:` block:

        canonical:
          entity_id: session_id
          group: journey
          metrics: [dwell_ms, back_presses]
          dims: [screen, error_code]
          text: last_comment
    """
    ent_key = mapping["entity_id"]
    grp_key = mapping["group"]
    metric_keys = mapping.get("metrics", [])
    dim_keys = mapping.get("dims", [])
    text_key = mapping.get("text")

    out: list[CanonicalRecord] = []
    for r in raw_rows:
        metrics = {}
        for k in metric_keys:
            v = r.get(k)
            if v is not None:
                try:
                    metrics[k] = float(v)
                except (TypeError, ValueError):
                    pass
        out.append(CanonicalRecord(
            entity_id=str(r.get(ent_key, "")),
            group=str(r.get(grp_key, "")),
            metrics=metrics,
            dims={k: r.get(k) for k in dim_keys},
            text=str(r.get(text_key, "") or "") if text_key else "",
        ))
    return out
