"""Read-only presentation joins. Persisted commercial records remain authoritative."""
from decimal import Decimal
from typing import Any, Dict, List
from .database import Database
from .crm import CRM
from .verification import verification_snapshot
from .policies import MANAGEMENT_THRESHOLD

STATUS_LABELS = {
    "OFFER_READY":"Offer ready", "APPROVAL_PENDING":"Awaiting approval",
    "APPROVED_AWAITING_RESUME":"Approved · finalization needed", "REJECTED":"Changes requested",
    "NEEDS_INFORMATION":"Customer details needed", "NEEDS_REVIEW":"Review required",
    "UNSUPPORTED_REQUIREMENTS":"Scope needs review", "INFEASIBLE_TIMELINE":"Delivery needs review",
    "OUTSIDE_BUDGET":"Budget needs review", "POLICY_BLOCKED":"Commercial review required",
    "PROVIDER_UNAVAILABLE":"Analysis unavailable", "PROVIDER_ERROR":"Analysis interrupted",
    "VALIDATION_ERROR":"Validation needs review", "TOOL_ERROR":"Save interrupted",
    "VERIFICATION_FAILED":"Record check needs review", "RUNNING":"In progress",
    "QUALIFYING":"Qualification in progress", "LOOP_LIMIT":"Review required",
}
NEXT_ACTIONS = {
    "OFFER_READY":"Review the finalized demo offer. No email or external submission has been made.",
    "APPROVAL_PENDING":"Ask a manager to review this exact quote in Approvals. The proposal remains a draft.",
    "APPROVED_AWAITING_RESUME":"Resume the workflow to revalidate the approved quote and finalize the offer.",
    "REJECTED":"Review the commercial terms with your manager, then revise the inquiry. The current offer cannot finalize.",
    "NEEDS_INFORMATION":"Confirm the missing customer details, then revise the inquiry.",
    "UNSUPPORTED_REQUIREMENTS":"Agree on supported scope with the customer before revising the inquiry.",
    "INFEASIBLE_TIMELINE":"Agree on a feasible delivery date, then revise the inquiry.",
    "OUTSIDE_BUDGET":"Confirm a sufficient budget or reduce the requested scope.",
    "POLICY_BLOCKED":"Revise the terms to meet company policy. Approval cannot override minimum prices.",
    "PROVIDER_UNAVAILABLE":"Ask your administrator to configure the analysis provider, then retry.",
    "PROVIDER_ERROR":"Retry the saved inquiry after your administrator checks the analysis connection.",
    "TOOL_ERROR":"Retry the saved inquiry. Existing CRM writes use the same safe request keys.",
    "VALIDATION_ERROR":"Review the extracted details and commercial findings before retrying or revising.",
    "VERIFICATION_FAILED":"Ask your administrator to investigate the record check before using this offer.",
    "RUNNING":"Retry this interrupted workflow to continue from its saved progress.",
}


def sar(value) -> str:
    return f"SAR {Decimal(str(value)):,.2f}" if value is not None else "Not quoted"


def label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").capitalize())


def load_deals(db: Database) -> List[Dict[str, Any]]:
    opportunities = db.list("opportunity")
    inquiries = {(i["id"], i["revision"]):i for i in db.list("inquiry")}
    quotes = {q["id"]:q for q in db.list("quote")}
    proposals = {p["opportunity_id"]:p for p in db.list("proposal")}
    approvals = {a["opportunity_id"]:a for a in db.list("approval")}
    results = {(r["opportunity_id"]):r for r in db.list("result") if r.get("opportunity_id")}
    tasks = db.list("task")
    verification_reports = {r["opportunity_id"]:r for r in db.list("verification")}
    audits = db.audits()
    linked = set()
    deals = []

    def assemble(run, opp):
        inquiry = (run or {}).get("inquiry") or (inquiries.get((opp["inquiry_id"], opp["revision"])) if opp else None) or {}
        request = (run or {}).get("request") or {}
        customer = inquiry.get("customer") or request.get("customer") or {}
        if not inquiry and (run or {}).get("extraction"):
            extracted = run["extraction"]
            inquiry = {"requirements":run.get("requirements", []), "revision":request.get("revision", 1)}
            for field in ("budget", "users", "requested_days", "discount"):
                evidence = extracted.get(field)
                inquiry[field] = evidence["value"] if evidence else None
        result = (run or {}).get("execution_results") or (results.get(opp["id"]) if opp else None) or {}
        canonical = proposals.get(opp["id"]) if opp else None
        quote_id = result.get("quote_id") or (canonical or {}).get("quote_id")
        quote = quotes.get(quote_id) or (run or {}).get("quote")
        approval = approvals.get(opp["id"]) if opp else None
        status = (run or {}).get("status") or (opp or {}).get("status", "NEEDS_REVIEW")
        # A failed workflow must not be relabeled successful merely because some writes committed.
        failure = status in ("VERIFICATION_FAILED", "VALIDATION_ERROR", "TOOL_ERROR", "PROVIDER_ERROR", "LOOP_LIMIT")
        if not failure:
            if approval and approval["status"] == "REJECTED":
                status = "REJECTED"
            elif quote and quote["status"] == "FINAL" and canonical and canonical["status"] == "FINAL" and (opp or {}).get("status") == "OFFER_READY":
                status = "OFFER_READY"
            elif approval and approval["status"] == "APPROVED":
                status = "APPROVED_AWAITING_RESUME"
            elif approval and approval["status"] == "PENDING":
                status = "APPROVAL_PENDING"
        integrity = []
        if quote and opp and (quote_id in quotes):
            try:
                CRM(db).validated_quote(opp["id"], quote_id)
            except ValueError:
                integrity.append("The saved quote no longer matches the validated customer scope and pricing.")
        exact_approval = bool(approval and quote and opp and approval["quote_id"] == quote["id"] and approval["id"] == f'approval-{quote["id"]}' and approval["opportunity_id"] == opp["id"])
        if approval and not exact_approval:
            integrity.append("The approval is not linked to this exact quotation.")
        if approval and approval["status"] in ("APPROVED", "REJECTED") and approval.get("approver") != "management":
            integrity.append("The recorded decision lacks management authorization.")
        authorized = bool(quote and (Decimal(quote["discount_percent"]) <= MANAGEMENT_THRESHOLD or (exact_approval and approval["status"] == "APPROVED" and approval["approver"] == "management")))
        final = bool(quote and quote["status"] == "FINAL" and canonical and canonical["status"] == "FINAL" and canonical["quote_id"] == quote["id"] and (opp or {}).get("status") == "OFFER_READY" and authorized and not integrity)
        if quote and quote["status"] == "FINAL" and not final:
            integrity.append("A saved final offer lacks matching records or exact management authorization.")
        if integrity:
            status = "VALIDATION_ERROR"
        elif status == "OFFER_READY" and not final:
            status = "VALIDATION_ERROR"
            integrity.append("The workflow says offer ready, but the complete finalized records are missing.")
        report = verification_reports.get((opp or {}).get("id"))
        report_current = bool(report and report["snapshot_digest"] == verification_snapshot(db, opp["id"]))
        if report_current and report["status"] == "FAILED":
            status = "VERIFICATION_FAILED"
        elif report_current and report["status"] == "PASSED" and status == "VERIFICATION_FAILED" and not integrity:
            # An explicit new reconciliation can resolve an older failed check.
            if final:
                status = "OFFER_READY"
            elif exact_approval:
                status = {"APPROVED":"APPROVED_AWAITING_RESUME", "PENDING":"APPROVAL_PENDING", "REJECTED":"REJECTED"}[approval["status"]]
            else:
                status = (run or {}).get("stop_status") or (opp or {}).get("status", "NEEDS_REVIEW")
        ids = {str((run or {}).get("run_id", "")), str((opp or {}).get("id", "")), str(quote_id or ""), str((approval or {}).get("id", "")),
               str((canonical or {}).get("id", "")),
               f'{inquiry.get("id")}:r{inquiry.get("revision")}' if inquiry.get("id") else "",
               *[t["id"] for t in tasks if opp and t["opportunity_id"] == opp["id"]]} - {""}
        activity = [a for a in audits if a["record_id"] in ids]
        return {"key":"ai:" + run["run_id"] if run else "crm:" + opp["id"], "run":run, "opportunity":opp,
                "inquiry":inquiry, "customer":customer, "result":result, "quote":quote,
                "proposal":canonical, "approval":approval, "status":status,
                "revision":inquiry.get("revision", request.get("revision", 1)),
                "name":customer.get("name", "Customer details unavailable"),
                "source":"AI-assisted" if run else "Sample / structured",
                "findings":(run or {}).get("policy_findings", []) or result.get("issues", []),
                "tasks":[t for t in tasks if opp and t["opportunity_id"] == opp["id"]],
                "activity":activity, "updated":activity[-1]["timestamp"] if activity else "",
                "integrity_findings":integrity, "offer_final":final, "exact_approval":exact_approval,
                "verification":report, "verification_current":report_current,
                "timeline":(run or {}).get("timeline") or (db.get("timeline", f'{inquiry["id"]}:r{inquiry["revision"]}') if inquiry.get("id") else None)}

    for run in db.list("agent_run"):
        result = run.get("execution_results") or {}
        inquiry = run.get("inquiry") or {}
        opp = next((o for o in opportunities if o["id"] == result.get("opportunity_id") or (o["inquiry_id"] == inquiry.get("id") and o["revision"] == inquiry.get("revision"))), None)
        if opp:
            linked.add(opp["id"])
        deals.append(assemble(run, opp))
    deals.extend(assemble(None, opp) for opp in opportunities if opp["id"] not in linked)
    return sorted(deals, key=lambda d:d["updated"], reverse=True)
