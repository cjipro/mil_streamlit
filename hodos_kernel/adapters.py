"""
hodos_kernel.adapters — "ingest from anywhere" boundary (HODOS-4 spike).

A SourceAdapter is the single, thin, versioned boundary between the engine and
any data source — the pattern the research flagged (MCP "USB-C for data";
per-source auth/schema → unified interface). A new source = a new adapter; the
kernel never knows where data came from.

Each adapter emits RAW source-shaped dicts (deliberately different shapes per
adapter, to prove the canonicaliser does real schema conversion). Two synthetic
adapters here; a production adapter would wrap an API / DB / MCP server behind
the same `fetch()` contract.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any

ADAPTER_CONTRACT_VERSION = "0.1"


class SourceAdapter(ABC):
    """The whole boundary. Implement fetch(); return raw source-shaped rows."""
    name: str = "source"

    @abstractmethod
    def fetch(self) -> list[dict[str, Any]]:
        ...


# --------------------------------------------------------------------------
# Synthetic adapter 1 — journey telemetry (Pulse-like). Row shape: events.
# --------------------------------------------------------------------------

class SyntheticJourneyEvents(SourceAdapter):
    name = "synthetic_journey_events"

    def __init__(self, n: int = 600, seed: int = 42):
        self.n, self.seed = n, seed

    def fetch(self) -> list[dict[str, Any]]:
        rng = random.Random(self.seed)
        journeys = [
            ("loans.apply.step3", 0.42),          # high-friction by design
            ("international.beneficiary.setup", 0.30),
            ("cards.credit.apply.eligibility", 0.18),
            ("payments.domestic.transfer", 0.05),  # healthy
            ("login.biometric", 0.04),
        ]
        errors = ["", "", "", "ERR_TIMEOUT", "ERR_VALIDATION", "ERR_5XX"]
        comments = [
            "Kept timing out on the last step, gave up.",
            "Why does it keep throwing me back?",
            "Couldn't add the payee, app froze.",
            "Smooth, no issues.",
            "",
        ]
        rows = []
        for i in range(self.n):
            j, p = rng.choices(journeys, weights=[1, 1, 1, 1, 1])[0]
            frictional = rng.random() < p
            rows.append({
                "session_id": f"s{i:05d}",
                "journey": j,
                "screen": j.split(".")[-1],
                "dwell_ms": int(rng.gauss(30000 if frictional else 6000, 4000)),
                "back_presses": rng.choice([3, 4, 5]) if frictional else rng.choice([0, 0, 1]),
                "error_code": rng.choice(errors[3:]) if frictional else rng.choice(errors),
                "last_comment": rng.choice(comments[:3]) if frictional else rng.choice(comments[3:]),
            })
        return rows


# --------------------------------------------------------------------------
# Synthetic adapter 2 — account snapshots (telco-churn). DIFFERENT row shape.
# --------------------------------------------------------------------------

class SyntheticTelcoAccounts(SourceAdapter):
    name = "synthetic_telco_accounts"

    def __init__(self, n: int = 500, seed: int = 7):
        self.n, self.seed = n, seed

    def fetch(self) -> list[dict[str, Any]]:
        rng = random.Random(self.seed)
        segments = [
            ("fibre_premium", 0.10),
            ("mobile_payg", 0.46),                 # high-churn by design
            ("bundle_family", 0.22),
            ("business_sme", 0.12),
        ]
        gripes = [
            "Bill went up again with no warning.",
            "Signal drops every evening.",
            "Spent an hour on hold to cancel.",
            "Happy enough for now.",
            "",
        ]
        rows = []
        for i in range(self.n):
            seg, p = rng.choices(segments, weights=[1, 1, 1, 1])[0]
            churny = rng.random() < p
            rows.append({
                "account_ref": f"a{i:05d}",
                "segment": seg,
                "support_tickets_90d": rng.choice([3, 4, 6]) if churny else rng.choice([0, 1]),
                "nps": rng.choice([-100, -50, 0]) if churny else rng.choice([20, 50, 80]),
                "tenure_months": rng.randint(1, 8) if churny else rng.randint(12, 96),
                "verbatim": rng.choice(gripes[:3]) if churny else rng.choice(gripes[3:]),
            })
        return rows


_REGISTRY = {a.name: a for a in (SyntheticJourneyEvents, SyntheticTelcoAccounts)}


def get_adapter(name: str, **config) -> SourceAdapter:
    if name not in _REGISTRY:
        raise KeyError(f"unknown adapter '{name}' — registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name](**config)
