"""
validate_title_fix.py — spot-check 5 random Jira tickets against manifest names.
Confirms summaries were correctly updated by _update_jira_titles.py.
"""
import os, yaml, random, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE = os.getenv("JIRA_BASE_URL", "https://cjipro.atlassian.net")
AUTH = (os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
HDR  = {"Accept": "application/json"}

manifest = yaml.safe_load(Path("manifests/system_manifest.yaml").read_text(encoding="utf-8"))
pairs = {c["jira_key"]: c["name"] for c in manifest.get("components", []) if "jira_key" in c}

sample = random.sample(list(pairs.items()), 5)

print("validate_title_fix.py — spot-check 5 random tickets")
print("=" * 60)

passed, failed = 0, 0

for key, expected in sample:
    r = requests.get(f"{BASE}/rest/api/3/issue/{key}?fields=summary", auth=AUTH, headers=HDR)
    if r.status_code != 200:
        print(f"  [FAIL] {key}: HTTP {r.status_code}")
        failed += 1
        continue
    actual = r.json()["fields"]["summary"]
    if actual == expected:
        print(f"  [PASS] {key}: {actual}")
        passed += 1
    else:
        print(f"  [FAIL] {key}")
        print(f"         expected: {expected}")
        print(f"         actual:   {actual}")
        failed += 1

print()
print(f"Result: {passed} passed, {failed} failed")
print("PASS" if failed == 0 else "FAIL")
