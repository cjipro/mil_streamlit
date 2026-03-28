"""
mil/tests/test_youtube.py — YouTube API key test.
Searches for "NatWest app not working". Returns first 3 video titles.
"""
import os
import urllib.parse
import requests
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

api_key = os.getenv("YOUTUBE_API_KEY", "")
if not api_key:
    print("FAIL — YOUTUBE_API_KEY not found in environment")
    raise SystemExit(1)

resp = requests.get(
    "https://www.googleapis.com/youtube/v3/search",
    params={
        "q": "NatWest app not working",
        "part": "snippet",
        "type": "video",
        "maxResults": 3,
        "key": api_key,
    },
    timeout=15,
)

print(f"HTTP {resp.status_code}")

if resp.status_code == 200:
    items = resp.json().get("items", [])
    for i, item in enumerate(items, 1):
        title = item.get("snippet", {}).get("title", "(no title)")
        print(f"  {i}. {title}")
    print("PASS")
elif resp.status_code == 400:
    print(f"FAIL — Bad request: {resp.json().get('error', {}).get('message', '')}")
elif resp.status_code == 403:
    err = resp.json().get("error", {}).get("message", "")
    print(f"FAIL — Forbidden (quota exceeded or API not enabled): {err}")
else:
    print(f"FAIL — {resp.text[:300]}")
