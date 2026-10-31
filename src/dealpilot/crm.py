from typing import Any, Dict, List, Tuple
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
        if not data:
            raise ValueError("Approval is absent")
        approval = Approval.model_validate(data)
        if approval.id != id or id != f"approval-{approval.quote_id}":
            raise ValueError("Approval does not identify the exact quote")
        self.validated_quote(approval.opportunity_id, approval.quote_id)
        if approval.status != "PENDING":
            if approval.status == decision and approval.approver == role:
                return data
            raise ValueError("Approval is already decided")
        if self.db.get("quote", approval.quote_id)["status"] != "DRAFT":
            raise ValueError("Only a draft quote can receive a new approval decision")
        data.update(status=decision, approver=role)
        return self.db.write("approval", id, data, key, "decide_approval")

    def save_proposal_draft(self, proposal: Proposal) -> Dict[str, Any]:
        if proposal.status != "DRAFT":
            raise ValueError("Draft tool only accepts drafts")
        return self.db.write("proposal", proposal.id, proposal.model_dump(mode="json"), f"{proposal.id}:draft", "save_proposal_draft")

    def validated_quote(self, opportunity_id: str, quote_id: str, require_approval: bool = False) -> Tuple[Inquiry, Quote]:
        """Shared read-only validation for human decisions and finalization."""
        from .qualification import recommend
        from .pricing import price
        opp = self.db.get("opportunity", opportunity_id)
        if not opp:
            raise ValueError("Opportunity not found")
        inquiry = Inquiry.model_validate(self.db.get("inquiry", f'{opp["inquiry_id"]}:r{opp["revision"]}'))
        products, errors = recommend(inquiry)
        quote = price(inquiry, products)
        if errors or inquiry.budget is None or quote.total > inquiry.budget or quote.id != quote_id:
            raise ValueError("Qualification or quote validation failed")
        stored = self.db.get("quote", quote_id)
        if not stored:
            raise ValueError("Persisted quote missing")
        Quote.model_validate(stored)
        if {**stored, "status":"DRAFT"} != quote.model_dump(mode="json"):
            raise ValueError("Persisted quote does not match validated pricing")
        if require_approval and quote.discount_percent > MANAGEMENT_THRESHOLD:
            approval = self.db.get("approval", f"approval-{quote.id}")
            if not approval or approval["status"] != "APPROVED" or approval["approver"] != "management" or approval["opportunity_id"] != opportunity_id or approval["quote_id"] != quote.id or approval["id"] != f"approval-{quote.id}":
                raise ValueError("Management approval required")
        return inquiry, quote

    def finalize(self, opportunity_id: str, quote_id: str) -> Proposal:
        """Recompute from persisted input; never trust submitted totals or approvals."""
        from .proposal import render
        inquiry, quote = self.validated_quote(opportunity_id, quote_id, require_approval=True)
        quote.status = "FINAL"
        self.db.write("quote", quote.id, quote.model_dump(mode="json"), f"{quote.id}:final", "finalize_quote")
        proposal = render(inquiry, opportunity_id, quote)
        self.db.write("proposal", proposal.id, proposal.model_dump(mode="json"), f"{proposal.id}:final", "finalize_proposal")
        self.update_opportunity(opportunity_id, "OFFER_READY", f"{opportunity_id}:ready")
        return proposal

    def retrieve_records(self, kind: str) -> List[Dict[str, Any]]:
        return self.db.list(kind)
