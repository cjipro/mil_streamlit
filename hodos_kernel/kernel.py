"""
hodos_kernel.kernel — the engine (HODOS-4 spike).

run(manifest, runtime) wires the product-agnostic pipeline:

    sources(adapters) → canonicalize → detectors → decide → synthesize(runtime)
                      → DecisionLog (hash-chain) → surface (HTML)

The SAME function produces Pulse-like friction OR telco-churn — the only thing
that changes is the manifest. `runtime` selects deterministic vs llm synthesis
WITHOUT changing the decisions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hodos_kernel.adapters import get_adapter
from hodos_kernel.canonical import CanonicalRecord, canonicalize
from hodos_kernel.decision import Decision, DecisionLog, decide
from hodos_kernel.detectors import Signal, run_detectors
from hodos_kernel.manifest import load_manifest
from hodos_kernel.surface import render
from hodos_kernel.synthesis import get_provider


@dataclass
class ProductRun:
    product: str
    runtime: str
    records: int
    signals: int
    decisions: list[Decision]
    log: DecisionLog
    html: str
    title: str = ""

    def verdict_counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for d in self.decisions:
            c[d.verdict] = c.get(d.verdict, 0) + 1
        return c


def run(manifest: dict[str, Any] | str | Path, runtime: str = "deterministic") -> ProductRun:
    m = manifest if isinstance(manifest, dict) else load_manifest(manifest)
    product = m["product"]

    # 1. ingest from every declared source (adapter boundary)
    raw: list[dict] = []
    for src in m["sources"]:
        raw.extend(get_adapter(src["adapter"], **(src.get("config") or {})).fetch())

    # 2. canonicalize → one schema
    records: list[CanonicalRecord] = canonicalize(raw, m["canonical"])

    # 3. detect (deterministic, declarative)
    signals: list[Signal] = run_detectors(records, m["detectors"])

    # 4. decide (deterministic — runtime-independent)
    decisions = decide(product, signals, m["decision"])

    # 5. synthesize narrative (selectable runtime — explanation only)
    get_provider(runtime).apply(decisions, m.get("synthesis", {}))

    # 6. lineage: hash-chain the decisions
    log = DecisionLog()
    for d in decisions:
        log.append(d)

    # 7. surface
    title = m["surface"].get("title", product)
    html = render(title, runtime, decisions, log, m["surface"])

    return ProductRun(product=product, runtime=runtime, records=len(records),
                      signals=len(signals), decisions=decisions, log=log,
                      html=html, title=title)


def run_to_file(manifest_path: str | Path, runtime: str, out_dir: str | Path) -> ProductRun:
    pr = run(manifest_path, runtime)
    out = Path(out_dir) / f"{pr.product}__{runtime}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pr.html, encoding="utf-8")
    pr.html_path = str(out)  # type: ignore[attr-defined]
    return pr
