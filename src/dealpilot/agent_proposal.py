"""An extractive LLM drafting contract with enforceable factual grounding."""
from typing import Dict
from .models import Inquiry, Quote
from .catalog import CATALOG
from .agent_models import GroundedDraft


def facts_for(inquiry: Inquiry, quote: Quote) -> Dict[str, str]:
    facts = {
        "customer": f"Prepared for {inquiry.customer.name}, Saudi Arabia.",
        "term": "Software subscriptions are annual; implementation services are one-time.",
        "subtotal": f"Subtotal before discount: SAR {quote.subtotal:.2f}.",
        "discount": f"Requested discount: {quote.discount_percent}%; discount amount: SAR {quote.discount_amount:.2f}.",
        "net": f"Net amount: SAR {quote.net:.2f}.",
        "vat": f"VAT simulation assumption (15%): SAR {quote.vat:.2f}.",
        "total": f"Total including VAT: SAR {quote.total:.2f}.",
        "delivery": f"Delivery estimate: {quote.delivery_days} calendar days from simulated acceptance, using sequential catalog lead times.",
        "governance": f"Policy {quote.policy_version} applies. This DRAFT is not a finalized offer. Any required management approval must be recorded before finalization.",
        "simulation": "This is a fictional presales simulation. No external submission or contractual commitment is created.",
    }
    for line in quote.lines:
        p = CATALOG[line.product_id]
        scope = "; ".join(c.description for c in p.capabilities)
        facts[f"product-{p.id}"] = f"{p.name}: {line.quantity} × SAR {line.unit_price:.2f}. Scope: {scope}."
    return facts


def compose(draft: GroundedDraft, facts: Dict[str, str]) -> str:
    ids = [id for section in draft.sections for id in section.fact_ids]
    if len(draft.sections) > 4 or len(ids) != len(set(ids)) or set(ids) != set(facts):
        raise ValueError("Proposal must include every validated fact exactly once; unknown or omitted facts rejected")
    if any(not section.fact_ids for section in draft.sections):
        raise ValueError("Empty proposal section")
    return "DRAFT — AI-composed DealPilot simulated proposal\n\n" + "\n\n".join(
        section.heading + "\n" + "\n".join(facts[id] for id in section.fact_ids)
        for section in draft.sections
    )
