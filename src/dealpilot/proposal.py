from .models import Inquiry, Quote, Proposal

def render(inquiry: Inquiry, opportunity_id: str, quote: Quote) -> Proposal:
    # Notes are intentionally excluded; all claims come from validated fields.
    text = f"{quote.status} — DealPilot simulated proposal\nCustomer: {inquiry.customer.name}\n"
    text += "Term: annual software subscription; services are one-time.\n"
    text += "\n".join(f"• {line.description}: {line.quantity} × SAR {line.unit_price:.2f}" for line in quote.lines)
    text += f"\nDiscount: {quote.discount_percent}%\nNet: SAR {quote.net:.2f}\nVAT (simulation assumption 15%): SAR {quote.vat:.2f}\nTotal: SAR {quote.total:.2f}\nDelivery: {quote.delivery_days} calendar days from simulated acceptance.\nPolicy: {quote.policy_version}\n"
    text += "Scope is limited to catalog capabilities. No external submission or contract is created."
    return Proposal(id=f"proposal-{quote.id}", opportunity_id=opportunity_id, quote_id=quote.id, status=quote.status, text=text)
