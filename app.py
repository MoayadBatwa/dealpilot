"""Run with python -m streamlit run app.py."""
import os
import sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path(__file__).parent / "src"))
import streamlit as st
from dealpilot.database import Database
from dealpilot.simulation import scenarios, seed, run
from dealpilot.models import Customer, Inquiry, Requirement
from dealpilot.catalog import CATALOG
from dealpilot.crm import CRM
from dealpilot.verification import verify
from dealpilot.policies import POLICIES, VERSION

st.set_page_config(page_title="DealPilot AI | Presales", page_icon="◈", layout="wide")
st.markdown('''<style>.stApp{background:#0b1220} div[data-testid="stMetric"]{background:#152238;padding:18px;border-radius:12px} h1{letter-spacing:-1.5px}</style>''', unsafe_allow_html=True)
db = Database(os.environ.get("DEALPILOT_DB", "data/dealpilot.sqlite3"))
seed(db)
crm = CRM(db)
st.title("◈ DealPilot AI")
st.caption("HUMAIN AI Builder • Autonomous Enterprise • Deterministic controls + optional live AI")
st.info("SIMULATED DATA ONLY · Fictional Saudi companies · SAR · Optional Groq / OpenAI mode in AI Agent Workspace · No external CRM, email, or payments")
opps = db.list("opportunity")
approvals = db.list("approval")
quotes = db.list("quote")
cols = st.columns(4)
cols[0].metric("Opportunities", len(opps))
cols[1].metric("Offers ready", sum(o["status"] == "OFFER_READY" for o in opps))
cols[2].metric("Pending approvals", sum(a["status"] == "PENDING" for a in approvals))
cols[3].metric("Final offer value · SAR", f'{sum((Decimal(q["total"]) for q in quotes if q["status"] == "FINAL"), Decimal("0")):,.2f}')
tabs = st.tabs(["Workspace", "New inquiry", "Approvals", "Catalog & policies", "CRM & audit", "Verification", "AI Agent Workspace"])
with tabs[0]:
    st.subheader("Opportunity pipeline")
    st.dataframe(opps, use_container_width=True, hide_index=True)
    cases = scenarios()
    label = st.selectbox("Inspect a seeded scenario", [l for l,_ in cases])
    inquiry = next(i for l,i in cases if l == label)
    left, right = st.columns([1, 2])
    with left:
        st.subheader("Structured inquiry")
        st.json(inquiry.model_dump(mode="json"))
        if st.button("Run / replay this simulation", type="primary"):
            st.json(run(db, inquiry))
        result = db.get("result", f"{inquiry.id}:r{inquiry.revision}")
        if result:
            st.write("Workflow result", result)
        elif inquiry.simulate_crm_failure:
            st.warning("CRM outage is simulated. The failed opportunity write leaves no partial record; retry reproduces the outage.")
    with right:
        st.subheader("Recommendation, pricing & proposal")
        if result and result.get("quote_id"):
            quote = db.get("quote", result["quote_id"])
            st.dataframe(quote["lines"], hide_index=True)
            st.write({k:v for k,v in quote.items() if k != "lines"})
            proposal = db.get("proposal", f'proposal-{quote["id"]}')
            st.text(proposal["text"])
            st.download_button("Download simulated proposal", proposal["text"], file_name=f'{proposal["id"]}.txt')
        elif result:
            st.warning("; ".join(result["issues"]))
            st.write("Candidate product IDs", result["products"])
with tabs[1]:
    st.subheader("Run a complete simulated workflow")
    with st.form("inquiry"):
        request_id = st.text_input("Stable inquiry ID", "demo-custom-001")
        company = st.text_input("Fictional company", "Diriyah Demo Services")
        sector = st.selectbox("Sector", ["retail", "manufacturing", "services"])
        capabilities = st.multiselect("Required capabilities", [c.code for p in CATALOG.values() for c in p.capabilities], default=["crm", "bilingual"])
        users = st.number_input("Users", 1, 10000, 10)
        budget = st.text_input("VAT-inclusive budget · SAR (blank = unknown)", "100000")
        discount = st.text_input("Requested discount %", "0")
        days = st.number_input("Requested calendar days", 1, 3650, 60)
        revision = st.number_input("Revision (increment when requirements change)", 1, 1000, 1)
        notes = st.text_area("Untrusted customer notes (stored only)")
        submit = st.form_submit_button("Execute simulation", type="primary")
    if submit:
        try:
            inquiry = Inquiry(id=request_id, customer=Customer(id=f"customer-{request_id}", name=company, sector=sector), requirements=[Requirement(capability=c) for c in capabilities], users=users, budget=Decimal(budget) if budget else None, discount=Decimal(discount), requested_days=days, revision=revision, notes=notes)
            st.json(run(db, inquiry))
            st.success("Saved. Inspect CRM records and approvals in their tabs.")
        except (ValueError, ArithmeticError) as exc:
            st.error(str(exc))
with tabs[2]:
    st.subheader("Simulated management approval queue")
    st.caption("Role selection is a local demonstration, not authentication. Approval alone does not finalize an offer.")
    role = st.selectbox("Simulated role", ["sales", "management"])
    for approval in db.list("approval"):
        with st.container(border=True):
            st.write(approval)
            if approval["status"] == "PENDING":
                c1,c2 = st.columns(2)
                for col, decision in [(c1,"APPROVED"),(c2,"REJECTED")]:
                    if col.button(decision.title(), key=f'{approval["id"]}-{decision}'):
                        try:
                            crm.decide_approval(approval["id"], decision, role, f'{approval["id"]}:{decision}')
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
            if approval["status"] == "APPROVED" and st.button("Validate and finalize simulated offer", key=approval["id"]):
                try:
                    crm.finalize(approval["opportunity_id"], approval["quote_id"])
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
with tabs[3]:
    st.subheader("Fictional enterprise catalog")
    st.caption("Software prices are annual per user where indicated; services are one-time. Dependency delivery times are added sequentially.")
    for p in CATALOG.values():
        with st.expander(f"{p.name} · SAR {p.price:,.2f}" ):
            st.json(p.model_dump(mode="json"))
    st.subheader(f"Company policies · {VERSION}")
    st.json(POLICIES)
with tabs[4]:
    kind = st.selectbox("Persisted record type", ["opportunity", "inquiry", "quote", "proposal", "approval", "task", "result"])
    st.json(crm.retrieve_records(kind))
    st.subheader("Audit timeline · UTC")
    st.dataframe(db.audits(), use_container_width=True, hide_index=True)
with tabs[5]:
    issues = verify(db)
    if issues:
        st.error(f"{len(issues)} discrepancies detected")
        st.write(issues)
    else:
        st.success("Persisted proposals, quotes, approvals and opportunity states reconcile.")
    st.caption("Verifier is read-only and recalculates from persisted structured inquiries. It does not call the workflow.")

with tabs[6]:
    from dealpilot.agent_ui import render_ai_workspace
    render_ai_workspace(db)
