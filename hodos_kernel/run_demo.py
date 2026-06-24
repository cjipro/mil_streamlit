"""
hodos_kernel.run_demo — prove the thesis (HODOS-4 spike).

Runs BOTH products through the SAME kernel in BOTH runtimes (4 runs), writes
the Holter-style HTML for each, and prints a summary showing:
  • two different products fall out of two manifests + one engine
  • the deterministic and llm runtimes produce the SAME decisions (verdicts +
    scores), differing only in narrative — the governance property.

Run:  py -m hodos_kernel.run_demo
"""
from __future__ import annotations

from pathlib import Path

from hodos_kernel.kernel import run, run_to_file

_HERE = Path(__file__).parent
_PRODUCTS = [_HERE / "products" / "pulse_friction.yaml",
             _HERE / "products" / "telco_churn.yaml"]
_OUT = _HERE / "output"


def main() -> None:
    print("=" * 72)
    print("  HODOS KERNEL SPIKE — one engine, many decision products")
    print("=" * 72)
    for manifest in _PRODUCTS:
        det = run_to_file(manifest, "deterministic", _OUT)
        llm = run_to_file(manifest, "llm", _OUT)

        # The governance check: decisions identical across runtimes.
        det_core = [d.core() for d in det.decisions]
        llm_core = [d.core() for d in llm.decisions]
        runtime_independent = det_core == llm_core

        print(f"\n▶ {det.product}")
        print(f"   records={det.records}  signals={det.signals}  "
              f"decisions={len(det.decisions)}  verdicts={det.verdict_counts()}")
        print(f"   lineage verified: {det.log.verify()}  "
              f"head={det.log.rows[-1]['row_hash'][:12] if det.log.rows else '—'}")
        print(f"   runtime-independent decisions (det == llm): {runtime_independent}")
        top = det.decisions[0]
        print(f"   top decision: [{top.verdict}] {top.subject} (score {top.score:g})")
        print(f"     deterministic ▸ {det.decisions[0].narrative}")
        print(f"     llm           ▸ {llm.decisions[0].narrative}")
        print(f"   surfaces: {Path(det.html_path).name}, {Path(llm.html_path).name}")

    print(f"\nHTML written to {_OUT}")
    print("Same kernel.run() produced both products. Manifest = the product.")


if __name__ == "__main__":
    main()
