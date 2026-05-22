"""Pulse convergence + fairness method registry.

Investigations flagged `convergence_required: true` must hit at least one
fairness-aware method alongside statistical-power methods. See
CONVERGENCE_DESIGN.md.

Filed under PULSE-89.
"""

from pulse.convergence.fairness import FairnessResult, assess_fairness, chi_squared_2x2

__all__ = ["FairnessResult", "assess_fairness", "chi_squared_2x2"]
