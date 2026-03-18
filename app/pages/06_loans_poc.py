"""
CJI Pulse — Loans Journey POC
End-to-end proof: HDFS → Sessionisation → Qwen Narrative → Dashboard
"""

import sys
sys.path.insert(0, "/app/../poc")

import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io
from collections import OrderedDict

try:
    import streamlit_shadcn_ui as ui
    HAS_SHADCN = True
except ImportError:
    HAS_SHADCN = False

try:
    from streamlit_extras.colored_header import colored_header
    HAS_EXTRAS = True
except ImportError:
    HAS_EXTRAS = False

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

st.set_page_config(page_title="CJI Pulse — Loans POC", layout="wide", page_icon="📊")

# --- Header ---
if HAS_EXTRAS:
    colored_header(
        label="Loans Journey Intelligence",
        description=f"{SEALED_ORG} · HDFS → Sessionisation → Qwen Narrative · POC",
        color_name="red-70",
    )
else:
    st.title("Loans Journey Intelligence — POC")
    st.caption(f"{SEALED_ORG} · HDFS → Sessionisation → Qwen Narrative")


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
    completed = int(sessions_df[sessions_df["last_step"] == "Confirmation"].shape[0])

    summary = {
        "total_loans_sessions": total,
        "abandoned_count": abandoned_count,
        "abandonment_rate_pct": round(abandoned_count / total * 100, 1) if total else 0,
        "completed_count": completed,
        "completion_rate_pct": round(completed / total * 100, 1) if total else 0,
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


# --- Load & sessionise ---
df, source = load_data()

if df is None:
    st.error(f"Could not load data. {source}")
    st.stop()

st.caption(f"✓ {len(df):,} events loaded from {source}")
summary, sessions_df = sessionise(df)

# --- KPI Cards ---
st.subheader("Today's Signal")

if HAS_SHADCN:
    cols = st.columns(4)
    with cols[0]:
        ui.metric_card(
            title="Total Sessions",
            content=f"{summary['total_loans_sessions']:,}",
            description="Loans journey sessions",
            key="card_total",
        )
    with cols[1]:
        ui.metric_card(
            title="Abandoned",
            content=f"{summary['abandoned_count']:,}",
            description=f"{summary['abandonment_rate_pct']}% of sessions",
            key="card_abandoned",
        )
    with cols[2]:
        ui.metric_card(
            title="Completed",
            content=f"{summary['completed_count']:,}",
            description=f"{summary['completion_rate_pct']}% completion rate",
            key="card_completed",
        )
    with cols[3]:
        ui.metric_card(
            title="Avg Time Before Abandon",
            content=f"{summary['avg_abandon_duration_s']}s",
            description="Seconds before giving up",
            key="card_duration",
        )
else:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sessions", f"{summary['total_loans_sessions']:,}")
    c2.metric("Abandoned", f"{summary['abandoned_count']:,}", f"{summary['abandonment_rate_pct']}%", delta_color="inverse")
    c3.metric("Completed", f"{summary['completed_count']:,}", f"{summary['completion_rate_pct']}%")
    c4.metric("Avg Time Before Abandon", f"{summary['avg_abandon_duration_s']}s")

st.divider()

# --- Drop-off chart ---
left, right = st.columns([2, 1])

with left:
    if HAS_EXTRAS:
        colored_header(label="Drop-off by Step", description="Sessions abandoned at each Loans journey step", color_name="red-70")
    else:
        st.subheader("Drop-off by Step")

    dropoff_df = pd.DataFrame([
        {"Step": step, "Abandoned": count, "Order": order}
        for (step, order), count in zip(LOANS_STEPS.items(), summary["dropoff_by_step"].values())
    ]).sort_values("Order")

    fig = px.bar(
        dropoff_df,
        x="Step", y="Abandoned",
        color="Abandoned",
        color_continuous_scale=["#fee2e2", "#dc2626"],
        text="Abandoned",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", size=13),
        margin=dict(t=20, b=20),
        coloraxis_showscale=False,
    )
    fig.update_xaxes(title="", tickangle=-20)
    fig.update_yaxes(title="Abandoned Sessions", gridcolor="#f3f4f6")
    st.plotly_chart(fig, use_container_width=True)

with right:
    if HAS_EXTRAS:
        colored_header(label="Top Drop-off", description="Highest friction point", color_name="red-70")
    else:
        st.subheader("Top Drop-off")

    st.markdown(f"""
    <div style="background:#fef2f2;border-left:4px solid #dc2626;padding:1.2rem;border-radius:6px;margin-top:0.5rem">
        <div style="font-size:0.8rem;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em">Critical Step</div>
        <div style="font-size:1.6rem;font-weight:700;color:#dc2626;margin:0.3rem 0">{summary['top_dropoff_step'].replace('_', ' ')}</div>
        <div style="font-size:2rem;font-weight:800;color:#111">{summary['top_dropoff_count']:,}</div>
        <div style="font-size:0.85rem;color:#6b7280">sessions abandoned here</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    step_num = LOANS_STEPS.get(summary['top_dropoff_step'], '?')
    st.markdown(f"""
    <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:1rem;border-radius:6px">
        <div style="font-size:0.8rem;color:#6b7280;text-transform:uppercase;letter-spacing:0.05em">Journey Position</div>
        <div style="font-size:1.4rem;font-weight:700;color:#16a34a">Step {step_num} of 6</div>
        <div style="font-size:0.85rem;color:#6b7280">in the Loans application flow</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# --- Qwen Narrative ---
if HAS_EXTRAS:
    colored_header(label="CJI Intelligence", description=f"Generated by {MODEL} via Ollama", color_name="blue-70")
else:
    st.subheader("CJI Intelligence")

if "narrative" not in st.session_state:
    st.session_state.narrative = None

if st.button("Generate Narrative", type="primary", use_container_width=False):
    with st.spinner(f"Asking {MODEL}..."):
        narrative, error = get_narrative(summary)
    if error:
        st.error(f"Qwen unavailable: {error}")
    else:
        st.session_state.narrative = narrative

if st.session_state.narrative:
    st.markdown(f"""
    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:1.5rem;margin-top:0.5rem">
        <div style="font-size:0.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.8rem">
            ● CJI Pulse · {MODEL}
        </div>
        <div style="font-size:1rem;line-height:1.7;color:#1e293b">{st.session_state.narrative}</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("Raw data sent to Qwen"):
        st.json(summary)
else:
    st.caption("Click **Generate Narrative** to ask Qwen for an insight.")
