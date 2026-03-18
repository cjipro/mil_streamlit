"""
generate_batch_01.py — MAER Synthetic Data Factory
Batch: batch_01_habib_bank.csv | Rows: 50,000
Governance: P4 (hmac_ref=HASH_PENDING_ORIGINAL) + P5 (org_name=Habib Bank, BMB→APP)
"""

import csv
import random
import uuid
from datetime import datetime, timedelta

OUTPUT_FILE = "batch_01_habib_bank.csv"
ROW_COUNT = 50_000

# P5 compliant — no BMB, no original client name
ORG_NAME = "Habib Bank"
CHANNELS = ["APP_Mobile", "APP_Web", "APP_Tablet"]  # BMB substituted → APP

# Journey Paths: list of (step_sequence, outcome)
# Each path is a realistic user journey with step durations (min_s, max_s)
JOURNEY_PATHS = [
    {
        "name": "successful_login",
        "steps": [
            ("Landing", 2, 8),
            ("Username_Entry", 5, 15),
            ("Password_Entry", 4, 12),
            ("MFA_Verify", 8, 30),
            ("Dashboard", 3, 10),
        ],
        "outcome": "SUCCESS",
        "weight": 35,
    },
    {
        "name": "failed_login_lockout",
        "steps": [
            ("Landing", 2, 8),
            ("Username_Entry", 5, 15),
            ("Password_Entry", 4, 12),
            ("Password_Entry_Retry", 6, 20),
            ("Password_Entry_Retry", 6, 25),
            ("Account_Locked", 2, 5),
        ],
        "outcome": "LOCKED",
        "weight": 10,
    },
    {
        "name": "password_reset_success",
        "steps": [
            ("Landing", 2, 8),
            ("Username_Entry", 5, 15),
            ("Password_Entry", 4, 12),
            ("Forgot_Password_Link", 3, 8),
            ("OTP_Request", 5, 15),
            ("OTP_Entry", 10, 45),
            ("New_Password_Set", 8, 20),
            ("Dashboard", 3, 10),
        ],
        "outcome": "RESET_SUCCESS",
        "weight": 12,
    },
    {
        "name": "loan_application_complete",
        "steps": [
            ("Dashboard", 3, 10),
            ("Loans_Menu", 4, 12),
            ("Loan_Type_Select", 8, 25),
            ("Eligibility_Check", 10, 35),
            ("Document_Upload", 30, 120),
            ("Review_Submit", 15, 45),
            ("Confirmation", 3, 8),
        ],
        "outcome": "APPLICATION_SUBMITTED",
        "weight": 15,
    },
    {
        "name": "loan_application_abandoned_step3",
        "steps": [
            ("Dashboard", 3, 10),
            ("Loans_Menu", 4, 12),
            ("Loan_Type_Select", 8, 25),
            ("Eligibility_Check", 10, 35),
        ],
        "outcome": "ABANDONED",
        "weight": 12,
    },
    {
        "name": "funds_transfer_success",
        "steps": [
            ("Dashboard", 3, 10),
            ("Transfer_Menu", 4, 12),
            ("Beneficiary_Select", 10, 30),
            ("Amount_Entry", 8, 20),
            ("OTP_Entry", 10, 40),
            ("Transfer_Confirmation", 3, 8),
        ],
        "outcome": "TRANSFER_SUCCESS",
        "weight": 20,
    },
    {
        "name": "session_timeout_idle",
        "steps": [
            ("Dashboard", 3, 10),
            ("Loans_Menu", 4, 12),
            ("Idle", 180, 300),
            ("Session_Expired", 1, 2),
        ],
        "outcome": "SESSION_TIMEOUT",
        "weight": 6,
    },
    {
        "name": "statement_download",
        "steps": [
            ("Dashboard", 3, 10),
            ("Accounts_Menu", 4, 12),
            ("Account_Select", 5, 15),
            ("Statement_Request", 8, 20),
            ("Download_Complete", 5, 15),
        ],
        "outcome": "SUCCESS",
        "weight": 8,
    },
    {
        "name": "mfa_failure_abandon",
        "steps": [
            ("Landing", 2, 8),
            ("Username_Entry", 5, 15),
            ("Password_Entry", 4, 12),
            ("MFA_Verify", 8, 30),
            ("MFA_Verify_Retry", 8, 35),
            ("MFA_Failed_Exit", 2, 5),
        ],
        "outcome": "ABANDONED",
        "weight": 5,
    },
    {
        "name": "registration_new_user",
        "steps": [
            ("Landing", 2, 8),
            ("Register_Link", 3, 8),
            ("Personal_Details", 20, 60),
            ("Document_Upload", 30, 120),
            ("OTP_Verify", 10, 40),
            ("Account_Created", 3, 8),
        ],
        "outcome": "REGISTRATION_SUCCESS",
        "weight": 8,  # Note: weights sum slightly off — normalised below
    },
]

# Normalise weights
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


def random_ts(base: datetime, jitter_hours: int = 72) -> datetime:
    offset = random.randint(0, jitter_hours * 3600)
    return base + timedelta(seconds=offset)


def generate_rows(n: int):
    base_ts = datetime(2026, 3, 1, 6, 0, 0)
    rows = []
    for _ in range(n):
        path = pick_path()
        session_id = str(uuid.uuid4())
        channel = random.choice(CHANNELS)
        session_start = random_ts(base_ts)

        current_ts = session_start
        for step_name, min_s, max_s in path["steps"]:
            duration = random.randint(min_s, max_s)
            rows.append({
                "session_id": session_id,
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


def main():
    print(f"[generate_batch_01] Generating {ROW_COUNT:,} session rows...")
    rows = generate_rows(ROW_COUNT)
    print(f"[generate_batch_01] Total event rows produced: {len(rows):,}")

    fieldnames = ["session_id", "org_name", "channel", "journey_step",
                  "event_ts", "step_duration_s", "outcome", "hmac_ref"]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[generate_batch_01] Written: {OUTPUT_FILE}")

    # Quick governance check
    p5_violations = sum(1 for r in rows if r["org_name"] != "Habib Bank")
    bmb_violations = sum(1 for r in rows if "BMB" in r["channel"])
    p4_violations = sum(1 for r in rows if r["hmac_ref"] != "HASH_PENDING_ORIGINAL")

    print(f"[governance] P5 org_name violations : {p5_violations}")
    print(f"[governance] P5 BMB channel violations: {bmb_violations}")
    print(f"[governance] P4 hmac_ref violations  : {p4_violations}")

    if p5_violations + bmb_violations + p4_violations == 0:
        print("[governance] PASS — all rows compliant")
    else:
        print("[governance] WARN — violations detected, review before HDFS push")


if __name__ == "__main__":
    main()
