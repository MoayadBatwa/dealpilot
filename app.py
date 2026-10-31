"""DealPilot's business workspace. Run: python -m streamlit run app.py."""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
import streamlit as st
from dealpilot.database import Database
from dealpilot.simulation import seed
from dealpilot.ui_pages import dashboard, deals_page, approvals_page, admin_page
from dealpilot.agent_ui import render_new_opportunity, begin_opportunity

st.set_page_config(page_title="DealPilot AI | Sales Workspace", page_icon="D", layout="wide")
st.markdown("""<style>
.block-container {max-width:1280px;padding-top:4rem;padding-bottom:3rem}
h1 {letter-spacing:-1.2px;font-weight:700} h2,h3 {letter-spacing:-.4px}
[data-testid="stSidebar"] {background:#101e35}
[data-testid="stSidebar"] * {color:#edf2fa}
[data-testid="stSidebar"] [data-baseweb="select"] * {color:#15243d}
[data-testid="stMetric"] {border:1px solid #e1e7f0;border-radius:12px;padding:18px;background:#fff}
[data-testid="stMetricLabel"] {color:#526078}
[data-testid="stMetricValue"] {font-size:1.65rem;color:#132540}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:12px}
div.stButton > button[kind="primary"] {background:#214fc0;border-color:#214fc0}
</style>""", unsafe_allow_html=True)
db = Database(os.environ.get("DEALPILOT_DB", "data/dealpilot.sqlite3"))
seed(db)


def navigate(page):
    # Apply on the next rerun, before navigation widgets are instantiated.
    st.session_state["_next_page"] = page


def close_admin():
    st.session_state["admin_tool"] = "Choose a tool"


if "_next_page" in st.session_state:
    st.session_state["page"] = st.session_state.pop("_next_page")
    st.session_state["admin_tool"] = "Choose a tool"

if "_next_tool" in st.session_state:
    st.session_state["admin_tool"] = st.session_state.pop("_next_tool")

if "_focus_deal" in st.session_state:
    st.session_state["deal_choice"] = st.session_state.pop("_focus_deal")
    st.session_state["deal_status_filter"] = "All statuses"
    st.session_state["deal_source_filter"] = "All sources"
    st.session_state["deal_search"] = ""

with st.sidebar:
    st.markdown("## DealPilot AI")
    st.caption("SALES WORKSPACE")
    st.button("New Opportunity", type="primary", use_container_width=True, key="sidebar_new", on_click=begin_opportunity, args=(navigate,))
    page = st.radio("Navigation", ["Dashboard", "New Opportunity", "Deals", "Approvals"], key="page", label_visibility="collapsed", on_change=close_admin)
    st.divider()
    st.caption("HUMAIN AI Builder\n\nAutonomous Enterprise")
    with st.expander("Admin / Developer Tools"):
        tool = st.selectbox("Tools", ["Choose a tool", "Catalog", "Company Policies", "Audit Log", "Verification", "Test Scenarios"], key="admin_tool")
st.caption("DEMO ENVIRONMENT · Fictional customer data · No external CRM, email or contractual commitments")
if tool != "Choose a tool":
    admin_page(db, tool)
elif page == "Dashboard":
    dashboard(db, navigate)
elif page == "New Opportunity":
    render_new_opportunity(db, navigate)
elif page == "Deals":
    deals_page(db, navigate)
else:
    approvals_page(db, navigate)
