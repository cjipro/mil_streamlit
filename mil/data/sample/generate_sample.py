"""mil/data/sample/generate_sample.py — MIL-123 frozen sample corpus generator.

Emits a deterministic 100-record enriched corpus across six retail-banking
subjects + two store sources. The output is wholly synthetic: fictional
usernames, generic review content, and a deliberate severity / issue-type
distribution so a fork can run inference + benchmark + publish end-to-end
without first fetching live data or hitting a live LLM for enrichment.

How a fork uses this:
    1. cp mil/data/sample/*.json mil/data/historical/enriched/
    2. py run_daily.py --skip-fetch
       (skips fetch + enrich, runs inference + benchmark + publish)

Re-generating:
    py mil/data/sample/generate_sample.py
    Fixed seed = byte-stable output across runs.

The generator is committed alongside the JSON output so a fork can edit
the generator (different cohort, different issue types) and re-emit. The
JSON is the source of truth for run_daily.py — the generator exists for
maintainability.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Fixed seed → byte-stable output. Bumping is a deliberate change.
SEED = 20260430

OUTPUT_DIR = Path(__file__).parent

# Subjects: 6 UK retail banking apps (cjipro.com cohort).
# A fork retargeting to a different cohort edits this list.
SUBJECTS = ["barclays", "natwest", "lloyds", "hsbc", "monzo", "revolut"]

# Records per (source, subject). 12 stores × ~8 records = ~96, padded to 100.
# Distribution heavy on Barclays (the default subject in tenant.yaml) so
# Box 1/2/3 have something to render; lighter on peers.
RECORDS_PER_FILE = {
    "barclays": 14,
    "natwest":  10,
    "lloyds":    8,
    "hsbc":      6,
    "monzo":     6,
    "revolut":   6,
}
# Total = (14+10+8+6+6+6) × 2 sources = 100 records.

# Issue types lifted from mil/config/domain_taxonomy.yaml. The generator
# does NOT import the loader — we want the sample frozen even if taxonomy
# evolves. If taxonomy drifts, regen this file.
ISSUE_TYPES = [
    ("App Crashing",         "P0", -0.9, "App crashed unexpectedly during use."),
    ("Login Failed",         "P0", -0.9, "Could not sign in despite correct credentials."),
    ("Payment Failed",       "P0", -0.8, "Payment did not go through and money was held."),
    ("Account Locked",       "P0", -0.8, "Account locked with no clear reason or recovery path."),
    ("App Not Opening",      "P0", -0.9, "App refuses to open after the latest update."),
    ("Transfer Failed",      "P0", -0.7, "Transfer to another account failed silently."),
    ("Slow Performance",     "P1", -0.5, "App takes a long time to load each screen."),
    ("Feature Broken",       "P1", -0.5, "A specific feature stopped working after the update."),
    ("Customer Service",     "P1", -0.6, "Could not reach a human agent for a real problem."),
    ("Notification Issue",   "P2", -0.3, "Push notifications arrive late or not at all."),
    ("Biometric / Face ID",  "P1", -0.5, "Biometric login fails repeatedly."),
    ("Incorrect Balance",    "P0", -0.7, "Displayed balance does not match actual balance."),
    ("Missing Transaction",  "P0", -0.7, "A recent transaction is missing from the feed."),
    ("UI Confusing",         "P2", -0.2, "Recent UI redesign is confusing to navigate."),
    ("Positive Feedback",    "P2",  0.8, "Generally pleased with the app — works well."),
    ("Other",                "P2", -0.1, "Mixed feedback covering several minor topics."),
]

JOURNEYS_BY_ISSUE = {
    "App Crashing":         "General App Use",
    "App Not Opening":      "General App Use",
    "Login Failed":         "Login",
    "Biometric / Face ID":  "Login",
    "Account Locked":       "Account Service",
    "Customer Service":     "Account Service",
    "Payment Failed":       "Payments",
    "Transfer Failed":      "Payments",
    "Incorrect Balance":    "Payments",
    "Missing Transaction":  "Payments",
    "Slow Performance":     "General App Use",
    "Feature Broken":       "General App Use",
    "Notification Issue":   "General App Use",
    "UI Confusing":         "General App Use",
    "Positive Feedback":    "General App Use",
    "Other":                "General App Use",
}

# Synthetic review templates per issue type. Generic enough to be plausible
# but never lifted from real customer reviews — the sample corpus is
# wholly fabricated.
REVIEW_TEMPLATES = {
    "App Crashing":        ["Keeps crashing when I open it.", "Crashes every time I tap the home screen.", "App freezes and dies on launch."],
    "Login Failed":        ["Cannot sign in with my correct password.", "Login screen rejects my credentials repeatedly.", "Stuck on the login screen for days."],
    "Payment Failed":      ["Payment failed but the money was still taken.", "Cannot make any payments since the update.", "Tried three times to pay a bill — all failed."],
    "Account Locked":      ["Account locked with no reason given.", "Locked out and the recovery flow does not work.", "Account suspended without warning."],
    "App Not Opening":     ["App will not open at all after the update.", "Click the icon and nothing happens.", "Stuck on the splash screen forever."],
    "Transfer Failed":     ["Transfer to another bank failed silently.", "Money disappeared during a transfer.", "Cannot send money to anyone any more."],
    "Slow Performance":    ["Takes forever to load every screen.", "App is painfully slow to use.", "Each tap takes seconds to register."],
    "Feature Broken":      ["The savings feature stopped working.", "Statements feature is broken since the update.", "Direct debits screen is empty now."],
    "Customer Service":    ["Cannot reach a real person to fix this.", "Bot keeps looping me back to the same menu.", "Three days waiting for a callback."],
    "Notification Issue":  ["Notifications arrive hours late.", "Stopped getting payment alerts.", "Push notifications never come through."],
    "Biometric / Face ID": ["Face ID stopped working on this app.", "Fingerprint login fails every time.", "Biometric setup loop never completes."],
    "Incorrect Balance":   ["Balance shows wrong amount.", "Available balance does not match my actual money.", "Displayed total is hundreds off."],
    "Missing Transaction": ["A transaction from yesterday is missing.", "Recent payment is not showing.", "Transactions feed is incomplete."],
    "UI Confusing":        ["Cannot find the simple options any more.", "Everything is buried under three menus.", "Redesign made things worse."],
    "Positive Feedback":   ["Works really well, no complaints.", "Smooth and reliable for everyday banking.", "Best banking app I have used."],
    "Other":               ["A few small issues but mostly fine.", "Some good, some annoying.", "Mixed feelings about the recent changes."],
}

# Synthetic author/userName fields. Index appended to keep them unique.
SYNTHETIC_HANDLES = [
    "Sample User", "Anon Reviewer", "Banking Test", "Mobile Tester",
    "App Reviewer", "Frequent User", "Daily Banker", "Sample Customer",
]


def _date_range(n: int) -> list[str]:
    """Generate n dates spread across the last 14 days, deterministic."""
    today = datetime(2026, 4, 30, tzinfo=timezone.utc)
    return [
        (today - timedelta(days=i % 14, hours=(i * 7) % 24, minutes=(i * 13) % 60)).isoformat()
        for i in range(n)
    ]


def _make_app_store_records(subject: str, n: int, rng: random.Random) -> list[dict]:
    dates = _date_range(n)
    records: list[dict] = []
    for i in range(n):
        issue, severity, sentiment, reasoning = rng.choice(ISSUE_TYPES)
        review_text = rng.choice(REVIEW_TEMPLATES[issue])
        rating = 5 if issue == "Positive Feedback" else rng.choice([1, 1, 2, 2, 3])
        records.append({
            "rating": rating,
            "title": f"Review {i+1:03d}",
            "review": review_text,
            "version": "8.20.1",
            "date": dates[i],
            "author": f"{rng.choice(SYNTHETIC_HANDLES)} {i:03d}",
            "issue_type": issue,
            "customer_journey": JOURNEYS_BY_ISSUE[issue],
            "sentiment_score": sentiment,
            "severity_class": severity,
            "reasoning": reasoning,
        })
    return records


def _make_google_play_records(subject: str, n: int, rng: random.Random) -> list[dict]:
    dates = _date_range(n)
    records: list[dict] = []
    for i in range(n):
        issue, severity, sentiment, reasoning = rng.choice(ISSUE_TYPES)
        review_text = rng.choice(REVIEW_TEMPLATES[issue])
        rating = 5 if issue == "Positive Feedback" else rng.choice([1, 1, 2, 2, 3])
        records.append({
            "rating": rating,
            "content": review_text,
            "at": dates[i].replace("+00:00", "").rstrip("Z"),
            "userName": f"{rng.choice(SYNTHETIC_HANDLES)} {i:03d}",
            "thumbsUpCount": rng.randint(0, 3),
            "reviewCreatedVersion": "8.20.1",
            "issue_type": issue,
            "customer_journey": JOURNEYS_BY_ISSUE[issue],
            "sentiment_score": sentiment,
            "severity_class": severity,
            "reasoning": reasoning,
        })
    return records


def _wrap(source: str, subject: str, records: list[dict]) -> dict:
    return {
        "source": source,
        "competitor": subject,
        "enriched_count": len(records),
        "model": "sample-corpus-v1",
        "schema_version": "v3",
        "records": records,
    }


def main() -> None:
    rng = random.Random(SEED)
    total = 0
    for subject, n in RECORDS_PER_FILE.items():
        # App Store
        recs = _make_app_store_records(subject, n, rng)
        out_path = OUTPUT_DIR / f"app_store_{subject}_enriched.json"
        out_path.write_text(json.dumps(_wrap("app_store", subject, recs), indent=2), encoding="utf-8")
        total += n

        # Google Play
        recs = _make_google_play_records(subject, n, rng)
        out_path = OUTPUT_DIR / f"google_play_{subject}_enriched.json"
        out_path.write_text(json.dumps(_wrap("google_play", subject, recs), indent=2), encoding="utf-8")
        total += n

    print(f"[sample] wrote {total} records across {len(RECORDS_PER_FILE)} subjects × 2 sources to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
