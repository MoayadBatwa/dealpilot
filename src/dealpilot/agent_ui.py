"""Primary opportunity intake. All execution delegates to the existing graph."""
import streamlit as st
from .database import Database
from .models import Customer
from .llm import get_provider
from .ui_components import progress_view, deal_detail
from .ui_data import load_deals


def begin_opportunity(navigate):
    st.session_state.pop("opportunity_revision_context", None)
    st.session_state.pop("new_opportunity_result", None)
    navigate("New Opportunity")


def render_new_opportunity(db: Database, navigate) -> None:
    st.title("New Opportunity")
    st.write("Turn a customer inquiry into a qualified solution and a proposal you can act on.")
    try:
        provider = get_provider(load_local_env=True)
        available = provider.status()["available"]
    except ValueError:
        provider, available = None, False
    if available:
        st.caption(f'Analysis configured · {provider.status()["name"]} · Connection is checked when you analyze; inquiry data is sent to this provider.')
    else:
        st.warning("AI analysis is unavailable. Ask your administrator to configure the connection. Saved deals remain available.")
    context = st.session_state.get("opportunity_revision_context")
    if context:
        st.info(f'Revising {context["customer"]["name"]} · Current revision {context["revision"]}. Changed details will be saved as the next revision; the earlier offer is retained.')
        if st.button("Start a separate opportunity"):
            st.session_state.pop("opportunity_revision_context", None)
            st.session_state.pop("new_opportunity_result", None)
            st.rerun()
    form_key = "new_opportunity_" + (context["run_id"] if context else "fresh")
    with st.form(form_key):
        left, right = st.columns([2, 1])
        company = left.text_input("Company name", value=context["customer"]["name"] if context else "", placeholder="e.g. Diriyah Demo Services")
        sectors = ["retail", "manufacturing", "services"]
        sector = right.selectbox("Sector", sectors, index=sectors.index(context["customer"]["sector"]) if context else 2, format_func=str.title)
        text = st.text_area("What does the customer need?", value=context["text"] if context else "", height=180,
                            placeholder="We need CRM integration and Arabic / English support for 10 users. Our budget is SAR 100,000 including VAT, and we need delivery within 60 calendar days. We request a 15% discount.")
        st.caption("Include the required features, user count, budget in SAR, a delivery target (for example, within six weeks), and any requested discount. Use fictional data for this demo.")
        submitted = st.form_submit_button("Analyze opportunity", type="primary", disabled=not available)
    if submitted:
        if not company.strip() or not text.strip():
            st.error("Enter a company name and the customer's inquiry to continue.")
        else:
            customer = Customer(id=context["customer"]["id"] if context else "ai-customer", name=company.strip(), sector=sector)
            unchanged = bool(context and context["text"] == text and context["customer"] == customer.model_dump(mode="json"))
            revision = context["revision"] + (0 if unchanged else 1) if context else 1
            observed = []
            display = st.empty()
            def on_event(event):
                observed.append(event)
                with display.container():
                    progress_view(observed)
            try:
                from .agents import AgentWorkflow
                with st.spinner("Reviewing the inquiry and preparing your opportunity…"):
                    state = AgentWorkflow(db, provider, on_event).start(text, customer, revision)
                st.session_state["new_opportunity_result"] = state["run_id"]
                if context and state["request"]["revision"] != context["revision"]:
                    st.session_state["opportunity_revision_context"] = {**state["request"], "run_id":state["run_id"]}
                    st.rerun()
            except Exception:
                st.error("The analysis could not finish. Your saved progress is retained. Open Deals to review or retry it.")
    active = st.session_state.get("new_opportunity_result")
    deal = next((d for d in load_deals(db) if d["run"] and d["run"]["run_id"] == active), None)
    if deal:
        st.divider()
        st.subheader("Your opportunity")
        if not submitted:
            with st.expander("Review completed steps"):
                progress_view(deal["run"].get("trace", []))
        if st.button("Open in Deals", type="primary"):
            st.session_state["deal_choice"] = deal["key"]
            navigate("Deals")
            st.rerun()
        deal_detail(db, deal, navigate)
