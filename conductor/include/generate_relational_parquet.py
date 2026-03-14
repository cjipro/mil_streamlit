"""
generate_relational_parquet.py — MAER Relational Parquet Factory
Schema: customer_id -> session_id -> journey steps
Target: ~1,000,000 event rows per run
Format: Snappy-compressed Parquet
Governance: P4 (hmac_ref=HASH_PENDING_ORIGINAL) + P5 (org_name=Habib Bank)
"""

import os
import sys
import uuid
import random
from datetime import datetime, timedelta

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

OUTPUT_DIR = os.getenv("OUTPUT_DIR", ".")
ORG_NAME = "Habib Bank"
CHANNELS = ["APP_Mobile", "APP_Web", "APP_Tablet"]

# ~10k customers × ~18 sessions avg × 5.7 steps avg ≈ 1,026,000 rows
N_CUSTOMERS = 10_000
SESSIONS_PER_CUSTOMER_MIN = 15
SESSIONS_PER_CUSTOMER_MAX = 22

JOURNEY_PATHS = [
    {
        "name": "successful_login",
        "steps": [("Landing", 2, 8), ("Username_Entry", 5, 15), ("Password_Entry", 4, 12),
                  ("MFA_Verify", 8, 30), ("Dashboard", 3, 10)],
        "outcome": "SUCCESS", "weight": 35,
    },
    {
        "name": "failed_login_lockout",
        "steps": [("Landing", 2, 8), ("Username_Entry", 5, 15), ("Password_Entry", 4, 12),
                  ("Password_Entry_Retry", 6, 20), ("Password_Entry_Retry", 6, 25), ("Account_Locked", 2, 5)],
        "outcome": "LOCKED", "weight": 10,
    },
    {
        "name": "password_reset_success",
        "steps": [("Landing", 2, 8), ("Username_Entry", 5, 15), ("Password_Entry", 4, 12),
                  ("Forgot_Password_Link", 3, 8), ("OTP_Request", 5, 15), ("OTP_Entry", 10, 45),
                  ("New_Password_Set", 8, 20), ("Dashboard", 3, 10)],
        "outcome": "RESET_SUCCESS", "weight": 12,
    },
    {
        "name": "loan_application_complete",
        "steps": [("Dashboard", 3, 10), ("Loans_Menu", 4, 12), ("Loan_Type_Select", 8, 25),
                  ("Eligibility_Check", 10, 35), ("Document_Upload", 30, 120),
                  ("Review_Submit", 15, 45), ("Confirmation", 3, 8)],
        "outcome": "APPLICATION_SUBMITTED", "weight": 15,
    },
    {
        "name": "loan_application_abandoned_step3",
        "steps": [("Dashboard", 3, 10), ("Loans_Menu", 4, 12), ("Loan_Type_Select", 8, 25),
                  ("Eligibility_Check", 10, 35)],
        "outcome": "ABANDONED", "weight": 12,
    },
    {
        "name": "funds_transfer_success",
        "steps": [("Dashboard", 3, 10), ("Transfer_Menu", 4, 12), ("Beneficiary_Select", 10, 30),
                  ("Amount_Entry", 8, 20), ("OTP_Entry", 10, 40), ("Transfer_Confirmation", 3, 8)],
        "outcome": "TRANSFER_SUCCESS", "weight": 20,
    },
    {
        "name": "session_timeout_idle",
        "steps": [("Dashboard", 3, 10), ("Loans_Menu", 4, 12), ("Idle", 180, 300),
                  ("Session_Expired", 1, 2)],
        "outcome": "SESSION_TIMEOUT", "weight": 6,
    },
    {
        "name": "statement_download",
        "steps": [("Dashboard", 3, 10), ("Accounts_Menu", 4, 12), ("Account_Select", 5, 15),
                  ("Statement_Request", 8, 20), ("Download_Complete", 5, 15)],
        "outcome": "SUCCESS", "weight": 8,
    },
    {
        "name": "mfa_failure_abandon",
        "steps": [("Landing", 2, 8), ("Username_Entry", 5, 15), ("Password_Entry", 4, 12),
                  ("MFA_Verify", 8, 30), ("MFA_Verify_Retry", 8, 35), ("MFA_Failed_Exit", 2, 5)],
        "outcome": "ABANDONED", "weight": 5,
    },
    {
        "name": "registration_new_user",
        "steps": [("Landing", 2, 8), ("Register_Link", 3, 8), ("Personal_Details", 20, 60),
                  ("Document_Upload", 30, 120), ("OTP_Verify", 10, 40), ("Account_Created", 3, 8)],
        "outcome": "REGISTRATION_SUCCESS", "weight": 8,
    },
]

total_weight = sum(p["weight"] for p in JOURNEY_PATHS)
for p in JOURNEY_PATHS:
    p["_prob"] = p["weight"] / total_weight


def pick_path():
    r = random.random()
    cumulative = 0.0
    for path in JOURNEY_PATHS:
        cumulative += path["_prob"]
        if r <= cumulative:
            return path
    return JOURNEY_PATHS[-1]


def generate_rows():
    base_ts = datetime(2026, 3, 1, 6, 0, 0)
    rows = []
    for _ in range(N_CUSTOMERS):
        customer_id = str(uuid.uuid4())
        n_sessions = random.randint(SESSIONS_PER_CUSTOMER_MIN, SESSIONS_PER_CUSTOMER_MAX)
        for _ in range(n_sessions):
            session_id = str(uuid.uuid4())
            channel = random.choice(CHANNELS)
            path = pick_path()
            session_start = base_ts + timedelta(seconds=random.randint(0, 72 * 3600))
            current_ts = session_start
            for step_name, min_s, max_s in path["steps"]:
                duration = random.randint(min_s, max_s)
                rows.append({
                    "session_id": session_id,
                    "customer_id": customer_id,
                    "org_name": ORG_NAME,
                    "channel": channel,
                    "journey_step": step_name,
                    "event_ts": current_ts.strftime("%Y-%m-%dT%H:%M:%S"),
                    "step_duration_s": duration,
                    "outcome": path["outcome"],
                    "hmac_ref": "HASH_PENDING_ORIGINAL",
                })
                current_ts += timedelta(seconds=duration)
    return rows


def governance_check(rows):
    p5_violations = sum(1 for r in rows if r["org_name"] != "Habib Bank")
    bmb_violations = sum(1 for r in rows if "BMB" in r["channel"])
    p4_violations = sum(1 for r in rows if r["hmac_ref"] != "HASH_PENDING_ORIGINAL")
    print(f"[governance] P5 org_name violations  : {p5_violations}")
    print(f"[governance] P5 BMB channel violations: {bmb_violations}")
    print(f"[governance] P4 hmac_ref violations   : {p4_violations}")
    if p5_violations + bmb_violations + p4_violations > 0:
        print("[governance] FAIL — violations detected, aborting write")
        sys.exit(1)
    print("[governance] PASS — all rows compliant")


def write_parquet(rows):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"batch_{timestamp}.parquet"
    output_path = os.path.join(OUTPUT_DIR, filename)

    df = pd.DataFrame(rows)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, output_path, compression="snappy")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[parquet] Written : {output_path}")
    print(f"[parquet] Rows    : {len(rows):,}")
    print(f"[parquet] Size    : {size_mb:.1f} MB (snappy)")
    return output_path, filename


def main():
    print(f"[generate] Starting — {N_CUSTOMERS:,} customers, {SESSIONS_PER_CUSTOMER_MIN}-{SESSIONS_PER_CUSTOMER_MAX} sessions each")
    rows = generate_rows()
    print(f"[generate] Total event rows: {len(rows):,}")
    governance_check(rows)
    output_path, filename = write_parquet(rows)
    print(f"[generate] Done — {filename}")
    # Write filename to stdout last line for DAG to capture
    print(f"PARQUET_FILE={filename}")


if __name__ == "__main__":
    main()
