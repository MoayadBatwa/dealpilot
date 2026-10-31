"""Optional AI UI; production UI always constructs the real provider."""
import streamlit as st
from .database import Database
from .models import Customer
from .llm import get_provider


def render_ai_workspace(db: Database) -> None:
    st.subheader("AI Agent Workspace")
    try:
        provider = get_provider(load_local_env=True)
    except ValueError:
        st.error("Invalid DEALPILOT_LLM_PROVIDER: choose groq or openai.")
        return
    status = provider.status()
    st.write({"provider":status["name"], "model":status["model"], "key_configured":status["available"]})
    if status["available"]:
        st.info(status["message"] + f" Inquiry data will be sent to {status['name']} when you run AI agents.")
    else:
        st.warning(status["message"])
    st.caption("Three live model specialists: extraction, catalog selection and grounded draft composition. Pricing, routing, CRM authorization and verification execute in code. No model can approve a discount.")
    with st.form("ai_inquiry"):
        company = st.text_input("Fictional AI customer", "Diriyah AI Demo Services")
        sector = st.selectbox("AI customer sector", ["retail", "manufacturing", "services"])
        revision = st.number_input("AI inquiry revision", 1, 1000, 1)
        text = st.text_area("Natural-language customer inquiry", "We need CRM integration and bilingual Arabic/English support for 10 users. Our budget is SAR 100,000 including VAT. Please deliver within 60 calendar days. We request a 15% discount.", height=160)
        st.caption("State budget, user count and delivery in calendar days explicitly. Use digits (100,000 rather than 100k). Missing fields stop the workflow for clarification.")
        retry = st.checkbox("Retry a failed or interrupted run with the same input (bounded; CRM writes remain idempotent)")
        submitted = st.form_submit_button("Run AI Agents", type="primary", disabled=not status["available"])
    live_trace = st.empty()

    def on_event(event):
        # Events arrive only after an actual graph node attempt completes.
        live_trace.write(f'Step {event["sequence"]}: {event["node"]} · {event["outcome"]} · {event["elapsed_ms"]} ms')

    if submitted:
        try:
            from .agents import AgentWorkflow
            with st.spinner("Executing LangGraph nodes with the configured provider…"):
                customer = Customer(id="ai-customer", name=company, sector=sector)
                state = AgentWorkflow(db, provider, on_event).start(text, customer, int(revision), retry=retry)
            st.session_state["active_ai_run"] = state["run_id"]
        except Exception as exc:
            # Never render raw SDK exceptions or credentials.
            st.error(f"AI workflow could not execute ({type(exc).__name__}). Check configuration, dependencies and persisted records.")
    runs = db.list("agent_run")
    if not runs:
        st.caption("No AI workflow has executed. Deterministic seeded cases are available in Workspace.")
        return
    ids = [r["run_id"] for r in runs]
    active = st.session_state.get("active_ai_run")
    selected = st.selectbox("Persisted AI run", ids, index=ids.index(active) if active in ids else 0,
                            format_func=lambda id: f'{id} · {next(r["status"] for r in runs if r["run_id"] == id)}')
    state = db.get("agent_run", selected)
    st.write("Workflow status", state["status"])
    if state.get("errors"):
        st.error("; ".join(state["errors"]))
    if state.get("pending_approval"):
        approval = db.get("approval", state["pending_approval"])
        st.warning("Approval pending workflow: the offer cannot finalize until the exact management approval is persisted. Use the existing Approvals tab.")
        st.json(approval)
        if st.button("Resume AI workflow after approval", key=f"resume-{selected}"):
            try:
                from .agents import AgentWorkflow
                AgentWorkflow(db, provider, on_event).resume(selected)
                st.rerun()
            except ValueError:
                st.error("Resume blocked: exact management approval is required, and the quote must still pass deterministic validation.")
    st.subheader("Actual execution trace")
    st.caption("Operational summaries only; these are observed node attempts, not model chain-of-thought. Failed attempts and retries are included.")
    st.dataframe(state.get("trace", []), hide_index=True, use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.write("Extracted requirements and source evidence")
        st.json(state.get("extraction"))
        st.write("Validated product recommendation", state.get("selected_products", []))
        st.write("Policy decisions", state.get("policy_findings", []))
        if state.get("quote"):
            result = state.get("execution_results") or {}
            quote = db.get("quote", result.get("quote_id", "")) or state["quote"]
            st.write("Deterministic quote")
            st.json(quote)
    with right:
        if state.get("proposal"):
            st.text(state["proposal"]["text"])
            st.caption("AI draft uses model-selected section structure and immutable validated fact blocks. The canonical CRM proposal remains governed by the existing deterministic template.")
        st.write("CRM execution", state.get("execution_results"))
        st.write("Verification report", state.get("verification_findings", []))
        if state.get("phase") == "verification" and not state.get("verification_findings"):
            st.success("Persisted records reconcile for this completed verification pass.")
