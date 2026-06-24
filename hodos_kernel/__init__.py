"""
hodos_kernel — SPIKE (HODOS-4).

A throwaway-able prototype of the Hodos platform thesis: ONE engine that
manufactures DECISION products from a declarative `product.yaml` manifest.
A product (Pulse, Sonar, telco-churn, …) is config, not a bespoke codebase.

Pipeline:  sources(adapters) → canonical → detectors → decisions → synthesis → surface
with a hash-chained DecisionLog threaded through (lineage by design).

Isolated: does NOT import from or touch live `mil/` or `pulse/`. See README.md.
"""
