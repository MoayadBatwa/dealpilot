from typing import Any, Dict, List
from .database import Database
from .models import Inquiry
from .models import Opportunity, CRMTask, Approval, Proposal, Quote
from .policies import MANAGEMENT_THRESHOLD

class CRM:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_opportunity(self, inquiry: Inquiry) -> str:
        id = f"opp-{inquiry.id}-r{inquiry.revision}"
        opp = Opportunity(id=id, inquiry_id=inquiry.id, customer_id=inquiry.customer.id, status="QUALIFYING", revision=inquiry.revision)
        self.db.write("opportunity", id, opp.model_dump(mode="json"), f"{id}:create", "create_opportunity", inquiry.simulate_crm_failure)
        return id

    def update_opportunity(self, id: str, status: str, key: str) -> Dict[str, Any]:
        data = self.db.get("opportunity", id)
        if data is None:
            raise ValueError("Opportunity not found")
        data["status"] = status
        return self.db.write("opportunity", id, data, key, "update_opportunity")

    def create_follow_up_task(self, id: str, description: str, key: str) -> Dict[str, Any]:
        task = CRMTask(id=f"task-{key}", opportunity_id=id, description=description)
        return self.db.write("task", task.id, task.model_dump(mode="json"), key, "create_follow_up_task")

    def request_approval(self, id: str, quote: Quote) -> str:
        approval = Approval(id=f"approval-{quote.id}", opportunity_id=id, quote_id=quote.id)
        self.db.write("approval", approval.id, approval.model_dump(mode="json"), f"{approval.id}:request", "request_approval")
        return approval.id

    def decide_approval(self, id: str, decision: str, role: str, key: str) -> Dict[str, Any]:
        if role != "management" or decision not in ("APPROVED", "REJECTED"):
            raise ValueError("Management role and valid decision required")
        data = self.db.get("approval", id)
        if not data or data["status"] != "PENDING":
            prior = self.db.get("approval", id)
            if prior and prior["status"] == decision and prior["approver"] == role:
                return prior
            raise ValueError("Approval is absent or already decided")
        data.update(status=decision, approver=role)
        return self.db.write("approval", id, data, key, "decide_approval")

    def save_proposal_draft(self, proposal: Proposal) -> Dict[str, Any]:
        if proposal.status != "DRAFT":
            raise ValueError("Draft tool only accepts drafts")
        return self.db.write("proposal", proposal.id, proposal.model_dump(mode="json"), f"{proposal.id}:draft", "save_proposal_draft")

    def finalize(self, opportunity_id: str, quote_id: str) -> Proposal:
        """Recompute from persisted structured input; never trust submitted totals."""
        from .qualification import recommend
        from .pricing import price
        from .proposal import render
        opp = self.db.get("opportunity", opportunity_id)
        if not opp:
            raise ValueError("Opportunity not found")
        from .models import Inquiry
        inquiry = Inquiry.model_validate(self.db.get("inquiry", f'{opp["inquiry_id"]}:r{opp["revision"]}'))
        products, errors = recommend(inquiry)
        quote = price(inquiry, products)
        if errors or inquiry.budget is None or quote.total > inquiry.budget or quote.id != quote_id:
            raise ValueError("Qualification or quote validation failed")
        stored = self.db.get("quote", quote_id)
        if not stored:
            raise ValueError("Persisted quote missing")
        expected = quote.model_dump(mode="json")
        if {**stored, "status":"DRAFT"} != expected:
            raise ValueError("Persisted quote does not match validated pricing")
        if quote.discount_percent > MANAGEMENT_THRESHOLD:
            approval = self.db.get("approval", f"approval-{quote.id}")
            if not approval or approval["status"] != "APPROVED" or approval["approver"] != "management" or approval["opportunity_id"] != opportunity_id:
                raise ValueError("Management approval required")
        quote.status = "FINAL"
        self.db.write("quote", quote.id, quote.model_dump(mode="json"), f"{quote.id}:final", "finalize_quote")
        proposal = render(inquiry, opportunity_id, quote)
        self.db.write("proposal", proposal.id, proposal.model_dump(mode="json"), f"{proposal.id}:final", "finalize_proposal")
        self.update_opportunity(opportunity_id, "OFFER_READY", f"{opportunity_id}:ready")
        return proposal

    def retrieve_records(self, kind: str) -> List[Dict[str, Any]]:
        return self.db.list(kind)
