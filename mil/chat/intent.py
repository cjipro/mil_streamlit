"""
mil/chat/intent.py — MIL-40.

Intent classification + retriever dispatch.

Every /ask query passes through classify() before any retrieval runs.
Haiku call via the `intent_classification` route; strict JSON output
with intent + confidence + extracted entities. Out-of-scope queries
(internal telemetry, PII, non-MIL) are caught here before the
retriever pool is touched.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Optional

from mil.config.model_client import call_anthropic
from mil.config.taxonomy_loader import (
    customer_journeys,
    issue_types,
    journey_map,
)

logger = logging.getLogger(__name__)

VALID_COMPETITORS = ("barclays", "natwest", "lloyds", "hsbc", "monzo", "revolut")
VALID_SOURCES = ("app_store", "google_play", "reddit", "youtube", "downdetector", "city_am")


class Intent(str, Enum):
    TREND = "trend"                  # "how has X moved over time"
    COMPARE = "compare"              # "X vs Y"
    ISSUE_LOOKUP = "issue_lookup"    # "current state of issue X"
    QUOTE_SEARCH = "quote_search"    # "show me reviews mentioning X"
    PEER_RANK = "peer_rank"          # "rank competitors on X"
    CHRONICLE = "chronicle"          # "what does CHRONICLE say about X"
    STATUS = "status"                # "do you have last N days?", "what sources?", "how many reviews?"

    OUT_OF_SCOPE = "out_of_scope"    # non-MIL / internal telemetry / PII
    INSUFFICIENT = "insufficient"    # query too vague to route
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    confidence: float
    entities: dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""


# ── System prompt (cached per scope) ──────────────────────────────────────

# Sonar-flavoured subject-policy block. Keeps the long-standing Barclays-
# default behaviour for the firm-specific product surface (Sonar / legacy
# /ask page).
_SUBJECT_POLICY_SONAR = (
    "BARCLAYS IS THE DEFAULT SUBJECT.\n"
    "The user's own bank is Barclays. Competitors exist only to contextualise\n"
    "Barclays performance. If a query does NOT explicitly name a competitor and\n"
    "does NOT clearly ask for peer/rank/compare, default entities.competitor to\n"
    "`barclays`. Examples:\n"
    '  "Which journey is regressing?"    → entities.competitor=barclays\n'
    '  "Any active P0 signals?"          → entities.competitor=barclays\n'
    '  "what\'s the current state?"       → entities.competitor=barclays\n'
    '  "daily sentiment chart"           → entities.competitor=barclays\n'
    "Use all-competitor scanning ONLY when the query explicitly asks for it:\n"
    '  "rank the banks", "compare", "peer", "which bank is worst", "all competitors".\n'
    "When defaulting, set `entities.competitor_default` to the string `implicit`\n"
    "so the system knows it was inferred (not stated by the user).\n\n"
)

# Reckoner-flavoured subject-policy block. Reckoner is industry-wide cohort
# intelligence — queries WITHOUT a named competitor are the norm, not a
# refusal trigger. Single-firm drill-ins are explicitly redirected to Sonar
# upstream by the pipeline scope guard, so we don't need the classifier to
# guard them too — the classifier just has to route them substantively.
_SUBJECT_POLICY_RECKONER = (
    "RECKONER IS COHORT-WIDE INDUSTRY INTELLIGENCE.\n"
    "Queries WITHOUT a named competitor are the NORM here — they're cohort-\n"
    "wide questions. Do NOT mark them insufficient. Do NOT default to any\n"
    "single firm. Route them as cross-cohort queries against the monitored\n"
    "competitor list. Examples:\n"
    '  "industry sentiment"              → peer_rank or trend (cohort-wide)\n'
    '  "which banks are seeing logins fail" → peer_rank, no competitor key\n'
    '  "current outage patterns"         → issue_lookup, no competitor key\n'
    '  "login crisis across the cohort"  → peer_rank or issue_lookup\n'
    '  "what is the worst journey"       → peer_rank, no competitor key\n'
    "If the user names a SINGLE competitor with no peer/cohort framing\n"
    "(e.g. \"how is barclays doing on logins\"), still classify it normally —\n"
    "an upstream scope guard will redirect them to Sonar. Don't refuse here.\n"
    "Use `insufficient` ONLY when the query carries NO classifiable signal at\n"
    "all — no issue type, no journey noun, no timeframe, no cohort framing,\n"
    "no severity, no chronicle reference. A bare two-word phrase like\n"
    "\"industry sentiment\" or \"cohort health\" IS classifiable — route to\n"
    "peer_rank or trend with default 7-day window.\n\n"
)


@lru_cache(maxsize=4)
def _system_prompt(scope: str = "all") -> str:
    issue_list = sorted(issue_types())
    journey_list = list(customer_journeys())
    journey_ids = sorted({v for v in journey_map().values() if v})

    subject_policy = (
        _SUBJECT_POLICY_RECKONER if scope == "reckoner" else _SUBJECT_POLICY_SONAR
    )

    return (
        "You are the intent classifier for Ask CJI Pro — a conversational layer over\n"
        "PUBLIC UK banking market signals (app reviews, DownDetector, City A.M., Reddit, YouTube).\n"
        "Monitored competitors: "
        + ", ".join(VALID_COMPETITORS)
        + ".\n"
        "Scope: no internal telemetry, no PII, no non-MIL questions.\n\n"
        "MIL VOCABULARY (all IN-SCOPE, never treat as telemetry):\n"
        "- severity classes: P0 (blocking), P1 (friction), P2 (minor)\n"
        "- 'signals' / 'findings' / 'signal cluster' — public-review-derived, scoped\n"
        "- 'churn risk', 'over-indexed', 'under-indexed', 'gap_pp', 'CAC'\n"
        "- CHR-XXX codes refer to the CHRONICLE ledger (public banking failures)\n"
        "- journey ids (J_LOGIN_01, J_PAY_01, J_SERVICE_01, J_ONBOARD_01)\n"
        "A bare 'any P0 signals?' / 'show me current findings' / 'what are the P1 issues?'\n"
        "is a valid issue_lookup or peer_rank query — default to the most recent\n"
        "window (7 days) and include all competitors unless the user named one.\n\n"
        "BIAS TOWARD ANSWERING (not refusing).\n"
        "If a query has a named competitor + a journey noun (login, payment, transfer,\n"
        "card, service, crash, support) it IS answerable — route to issue_lookup or\n"
        'peer_rank. Translate shorthand: "login score" / "payment score" / "crash score"\n'
        "= current severity + volume + rating for that journey; route to issue_lookup\n"
        "with the mapped issue_type. Do NOT refuse because the exact phrasing isn't\n"
        "MIL vocabulary — map it and route. Only use `insufficient` when the query has\n"
        "no competitor, no issue type, no journey noun, and no timeframe clue.\n\n"
        + subject_policy +
        "SEVERITY EXTRACTION (mandatory when present):\n"
        'If the user mentions P0 / P1 / P2 / "critical" / "blocking" / "severe",\n'
        'ALWAYS include `"severity": "P0"` (or P1 / P2) in entities. Without it,\n'
        "retrievers cannot filter by severity and will surface irrelevant reviews.\n"
        '"critical" and "blocking" → P0; "friction" / "significant" → P1; "minor" → P2.\n\n'
        "The `chronicle` intent is BROADER than the monitored-competitor list — the\n"
        "CHRONICLE is an immutable banking-failure ledger (TSB 2018, HSBC 2025,\n"
        "Lloyds 2025, and others). Any historical UK banking failure or migration\n"
        "is a valid chronicle query even if the bank is not actively monitored.\n\n"
        "## INTENTS (pick ONE)\n"
        "- trend          : change over time / trajectory\n"
        "- compare        : head-to-head between named competitors\n"
        "- issue_lookup   : state of a specific issue / journey\n"
        "- quote_search   : find verbatim reviews / customer voice\n"
        "- peer_rank      : rank competitors on some dimension\n"
        "- chronicle      : historical pattern / CHRONICLE entry lookup\n"
        "- status         : data coverage / freshness / system state. Examples:\n"
        "                   'do you have the last 20 days?', 'when was last update?',\n"
        "                   'which competitors do you track?', 'how many reviews?',\n"
        "                   'what sources?', 'what window do you cover?'\n"
        "- out_of_scope   : internal telemetry, PII, non-MIL — REFUSE\n"
        "- insufficient   : too vague to route\n"
        "- unknown        : cannot classify\n\n"
        "## ENTITIES (extract what the query contains, omit what it does not)\n"
        "- competitor      : one of " + json.dumps(list(VALID_COMPETITORS)) + "\n"
        "- competitors     : list when multiple are named\n"
        "- issue_type      : one of " + json.dumps(issue_list) + "\n"
        "- journey         : one of " + json.dumps(journey_list) + "\n"
        "- journey_id      : one of " + json.dumps(journey_ids) + "\n"
        "- source          : one of " + json.dumps(list(VALID_SOURCES)) + "\n"
        "- timeframe_days  : integer lookback in days ('last week' = 7, 'last month' = 30,\n"
        "                    'last 3 months' = 90, null for all-time).\n"
        "                    IMPORTANT: 'daily chart' / 'daily trend' / 'day-by-day'\n"
        "                    describes visual GRANULARITY, not window width. Never map\n"
        "                    'daily' to timeframe_days=1. If no window is stated,\n"
        "                    leave timeframe_days unset and let retrievers use their default.\n"
        "                    Minimum sensible window is 7 days.\n\n"
        "## OUTPUT CONTRACT\n"
        "Return ONE JSON object and nothing else. No prose, no markdown fences.\n"
        "Keys:\n"
        '  "intent"     (string from the INTENTS list)\n'
        '  "confidence" (float 0.0-1.0)\n'
        '  "entities"   (object, only keys that apply)\n'
        '  "reason"     (string, short, ONLY for out_of_scope / insufficient)\n'
    )


# ── Response parsing ──────────────────────────────────────────────────────

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[dict]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _coerce_intent(value: Any) -> Intent:
    try:
        return Intent(str(value))
    except (ValueError, TypeError):
        return Intent.UNKNOWN


def _normalise_entities(entities: dict) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (entities or {}).items():
        if value is None or value == "" or value == []:
            continue
        if key == "competitor" and isinstance(value, str):
            value = value.lower()
        elif key == "competitors" and isinstance(value, list):
            value = [v.lower() for v in value if isinstance(v, str)]
        elif key == "source" and isinstance(value, str):
            value = value.lower()
        out[key] = value
    return out


# ── Public API ────────────────────────────────────────────────────────────

# Deterministic safety net — keyword → journey/issue mapping for the override
# applied when the LLM classifier refuses a query that clearly has a named
# competitor + a journey noun. Lowercased match against the raw query.
_JOURNEY_KEYWORDS: dict[str, tuple[str, str, str]] = {
    # keyword           (journey_name,            journey_id,    issue_type)
    "login":            ("Log In to Account",     "J_LOGIN_01",  "Login Failed"),
    "log in":           ("Log In to Account",     "J_LOGIN_01",  "Login Failed"),
    "sign in":          ("Log In to Account",     "J_LOGIN_01",  "Login Failed"),
    "biometric":        ("Log In to Account",     "J_LOGIN_01",  "Biometric / Face ID Issue"),
    "face id":          ("Log In to Account",     "J_LOGIN_01",  "Biometric / Face ID Issue"),
    "account locked":   ("Log In to Account",     "J_LOGIN_01",  "Account Locked"),
    "locked out":       ("Log In to Account",     "J_LOGIN_01",  "Account Locked"),
    "payment":          ("Make a Payment",        "J_PAY_01",    "Payment Failed"),
    "transfer":         ("Transfer Money",        "J_PAY_01",    "Transfer Failed"),
    "balance":          ("Check Balance or Statement", "J_PAY_01", "Incorrect Balance"),
    "transaction":      ("Make a Payment",        "J_PAY_01",    "Missing Transaction"),
    "crash":            ("General App Use",       "J_SERVICE_01","App Crashing"),
    "not opening":      ("General App Use",       "J_SERVICE_01","App Not Opening"),
    "won't open":       ("General App Use",       "J_SERVICE_01","App Not Opening"),
    "slow":             ("General App Use",       "J_SERVICE_01","Slow Performance"),
    "card":             ("Manage Card",           "J_SERVICE_01","Card Frozen or Blocked"),
    "support":          ("Get Support",           "J_SERVICE_01","Customer Support Failure"),
    "notification":     ("General App Use",       "J_SERVICE_01","Notification Issue"),
}


_DEFAULT_COMPETITOR = "barclays"

# Scope tags. "all"/"sonar" use the existing Barclays-default behaviour
# (sonar is the firm-specific product). "reckoner" disables the default
# because Reckoner is cohort-wide industry intelligence.
VALID_SCOPES = ("all", "sonar", "reckoner")

# Queries that genuinely want cross-competitor analysis — these phrases mean
# "don't default to Barclays". Anything else defaults to Barclays.
_PEER_HINTS = (
    "rank", "compare", "comparison", "peer", "peers", "competitors",
    "other banks", "which bank", "which banks", "all banks",
    "vs ", " vs.", "versus", "across the",
)


def _wants_peer_view(query_lc: str) -> bool:
    return any(h in query_lc for h in _PEER_HINTS)


def _keyword_override(query: str, entities: dict) -> Optional[dict]:
    """
    Deterministic backup. Two triggers:
      1) query mentions a journey noun + has a clear competitor OR wants Barclays default
      2) query refused by the LLM but mentions any journey/issue domain word — default to
         Barclays and route to issue_lookup so retrievers get a chance.

    Returns a merged-entity dict when either trigger fires, else None.
    """
    q = query.lower()

    # Pick competitor: explicit > Barclays default (unless the query asks for a peer view)
    comp_found: Optional[str] = None
    for c in VALID_COMPETITORS:
        if c in q:
            comp_found = c
            break
    if not comp_found:
        if _wants_peer_view(q):
            comp_found = None   # leave unset so retrievers scan all peers
        else:
            comp_found = _DEFAULT_COMPETITOR

    # Try to find a journey keyword
    for keyword, (journey, journey_id, issue_type) in _JOURNEY_KEYWORDS.items():
        if keyword in q:
            out = {
                "journey":     journey,
                "journey_id":  journey_id,
                "issue_type":  issue_type,
                "timeframe_days": 7,
                "_override":   f"keyword:{keyword}",
                **{k: v for k, v in entities.items() if k not in
                   ("journey", "journey_id", "issue_type", "timeframe_days")},
            }
            if comp_found:
                out["competitor"] = comp_found
                if comp_found == _DEFAULT_COMPETITOR and _DEFAULT_COMPETITOR not in q:
                    out["competitor_default"] = "implicit"
            return out

    # No journey keyword but the query is about "regression" / "trend" /
    # "state" / "findings" / "signals" — treat as an issue_lookup request
    # against the default competitor.
    domain_hints = ("regress", "trend", "findings", "signal", "p0", "p1",
                    "current state", "what's happening", "score", "health")
    if any(h in q for h in domain_hints):
        out = {
            "timeframe_days": 7,
            "_override": "domain_hint",
            **{k: v for k, v in entities.items() if k not in ("timeframe_days",)},
        }
        if comp_found:
            out["competitor"] = comp_found
            if comp_found == _DEFAULT_COMPETITOR and _DEFAULT_COMPETITOR not in q:
                out["competitor_default"] = "implicit"
        return out

    return None


def classify(query: str, scope: str = "all") -> IntentResult:
    """Classify a user query. Returns an IntentResult with extracted entities.

    Args:
        query: user question
        scope: "all" / "sonar" / "reckoner". Sonar/all keep the Barclays
               default-competitor injection. Reckoner disables it (cohort
               intelligence — no single firm is the implicit subject).
    """
    raw = call_anthropic(
        task="intent_classification",
        user_prompt=query,
        system=_system_prompt(scope),
        max_tokens=256,
    )
    payload = _extract_json(raw)
    if payload is None:
        logger.warning("[intent] could not parse JSON — %r", raw[:200])
        payload = {}

    entities = _normalise_entities(payload.get("entities") or {})
    if payload.get("reason"):
        entities["reason"] = payload["reason"]

    intent = _coerce_intent(payload.get("intent"))

    # Safety net: the LLM refused but the query is clearly answerable. Force
    # issue_lookup so the retrievers get a chance to find something.
    # Skip under Reckoner scope — the safety net's Barclays-default would
    # contradict the cohort-wide framing.
    if scope != "reckoner" and intent in (Intent.INSUFFICIENT, Intent.UNKNOWN):
        override = _keyword_override(query, entities)
        if override is not None:
            logger.info("[intent] keyword override fired for %r: %s",
                        query, override.get("_override"))
            return IntentResult(
                intent=Intent.ISSUE_LOOKUP,
                confidence=0.70,
                entities=override,
                raw_response=raw,
            )

    # Barclays default: if the LLM classified successfully but left competitor
    # unset, inject Barclays unless the query explicitly asked for a peer view.
    # Peer intents (COMPARE, PEER_RANK) are always cross-competitor by design.
    # Reckoner scope skips this entirely — its product surface is cohort-
    # wide and has no implicit firm subject.
    needs_default_comp = (
        scope != "reckoner"
        and intent not in (Intent.COMPARE, Intent.PEER_RANK,
                           Intent.INSUFFICIENT, Intent.OUT_OF_SCOPE, Intent.UNKNOWN)
        and not entities.get("competitor")
        and not entities.get("competitors")
        and not _wants_peer_view(query.lower())
    )
    if needs_default_comp:
        entities["competitor"] = _DEFAULT_COMPETITOR
        entities["competitor_default"] = "implicit"
        logger.info("[intent] injected default competitor=barclays for %r", query)

    return IntentResult(
        intent=intent,
        confidence=float(payload.get("confidence") or 0.0),
        entities=entities,
        raw_response=raw,
    )


# ── Retriever dispatch ────────────────────────────────────────────────────
# Ordered retriever chain per intent. First retriever is primary; additional
# retrievers fold their evidence into the same bundle before synthesis.
# Refusal intents return empty — synthesis layer short-circuits to a refusal.

_DISPATCH: dict[Intent, tuple[str, ...]] = {
    Intent.TREND:        ("sql",),
    Intent.COMPARE:      ("sql", "structured"),
    Intent.ISSUE_LOOKUP: ("structured", "bm25"),
    Intent.QUOTE_SEARCH: ("bm25", "embedding"),
    Intent.PEER_RANK:    ("sql",),
    Intent.CHRONICLE:    ("embedding", "structured"),
    Intent.STATUS:       ("status",),
}


def dispatch_plan(intent: Intent) -> list[str]:
    """Return ordered retriever names for the given intent. Empty for refusals."""
    return list(_DISPATCH.get(intent, ()))


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Ask CJI Pro intent classifier — smoke test")
    parser.add_argument("query", help="User query to classify")
    args = parser.parse_args()

    result = classify(args.query)
    print(f"intent:     {result.intent.value}")
    print(f"confidence: {result.confidence:.2f}")
    print(f"entities:   {json.dumps(result.entities, indent=2)}")
    print(f"retrievers: {dispatch_plan(result.intent)}")
