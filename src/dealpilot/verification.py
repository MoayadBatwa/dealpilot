from typing import List
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
                if expected.discount_percent > MANAGEMENT_THRESHOLD and (not approval or approval["status"] != "APPROVED" or approval["approver"] != "management" or approval["opportunity_id"] != opp["id"]):
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
