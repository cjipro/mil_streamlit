"""
bootstrap_hdfs.py — Create MIL HDFS directory structure.
Run once after mil-namenode is confirmed live.
Safe to re-run — MKDIRS is idempotent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from mil.storage.hdfs_client import MILHDFSClient

DIRS = [
    "/user/mil/signals",
    "/user/mil/historical/app_store/natwest",
    "/user/mil/historical/app_store/lloyds",
    "/user/mil/historical/app_store/hsbc",
    "/user/mil/historical/app_store/monzo",
    "/user/mil/historical/app_store/revolut",
    "/user/mil/historical/app_store/barclays",
    "/user/mil/historical/google_play/natwest",
    "/user/mil/historical/google_play/lloyds",
    "/user/mil/historical/google_play/hsbc",
    "/user/mil/historical/google_play/monzo",
    "/user/mil/historical/google_play/revolut",
    "/user/mil/historical/google_play/barclays",
    "/user/mil/historical/reddit",
    "/user/mil/historical/youtube",
    "/user/mil/chronicle_evidence/CHR-001_tsb_2018",
    "/user/mil/chronicle_evidence/CHR-002_lloyds_2025",
    "/user/mil/chronicle_evidence/CHR-003_hsbc_2025",
    "/user/mil/enriched",
    "/user/mil/findings",
]

client = MILHDFSClient()

if not client.is_available():
    print("FAIL — MIL HDFS not reachable at localhost:9871")
    sys.exit(1)

passed = 0
failed = 0

for path in DIRS:
    ok = client.mkdir(path)
    status = "OK  " if ok else "FAIL"
    print(f"  {status}  {path}")
    if ok:
        passed += 1
    else:
        failed += 1

print()
print(f"Results: {passed}/{len(DIRS)} created, {failed} failed")
print("PASS" if failed == 0 else "FAIL — check above")
