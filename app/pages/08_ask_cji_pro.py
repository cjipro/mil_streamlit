"""
app/pages/08_ask_cji_pro.py — Ask CJI Pro.

Thin routing shim (mirrors app/pages/07_mil.py pattern).
All logic lives in mil/command/ask_page.py.
"""
import streamlit as st

from mil.command.ask_page import render_ask_page

st.set_page_config(
    page_title="Ask CJI Pro",
    page_icon="💬",
    layout="wide",
)

render_ask_page()
