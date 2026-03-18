"""
POC — Loans Journey Sessionisation
Reads batch CSV from HDFS WebHDFS, sessionises Loans journey events,
returns a summary dict ready for narrative generation.
"""

import requests
import pandas as pd
import io
from collections import OrderedDict

HDFS_URL = "http://localhost:9870"
HDFS_PATH = "/user/twin/staged/batch_01_habib_bank.csv"

LOANS_STEPS = OrderedDict([
    ("Loans_Menu", 1),
    ("Loan_Type_Select", 2),
    ("Eligibility_Check", 3),
    ("Document_Upload", 4),
    ("Review_Submit", 5),
    ("Confirmation", 6),
])

ABANDONED_OUTCOMES = {"ABANDONED", "SESSION_TIMEOUT"}


def load_from_hdfs(hdfs_url=HDFS_URL, hdfs_path=HDFS_PATH):
    url = f"{hdfs_url}/webhdfs/v1{hdfs_path}?op=OPEN&noredirect=true"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    location = r.json()["Location"]
    data = requests.get(location, timeout=30)
    data.raise_for_status()
    return pd.read_csv(io.StringIO(data.text))


def load_from_file(path):
    return pd.read_csv(path)


def sessionise(df):
    # Filter to Loans journey sessions only
    loans_sessions = df[df["journey_step"].isin(LOANS_STEPS)]["session_id"].unique()
    loans_df = df[df["session_id"].isin(loans_sessions)].copy()

    # Map step order
    loans_df["step_order"] = loans_df["journey_step"].map(LOANS_STEPS)
    loans_only = loans_df[loans_df["step_order"].notna()].copy()

    # Per session: last step reached, outcome, duration
    sessions = []
    for session_id, grp in loans_only.groupby("session_id"):
        grp_sorted = grp.sort_values("step_order")
        last_step = grp_sorted.iloc[-1]["journey_step"]
        outcome = grp_sorted.iloc[-1]["outcome"]
        duration = grp_sorted["step_duration_s"].sum()
        abandoned = outcome in ABANDONED_OUTCOMES
        sessions.append({
            "session_id": session_id,
            "last_step": last_step,
            "outcome": outcome,
            "abandoned": abandoned,
            "total_duration_s": duration,
        })

    sessions_df = pd.DataFrame(sessions)

    total = len(sessions_df)
    abandoned_df = sessions_df[sessions_df["abandoned"]]
    abandoned_count = len(abandoned_df)
    abandonment_rate = round(abandoned_count / total * 100, 1) if total else 0

    # Drop-off by step
    dropoff = (
        abandoned_df.groupby("last_step")
        .size()
        .reindex(LOANS_STEPS.keys(), fill_value=0)
        .to_dict()
    )

    # Completion
    completed = len(sessions_df[sessions_df["last_step"] == "Confirmation"])
    completion_rate = round(completed / total * 100, 1) if total else 0

    # Avg duration of abandoned sessions
    avg_abandon_duration = round(abandoned_df["total_duration_s"].mean(), 1) if abandoned_count else 0

    # Top drop-off step
    top_dropoff = max(dropoff, key=dropoff.get) if dropoff else "Unknown"

    return {
        "total_loans_sessions": total,
        "abandoned_count": abandoned_count,
        "abandonment_rate_pct": abandonment_rate,
        "completion_rate_pct": completion_rate,
        "completed_count": completed,
        "avg_abandon_duration_s": avg_abandon_duration,
        "dropoff_by_step": dropoff,
        "top_dropoff_step": top_dropoff,
        "top_dropoff_count": dropoff.get(top_dropoff, 0),
    }


if __name__ == "__main__":
    import json
    print("Loading from HDFS...")
    try:
        df = load_from_hdfs()
        print(f"Loaded {len(df):,} rows from HDFS")
    except Exception as e:
        print(f"HDFS failed ({e}), falling back to local CSV")
        df = load_from_file("batch_01_habib_bank.csv")
        print(f"Loaded {len(df):,} rows from local CSV")

    summary = sessionise(df)
    print(json.dumps(summary, indent=2))
