"""Business-facing display components, with technical evidence kept expandable."""
import streamlit as st
from .catalog import CATALOG
from .ui_data import label, sar, NEXT_ACTIONS

CAPABILITIES = {"crm":"Sales CRM", "crm_integration":"CRM integration", "bilingual":"Arabic & English support", "analytics":"Sales analytics", "customer_service":"Customer service", "migration":"Data migration", "regulated_setup":"Regulated workflow setup"}
STEPS = [("intake", "Understand the inquiry"), ("solution", "Recommend a solution"), ("commercial", "Validate commercial terms"), ("proposal", "Prepare the proposal"), ("execution", "Save the deal"), ("verification", "Check saved records")]


def progress_view(trace):
    """Only completed observed attempts count as completed steps."""
    for node, title in STEPS:
        attempts = [e for e in trace if e["node"] == node]
        if not attempts:
            state = "Not reached"
        elif attempts[-1].get("error"):
            state = "Needs attention"
        else:
            state = "Completed"
        st.write(f"{title} — {state}")


def next_action(deal):
    message = NEXT_ACTIONS.get(deal["status"], "Review the customer requirements and follow-up tasks before proceeding.")
    if deal["status"] == "OFFER_READY":
        st.success(message)
    elif deal["status"] in ("APPROVAL_PENDING", "REJECTED", "APPROVED_AWAITING_RESUME"):
        st.warning(message)
    else:
        st.info(message)


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
    st.caption(f'{deal["source"]} · Revision {deal["revision"]} · {label(deal["status"])}')
    next_action(deal)
    if deal["approval"]:
        if deal["status"] in ("APPROVAL_PENDING", "APPROVED_AWAITING_RESUME"):
            st.button("Review approval", key="detail_approval", on_click=navigate, args=("Approvals",))
    if deal["run"] and st.button("Revise inquiry", key="revise_deal"):
        request = deal["run"]["request"]
        st.session_state["opportunity_revision_context"] = {**request, "run_id":deal["run"]["run_id"]}
        st.session_state.pop("new_opportunity_result", None)
        navigate("New Opportunity")
        st.rerun()
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
        for title, value in [("Sector", deal["customer"].get("sector", "Not confirmed").capitalize()), ("Users", inquiry.get("users") or "Not confirmed"), ("Requested delivery", str(inquiry["requested_days"]) + " calendar days" if inquiry.get("requested_days") else "Not confirmed"), ("Budget including VAT", sar(inquiry.get("budget")) if inquiry.get("budget") is not None else "Not confirmed")]:
            st.write(title, value)
        st.markdown("#### Recommended solution")
        ids = [l["product_id"] for l in (deal["quote"] or {}).get("lines", [])] or (deal["run"] or {}).get("selected_products", []) or deal["result"].get("products", [])
        if not ids:
            st.caption("Recommendations appear after qualification.")
        for id in ids:
            if id in CATALOG:
                st.write(CATALOG[id].name)
                st.caption(" · ".join(c.description for c in CATALOG[id].capabilities))
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
        quote_view(deal["quote"], inquiry)
        st.markdown("#### Proposal")
        canonical = deal["proposal"]
        draft = (deal["run"] or {}).get("proposal")
        if canonical and canonical["status"] == "FINAL":
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
            st.write("Recorded errors", run.get("errors", []))
            if run.get("provider"):
                st.write("Provider", run["provider"])
        st.json({"opportunity":deal["opportunity"], "run":run, "quote":deal["quote"], "approval":deal["approval"]})
        st.dataframe(deal["activity"], hide_index=True)
