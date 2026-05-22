"""Pulse data pipeline — MA_D (raw canonical events) → MA_S (sessionised) → marts.

DuckDB + PyArrow, single-node, Python 3.11 (PySpark rejected under the bank lock).
MA_S is the session-grain fact layer; surfaces never read it directly — they read
pre-aggregated per-box marts built from it (see pulse/serving/).

Owned by while-sleeping (PULSE-34 sessionisation; engine relocated under PULSE-128).
"""
