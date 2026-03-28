"""
mil/tests/test_twitter.py — Twitter API credential test

Tests:
  Test 1: Recent search — GET /2/tweets/search/recent
  Test 2: Filtered Stream rules — GET /2/tweets/search/stream/rules

Reads credentials from .env via python-dotenv.
Bearer token is URL-decoded before use (handles %2B, %3D encoding).
"""
import os
import urllib.parse
import requests
from pathlib import Path

# Load .env from repo root
try:
    from dotenv import load_dotenv
    root = Path(__file__).parent.parent.parent
    load_dotenv(root / ".env")
except ImportError:
    pass  # Fall back to environment variables already set

raw_token = os.getenv("TWITTER_BEARER_TOKEN", "")
if not raw_token:
    print("FAIL — TWITTER_BEARER_TOKEN not found in environment")
    raise SystemExit(1)

# Decode URL-encoded token (%2B → +, %3D → =, etc.)
bearer_token = urllib.parse.unquote(raw_token)

HEADERS = {"Authorization": f"Bearer {bearer_token}"}

passed = 0
failed = 0

# ── Test 1: Recent Search ─────────────────────────────────────
print("Test 1: Recent search — GET /2/tweets/search/recent")
try:
    resp = requests.get(
        "https://api.twitter.com/2/tweets/search/recent",
        headers=HEADERS,
        params={"query": "NatWest app not working", "max_results": 10},
        timeout=15,
    )
    status = resp.status_code
    if status == 200:
        data = resp.json()
        count = data.get("meta", {}).get("result_count", "?")
        print(f"  PASS — HTTP {status} — result_count: {count}")
        passed += 1
    elif status == 401:
        print(f"  FAIL — HTTP {status} — Unauthorized. Token invalid or expired.")
        print(f"  Response: {resp.text[:300]}")
        failed += 1
    elif status == 403:
        print(f"  FAIL — HTTP {status} — Forbidden. Check app permissions / API tier.")
        print(f"  Response: {resp.text[:300]}")
        failed += 1
    else:
        print(f"  FAIL — HTTP {status}")
        print(f"  Response: {resp.text[:300]}")
        failed += 1
except Exception as e:
    print(f"  FAIL — Exception: {e}")
    failed += 1

# ── Test 2: Filtered Stream Rules ────────────────────────────
print("Test 2: Filtered Stream rules — GET /2/tweets/search/stream/rules")
try:
    resp = requests.get(
        "https://api.twitter.com/2/tweets/search/stream/rules",
        headers=HEADERS,
        timeout=15,
    )
    status = resp.status_code
    if status == 200:
        data = resp.json()
        rules = data.get("data", [])
        print(f"  PASS — HTTP {status} — active rules: {len(rules)}")
        passed += 1
    elif status == 401:
        print(f"  FAIL — HTTP {status} — Unauthorized. Token invalid or expired.")
        print(f"  Response: {resp.text[:300]}")
        failed += 1
    elif status == 403:
        print(f"  FAIL — HTTP {status} — Forbidden. Filtered Stream requires elevated API access.")
        print(f"  Response: {resp.text[:300]}")
        failed += 1
    else:
        print(f"  FAIL — HTTP {status}")
        print(f"  Response: {resp.text[:300]}")
        failed += 1
except Exception as e:
    print(f"  FAIL — Exception: {e}")
    failed += 1

# ── Summary ───────────────────────────────────────────────────
print()
print(f"Results: {passed}/2 passed, {failed}/2 failed")
if failed == 0:
    print("OVERALL: PASS")
else:
    print("OVERALL: FAIL")
