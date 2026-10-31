from typing import List, Tuple
from .models import Inquiry, Product
from .catalog import CATALOG

def recommend(inquiry: Inquiry) -> Tuple[List[Product], List[str]]:
    selected = set()
    errors = []
    for req in inquiry.requirements:
        matches = [p for p in CATALOG.values() if any(c.code == req.capability for c in p.capabilities)]
        eligible = [p for p in matches if inquiry.customer.sector in p.eligible_sectors and inquiry.users <= p.max_users]
        if not eligible:
            errors.append(f"Unsupported or ineligible capability: {req.capability}")
        else:
            selected.add(eligible[0].id)
    def include(pid):
        for dep in CATALOG[pid].dependencies:
            if dep not in selected:
                selected.add(dep)
                include(dep)
    for pid in list(selected):
        include(pid)
    if inquiry.budget is None:
        errors.append("Budget is missing; qualification follow-up required")
    return [CATALOG[pid] for pid in sorted(selected)], errors
