"""Business-facing display components, with technical evidence kept expandable."""
import streamlit as st
from .catalog import CATALOG
from .ui_data import label, sar, NEXT_ACTIONS
from .deal_insights import business_status, decision_explanation, product_reasons, workflow_timeline, requested_discount

CAPABILITIES = {"crm":"Sales CRM", "crm_integration":"CRM integration", "bilingual":"Arabic & English support", "analytics":"Sales analytics", "customer_service":"Customer service", "migration":"Data migration", "regulated_setup":"Regulated workflow setup"}
STEPS = [("intake", "Understand the inquiry"), ("solution", "Recommend a solution"), ("commercial", "Validate commercial terms"), ("proposal", "Prepare the proposal"), ("execution", "Save the deal"), ("verification", "Check saved records")]


def progress_view(trace):
    """Report actual attempts; persisted artifacts determine business success."""
    for node, title in STEPS:
        attempts = [e for e in trace if e["node"] == node]
        if not attempts:
            state = "Not reached"
        elif attempts[-1].get("error"):
            state = "Needs attention"
        else:
            state = "Processed"
        st.write(f"{title} — {state}")


def next_action(db, deal, navigate):
    """One primary action selected from persisted business state."""
    state = business_status(deal)
    st.markdown("#### Recommended Next Action")
    message = NEXT_ACTIONS.get(deal["status"], "Review customer requirements and follow-up tasks before proceeding.")
    if state == "Completed":
        st.success("Review or download the finalized demo offer and proposal below. Saved records have passed verification; no external submission has been made.")
        if deal.get("proposal"):
            st.download_button("Download finalized proposal", deal["proposal"]["text"], "dealpilot-proposal.txt", type="primary", key="next_download")
        return
    if state == "Needs Information":
        message = "Confirm the missing customer information shown in Gaps & risks, then update the inquiry."
    if state == "Ready for Review" and deal.get("offer_final"):
        message = "Check the current saved records before marking the customer-to-deal process complete."
    if state in ("Pending Approval", "Approved", "Rejected", "Blocked"):
        st.warning(message)
    else:
        st.info(message)
    if deal.get("integrity_findings"):
        st.warning("The saved commercial records need an administrator's review. Do not use this offer.")
        st.button("Review record checks", type="primary", key="next_admin", on_click=_open_verification, args=(navigate,))
    elif deal["status"] == "VERIFICATION_FAILED" and deal.get("opportunity"):
        if st.button("Recheck saved records", type="primary", key="next_recheck"):
            try:
                if deal["run"] and deal["result"].get("status") == "OFFER_READY":
                    from .agents import AgentWorkflow
                    AgentWorkflow(db).resume(deal["run"]["run_id"])
                else:
                    _check_records(db, deal)
                _refresh_deal(deal)
            except Exception:
                st.error("The check could not finish. Saved progress is retained for administrator review.")
    elif state == "Pending Approval":
        st.button("Review approval", type="primary", key="detail_approval", on_click=navigate, args=("Approvals",))
    elif state == "Approved":
        if st.button("Resume Workflow", type="primary", key="detail_resume"):
            try:
                if deal["run"]:
                    from .agents import AgentWorkflow
                    state = AgentWorkflow(db).resume(deal["run"]["run_id"])
                    if state["status"] != "OFFER_READY":
                        st.error("Final validation did not pass. Review the updated deal findings before retrying.")
                        return
                else:
                    from .crm import CRM
                    CRM(db).finalize(deal["opportunity"]["id"], deal["quote"]["id"])
                    _check_records(db, deal)
                _refresh_deal(deal)
            except Exception:
                st.error("The offer cannot finalize: the exact management approval and commercial terms must still be valid.")
    elif state == "Ready for Review" and deal["opportunity"]:
        if st.button("Check saved records", type="primary", key="next_verify"):
            try:
                _check_records(db, deal)
                _refresh_deal(deal)
            except Exception:
                st.error("The record check could not finish. Your saved deal is unchanged; retry or ask an administrator to investigate.")
    elif state in ("Needs Information", "Rejected", "Blocked") and deal["status"] != "PROVIDER_UNAVAILABLE":
        st.button("Update customer details", type="primary", key="next_revise", on_click=_revise, args=(deal, navigate))
    elif deal["run"] and (deal["run"].get("failed_node") or deal["run"]["status"] == "RUNNING"):
        if st.button("Retry saved inquiry", type="primary", key="next_retry"):
            try:
                from .agents import AgentWorkflow
                from .llm import get_provider
                from .models import Customer
                request = deal["run"]["request"]
                AgentWorkflow(db, get_provider(load_local_env=True)).start(request["text"], Customer.model_validate(request["customer"]), request["revision"], retry=True)
                _refresh_deal(deal)
            except Exception:
                st.error("The retry could not finish. Saved progress is retained for another attempt.")
    else:
        st.button("Review company policies", type="primary", key="next_policies", on_click=_open_policies, args=(navigate,))


def _refresh_deal(deal):
    st.session_state["_focus_deal"] = deal["key"]
    st.rerun()


def _revise(deal, navigate):
    if deal["run"]:
        request = deal["run"]["request"]
        source = deal["run"]["run_id"]
    else:
        inquiry = deal["inquiry"]
        parts = ["Required features: " + ", ".join(CAPABILITIES.get(r["capability"], r["capability"]) for r in inquiry.get("requirements", [])) + "."]
        if inquiry.get("users"):
            parts.append(f'Users: {inquiry["users"]}.')
        if inquiry.get("budget") is not None:
            parts.append(f'Budget including VAT: SAR {inquiry["budget"]}.')
        if inquiry.get("requested_days"):
            parts.append(f'Delivery required within {inquiry["requested_days"]} calendar days.')
        if inquiry.get("discount") is not None:
            parts.append(f'Requested discount: {inquiry["discount"]}%.')
        request = {"text":" ".join(parts), "customer":deal["customer"], "revision":deal["revision"]}
        source = deal["key"]
    st.session_state["opportunity_revision_context"] = {**request, "run_id":source}
    st.session_state.pop("new_opportunity_result", None)
    navigate("New Opportunity")


def _open_verification(navigate):
    # Deferred tool selection survives navigation widget creation on the next rerun.
    navigate("Deals")
    st.session_state["_next_tool"] = "Verification"


def _open_policies(navigate):
    navigate("Deals")
    st.session_state["_next_tool"] = "Company Policies"


def _check_records(db, deal):
    from .verification import verify, save_verification
    return save_verification(db, deal["opportunity"]["id"], verify(db))


def timeline_view(deal):
    st.markdown("#### Workflow timeline")
    st.caption("Business stages backed by saved evidence. Drafting may occur before the approval request; Advanced Details preserves actual execution order.")
    for entry in workflow_timeline(deal):
        st.write(f'{entry["title"]} · {entry["state"]}')
        if entry["state"] != "Pending" or entry["key"] == "verified":
            st.caption(entry["detail"])
        if entry.get("timestamp"):
            st.caption(entry["timestamp"][:19].replace("T", " ") + " UTC")


def quote_view(quote, inquiry):
    if not quote:
        st.info("A quotation will appear after customer details and commercial terms pass review.")
        return
    st.caption("Finalized demo offer" if quote["status"] == "FINAL" else "DRAFT · Not a finalized offer")
    st.dataframe([{"Solution":line["description"], "Quantity":line["quantity"], "Unit price":sar(line["unit_price"]), "Before discount":sar(line["net"])} for line in quote["lines"]], hide_index=True, use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.write("Subtotal", sar(quote["subtotal"]))
        st.write(f'Discount ({quote["discount_percent"]}%)', sar(quote["discount_amount"]))
        st.write("Net amount", sar(quote["net"]))
    with right:
        st.write("VAT · 15% demo assumption", sar(quote["vat"]))
        st.metric("Total including VAT", sar(quote["total"]))
    requested = inquiry.get("requested_days")
    st.write(f'Delivery estimate: {quote["delivery_days"]} calendar days from acceptance.')
    if requested:
        if quote["delivery_days"] <= requested:
            st.caption(f'Within the requested {requested}-day window. Sequential catalog lead times apply.')
        else:
            st.warning(f'The requested {requested}-day window cannot be met.')


def deal_detail(db, deal, navigate):
    st.subheader(deal["name"])
    st.caption(f'{deal["source"]} · Revision {deal["revision"]}')
    st.markdown("#### Deal brief")
    brief_left, brief_right = st.columns([2, 1])
    brief_left.text("Opportunity: " + deal["name"] + " — Software solution")
    brief_left.caption("Descriptive workspace title; no separate opportunity name is stored in the CRM.")
    brief_left.text("Industry: " + deal["customer"].get("sector", "Not confirmed").capitalize())
    brief_right.metric("Business status", business_status(deal))
    brief_inquiry = deal["inquiry"]
    budget_col, delivery_col, discount_col = st.columns(3)
    budget_col.metric("Customer budget", sar(brief_inquiry.get("budget")) if brief_inquiry.get("budget") is not None else "Not confirmed")
    delivery_col.metric("Requested timeline", str(brief_inquiry["requested_days"]) + " days" if brief_inquiry.get("requested_days") else "Not confirmed")
    timeline = deal.get("timeline")
    if timeline and timeline.get("source_phrase"):
        delivery_col.text(timeline["source_phrase"])
        delivery_col.caption(f'{timeline["precision"].capitalize()} · {timeline["constraint"]} · ' + ("Explicit confirmation stated" if timeline["explicitly_confirmed"] else "No explicit confirmation recorded"))
        if timeline.get("deadline"):
            delivery_col.caption(("Estimated date: " if timeline["precision"] in ("approximate", "tentative") else "Calendar target: ") + timeline["deadline"] + " · Saudi time")
    discount_text = requested_discount(deal)
    discount_col.metric("Requested discount", discount_text.split(";")[0])
    if ";" in discount_text:
        discount_col.caption(discount_text.split(";", 1)[1].strip())
    requirements = brief_inquiry.get("requirements", [])
    if requirements:
        st.text("Requirements: " + "; ".join(CAPABILITIES.get(r["capability"], r["capability"].replace("unsupported:", "Needs scope review: ")) for r in requirements))
    next_action(db, deal, navigate)
    if deal["run"] and st.button("Revise inquiry", key="revise_deal"):
        _revise(deal, navigate)
        st.rerun()
    explanation, risks = decision_explanation(deal)
    st.markdown("#### Why this decision?")
    for sentence in explanation:
        st.text(sentence)
    if risks:
        st.markdown("#### Gaps & risks")
        for risk in risks:
            st.text(risk)
    left, right = st.columns([1, 1.4])
    with left:
        st.markdown("#### Customer requirements")
        inquiry = deal["inquiry"]
        text = (deal["run"] or {}).get("request", {}).get("text") or inquiry.get("notes")
        if text:
            st.text(text)
        requirements = inquiry.get("requirements") or (deal["run"] or {}).get("requirements", [])
        for item in requirements:
            st.write("• " + CAPABILITIES.get(item["capability"], item["capability"].replace("unsupported:", "Needs scope review: ")))
        for title, value in [("Sector", deal["customer"].get("sector", "Not confirmed").capitalize()), ("Users", inquiry.get("users") or "Not confirmed"), ("Requested delivery", str(inquiry["requested_days"]) + " calendar days" if inquiry.get("requested_days") else "Not confirmed"), ("Budget including VAT", sar(inquiry.get("budget")) if inquiry.get("budget") is not None else "Not confirmed"), ("Requested discount", requested_discount(deal))]:
            st.write(title, value)
        st.markdown("#### Recommended solution")
        reasons = product_reasons(deal)
        if not reasons:
            st.caption("Recommendations appear after qualification.")
        for product in reasons:
            st.write(product["name"])
            for reason in product["reasons"]:
                st.caption(reason)
        st.markdown("#### Commercial review")
        if deal["findings"]:
            for finding in deal["findings"]:
                st.text(finding)
        else:
            st.caption("No blocking policy findings recorded." if deal["quote"] else "No commercial review has been recorded yet.")
        if deal["approval"]:
            st.write("Approval decision", deal["approval"]["status"].capitalize())
    with right:
        st.markdown("#### Quotation")
        if deal.get("integrity_findings"):
            st.error("The stored quotation needs validation. Its amounts are available only in Advanced Details until the discrepancy is resolved.")
        else:
            quote_view(deal["quote"], inquiry)
        st.markdown("#### Proposal")
        canonical = deal["proposal"]
        draft = (deal["run"] or {}).get("proposal")
        if canonical and canonical["status"] == "FINAL" and not deal.get("offer_final"):
            st.error("This saved proposal is marked final without valid supporting records. Do not use it; review the record checks.")
        elif canonical and canonical["status"] == "FINAL":
            st.success("Finalized demo proposal · Saved to CRM")
            st.text(canonical["text"])
            st.download_button("Download proposal", canonical["text"], "dealpilot-proposal.txt", key="download_final")
        elif draft or canonical:
            proposal = draft or canonical
            st.warning("DRAFT · Approval and final validation may still be required")
            st.text(proposal["text"])
            st.download_button("Download draft", proposal["text"], "dealpilot-draft.txt", key="download_draft")
        else:
            st.caption("A proposal is prepared only after a valid solution and quotation are available.")
    timeline_view(deal)
    st.markdown("#### CRM activity & next steps")
    if deal["opportunity"]:
        st.write("Opportunity saved to the demo CRM.")
    else:
        st.caption("This inquiry is saved in the workspace. No CRM opportunity has been created yet.")
    for task in deal["tasks"]:
        st.text("Follow up: " + task["description"])
    if deal["activity"]:
        st.caption(f'{len(deal["activity"])} recorded updates · Last update {deal["updated"][:16].replace("T", " ")} UTC')
    run = deal["run"]
    if run and run.get("phase") == "verification":
        if run.get("verification_findings"):
            st.warning("Saved records need review. Open Advanced Details for the findings.")
        else:
            st.caption("Saved records reconciled at the last workflow check.")
    with st.expander("Advanced Details"):
        if run:
            st.write("Actual workflow execution trace")
            st.dataframe(run.get("trace", []), hide_index=True, use_container_width=True)
            st.write("Verification findings", run.get("verification_findings", []))
            st.write("Business timeline evidence", workflow_timeline(deal))
            st.write("Recorded errors", run.get("errors", []))
            if run.get("provider"):
                st.write("Provider", run["provider"])
        st.json({"opportunity":deal["opportunity"], "run":run, "quote":deal["quote"], "approval":deal["approval"], "verification":deal.get("verification"), "integrity_findings":deal.get("integrity_findings")})
        st.dataframe(deal["activity"], hide_index=True)
