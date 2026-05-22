"""Three-altitude single-surface design (Bank / Journey / Signal).

Per HOL-1 lock (2026-05-17). Same investigation, multiple renderings;
no role-gated screens. Rendering is the variable; investigation is the
invariant.
"""

from __future__ import annotations

from enum import Enum


class Altitude(str, Enum):
    """The three altitudes of the canonical single-surface design.

    - BANK    — executive headline, cohort-wide patterns. Maximum compression.
    - JOURNEY — specific journey friction, screen sequence. Default altitude.
    - SIGNAL  — individual event, anomaly detail. Maximum expansion.

    Any altitude can answer any question; the CEO's headline is the same
    investigation as the analyst's full panel, just compressed.
    """

    BANK = "Bank"
    JOURNEY = "Journey"
    SIGNAL = "Signal"
