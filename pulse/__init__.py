"""Pulse engine — canonical decision-intelligence runtime.

Lives in cjipro/holter (build codename Holter, after Norman Holter — inventor
of the wearable continuous ECG monitor, 1949). The Python package identity
stays `pulse` so engine imports survive any future repo moves.

v1 design spine landed 2026-05-17:
- PULSE-87 schema/ + adapters/ + contracts/  (canonical event schema)
- PULSE-88 frictionbench/                    (public benchmark spec)
- PULSE-89 lineage/ + synthesis/             (audit chain + provider interface)
         + decision_packs/ + convergence/   (pack metadata + fairness methods)
         + audit/                            (audit query interface spec)
- PULSE-90 cjipro/holter scaffolded          (codename + repo)
- PULSE-91 pulse/ tree migrated from cjipro/mil_streamlit

tests/ — round-trip, deny-list, lineage chain, synthesis interface,
         decision-pack validator, FrictionBench scoring + submission manifest
"""

__version__ = "0.1.0"
