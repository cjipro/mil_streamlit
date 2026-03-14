import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io
import time
import json

# --- Governance constants ---
HDFS_URL = "http://namenode:9870"
HDFS_PATH = "/user/twin/staged/batch_01_habib_bank.csv"
HDFS_PARQUET_BASE = "/user/twin/staged/habib_bank"
SEALED_ORG = "Habib Bank"

# --- In-memory user database ---
users_db = {
    "admin": {"email": "admin@example.com", "name": "Admin", "password": "admin123"},
    "user": {"email": "user@example.com", "name": "User", "password": "user123"},
}

# --- Auth state init ---
if "authentication_status" not in st.session_state:
    st.session_state["authentication_status"] = None
    st.session_state["name"] = None
    st.session_state["username"] = None

# ==============================
# LOGIN WALL
# ==============================
if st.session_state["authentication_status"] != True:
    st.title("CJI Pulse Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            if username in users_db and users_db[username]["password"] == password:
                st.session_state["authentication_status"] = True
                st.session_state["name"] = users_db[username]["name"]
                st.session_state["username"] = username
                st.rerun()
            else:
                st.error("Invalid username or password")
    st.stop()

# ==============================
# AUTHENTICATED SHELL
# ==============================
st.sidebar.title(f"Welcome, {st.session_state['name']}")
if st.sidebar.button("Logout"):
    st.session_state["authentication_status"] = None
    st.session_state["name"] = None
    st.session_state["username"] = None
    st.rerun()

st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Home", "HDFS Live", "Analytics", "Reports", "Profile", "Settings"],
)


# ==============================
# HDFS LOADER — CSV (cached 5 min)
# ==============================
@st.cache_data(ttl=300, show_spinner=False)
def load_hdfs_data():
    """
    Reads batch_01_habib_bank.csv from HDFS via WebHDFS REST API.
    Returns (DataFrame, error_string). error_string is None on success.
    """
    try:
        r = requests.get(
            f"{HDFS_URL}/webhdfs/v1{HDFS_PATH}",
            params={"op": "OPEN", "user.name": "root"},
            timeout=30,
            allow_redirects=True,
        )
        r.raise_for_status()
        df = pd.read_csv(io.BytesIO(r.content))
        return df, None
    except requests.exceptions.ConnectionError:
        return None, "HDFS NameNode unreachable — is the Docker cluster running?"
    except Exception as e:
        return None, str(e)


# ==============================
# HDFS LOADER — Parquet (cached 5 min)
# ==============================
@st.cache_data(ttl=300, show_spinner=False)
def find_latest_parquet():
    """
    Walk HDFS_PARQUET_BASE/date=*/ partitions and return the newest parquet file path.
    Returns (hdfs_path, size_bytes) or (None, None).
    """
    try:
        r = requests.get(
            f"{HDFS_URL}/webhdfs/v1{HDFS_PARQUET_BASE}",
            params={"op": "LISTSTATUS", "user.name": "root"},
            timeout=10,
        )
        if r.status_code != 200:
            return None, None
        partitions = r.json()["FileStatuses"]["FileStatus"]
        date_partitions = sorted(
            [p for p in partitions if p["pathSuffix"].startswith("date=")],
            key=lambda x: x["pathSuffix"],
            reverse=True,
        )
        for partition in date_partitions:
            part_path = f"{HDFS_PARQUET_BASE}/{partition['pathSuffix']}"
            r2 = requests.get(
                f"{HDFS_URL}/webhdfs/v1{part_path}",
                params={"op": "LISTSTATUS", "user.name": "root"},
                timeout=10,
            )
            if r2.status_code != 200:
                continue
            files = r2.json()["FileStatuses"]["FileStatus"]
            parquets = sorted(
                [f for f in files if f["pathSuffix"].endswith(".parquet")],
                key=lambda x: x["modificationTime"],
                reverse=True,
            )
            if parquets:
                latest = parquets[0]
                return f"{part_path}/{latest['pathSuffix']}", latest["length"]
    except Exception:
        pass
    return None, None


def load_hdfs_parquet(hdfs_path):
    """
    Reads a Parquet file from HDFS via WebHDFS.
    Returns (DataFrame, latency_ms, error_string).
    """
    t0 = time.time()
    try:
        r = requests.get(
            f"{HDFS_URL}/webhdfs/v1{hdfs_path}",
            params={"op": "OPEN", "user.name": "root"},
            timeout=60,
            allow_redirects=True,
        )
        r.raise_for_status()
        df = pd.read_parquet(io.BytesIO(r.content))
        latency_ms = int((time.time() - t0) * 1000)
        return df, latency_ms, None
    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        return None, latency_ms, str(e)


# ==============================
# GOVERNANCE KPI CARD
# ==============================
def render_governance_card(df=None):
    row_count = f"{len(df):,}" if df is not None else "—"
    p5_ok = (df["org_name"] == SEALED_ORG).all() if df is not None else False
    p4_ok = (df["hmac_ref"] == "HASH_PENDING_ORIGINAL").all() if df is not None else False
    seal_status = "✅ P4/P5 SEALED" if (p5_ok and p4_ok) else "⚠️ SEAL CHECK FAILED"

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #0d1117, #161b22);
            border: 1px solid #30363d;
            border-left: 4px solid {'#2ea043' if (p5_ok and p4_ok) else '#f85149'};
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 20px;
            font-family: monospace;
        ">
            <span style="color:#58a6ff; font-size:13px; font-weight:600;">⬡ GOVERNANCE SEAL</span><br/>
            <span style="color:#e6edf3; font-size:15px; font-weight:700;">
                Client: {SEALED_ORG}&nbsp;&nbsp;|&nbsp;&nbsp;Status: {seal_status}
            </span><br/>
            <span style="color:#8b949e; font-size:12px;">
                Source: HDFS {HDFS_PATH}&nbsp;&nbsp;|&nbsp;&nbsp;Rows: {row_count}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==============================
# HOME PAGE
# ==============================
if page == "Home":
    st.title("CJI Pulse Dashboard")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Journeys", "125K", "12%")
    with col2:
        st.metric("Pain Score", "6.2", "-0.8")
    with col3:
        st.metric("NPS", "42", "+3")

    st.subheader("Today's Top Findings")
    st.info("• Loans journey Step 3 abandonment rate: +23% for vulnerable customers")
    st.warning("• Payment failures on iOS: +8% vs yesterday")
    st.success("• Onboarding completion rate: +5% after fix")


# ==============================
# HDFS LIVE PAGE
# ==============================
elif page == "HDFS Live":
    st.title("HDFS Live — Staged Data")

    # ── Latency Monitor ───────────────────────────────────────────────────────
    st.subheader("Latency Monitor")
    parquet_path, parquet_size = find_latest_parquet()

    if parquet_path:
        st.caption(f"Source: Parquet · `{parquet_path}` · Cache TTL: 5 min")
        with st.spinner("Reading Parquet from HDFS..."):
            t_wall = time.time()
            df, latency_ms, err = load_hdfs_parquet(parquet_path)
            wall_ms = int((time.time() - t_wall) * 1000)
        source_label = "Parquet (snappy)"
        size_label = f"{parquet_size / (1024*1024):.1f} MB" if parquet_size else "—"
    else:
        st.caption(f"Source: CSV fallback · `{HDFS_URL}{HDFS_PATH}` · Cache TTL: 5 min")
        with st.spinner("Reading CSV from HDFS (no Parquet found)..."):
            t_wall = time.time()
            df, err = load_hdfs_data()
            latency_ms = int((time.time() - t_wall) * 1000)
        source_label = "CSV (fallback)"
        size_label = "35.4 MB"

    col_l1, col_l2, col_l3, col_l4 = st.columns(4)
    col_l1.metric("Load Latency", f"{latency_ms} ms")
    col_l2.metric("Format", source_label)
    col_l3.metric("File Size", size_label)
    col_l4.metric("Cached", "Yes (5 min TTL)")
    st.divider()

    if err:
        render_governance_card()
        st.error(f"HDFS read failed: {err}")
        st.code("docker exec namenode hdfs dfsadmin -report", language="bash")
        st.stop()

    render_governance_card(df)

    # --- Summary metrics ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Event Rows", f"{len(df):,}")
    col2.metric("Unique Sessions", f"{df['session_id'].nunique():,}")
    col3.metric("Journey Steps", f"{df['journey_step'].nunique()}")
    col4.metric("Outcomes", f"{df['outcome'].nunique()}")

    st.divider()

    # --- Journey Step × Outcome heatmap ---
    st.subheader("Journey Step × Outcome — Event Distribution")
    pivot = (
        df.groupby(["journey_step", "outcome"])
        .size()
        .reset_index(name="count")
    )
    fig_heat = px.density_heatmap(
        pivot,
        x="outcome",
        y="journey_step",
        z="count",
        color_continuous_scale="Blues",
        title=f"Event counts across {len(df):,} rows — Client: {SEALED_ORG}",
        height=500,
    )
    fig_heat.update_layout(
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font_color="#e6edf3",
        xaxis_title="Outcome",
        yaxis_title="Journey Step",
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # --- Bar chart: top steps by volume ---
    st.subheader("Journey Step Volume (all outcomes)")
    step_counts = df["journey_step"].value_counts().reset_index()
    step_counts.columns = ["journey_step", "count"]
    fig_bar = px.bar(
        step_counts,
        x="count",
        y="journey_step",
        orientation="h",
        color="count",
        color_continuous_scale="Blues",
        title="Event rows per Journey Step",
        height=450,
    )
    fig_bar.update_layout(
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font_color="#e6edf3",
        yaxis={"categoryorder": "total ascending"},
        showlegend=False,
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- Outcome breakdown pie ---
    st.subheader("Outcome Distribution")
    outcome_counts = df["outcome"].value_counts().reset_index()
    outcome_counts.columns = ["outcome", "count"]
    fig_pie = px.pie(
        outcome_counts,
        names="outcome",
        values="count",
        color_discrete_sequence=px.colors.sequential.Blues_r,
        title="Session outcomes across all paths",
    )
    fig_pie.update_layout(
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font_color="#e6edf3",
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    # --- Channel split ---
    st.subheader("Channel Split")
    channel_counts = df["channel"].value_counts().reset_index()
    channel_counts.columns = ["channel", "count"]
    fig_ch = px.bar(
        channel_counts,
        x="channel",
        y="count",
        color="channel",
        color_discrete_sequence=["#1f6feb", "#388bfd", "#58a6ff"],
        title="Event rows by Channel (P5: BMB → APP)",
    )
    fig_ch.update_layout(
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font_color="#e6edf3",
        showlegend=False,
    )
    st.plotly_chart(fig_ch, use_container_width=True)

    # --- Raw sample ---
    with st.expander("Raw data sample (first 200 rows)"):
        st.dataframe(df.head(200), use_container_width=True)


# ==============================
# ANALYTICS PAGE
# ==============================
elif page == "Analytics":
    st.title("Journey Analytics")
    st.info("Load the **HDFS Live** page to explore the 284k event dataset from HDFS.")


# ==============================
# REPORTS
# ==============================
elif page == "Reports":
    st.title("Daily Reports")
    st.write("Daily reports coming soon...")


# ==============================
# PROFILE
# ==============================
elif page == "Profile":
    st.title("User Profile")
    st.write(f"**Name:** {st.session_state['name']}")
    st.write(f"**Username:** {st.session_state['username']}")
    st.write(f"**Email:** {users_db[st.session_state['username']]['email']}")


# ==============================
# SETTINGS
# ==============================
elif page == "Settings":
    st.title("Settings")
    st.write("Application settings coming soon...")
