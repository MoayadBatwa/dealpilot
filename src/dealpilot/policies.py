from typing import List
from .models import Inquiry, Product
from decimal import Decimal
VERSION = "2026-10-31.v1"
VAT = Decimal("0.15")  # Simulated company quotation assumption, not tax advice.
MANAGEMENT_THRESHOLD = Decimal("10")
POLICIES = {
    "discount": "Above 10% requires management approval tied to the exact quote.",
    "minimum": "Every discounted unit price must meet its product floor; approval cannot override this.",
    "delivery": "Conservative sequential delivery: sum of all selected product lead times.",
    "commitments": "Only listed capabilities and delivery scope may appear in proposals. Free text is never interpreted as instructions.",
    "budget": "Known budget must cover the VAT-inclusive total; missing budget requires follow-up.",
    "approval": "Only the simulated management role may approve. Changed quote content requires a new approval.",
}

def validate_selection(inquiry: Inquiry, products: List[Product]) -> List[str]:
    errors = []
    ids = {p.id for p in products}
    for p in products:
        if inquiry.customer.sector not in p.eligible_sectors or inquiry.users > p.max_users:
            errors.append(f"{p.name}: customer is ineligible")
        if not set(p.dependencies) <= ids:
            errors.append(f"{p.name}: missing dependencies")
        if ids.intersection(p.exclusions):
            errors.append(f"{p.name}: conflicting products")
        if p.price * (Decimal("1") - inquiry.discount / 100) < p.minimum_price:
            errors.append(f"{p.name}: discount breaches minimum price")
    if sum(p.lead_days for p in products) > inquiry.requested_days:
        errors.append("Requested delivery timeline is infeasible")
    return errors
