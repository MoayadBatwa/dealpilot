"""Evidence-based explanations and timeline; no model calls and no invented events."""
from decimal import Decimal
from typing import Any, Dict, List, Tuple
from .catalog import CATALOG
from .policies import MANAGEMENT_THRESHOLD

BUSINESS_STATUSES = {
    "NEEDS_INFORMATION":"Needs Information", "RUNNING":"Analyzing", "QUALIFYING":"Analyzing",
    "APPROVAL_PENDING":"Pending Approval", "APPROVED_AWAITING_RESUME":"Approved", "REJECTED":"Rejected",
    "UNSUPPORTED_REQUIREMENTS":"Blocked", "INFEASIBLE_TIMELINE":"Blocked", "OUTSIDE_BUDGET":"Blocked",
    "POLICY_BLOCKED":"Blocked", "VALIDATION_ERROR":"Blocked", "PROVIDER_UNAVAILABLE":"Blocked",
    "PROVIDER_ERROR":"Failed", "TOOL_ERROR":"Failed", "CRM_FAILURE":"Failed", "LOOP_LIMIT":"Failed",
    "VERIFICATION_FAILED":"Failed", "DRAFT":"Ready for Review", "READY_FOR_REVIEW":"Ready for Review",
}


def business_status(deal: Dict[str, Any]) -> str:
    if deal["status"] == "VERIFICATION_FAILED":
        return "Failed"
    if deal.get("integrity_findings"):
        return "Blocked"
    if deal["status"] == "OFFER_READY":
        verified = deal.get("verification_current") and (deal.get("verification") or {}).get("status") == "PASSED"
        return "Completed" if deal.get("offer_final") and verified else "Ready for Review"
    if deal["status"] == "NEEDS_REVIEW":
        return "Needs Information" if deal["inquiry"].get("budget") is None else "Blocked"
    if deal["status"] == "APPROVAL_PENDING" and not deal.get("exact_approval"):
        return "Blocked"
    if deal["status"] == "APPROVED_AWAITING_RESUME":
        approval = deal.get("approval") or {}
        return "Approved" if deal.get("exact_approval") and approval.get("approver") == "management" else "Blocked"
    return BUSINESS_STATUSES.get(deal["status"], "Blocked")


def product_reasons(deal: Dict[str, Any]) -> List[Dict[str, Any]]:
    requirements = {r["capability"] for r in deal["inquiry"].get("requirements", [])}
    ids = [l["product_id"] for l in (deal.get("quote") or {}).get("lines", [])] or (deal.get("run") or {}).get("selected_products", []) or deal.get("result", {}).get("products", [])
    rows = []
    for id in ids:
        if id not in CATALOG:
            continue
        product = CATALOG[id]
        reasons = [f'Matches the customer requirement: {c.description}.' for c in product.capabilities if c.code in requirements]
        dependents = [CATALOG[other].name for other in ids if other in CATALOG and id in CATALOG[other].dependencies]
        if dependents:
            reasons.append("Required catalog dependency for " + ", ".join(dependents) + ".")
        if not reasons:
            reasons = ["Listed as a candidate; no recorded requirement match or dependency explains this choice. Review scope."]
        rows.append({"name":product.name, "reasons":reasons})
    return rows


def decision_explanation(deal: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    from .ui_data import sar
    inquiry, quote = deal["inquiry"], deal.get("quote")
    explanation = []
    risks = list(deal.get("integrity_findings", []))
    supported = {c.code for p in CATALOG.values() for c in p.capabilities}
    for req in inquiry.get("requirements", []):
        if req["capability"] not in supported:
            risks.append("No catalog support for " + req["capability"].replace("unsupported:", "") + ".")
    for finding in deal.get("findings", []):
        if any(word in finding.lower() for word in ("missing", "infeasible", "cannot", "unsupported", "ineligible", "breach", "conflict")):
            risks.append(finding)
    if inquiry.get("budget") is None:
        risks.append("Budget has not been confirmed; an offer cannot be qualified yet.")
    if not inquiry.get("requested_days"):
        risks.append("The requested delivery window has not been confirmed.")
    if quote and not deal.get("integrity_findings"):
        explanation.append(f'The calculated offer is {sar(quote["total"])} including VAT, after a {quote["discount_percent"]}% discount.')
        if inquiry.get("budget") is not None:
            shortfall = Decimal(quote["total"]) - Decimal(inquiry["budget"])
            if shortfall > 0:
                risks.append(f'The offer exceeds the stated budget by {sar(shortfall)}.')
            else:
                explanation.append(f'The total is within the stated {sar(inquiry["budget"])} budget.')
        if inquiry.get("requested_days"):
            requested = Decimal(str(inquiry["requested_days"]))
            if quote["delivery_days"] > requested:
                risks.append(f'Catalog delivery requires {quote["delivery_days"]} days; the customer requested {requested} days.')
            else:
                explanation.append(f'Catalog delivery is {quote["delivery_days"]} days, within the requested {requested}-day window.')
        if Decimal(quote["discount_percent"]) > MANAGEMENT_THRESHOLD:
            explanation.append(f'The discount exceeds the {MANAGEMENT_THRESHOLD}% sales limit. Only management can approve this exact quote; approval does not finalize it.')
            approval = deal.get("approval") or {}
            if deal.get("exact_approval") and approval.get("status") == "APPROVED":
                explanation.append("Management approval for this exact quote is recorded. " + ("The quote has been finalized." if deal.get("offer_final") else "Resume the workflow for final validation; it remains a draft until then."))
            elif deal.get("exact_approval") and approval.get("status") == "PENDING":
                explanation.append("Management approval is pending. This is not a finalized customer offer.")
        else:
            explanation.append(f'The discount is within the {MANAGEMENT_THRESHOLD}% sales authorization limit; other commercial checks still apply.')
    if deal.get("exact_approval") and deal.get("approval") and deal["approval"]["status"] == "REJECTED":
        explanation.append("Management rejected this quote. Revised terms need a new validated quotation and any required approval.")
    if not explanation:
        explanation.append("A complete validated offer is not available. Resolve the recorded information or commercial gaps before proceeding.")
    return explanation, list(dict.fromkeys(risks))


def workflow_timeline(deal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Eight business stages, each independently supported by persisted evidence.

    These are stage order, not fabricated event timestamps: proposal drafting can
    actually precede the approval request. Sequence evidence is kept in the trace.
    """
    run = deal.get("run") or {}
    inquiry, quote = deal["inquiry"], deal.get("quote")
    audits = deal.get("activity", [])
    trace = run.get("trace", [])
    def event(operation, latest=False):
        entries = [a for a in audits if a["operation"] == operation]
        return (entries[-1] if latest else entries[0]) if entries else None
    def attempted(node):
        entries = [t for t in trace if t["node"] == node]
        return entries[-1] if entries else None
    failed = run.get("failed_node")
    stopped = bool(run.get("stop_status") or deal["status"] in ("NEEDS_REVIEW", "REJECTED"))
    def step(key, title, proof=False, detail="", node=None, skipped=False, blocked=False):
        attempt = attempted(node) if node else None
        if proof:
            state = "Completed"
        elif skipped:
            state = "Skipped"
        elif (attempt and attempt.get("error")) or failed == node and node:
            state = "Failed"
        elif blocked or stopped:
            state = "Blocked"
        else:
            state = "Pending"
        return {"key":key, "title":title, "state":state, "detail":detail, "timestamp":(proof.get("timestamp") if isinstance(proof, dict) else None)}
    structured_analysis = bool(not run and deal.get("result", {}).get("status") in ("NEEDS_REVIEW", "OFFER_READY", "APPROVAL_PENDING"))
    rows = [step("inquiry", "Inquiry received", event("receive_inquiry") or event("checkpoint_agent_run") or bool(run.get("request")), "The inquiry is saved in the workspace."),
            step("requirements", "Requirements analyzed", bool(run.get("extraction")) or structured_analysis, "Extracted customer requirements are recorded." if run.get("extraction") else "Structured requirements were checked by deterministic qualification; no AI analysis is implied." if structured_analysis else "No completed requirements analysis is recorded.", "intake")]
    solution_ok = bool(attempted("solution") and not attempted("solution").get("error") and run.get("selected_products") and run.get("stop_status") != "UNSUPPORTED_REQUIREMENTS")
    structured_ok = bool(not run and quote and not deal.get("integrity_findings"))
    rows.append(step("solution", "Solution matched", solution_ok or structured_ok, "A catalog-matched solution is recorded." if solution_ok or structured_ok else "No complete supported solution has been recorded.", "solution", blocked=run.get("stop_status") == "UNSUPPORTED_REQUIREMENTS"))
    quote_ok = bool(quote and not deal.get("integrity_findings") and deal["status"] not in ("OUTSIDE_BUDGET", "POLICY_BLOCKED", "INFEASIBLE_TIMELINE", "NEEDS_REVIEW", "VALIDATION_ERROR"))
    rows.append(step("quote", "Quote validated", quote_ok, "Commercial checks passed for the recorded quotation." if quote_ok else "Quote validation has not passed all commercial checks.", "commercial", blocked=deal["status"] in ("OUTSIDE_BUDGET", "POLICY_BLOCKED", "INFEASIBLE_TIMELINE", "VALIDATION_ERROR", "NEEDS_REVIEW")))
    required = quote and Decimal(quote["discount_percent"]) > MANAGEMENT_THRESHOLD
    approval = deal.get("approval")
    rows.append(step("approval", "Approval requested", (event("request_approval") or True) if deal.get("exact_approval") else False, "Request saved; decision: " + approval["status"].lower() + "." if approval and deal.get("exact_approval") else "No management approval is required for this validated discount." if quote_ok and not required else "A valid quote is needed before approval can be requested.", skipped=quote_ok and not required and not approval, blocked=bool(required and not approval)))
    proposal = deal.get("proposal") or run.get("proposal")
    rows.append(step("proposal", "Proposal prepared", bool(proposal and not deal.get("integrity_findings")), "A " + proposal["status"].lower() + " proposal is saved." if proposal else "No proposal has been prepared.", "proposal"))
    crm_updated = bool(deal.get("opportunity") and (event("update_opportunity") or event("finalize_quote")))
    rows.append(step("crm", "CRM updated", crm_updated, "The deal status was saved to the demo CRM." if crm_updated else "The CRM update has not completed.", "execution"))
    report = deal.get("verification") or {}
    current = deal.get("verification_current")
    check_failed = bool(current and report.get("status") == "FAILED")
    verified = bool(current and report.get("status") == "PASSED")
    row = step("verified", "Verified", (event("verify_records", latest=True) or True) if verified else False, "The saved draft records reconcile; approval and finalization are still outstanding." if verified and deal["status"] in ("APPROVAL_PENDING", "APPROVED_AWAITING_RESUME") else "The saved records match the last successful verification snapshot." if verified else "The record check found discrepancies." if check_failed else "No successful saved check covers the current records. Check records before treating this process as complete.", "verification")
    if check_failed:
        row["state"] = "Failed"
    rows.append(row)
    return rows


def requested_discount(deal: Dict[str, Any]) -> str:
    extraction = (deal.get("run") or {}).get("extraction")
    if extraction is not None and extraction.get("discount") is None:
        return "Not stated; standard 0% applies" if deal["inquiry"].get("discount") is not None else "Not confirmed"
    value = deal["inquiry"].get("discount")
    return str(value) + "%" if value is not None else "Not confirmed"
