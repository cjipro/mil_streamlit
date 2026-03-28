"""
mil/tests/test_filtered_stream.py — Filtered Stream live test

Steps:
  1. Add rule: "NatWest app" lang:en  (tag: test_natwest)
  2. Open stream for 60 seconds — count tweets received
  3. Delete the test rule
  4. Report result

Reads TWITTER_BEARER_TOKEN from .env via python-dotenv.
"""
import os
import time
import json
import urllib.parse
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    root = Path(__file__).parent.parent.parent
    load_dotenv(root / ".env")
except ImportError:
    pass

raw_token = os.getenv("TWITTER_BEARER_TOKEN", "")
if not raw_token:
    print("FAIL — TWITTER_BEARER_TOKEN not found")
    raise SystemExit(1)

bearer_token = urllib.parse.unquote(raw_token)
HEADERS = {
    "Authorization": f"Bearer {bearer_token}",
    "Content-Type": "application/json",
}

RULES_URL = "https://api.twitter.com/2/tweets/search/stream/rules"
STREAM_URL = "https://api.twitter.com/2/tweets/search/stream"
RULE_TAG = "test_natwest"
RULE_VALUE = '"NatWest app" lang:en'

# ── Step 1: Add rule ──────────────────────────────────────────
print("Step 1: Adding stream rule...")
payload = {"add": [{"value": RULE_VALUE, "tag": RULE_TAG}]}
resp = requests.post(RULES_URL, headers=HEADERS, json=payload, timeout=15)
print(f"  POST /rules — HTTP {resp.status_code}")

if resp.status_code not in (200, 201):
    print(f"  FAIL — Could not add rule: {resp.text[:400]}")
    raise SystemExit(1)

data = resp.json()
rule_id = None
for entry in data.get("data", []):
    if entry.get("tag") == RULE_TAG:
        rule_id = entry["id"]
        break

if not rule_id:
    # Rule may already exist — fetch existing rules
    r2 = requests.get(RULES_URL, headers=HEADERS, timeout=15)
    for entry in r2.json().get("data", []):
        if entry.get("tag") == RULE_TAG:
            rule_id = entry["id"]
            break

if rule_id:
    print(f"  Rule added — id: {rule_id}  value: {RULE_VALUE}")
else:
    print("  WARNING — Rule ID not confirmed, will attempt cleanup by tag.")

# ── Step 2: Open stream for 60 seconds ───────────────────────
print()
print("Step 2: Opening Filtered Stream for 60 seconds...")
print(f"  Listening for: {RULE_VALUE}")
print()

tweet_count = 0
errors = []
DURATION = 60
start = time.time()

try:
    with requests.get(
        STREAM_URL,
        headers=HEADERS,
        stream=True,
        timeout=(10, DURATION + 10),
    ) as stream_resp:
        print(f"  Stream opened — HTTP {stream_resp.status_code}")

        if stream_resp.status_code != 200:
            print(f"  FAIL — {stream_resp.text[:400]}")
            errors.append(f"HTTP {stream_resp.status_code}")
        else:
            for line in stream_resp.iter_lines():
                elapsed = time.time() - start
                if elapsed >= DURATION:
                    print(f"  60 seconds elapsed — closing stream.")
                    break

                if line:
                    try:
                        obj = json.loads(line)
                        if "data" in obj:
                            tweet_count += 1
                            tweet_id = obj["data"].get("id", "?")
                            text_preview = obj["data"].get("text", "")[:80].replace("\n", " ")
                            print(f"  [{tweet_count}] {tweet_id}: {text_preview}")
                    except json.JSONDecodeError:
                        pass
                # Heartbeat lines (empty) are normal — keep alive

except requests.exceptions.Timeout:
    print("  Stream timed out after 60s (expected).")
except Exception as e:
    errors.append(str(e))
    print(f"  Stream exception: {e}")

# ── Step 3: Delete rule ───────────────────────────────────────
print()
print("Step 3: Deleting test rule...")

# Fetch current rules to find by tag in case rule_id is stale
r_check = requests.get(RULES_URL, headers=HEADERS, timeout=15)
ids_to_delete = []
for entry in r_check.json().get("data", []):
    if entry.get("tag") == RULE_TAG or entry.get("id") == rule_id:
        ids_to_delete.append(entry["id"])

if ids_to_delete:
    del_payload = {"delete": {"ids": ids_to_delete}}
    del_resp = requests.post(RULES_URL, headers=HEADERS, json=del_payload, timeout=15)
    if del_resp.status_code in (200, 201):
        print(f"  Rule deleted — id(s): {ids_to_delete}")
    else:
        print(f"  WARNING — Delete returned HTTP {del_resp.status_code}: {del_resp.text[:200]}")
else:
    print("  No matching rules found to delete.")

# ── Summary ───────────────────────────────────────────────────
print()
print("=" * 50)
print(f"Tweets received in 60s: {tweet_count}")
if not errors:
    print("OVERALL: PASS — Filtered Stream is operational")
else:
    print(f"OVERALL: FAIL — errors: {errors}")
print("=" * 50)
