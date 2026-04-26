"""
mil/chat/refusals.py — MIL-43.

Refusal taxonomy + logic-probe scope enforcement.

Two guardrails:
  1. LLM classifier catches most out-of-scope queries upstream (intent.py).
  2. check_logic_probe() is a second, regex-based guardrail — cheap, local,
     deterministic. It runs even when the classifier says out_of_scope,
     so a compromised / jailbroken classifier response cannot bypass scope.

LOGIC_PROBE is the Zero-Entanglement mirror at the conversational layer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RefusalClass(str, Enum):
    LOGIC_PROBE = "logic_probe"
    PII = "pii"
    OUT_OF_SCOPE = "out_of_scope"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    FABRICATION_GUARD = "fabrication_guard"
    SCOPE_MISMATCH = "scope_mismatch"


@dataclass(frozen=True)
class Refusal:
    reason_class: RefusalClass
    message: str
    query: str


# ── Logic probe patterns ──────────────────────────────────────────────────
# Internal-telemetry / session-state / product-funnel phrasing. Covers the
# common jailbreak wordings ("our customers", "my data"). All patterns are
# lowercased at match time.

_LOGIC_PROBE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(our|my|internal|taq)\s+customers?\b"),
    re.compile(r"\b(our|my|internal|taq)\s+(data|users?|clients?|sessions?)\b"),
    re.compile(r"\bstep\s+\d+\s+of\b"),
    re.compile(r"\binternal\s+(telemetry|analytics|data|system|kpi|metric)s?\b"),
    re.compile(r"\bsession\s+(state|data|id|token)\b"),
    re.compile(r"\bproduct\s+(roadmap|backlog|strategy|plan)\b"),
    re.compile(r"\bvulnerab(le|ility)\s+(customer|user|cohort|segment)"),
    re.compile(r"\b(who|which)\s+(customer|user|individual)"),
    re.compile(r"\bhmac|pii|personal\s+data\b"),
)


_PII_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b([A-Z][a-z]+\s+){2,3}\b"),          # three+ capitalised words in a row
    re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"),  # email
    re.compile(r"\b(?:\+?44|0)\s?7\d{3}\s?\d{6}\b"),   # UK mobile
    re.compile(r"\baccount\s+(?:number|#)\s*\d+"),
)


# ── User-facing refusal messages ──────────────────────────────────────────

_MESSAGES: dict[RefusalClass, str] = {
    RefusalClass.LOGIC_PROBE: (
        "Ask CJI Pro covers PUBLIC UK banking market signals only — app reviews, "
        "DownDetector, City A.M., Reddit, and YouTube. Internal telemetry, session "
        "state, and product funnels are out of scope."
    ),
    RefusalClass.PII: (
        "Ask CJI Pro doesn't answer questions about specific named individuals. "
        "Try a cohort-level question instead — e.g. 'what do Barclays customers "
        "report about login issues'."
    ),
    RefusalClass.OUT_OF_SCOPE: (
        "That sits outside Ask CJI Pro's remit. We monitor public market signals "
        "for Barclays, NatWest, Lloyds, HSBC, Monzo, and Revolut."
    ),
    RefusalClass.INSUFFICIENT_EVIDENCE: (
        "I couldn't find evidence in the vault to answer that. Try narrowing by "
        "competitor, issue type, or timeframe."
    ),
    RefusalClass.FABRICATION_GUARD: (
        "The verifier flagged the draft answer as unverifiable against the "
        "retrieved evidence. No answer returned."
    ),
    RefusalClass.SCOPE_MISMATCH: (
        "Reckoner answers cohort-wide pattern questions across UK retail banking — "
        "not single-firm drill-ins. For firm-specific questions (e.g. \"how is "
        "Barclays doing on logins\"), use Sonar instead. For cross-cohort questions "
        "(e.g. \"which banks are seeing biometric retry loops\"), keep going here."
    ),
}


# ── Reckoner scope guard ──────────────────────────────────────────────────
# Reckoner is industry intelligence — cohort-wide patterns. Single-firm
# drill-ins belong in Sonar. This deterministic guard runs after intent
# classification: if the query named exactly one competitor and didn't
# carry peer/cohort framing, refuse with SCOPE_MISMATCH.

_PEER_FRAMING_TERMS: tuple[str, ...] = (
    "rank", "compare", "comparison", "peer", "peers", "competitors",
    "other banks", "which bank", "which banks", "all banks",
    "vs ", " vs.", "versus", "across", "cohort", "industry",
    "uk banking", "uk retail banking", "sector",
)


def is_firm_specific_for_reckoner(query: str, entities: dict) -> bool:
    """
    True when a query under reckoner scope is asking about exactly one firm
    without any cohort/peer framing — i.e. it belongs in Sonar, not Reckoner.

    Uses the user's literal text rather than entities.competitor, because the
    intent layer's Barclays-default would mark every implicit-Barclays query
    as firm-specific even though the user never named anyone.
    """
    q = (query or "").lower()
    competitors = ("barclays", "natwest", "lloyds", "hsbc", "monzo", "revolut")
    named = [c for c in competitors if c in q]
    if len(named) != 1:
        return False
    if any(term in q for term in _PEER_FRAMING_TERMS):
        return False
    # Chronicle queries are explicitly cross-firm even when one bank is named
    # (e.g. "what does CHRONICLE say about TSB's 2018 outage").
    if "chronicle" in q or "chr-" in q:
        return False
    return True


# ── Public API ────────────────────────────────────────────────────────────

def check_logic_probe(query: str) -> bool:
    """Return True if query attempts internal-telemetry / session / product inference."""
    q = query.lower()
    return any(p.search(q) for p in _LOGIC_PROBE_PATTERNS)


def check_pii(query: str) -> bool:
    """Return True if query looks like it names an individual or carries PII."""
    return any(p.search(query) for p in _PII_PATTERNS)


def build_refusal(reason: RefusalClass, query: str, detail: str = "") -> Refusal:
    """Construct a user-facing refusal. `detail` is appended after the base message."""
    message = _MESSAGES.get(reason, "Query refused.")
    if detail:
        message = f"{message} {detail}"
    return Refusal(reason_class=reason, message=message, query=query)
