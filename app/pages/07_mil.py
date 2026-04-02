"""
app/pages/07_mil.py
Routing shim for MIL-9 Command Dashboard.
Registers as page 07 in the existing multi-page Streamlit app at port 8501.
Rules:
- This file is a shim only — no MIL logic here
- All logic delegated to mil/command/app.py
- Zero entanglement with CJI Pulse
"""

import sys
from pathlib import Path

# Import and run the MIL dashboard
from mil.command.app import render_dashboard

# Set page config
import streamlit as st
st.set_page_config(
    page_title="Sonar — Command Dashboard",
    page_icon="🔵",
    layout="wide"
)

# Render the dashboard
render_dashboard()
