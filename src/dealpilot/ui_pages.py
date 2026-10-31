"""Four business pages and a secondary developer toolbox."""
from decimal import Decimal
import streamlit as st
from .catalog import CATALOG
from .crm import CRM
from .policies import POLICIES, VERSION
from .simulation import scenarios, run
from .verification import verify
from .ui_data import label, sar, load_deals
from .ui_components import deal_detail


def dashboard(db, navigate):
    deals = load_deals(db)
    st.title("Dashboard")
    st.write("Your presales pipeline, with a clear next step for every deal.")
    from .agent_ui import begin_opportunity
    st.button("New Opportunity", type="primary", key="dashboard_new", on_click=begin_opportunity, args=(navigate,))
    ready = [d for d in deals if d["status"] == "OFFER_READY"]
    pending = [d for d in deals if d["status"] == "APPROVAL_PENDING"]
    amount = sum((Decimal(d["quote"]["total"]) for d in ready if d["quote"]), Decimal("0"))
    cols = st.columns(4)
    cols[0].metric("Saved deals", len(deals))
    cols[1].metric("Offers ready", len(ready))
    cols[2].metric("Awaiting approval", len(pending))
    cols[3].metric("Finalized offer value", sar(amount))
    st.caption("All figures reflect saved demo records, including sample scenarios and historical inquiry revisions. Offer value is not revenue.")
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Recent deals")
        if not deals:
            st.info("Your pipeline is ready. Create your first opportunity to get started.")
        for deal in deals[:5]:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.text(deal["name"])
                c1.caption(f'{label(deal["status"])} · {deal["source"]} · Revision {deal["revision"]}')
                c1.write(sar((deal["quote"] or {}).get("total")))
                if c2.button("View deal", key="recent_" + deal["key"]):
                    st.session_state["deal_choice"] = deal["key"]
                    navigate("Deals")
                    st.rerun()
    with right:
        st.subheader("Approval inbox")
        if pending:
            st.write(f'{len(pending)} draft offer(s) need management review.')
            st.caption("Discounts above 10% cannot be finalized until the exact quote is approved.")
            st.button("Review approvals", on_click=navigate, args=("Approvals",))
        else:
            st.success("No offers are waiting for approval.")
        st.subheader("From inquiry to offer")
        st.write("1. Share the customer's inquiry\n\n2. Review the solution and quote\n\n3. Obtain approval when needed\n\n4. Finalize and review the saved offer")


def deals_page(db, navigate):
    st.title("Deals")
    st.write("Review customer requirements, commercial decisions and saved proposals in one place.")
    deals = load_deals(db)
    left, middle, right = st.columns([2, 1, 1])
    search = left.text_input("Search companies", placeholder="Find a customer…")
    statuses = sorted({d["status"] for d in deals}, key=label)
    status = middle.selectbox("Deal status", ["All statuses"] + statuses, format_func=lambda v:label(v) if v != "All statuses" else v)
    source = right.selectbox("Source", ["All sources", "AI-assisted", "Sample / structured"])
    filtered = [d for d in deals if search.casefold() in d["name"].casefold() and (status == "All statuses" or d["status"] == status) and (source == "All sources" or d["source"] == source)]
    if not filtered:
        st.info("No deals match these filters. Clear the filters or create a new opportunity.")
        return
    st.dataframe([{"Company":d["name"], "Status":label(d["status"]), "Quote":sar((d["quote"] or {}).get("total")), "Source":d["source"], "Revision":d["revision"]} for d in filtered], use_container_width=True, hide_index=True)
    keys = [d["key"] for d in filtered]
    if st.session_state.get("deal_choice") not in keys:
        st.session_state["deal_choice"] = keys[0]
    names = {d["key"]:f'{d["name"]} · {label(d["status"])} · Revision {d["revision"]} · Record {i+1}' for i,d in enumerate(filtered)}
    choice = st.selectbox("Open a deal", keys, format_func=names.get, key="deal_choice")
    deal = next(d for d in filtered if d["key"] == choice)
    run_state = deal["run"]
    if run_state and (run_state.get("failed_node") or run_state["status"] == "RUNNING"):
        if st.button("Retry saved inquiry", type="primary"):
            try:
                from .agents import AgentWorkflow
                from .llm import get_provider
                from .models import Customer
                request = run_state["request"]
                AgentWorkflow(db, get_provider(load_local_env=True)).start(request["text"], Customer.model_validate(request["customer"]), request["revision"], retry=True)
                st.rerun()
            except Exception:
                st.error("The retry could not finish. Saved progress is retained; ask your administrator to check the connection.")
    deal_detail(db, deal, navigate)


def approvals_page(db, navigate):
    st.title("Approvals")
    st.write("Review discount requests, then resume approved offers for final validation.")
    st.caption("Demo role selection represents a human decision. It is not production authentication.")
    role = st.selectbox("Reviewing as", ["sales", "management"], format_func=lambda v:"Sales representative" if v == "sales" else "Manager")
    include_complete = st.checkbox("Show completed decisions", value=False)
    deals = load_deals(db)
    approvals = db.list("approval")
    visible = [a for a in approvals if include_complete or a["status"] == "PENDING" or (a["status"] == "APPROVED" and (db.get("quote", a["quote_id"]) or {}).get("status") != "FINAL")]
    if not visible:
        st.success("Your approval queue is clear.")
        return
    for approval in visible:
        deal = next((d for d in deals if d["opportunity"] and d["opportunity"]["id"] == approval["opportunity_id"]), None)
        quote = db.get("quote", approval["quote_id"])
        with st.container(border=True):
            st.subheader(deal["name"] if deal else "Customer record needs review")
            st.caption(f'{approval["status"].capitalize()} · {deal["source"] if deal else "Demo record"}')
            if not quote:
                st.error("The exact quotation is missing. Ask an administrator to investigate.")
                continue
            a,b,c = st.columns(3)
            a.metric("Requested discount", f'{quote["discount_percent"]}%')
            b.metric("Offer including VAT", sar(quote["total"]))
            c.metric("Discount amount", sar(quote["discount_amount"]))
            st.write("Reason: The requested discount exceeds the 10% sales authorization limit.")
            st.caption("Risk: An unapproved discount would breach sales authorization. Management approval applies only to this exact quote; pricing and delivery checks still apply.")
            if approval["status"] == "PENDING":
                st.warning("Awaiting management decision. The offer remains DRAFT.")
                left, right = st.columns(2)
                for column, decision, text in [(left,"APPROVED","Approve"), (right,"REJECTED","Reject")]:
                    if column.button(text, key=f'{approval["id"]}:{decision}', disabled=role != "management"):
                        try:
                            CRM(db).decide_approval(approval["id"], decision, role, f'{approval["id"]}:{decision}')
                            st.rerun()
                        except Exception:
                            st.error("The decision could not be saved. Check your role and the current approval state.")
                if role != "management":
                    st.caption("A manager must approve or reject this request.")
            elif approval["status"] == "REJECTED":
                st.warning("Changes requested. Revise the inquiry before requesting another offer.")
            elif quote["status"] == "FINAL":
                st.success("Finalized demo offer saved to CRM.")
            else:
                st.info("Management approved this quote. Resume the workflow to validate and finalize it. Approval alone does not finalize an offer.")
                if st.button("Resume Workflow", type="primary", key="resume_"+approval["id"]):
                    try:
                        if deal and deal["run"]:
                            from .agents import AgentWorkflow
                            resumed = AgentWorkflow(db).resume(deal["run"]["run_id"])
                            if resumed["status"] != "OFFER_READY":
                                st.error("The offer did not pass final validation. Open the deal to review the record checks before retrying.")
                                continue
                        else:
                            CRM(db).finalize(approval["opportunity_id"], approval["quote_id"])
                        st.rerun()
                    except Exception:
                        st.error("Finalization is blocked. The exact quote, management approval and commercial checks must still be valid.")
            if deal and st.button("Open deal", key="approval_deal_"+approval["id"]):
                st.session_state["deal_choice"] = deal["key"]
                navigate("Deals")
                st.rerun()
            with st.expander("Advanced Details"):
                st.json({"approval":approval, "quote":quote})


def admin_page(db, tool):
    st.title(tool)
    st.caption("Admin / Developer Tools · Technical evidence and deterministic demo scenarios")
    if tool == "Catalog":
        for p in CATALOG.values():
            with st.expander(p.name):
                st.write(sar(p.price), "per user / year" if p.per_user else "one-time service")
                for cap in p.capabilities:
                    st.write(cap.description)
                st.write(f"Delivery lead time: {p.lead_days} calendar days")
                st.json(p.model_dump(mode="json"))
    elif tool == "Company Policies":
        st.caption("Policy version " + VERSION)
        for name, text in POLICIES.items():
            st.subheader(name.replace("_", " ").title())
            st.write(text)
    elif tool == "Audit Log":
        st.dataframe(db.audits(), hide_index=True, use_container_width=True)
    elif tool == "Verification":
        findings = verify(db)
        if findings:
            st.error("Persisted records need review.")
            for finding in findings:
                st.text(finding)
        else:
            st.success("Persisted quotes, proposals and approvals reconcile.")
    elif tool == "Test Scenarios":
        cases = scenarios()
        selected = st.selectbox("Deterministic test scenario", [l for l,_ in cases])
        inquiry = next(i for l,i in cases if l == selected)
        st.info("Deterministic simulation data. This does not call an AI model.")
        if st.button("Run test scenario"):
            st.json(run(db, inquiry))
        st.json(inquiry.model_dump(mode="json"))
        result = db.get("result", f"{inquiry.id}:r{inquiry.revision}")
        if result:
            st.json(result)
