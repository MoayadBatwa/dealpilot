from typing import Any, Dict, List, Optional
from .database import Database
from .models import Inquiry
from .qualification import recommend
from .pricing import price
from .proposal import render
from .policies import MANAGEMENT_THRESHOLD

def verify(db: Database) -> List[str]:
    """Read-only reconciliation of persisted records against independent recomputation."""
    discrepancies = []
    opportunities = {o["id"]:o for o in db.list("opportunity")}
    for proposal in db.list("proposal"):
        label = proposal["id"]
        opp = opportunities.get(proposal["opportunity_id"])
        if not opp:
            discrepancies.append(f"{label}: missing opportunity")
            continue
        try:
            inquiry = Inquiry.model_validate(db.get("inquiry", f'{opp["inquiry_id"]}:r{opp["revision"]}'))
            products, errors = recommend(inquiry)
            expected = price(inquiry, products)
            actual = db.get("quote", proposal["quote_id"])
            expected.status = proposal["status"]
            if errors or inquiry.budget is None or expected.total > inquiry.budget:
                discrepancies.append(f"{label}: qualification invalid")
            if actual != expected.model_dump(mode="json"):
                discrepancies.append(f"{label}: quote pricing/content mismatch")
            if proposal != render(inquiry, opp["id"], expected).model_dump(mode="json"):
                discrepancies.append(f"{label}: proposal content mismatch")
            if proposal["status"] == "FINAL":
                approval = db.get("approval", f"approval-{expected.id}")
                if expected.discount_percent > MANAGEMENT_THRESHOLD and (not approval or approval["status"] != "APPROVED" or approval["approver"] != "management" or approval["opportunity_id"] != opp["id"] or approval["quote_id"] != expected.id or approval["id"] != f"approval-{expected.id}"):
                    discrepancies.append(f"{label}: final offer lacks management approval")
                if opp["status"] != "OFFER_READY":
                    discrepancies.append(f"{label}: opportunity status mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            discrepancies.append(f"{label}: invalid persisted data ({exc})")
    for quote in db.list("quote"):
        if not any(p["quote_id"] == quote["id"] for p in db.list("proposal")):
            discrepancies.append(f'{quote["id"]}: missing proposal')
    for opp in opportunities.values():
        if opp["status"] in ("OFFER_READY", "APPROVAL_PENDING") and not any(p["opportunity_id"] == opp["id"] for p in db.list("proposal")):
            discrepancies.append(f'{opp["id"]}: missing proposal')
    return discrepancies


def verification_snapshot(db: Database, opportunity_id: str) -> Optional[str]:
    """Fingerprint records checked, so later edits cannot reuse an old 'verified' badge."""
    import hashlib
    import json
    opp = db.get("opportunity", opportunity_id)
    if not opp:
        return None
    inquiry = db.get("inquiry", f'{opp["inquiry_id"]}:r{opp["revision"]}')
    proposals = [p for p in db.list("proposal") if p["opportunity_id"] == opportunity_id]
    approvals = [a for a in db.list("approval") if a["opportunity_id"] == opportunity_id]
    ids = {p["quote_id"] for p in proposals} | {a["quote_id"] for a in approvals}
    quotes = [db.get("quote", id) for id in sorted(ids)]
    from .catalog import CATALOG
    from .policies import VERSION
    payload = {"opportunity":opp, "inquiry":inquiry, "proposals":proposals, "approvals":approvals, "quotes":quotes,
               "catalog":[CATALOG[id].model_dump(mode="json") for id in sorted(CATALOG)], "policy_version":VERSION}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def save_verification(db: Database, opportunity_id: str, findings: List[str]) -> Dict[str, Any]:
    """Persist the existing verifier's result; never infer it from a successful CRM write."""
    import hashlib
    import json
    digest = verification_snapshot(db, opportunity_id)
    if digest is None:
        raise ValueError("Cannot record verification without an opportunity")
    report = {"opportunity_id":opportunity_id, "snapshot_digest":digest, "findings":findings,
              "status":"FAILED" if findings else "PASSED"}
    prior = db.get("verification", opportunity_id)
    if prior and {k:v for k,v in prior.items() if k != "check_revision"} == report:
        return prior
    # A repaired record can return to a previously checked fingerprint. A new
    # report revision updates the current report instead of replaying an obsolete key.
    report["check_revision"] = (prior or {}).get("check_revision", 0) + 1
    key = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    return db.write("verification", opportunity_id, report, f"verification:{opportunity_id}:{key}", "verify_records")
