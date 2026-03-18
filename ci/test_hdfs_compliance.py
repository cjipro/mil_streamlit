"""
ci/test_hdfs_compliance.py — GitLab CI test
Verifies HDFS file existence and row-level schema compliance.
Exits non-zero on failure so CI pipeline fails fast.
"""

import os
import sys
import csv
import io

HDFS_URL = os.getenv("HDFS_URL", "http://namenode:9870")
HDFS_PATH = os.getenv("HDFS_PATH", "/user/twin/staged/batch_01_habib_bank.csv")

REQUIRED_COLUMNS = {
    "session_id", "org_name", "channel", "journey_step",
    "event_ts", "step_duration_s", "outcome", "hmac_ref"
}


def test():
    try:
        from hdfs import InsecureClient
    except ImportError:
        print("[ci] ERROR — hdfs package not installed")
        sys.exit(1)

    client = InsecureClient(HDFS_URL, user="root")

    # Test 1: file exists
    status = client.status(HDFS_PATH, strict=False)
    if status is None:
        print(f"[ci] FAIL — file not found: {HDFS_PATH}")
        sys.exit(1)
    print(f"[ci] PASS — file exists: {status['length']:,} bytes")

    # Test 2: schema compliance (sample first 1000 rows)
    with client.read(HDFS_PATH, encoding="utf-8") as reader:
        sample = "".join([next(reader) for _ in range(1001)])

    rows = list(csv.DictReader(io.StringIO(sample)))
    headers = set(rows[0].keys()) if rows else set()

    missing = REQUIRED_COLUMNS - headers
    if missing:
        print(f"[ci] FAIL — missing columns: {missing}")
        sys.exit(1)
    print(f"[ci] PASS — schema valid: {sorted(headers)}")

    # Test 3: P5 check on sample
    p5_fail = [r for r in rows if r.get("org_name") != "Habib Bank"]
    if p5_fail:
        print(f"[ci] FAIL — P5 violation in sample: {len(p5_fail)} rows")
        sys.exit(1)
    print(f"[ci] PASS — P5 org_name sealed in sample ({len(rows)} rows checked)")

    # Test 4: P4 check on sample
    p4_fail = [r for r in rows if r.get("hmac_ref") != "HASH_PENDING_ORIGINAL"]
    if p4_fail:
        print(f"[ci] FAIL — P4 violation in sample: {len(p4_fail)} rows")
        sys.exit(1)
    print(f"[ci] PASS — P4 hmac_ref sealed in sample")

    print("[ci] All HDFS compliance tests PASSED")


if __name__ == "__main__":
    test()
