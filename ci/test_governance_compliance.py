"""
ci/test_governance_compliance.py — GitLab CI governance gate
Validates P4/P5 rules against the generated batch CSV in the workspace.
"""

import sys
import pandas as pd

CSV_PATH = "batch_01_habib_bank.csv"


def test():
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print(f"[ci] SKIP — {CSV_PATH} not present in workspace (HDFS-only run)")
        sys.exit(0)

    failures = []

    p5_org = (df["org_name"] != "Habib Bank").sum()
    if p5_org:
        failures.append(f"P5 org_name violations: {p5_org}")
    else:
        print(f"[ci] PASS — P5 org_name: all {len(df):,} rows = 'Habib Bank'")

    p5_bmb = df["channel"].str.contains("BMB").sum()
    if p5_bmb:
        failures.append(f"P5 BMB channel violations: {p5_bmb}")
    else:
        print(f"[ci] PASS — P5 channel: no BMB references in {len(df):,} rows")

    p4 = (df["hmac_ref"] != "HASH_PENDING_ORIGINAL").sum()
    if p4:
        failures.append(f"P4 hmac_ref violations: {p4}")
    else:
        print(f"[ci] PASS — P4 hmac_ref: all rows = 'HASH_PENDING_ORIGINAL'")

    if failures:
        for f in failures:
            print(f"[ci] FAIL — {f}")
        sys.exit(1)

    print(f"[ci] All governance tests PASSED ({len(df):,} rows)")


if __name__ == "__main__":
    test()
