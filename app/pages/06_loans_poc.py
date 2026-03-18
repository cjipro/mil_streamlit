"""
CJI Pulse — Loans Journey POC
End-to-end proof: HDFS → Sessionisation → Qwen Narrative → Dashboard
"""

import sys
import os
sys.path.insert(0, "/app/../poc")

import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io
import json
from collections import OrderedDict

# --- Config ---
HDFS_URL = "http://namenode:9870"
HDFS_PATH = "/user/twin/staged/batch_01_habib_bank.csv"
OLLAMA_URL = "http://ollama:11434"
MODEL = "qwen2.5-coder:14b"
SEALED_ORG = "Habib Bank"

LOANS_STEPS = OrderedDict([
    ("Loans_Menu", 1),
    ("Loan_Type_Select", 2),
    ("Eligibility_Check", 3),
    ("Document_Upload", 4),
    ("Review_Submit", 5),
    ("Confirmation", 6),
])
ABANDONED_OUTCOMES = {"ABANDONED", "SESSION_TIMEOUT"}

st.set_page_config(page_title="CJI Pulse — Loans POC", layout="wide")
st.title("Loans Journey Intelligence — POC")
st.caption(f"Data source: {SEALED_ORG} · HDFS → Sessionisation → Qwen Narrative")


# --- Data loading ---
@st.cache_data(show_spinner="Loading from HDFS...")
def load_data():
    try:
        url = f"{HDFS_URL}/webhdfs/v1{HDFS_PATH}?op=OPEN&noredirect=true"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        location = r.json()["Location"]
        data = requests.get(location, timeout=60)
        data.raise_for_status()
        return pd.read_csv(io.StringIO(data.text)), "HDFS"
    except Exception as e:
        return None, f"HDFS unavailable: {e}"


@st.cache_data(show_spinner="Sessionising Loans journey...")
def sessionise(_df):
    loans_sessions = _df[_df["journey_step"].isin(LOANS_STEPS)]["session_id"].unique()
    loans_df = _df[_df["session_id"].isin(loans_sessions)].copy()
    loans_df["step_order"] = loans_df["journey_step"].map(LOANS_STEPS)
    loans_only = loans_df[loans_df["step_order"].notna()].copy()

    sessions = []
    for session_id, grp in loans_only.groupby("session_id"):
        grp_sorted = grp.sort_values("step_order")
        last_step = grp_sorted.iloc[-1]["journey_step"]
        outcome = grp_sorted.iloc[-1]["outcome"]
        duration = grp_sorted["step_duration_s"].sum()
        sessions.append({
            "session_id": session_id,
            "last_step": last_step,
            "outcome": outcome,
            "abandoned": outcome in ABANDONED_OUTCOMES,
            "total_duration_s": duration,
        })

    sessions_df = pd.DataFrame(sessions)
    total = len(sessions_df)
    abandoned_df = sessions_df[sessions_df["abandoned"]]
    abandoned_count = len(abandoned_df)
    dropoff = (
        abandoned_df.groupby("last_step")
        .size()
        .reindex(LOANS_STEPS.keys(), fill_value=0)
        .to_dict()
    )
    top_dropoff = max(dropoff, key=dropoff.get)

    summary = {
        "total_loans_sessions": total,
        "abandoned_count": abandoned_count,
        "abandonment_rate_pct": round(abandoned_count / total * 100, 1) if total else 0,
        "completed_count": int(sessions_df[sessions_df["last_step"] == "Confirmation"].shape[0]),
        "completion_rate_pct": round(sessions_df[sessions_df["last_step"] == "Confirmation"].shape[0] / total * 100, 1) if total else 0,
        "avg_abandon_duration_s": round(float(abandoned_df["total_duration_s"].mean()), 1) if abandoned_count else 0,
        "dropoff_by_step": dropoff,
        "top_dropoff_step": top_dropoff,
        "top_dropoff_count": dropoff.get(top_dropoff, 0),
    }
    return summary, sessions_df


def get_narrative(summary):
    dropoff_lines = "\n".join(
        f"  - {step}: {count} sessions"
        for step, count in summary["dropoff_by_step"].items()
        if count > 0
    )
    prompt = f"""You are CJI Pulse — a customer journey intelligence system for a retail bank.
You have been given today's data on the Loans application journey.

DATA SUMMARY:
- Total Loans journey sessions: {summary['total_loans_sessions']}
- Sessions abandoned: {summary['abandoned_count']} ({summary['abandonment_rate_pct']}%)
- Sessions completed: {summary['completed_count']} ({summary['completion_rate_pct']}%)
- Top drop-off step: {summary['top_dropoff_step']} ({summary['top_dropoff_count']} sessions abandoned here)
- Average time spent before abandonment: {summary['avg_abandon_duration_s']} seconds

DROP-OFF BY STEP:
{dropoff_lines}

Write a professional 3-sentence customer journey intelligence briefing for a bank product manager.
Sentence 1: State the key finding (abandonment rate and where it is happening).
Sentence 2: Interpret what this likely means for the customer (friction, confusion, or a barrier).
Sentence 3: Give one concrete recommended action.

Be direct. No waffle. No generic advice. Specific to the data above."""

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["response"].strip(), None
    except Exception as e:
        return None, str(e)


# --- Load data ---
df, source = load_data()

if df is None:
    st.error(f"Could not load data. {source}")
    st.stop()

st.success(f"Loaded {len(df):,} events from {source}")

# --- Sessionise ---
summary, sessions_df = sessionise(df)

# --- Metric cards ---
st.subheader("Loans Journey — Today's Signal")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Sessions", f"{summary['total_loans_sessions']:,}")
c2.metric("Abandoned", f"{summary['abandoned_count']:,}", f"{summary['abandonment_rate_pct']}%", delta_color="inverse")
c3.metric("Completed", f"{summary['completed_count']:,}", f"{summary['completion_rate_pct']}%")
c4.metric("Avg Time Before Abandon", f"{summary['avg_abandon_duration_s']}s")

# --- Drop-off chart ---
st.subheader("Drop-off by Step")
dropoff_df = pd.DataFrame([
    {"Step": step, "Abandoned Sessions": count, "Step Order": order}
    for (step, order), count in zip(LOANS_STEPS.items(), summary["dropoff_by_step"].values())
])
fig = px.bar(
    dropoff_df.sort_values("Step Order"),
    x="Step", y="Abandoned Sessions",
    color="Abandoned Sessions",
    color_continuous_scale="Reds",
    title="Sessions abandoned at each Loans journey step",
)
fig.update_layout(showlegend=False, plot_bgcolor="white")
st.plotly_chart(fig, use_container_width=True)

# --- Qwen narrative ---
st.subheader("CJI Intelligence — Qwen Narrative")
st.caption(f"Generated by {MODEL} via Ollama")

if st.button("Generate Narrative", type="primary"):
    with st.spinner("Asking Qwen..."):
        narrative, error = get_narrative(summary)
    if error:
        st.error(f"Qwen unavailable: {error}")
    else:
        st.info(narrative)
        st.caption("Raw summary sent to Qwen:")
        st.json(summary)
else:
    st.caption("Click **Generate Narrative** to ask Qwen for an insight.")
