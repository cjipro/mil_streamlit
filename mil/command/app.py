"""
MIL-9 Command Dashboard
Streamlit app consuming get_briefing_data() and rendering Sonar briefing page.
Location: mil/command/app.py
Rules:
- Zero entanglement — mil/ only, no imports from app/ or pulse/
- Data layer only from briefing_data.py
- No HDFS reads, no inference calls
"""

import streamlit as st
import json
from datetime import datetime
from pathlib import Path
import sys

# Add mil to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mil.briefing_data import get_briefing_data

# ============================================================================
# STREAMLIT CONFIG
# ============================================================================

# ============================================================================
# CUSTOM CSS
# ============================================================================
st.markdown("""
<style>
    :root {
        --bg: #00273D;
        --topbar-bg: #001E30;
        --ticker-bg: #001828;
        --journey-bg: #001E30;
        --summary-bg: #002030;
        --feed-bg: #00273D;
        --panel-bg: #001828;
        --card: #002A3F;
        --border: #003A5C;
        --blue: #00AEEF;
        --teal: #00AFA0;
        --amber: #F5A623;
        --red: #CC0000;
        --text: #E8F4FA;
        --text-2: #7AACBF;
        --text-3: #4A7A8F;
        --muted: #3A6A7F;
        --mono: 'DM Mono', monospace;
        --sans: 'Plus Jakarta Sans', sans-serif;
    }

    * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: #00273D;
        color: #E8F4FA;
        font-family: 'Plus Jakarta Sans', sans-serif;
        font-size: 14px;
        line-height: 1.5;
    }

    [data-testid="stMainBlockContainer"] {
        padding: 0;
    }

    .metric-card {
        background: #002030;
        border: 1px solid #003A5C;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
    }

    .metric-value {
        font-family: 'DM Mono', monospace;
        font-size: 32px;
        font-weight: 800;
        margin: 10px 0;
    }

    .metric-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1.5px;
        color: #4A7A8F;
        text-transform: uppercase;
    }

    .journey-card {
        background: #002A3F;
        border: 1px solid #003A5C;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 12px;
    }

    .journey-card-title {
        font-size: 16px;
        font-weight: 700;
        color: #E8F4FA;
        margin-bottom: 8px;
    }

    .journey-card-meta {
        display: flex;
        gap: 12px;
        font-size: 12px;
        color: #7AACBF;
        margin-bottom: 8px;
    }

    .badge {
        font-size: 11px;
        font-weight: 700;
        padding: 3px 12px;
        border-radius: 12px;
        letter-spacing: 1px;
    }

    .badge-regression {
        background: rgba(204, 0, 0, 0.15);
        color: #FF4444;
    }

    .badge-watch {
        background: rgba(245, 166, 35, 0.12);
        color: #F5A623;
    }

    .badge-performing {
        background: rgba(0, 175, 160, 0.12);
        color: #00AFA0;
    }

    .topbar-section {
        background: #001E30;
        border: 1px solid #003A5C;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }

    .topbar-title {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 2px;
        color: #00AEEF;
        text-transform: uppercase;
        margin-bottom: 12px;
    }

    .competitor-ticker {
        background: #001828;
        border: 1px solid #003A5C;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 12px;
        display: flex;
        gap: 16px;
        overflow-x: auto;
    }

    .ticker-item {
        flex-shrink: 0;
        text-align: center;
    }

    .ticker-name {
        font-size: 12px;
        font-weight: 600;
        color: #7AACBF;
    }

    .ticker-score {
        font-family: 'DM Mono', monospace;
        font-size: 18px;
        font-weight: 700;
        margin-top: 4px;
    }

    .executive-alert {
        background: #001828;
        border: 2px solid #CC0000;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }

    .alert-title {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 2px;
        color: #CC0000;
        text-transform: uppercase;
        margin-bottom: 12px;
    }

    .alert-finding {
        font-size: 14px;
        font-weight: 700;
        color: #E8F4FA;
        margin-bottom: 10px;
    }

    .alert-pills {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 12px;
    }

    .pill {
        font-family: 'DM Mono', monospace;
        font-size: 11px;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 10px;
        background: rgba(0, 174, 239, 0.1);
        color: #00AEEF;
        border: 1px solid rgba(0, 174, 239, 0.2);
    }

    .publish-btn {
        background: #00AEEF;
        color: #001E30;
        border: none;
        border-radius: 8px;
        padding: 12px 20px;
        font-weight: 700;
        font-size: 13px;
        cursor: pointer;
        letter-spacing: 1px;
        margin-top: 16px;
        width: 100%;
    }

    .publish-btn:hover {
        background: #0090C8;
    }

    .success-msg {
        background: rgba(0, 175, 160, 0.15);
        color: #00AFA0;
        border: 1px solid rgba(0, 175, 160, 0.3);
        border-radius: 8px;
        padding: 12px;
        margin-top: 12px;
        font-size: 12px;
    }

    .chronicle-card {
        background: #002A3F;
        border: 1px solid #003A5C;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 8px;
        font-size: 11px;
    }

    .chronicle-id {
        font-family: 'DM Mono', monospace;
        font-weight: 600;
        color: #8BBCCC;
    }

    .chronicle-bank {
        font-weight: 600;
        color: #8BBCCC;
    }

    .chronicle-type {
        color: #7AACBF;
        margin-top: 4px;
    }

    .inference-card {
        background: #002A3F;
        border: 1px solid #CC0000;
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 12px;
    }

    .inference-label {
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 2px;
        color: #CC0000;
        text-transform: uppercase;
        margin-bottom: 8px;
    }

    .footer-text {
        font-size: 10px;
        color: #4A7A8F;
        text-align: center;
        margin-top: 24px;
        padding-top: 12px;
        border-top: 1px solid #003A5C;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# MAIN APP
# ============================================================================

def render_dashboard():
    """Main dashboard render function."""
    
    # Load data
    data = get_briefing_data()
    
    # ========================================================================
    # TOPBAR SECTION
    # ========================================================================
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        st.markdown("""
        <div class="topbar-section">
            <div class="topbar-title">CJI Sonar — App Intelligence</div>
            <div style="font-size: 12px; color: #7AACBF; margin-bottom: 8px;">
                Live customer signals across market channels — continuously monitored and interpreted
            </div>
            <div style="font-size: 11px; color: #4A7A8F;">v8.20.1 | 2026-03-30 13:37 UTC | LIVE</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="topbar-section">
            <div class="topbar-title">Issues Status</div>
            <div style="margin-bottom: 12px;">
                <div style="font-size: 28px; font-weight: 800; font-family: 'DM Mono', monospace; color: #CC0000;">
                    {data.get('issues_status', {}).get('needs_attention', 0)}
                </div>
                <div style="font-size: 10px; color: #4A7A8F; text-transform: uppercase; letter-spacing: 1px;">
                    Needs Attention
                </div>
            </div>
            <div style="margin-bottom: 12px; border-top: 1px solid #003A5C; padding-top: 8px;">
                <div style="font-size: 28px; font-weight: 800; font-family: 'DM Mono', monospace; color: #F5A623;">
                    {data.get('issues_status', {}).get('watch', 0)}
                </div>
                <div style="font-size: 10px; color: #4A7A8F; text-transform: uppercase; letter-spacing: 1px;">
                    Watch
                </div>
            </div>
            <div style="border-top: 1px solid #003A5C; padding-top: 8px;">
                <div style="font-size: 28px; font-weight: 800; font-family: 'DM Mono', monospace; color: #00AFA0;">
                    {data.get('issues_status', {}).get('performing_well', 0)}
                </div>
                <div style="font-size: 10px; color: #4A7A8F; text-transform: uppercase; letter-spacing: 1px;">
                    Performing Well
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        alert = data.get('executive_alert', {})
        st.markdown(f"""
        <div class="executive-alert">
            <div class="alert-title">⚠️ Executive Alert</div>
            <div class="alert-finding">
                {alert.get('finding', 'No active alert')}
            </div>
            <div class="alert-pills">
                <span class="pill">P0 {alert.get('p0_count', '—')}</span>
                <span class="pill">P1 {alert.get('p1_count', '—')}</span>
                <span class="pill">CAC {alert.get('cac_score', '—')}</span>
                <span class="pill">Clark {alert.get('clark_tier', '—')}</span>
            </div>
            <div style="font-size: 11px; color: #7AACBF; line-height: 1.5;">
                {alert.get('risk_interpretation', 'N/A')}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ========================================================================
    # COMPETITOR TICKER
    # ========================================================================
    st.markdown("<div class='topbar-title' style='margin-top: 24px; margin-left: 0;'>Competitor Sentiment Ticker</div>", unsafe_allow_html=True)
    
    ticker_html = '<div class="competitor-ticker">'
    for comp in data.get('competitor_ticker', []):
        color = '#2a9a5a' if comp.get('sentiment', 0) > 75 else '#e8a030'
        ticker_html += f"""
        <div class="ticker-item">
            <div class="ticker-name" style="color: {color};">{comp.get('name', '?')}</div>
            <div class="ticker-score" style="color: {color};">{comp.get('sentiment', '—')}</div>
        </div>
        """
    ticker_html += '</div>'
    st.markdown(ticker_html, unsafe_allow_html=True)
    
    # ========================================================================
    # METRICS STRIP
    # ========================================================================
    st.markdown("<div class='topbar-title' style='margin-top: 24px; margin-left: 0;'>Journey Health Summary</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: #CC0000;">
                {data.get('issues_status', {}).get('needs_attention', 0)}
            </div>
            <div class="metric-label">Needs Attention</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: #F5A623;">
                {data.get('issues_status', {}).get('watch', 0)}
            </div>
            <div class="metric-label">Watch</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value" style="color: #00AFA0;">
                {data.get('issues_status', {}).get('performing_well', 0)}
            </div>
            <div class="metric-label">Performing Well</div>
        </div>
        """, unsafe_allow_html=True)
    
    # ========================================================================
    # JOURNEY CARDS (LEFT COLUMN)
    # ========================================================================
    st.markdown("<div class='topbar-title' style='margin-top: 24px; margin-left: 0;'>Top Journeys by Risk</div>", unsafe_allow_html=True)
    
    for idx, journey in enumerate(data.get('journey_performance', [])[:5], 1):
        status = journey.get('status', 'UNKNOWN').upper()
        badge_class = 'badge-regression' if 'REGRESSION' in status else ('badge-watch' if 'WATCH' in status else 'badge-performing')
        color = '#CC0000' if 'REGRESSION' in status else ('#F5A623' if 'WATCH' in status else '#00AFA0')
        border_color = f'3px solid {color}'
        
        st.markdown(f"""
        <div class="journey-card" style="border-left: {border_color};">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                <div style="
                    background: #003A5C;
                    width: 32px;
                    height: 32px;
                    border-radius: 8px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: 700;
                    color: #4A7A8F;
                ">#{idx}</div>
                <div class="journey-card-title">{journey.get('name', 'Unknown')}</div>
                <span class="badge {badge_class}">{status}</span>
            </div>
            <div style="font-size: 12px; color: #7AACBF; margin-bottom: 8px; font-style: italic;">
                {journey.get('verdict', 'No verdict available')}
            </div>
            <div style="display: flex; gap: 16px; font-size: 12px; margin-top: 8px;">
                <div>
                    <div style="font-family: 'DM Mono', monospace; font-weight: 700; font-size: 14px;">
                        {journey.get('p1_count', 0)}
                    </div>
                    <div style="color: #4A7A8F; font-size: 10px;">P1 Signals</div>
                </div>
                <div>
                    <div style="font-family: 'DM Mono', monospace; font-weight: 700; font-size: 14px;">
                        {journey.get('p2_count', 0)}
                    </div>
                    <div style="color: #4A7A8F; font-size: 10px;">P2 Signals</div>
                </div>
                <div>
                    <div style="font-family: 'DM Mono', monospace; font-weight: 700; font-size: 14px;">
                        {journey.get('sentiment', '—')}
                    </div>
                    <div style="color: #4A7A8F; font-size: 10px;">Sentiment</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ========================================================================
    # RIGHT PANEL: CHRONICLE + INFERENCES
    # ========================================================================
    st.markdown("<div class='topbar-title' style='margin-top: 24px; margin-left: 0;'>CHRONICLE — Historical Failure Library</div>", unsafe_allow_html=True)
    
    for chr_entry in data.get('chronicle', []):
        st.markdown(f"""
        <div class="chronicle-card">
            <div style="display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
                <span class="chronicle-id">{chr_entry.get('id', '?')}</span>
                <span class="chronicle-bank">{chr_entry.get('bank', '?')}</span>
                <span style="color: #3A6A7F; font-size: 10px;">{chr_entry.get('date', '?')}</span>
            </div>
            <div class="chronicle-type">{chr_entry.get('type', '?')}</div>
            <div style="margin-top: 4px; color: #F5A623; font-size: 11px;">
                {chr_entry.get('impact', 'N/A')}
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    # ========================================================================
    # ACTIVE INFERENCES
    # ========================================================================
    st.markdown("<div class='topbar-title' style='margin-top: 24px; margin-left: 0;'>Active Inferences</div>", unsafe_allow_html=True)
    
    inferences = data.get('active_inferences', [])
    if inferences:
        for inf in inferences:
            st.markdown(f"""
            <div class="inference-card">
                <div class="inference-label">⚠️ Active Inference</div>
                <div style="font-size: 13px; font-weight: 700; color: #E8F4FA; margin-bottom: 8px;">
                    {inf.get('finding', 'N/A')}
                </div>
                <div style="font-size: 11px; color: #7AACBF; line-height: 1.5;">
                    {inf.get('description', 'N/A')}
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("<div style='font-size: 11px; color: #3A6A7F;'>No active inferences.</div>", unsafe_allow_html=True)
    
    # ========================================================================
    # PUBLISH BUTTON
    # ========================================================================
    st.markdown("<div class='topbar-title' style='margin-top: 24px; margin-left: 0;'>Dashboard Controls</div>", unsafe_allow_html=True)
    
    if st.button("📤 Publish Briefing to cjipro.com", key="publish_btn", use_container_width=True):
        try:
            html_content = generate_html_briefing(data)
            output_path = Path(__file__).parent.parent / "outputs" / "briefing.html"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html_content)
            
            st.success(f"""
✅ **briefing.html generated successfully**

Location: `mil/outputs/briefing.html`

Upload this file to your web server to update https://www.cjipro.com/briefing/

Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
            """)
        except Exception as e:
            st.error(f"❌ Publication failed: {str(e)}")
    
    # ========================================================================
    # FOOTER
    # ========================================================================
    st.markdown("""
    <div class="footer-text">
        INFERENCE LOCAL — PUBLISHED OUTPUT ONLY — sonar.cjipro.com/briefing<br>
        Sonar v0.6 — SOVEREIGN — Article Zero — Published 2026-03-30 UTC
    </div>
    """, unsafe_allow_html=True)


def generate_html_briefing(data):
    """Generate static HTML briefing page matching cjipro.com/briefing design."""
    
    alert = data.get('executive_alert', {})
    
    # Build competitor ticker items
    ticker_items = ""
    for comp in data.get('competitor_ticker', []):
        color = '#2a9a5a' if comp.get('sentiment', 0) > 75 else '#e8a030'
        ticker_items += f"""<span class="ticker-item"><span class="ticker-name" style="color:{color};">{comp.get('name', '?')}</span><span class="ticker-score" style="color:{color};">{comp.get('sentiment', '—')}</span><span class="mini-bar"><span class="mini-bar-fill" style="width:{int(comp.get('sentiment', 0)/2.5)}px;background:{color};"></span></span><span class="ticker-delta"><span class="delta-na">—</span></span></span><span class="ticker-sep">-</span>"""
    
    # Build journey row
    journey_row = ""
    for journey in data.get('journey_performance', [])[:5]:
        status = journey.get('status', 'UNKNOWN').upper()
        if 'REGRESSION' in status:
            color = 'var(--red)'
            icon = '↘'
        elif 'WATCH' in status:
            color = 'var(--amber)'
            icon = '→'
        else:
            color = 'var(--green)'
            icon = '↗'
        
        journey_row += f"""<div class="journey-cell" style="border-top:3px solid {color};"><div class="journey-cell-name">{journey.get('name', '?')}</div><div class="journey-cell-score" style="color:{color};">{journey.get('sentiment', '—')}</div><div class="journey-cell-meta"><span class="traj-icon" style="color:{color};">{icon}</span><span class="journey-status-label" style="color:{color};">{status}</span></div></div>"""
    
    # Build journey cards
    journey_cards = ""
    for idx, journey in enumerate(data.get('journey_performance', [])[:5], 1):
        status = journey.get('status', 'UNKNOWN').upper()
        if 'REGRESSION' in status:
            color = 'var(--red)'
            badge_bg = '#2a0a0a'
            left_border = '3px solid var(--red)'
        elif 'WATCH' in status:
            color = 'var(--amber)'
            badge_bg = '#2a1a0a'
            left_border = '3px solid var(--amber)'
        else:
            color = 'var(--green)'
            badge_bg = '#0a1e10'
            left_border = '3px solid var(--green)'
        
        journey_cards += f"""
<div class="journey-card" style="border-left:{left_border};">
  <div class="card-header">
    <span class="rank-num">#{idx}</span>
    <span class="journey-name">{journey.get('name', '?')}</span>
    <span class="badge" style="color:{color};background:{badge_bg};">{status}</span>
  </div>
  <div class="derived-note">SIGNAL ANALYSIS — INFERENCE PENDING</div>
  <div class="verdict-label">VERDICT</div>
  <div class="verdict-text">{journey.get('verdict', 'N/A')}</div>
  <div class="version-delta-row">
    <span class="version-label">v—</span>
    <code class="version-delta" style="color:#6b7088;">— no baseline</code>
  </div>
  <div class="signal-counts">
    <span class="sig-count sig-p1">P1: {journey.get('p1_count', 0)}</span>
    <span class="sig-count sig-p2">P2: {journey.get('p2_count', 0)}</span>
  </div>
  <div class="market-note">Market signal analysis — public app store data - {journey.get('avg_rating', 3.5)} avg rating</div>
</div>
        """
    
    # Build chronicle cards
    chronicle_cards = ""
    for chr_entry in data.get('chronicle', []):
        status_badge = ""
        if chr_entry.get('status') == 'HOLD':
            status_badge = '<span class="chronicle-hold">INFERENCE HOLD</span>'
        elif chr_entry.get('status') == 'ACTIVE':
            status_badge = '<span class="chronicle-active">ACTIVE</span>'
        
        chronicle_cards += f"""
<div class="chronicle-card">
  <div class="chronicle-header">
    <span class="chronicle-id">{chr_entry.get('id', '?')}</span>
    <span class="chronicle-bank">{chr_entry.get('bank', '?')}</span>
    <span class="chronicle-date">{chr_entry.get('date', '?')}</span>
    {status_badge}
  </div>
  <div class="chronicle-type">{chr_entry.get('type', '?')}</div>
  <div class="chronicle-impact">{chr_entry.get('impact', 'N/A')}</div>
</div>
        """
    
    # Build inferences section
    inferences_html = ""
    for inf in data.get('active_inferences', []):
        inferences_html += f"""
<div class="inference-card">
  <div class="inference-header">
    <span class="inference-label">ACTIVE INFERENCE</span>
    <span class="severity-badge severity-p1">P1</span>
  </div>
  <div class="inference-finding">{inf.get('finding', 'N/A')}</div>
  <ul class="blind-spots">
    <li class="blind-spot-item">{inf.get('description', 'N/A')}</li>
  </ul>
</div>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sonar — App Intelligence Briefing</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #00273D; --topbar-bg: #001E30; --ticker-bg: #001828; --journey-bg: #001E30;
  --summary-bg: #002030; --feed-bg: #00273D; --panel-bg: #001828; --card: #002A3F;
  --border: #003A5C; --blue: #00AEEF; --teal: #00AFA0; --amber: #F5A623; --red: #CC0000;
  --text: #E8F4FA; --text-2: #7AACBF; --text-3: #4A7A8F; --muted: #3A6A7F;
  --mono: 'DM Mono', monospace; --sans: 'Plus Jakarta Sans', sans-serif;
}}
html, body {{ background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 14px; line-height: 1.5; }}
a {{ color: var(--blue); text-decoration: none; }}

.topbar {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; padding: 16px 24px; background: var(--topbar-bg); border-bottom: 1px solid var(--border); }}
.topbar-box {{ background: #002A3F; border: 1px solid #003A5C; border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }}
.topbar-box-header {{ padding: 10px 16px; border-bottom: 1px solid #003A5C; }}
.topbar-box-title {{ font-size: 13px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; }}
.topbar-box-body {{ padding: 14px 16px; flex: 1; display: flex; flex-direction: column; gap: 10px; }}
.topbar-logo {{ font-weight: 800; font-size: 17px; letter-spacing: 1.5px; color: var(--blue); margin: 8px 0; }}
.brand-line {{ font-size: 11px; font-weight: 400; color: var(--text-2); line-height: 1.4; }}

.ticker-wrapper {{ overflow: hidden; background: var(--ticker-bg); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); padding: 11px 0; }}
.ticker-track {{ overflow: hidden; white-space: nowrap; }}
.ticker-inner {{ display: inline-flex; align-items: center; gap: 0; }}
.ticker-item {{ display: inline-flex; align-items: center; gap: 6px; padding: 0 20px; }}
.ticker-name {{ font-size: 13px; font-weight: 600; }}
.ticker-score {{ font-family: var(--mono); font-size: 15px; font-weight: 700; }}
.ticker-sep {{ color: var(--border); padding: 0 4px; }}
.mini-bar {{ display: inline-flex; align-items: center; width: 60px; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }}
.mini-bar-fill {{ height: 4px; border-radius: 2px; }}
.delta-na {{ font-family: var(--mono); font-size: 11px; color: var(--text-3); }}

.journey-row {{ display: flex; gap: 1px; background: var(--border); border-top: 1px solid var(--border); border-bottom: 2px solid var(--border); }}
.journey-cell {{ flex: 1; padding: 10px 32px; background: var(--journey-bg); }}
.journey-cell-name {{ font-size: 13px; font-weight: 700; color: var(--text-2); letter-spacing: 1px; margin-bottom: 4px; text-transform: uppercase; }}
.journey-cell-score {{ font-size: 30px; font-weight: 800; font-family: var(--mono); margin-bottom: 4px; }}
.journey-cell-meta {{ display: flex; align-items: center; gap: 6px; }}
.traj-icon {{ font-size: 14px; }}
.journey-status-label {{ font-size: 10px; font-weight: 700; letter-spacing: 0.06em; font-family: var(--mono); }}

.body-wrapper {{ display: grid; grid-template-columns: 1fr 360px; gap: 1px; background: var(--border); min-height: calc(100vh - 200px); }}
.left-col {{ background: var(--feed-bg); padding: 18px 32px 24px; }}
.right-col {{ background: var(--panel-bg); padding: 16px 18px; }}

.metrics-strip {{ display: flex; gap: 1px; background: var(--border); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); margin-bottom: 18px; }}
.metric-card {{ flex: 1; padding: 12px 32px; background: var(--summary-bg); }}
.metric-value {{ font-size: 28px; font-weight: 800; font-family: var(--mono); line-height: 1; margin-bottom: 4px; }}
.metric-label {{ font-size: 10px; font-weight: 700; letter-spacing: 1.5px; color: var(--text-3); text-transform: uppercase; }}

.journey-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin-bottom: 16px; }}
.card-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }}
.rank-num {{ font-family: var(--mono); font-size: 12px; font-weight: 800; color: var(--text-3); background: var(--border); width: 26px; height: 26px; border-radius: 7px; display: flex; align-items: center; justify-content: center; }}
.journey-name {{ font-size: 16px; font-weight: 700; color: var(--text); flex: 1; }}
.badge {{ font-size: 10px; font-weight: 700; letter-spacing: 1px; padding: 2px 10px; border-radius: 12px; }}
.derived-note {{ font-size: 11px; font-family: var(--mono); color: var(--amber); background: rgba(245,166,35,0.08); padding: 3px 8px; border-radius: 12px; margin: 10px 0; }}
.verdict-label {{ font-size: 10px; font-weight: 700; letter-spacing: 2px; color: var(--blue); text-transform: uppercase; margin: 8px 0; }}
.verdict-text {{ font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.65; margin-bottom: 8px; }}
.version-delta-row {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; }}
.version-label {{ font-family: var(--mono); font-size: 10px; font-weight: 700; color: var(--blue); background: var(--border); padding: 2px 6px; border-radius: 4px; }}
.version-delta {{ font-family: var(--mono); font-size: 12px; font-weight: 500; background: var(--border); padding: 2px 8px; border-radius: 4px; }}
.signal-counts {{ display: flex; gap: 8px; margin: 8px 0; }}
.sig-count {{ font-family: var(--mono); font-size: 11px; padding: 1px 6px; border-radius: 12px; }}
.sig-p1 {{ background: rgba(204, 0, 0, 0.15); color: #FF4444; border: 1px solid rgba(204, 0, 0, 0.2); }}
.sig-p2 {{ background: rgba(245, 166, 35, 0.10); color: var(--amber); border: 1px solid rgba(245, 166, 35, 0.2); }}
.market-note {{ font-size: 11px; color: var(--muted); font-style: italic; margin-top: 8px; }}

.panel-section {{ display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }}
.panel-title {{ font-size: 11px; font-weight: 700; letter-spacing: 2px; color: var(--blue); text-transform: uppercase; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}

.chronicle-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; }}
.chronicle-header {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.chronicle-id {{ font-family: var(--mono); font-size: 11px; font-weight: 600; color: #8BBCCC; }}
.chronicle-bank {{ font-size: 11px; font-weight: 600; color: #8BBCCC; }}
.chronicle-date {{ font-size: 10px; color: var(--muted); font-family: var(--mono); }}
.chronicle-type {{ font-size: 10px; color: #3A5A6F; margin-top: 4px; }}
.chronicle-impact {{ font-size: 11px; font-weight: 700; color: var(--amber); font-family: var(--mono); margin-top: 2px; }}
.chronicle-hold {{ font-size: 9px; font-weight: 700; background: rgba(74,122,143,0.2); color: var(--text-3); padding: 1px 5px; border-radius: 8px; }}
.chronicle-active {{ font-size: 9px; font-weight: 700; background: rgba(204,0,0,0.2); color: #FF6666; padding: 1px 5px; border-radius: 8px; }}

.inference-card {{ background: var(--card); border: 1px solid var(--red); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; }}
.inference-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.inference-label {{ font-size: 11px; font-weight: 800; letter-spacing: 2px; color: var(--red); text-transform: uppercase; }}
.severity-badge {{ font-size: 10px; font-weight: 700; padding: 1px 8px; border-radius: 12px; background: rgba(204,0,0,0.15); color: #FF4444; }}
.inference-finding {{ font-size: 13px; font-weight: 700; color: var(--text); line-height: 1.5; }}
.blind-spots {{ list-style: none; margin-top: 8px; }}
.blind-spot-item {{ font-size: 11px; color: #9A8080; line-height: 1.5; }}

.footer {{ background: var(--topbar-bg); border-top: 1px solid var(--border); padding: 16px 32px; font-size: 11px; color: #2A5A6F; }}
.footer-sovereign {{ font-weight: 700; letter-spacing: 1px; color: var(--blue); background: rgba(0,174,239,0.08); padding: 2px 8px; border-radius: 8px; display: inline-block; }}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-box">
    <div class="topbar-box-body">
      <div class="topbar-logo">CJI SONAR — APP INTELLIGENCE</div>
      <div class="brand-line">Live customer signals across market channels — continuously monitored and interpreted</div>
      <div style="font-size: 10px; color: var(--text-3); margin-top: 12px;">v8.20.1 | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | LIVE</div>
    </div>
  </div>
  <div class="topbar-box">
    <div class="topbar-box-header"><span class="topbar-box-title">Issues Status</span></div>
    <div class="topbar-box-body" style="gap: 12px;">
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="font-family: var(--mono); font-size: 40px; font-weight: 800; color: var(--red);">{data.get('issues_status', {}).get('needs_attention', 0)}</div>
        <div style="font-size: 11px; color: var(--text-3); text-transform: uppercase;">Needs Attention</div>
      </div>
      <div style="height: 1px; background: #003A5C;"></div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="font-family: var(--mono); font-size: 40px; font-weight: 800; color: var(--amber);">{data.get('issues_status', {}).get('watch', 0)}</div>
        <div style="font-size: 11px; color: var(--text-3); text-transform: uppercase;">Watch</div>
      </div>
      <div style="height: 1px; background: #003A5C;"></div>
      <div style="display: flex; align-items: center; gap: 12px;">
        <div style="font-family: var(--mono); font-size: 40px; font-weight: 800; color: var(--teal);">{data.get('issues_status', {}).get('performing_well', 0)}</div>
        <div style="font-size: 11px; color: var(--text-3); text-transform: uppercase;">Performing Well</div>
      </div>
    </div>
  </div>
  <div class="topbar-box" style="border: 1px solid var(--red); background: #001828;">
    <div class="topbar-box-header" style="background: #1A0000; border-bottom: 1px solid var(--red);">
      <span style="width: 7px; height: 7px; border-radius: 50%; background: var(--red); flex-shrink: 0;"></span>
      <span class="topbar-box-title" style="color: var(--red); flex: 1;">EXECUTIVE ALERT</span>
      <span style="font-size: 10px; color: #4A2A2A;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</span>
    </div>
    <div class="topbar-box-body">
      <div style="font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 8px;">{alert.get('finding', 'No alert')}</div>
      <div style="display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px; font-family: var(--mono); font-size: 11px;">
        <span style="background: rgba(204,0,0,0.15); color: #FF4444; padding: 2px 8px; border-radius: 10px;">P0 {alert.get('p0_count', '—')}</span>
        <span style="background: rgba(245,166,35,0.12); color: var(--amber); padding: 2px 8px; border-radius: 10px;">P1 {alert.get('p1_count', '—')}</span>
        <span style="background: rgba(0,174,239,0.10); color: var(--blue); padding: 2px 8px; border-radius: 10px;">CAC {alert.get('cac_score', '—')}</span>
      </div>
      <div style="font-size: 11px; color: var(--text-2); line-height: 1.5;">{alert.get('risk_interpretation', 'N/A')}</div>
    </div>
  </div>
</div>

<div class="ticker-wrapper">
  <div class="ticker-track"><div class="ticker-inner">{ticker_items}{ticker_items}</div></div>
</div>

<div class="journey-row">{journey_row}</div>

<div class="body-wrapper">
  <div class="left-col">
    <div class="metrics-strip">
      <div class="metric-card"><div class="metric-value" style="color: var(--red);">{data.get('issues_status', {}).get('needs_attention', 0)}</div><div class="metric-label">Needs Attention</div></div>
      <div class="metric-card"><div class="metric-value" style="color: var(--amber);">{data.get('issues_status', {}).get('watch', 0)}</div><div class="metric-label">Watch</div></div>
      <div class="metric-card"><div class="metric-value" style="color: var(--teal);">{data.get('issues_status', {}).get('performing_well', 0)}</div><div class="metric-label">Performing Well</div></div>
    </div>
    {journey_cards}
  </div>
  <div class="right-col">
    <div class="panel-section">
      <div class="panel-title">CHRONICLE — Failure Library</div>
      {chronicle_cards}
    </div>
    <div class="panel-section">
      <div class="panel-title">ACTIVE INFERENCES</div>
      {inferences_html}
    </div>
  </div>
</div>

<div class="footer">
  INFERENCE LOCAL — PUBLISHED OUTPUT ONLY — sonar.cjipro.com/briefing<br>
  Sonar v0.6 — <span class="footer-sovereign">SOVEREIGN</span> — Article Zero — Published {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}
</div>

</body>
</html>"""
    
    return html


if __name__ == "__main__":
    render_dashboard()
