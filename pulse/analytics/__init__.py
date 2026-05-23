"""Pulse analytics layer (PULSE-96).

Produces `AnalyticOutputs` — the investigation-grain inputs the synthesis layer
(PULSE-93/94) renders into a brief. v1 implements the **Cause** question class
(`pulse.analytics.cause`); the other six question classes are v2.
"""

from __future__ import annotations

from pulse.analytics.cause import build_analytic_outputs

__all__ = ["build_analytic_outputs"]
