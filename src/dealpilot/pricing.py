from decimal import Decimal, ROUND_HALF_UP
import hashlib
from typing import List
from .models import Inquiry, Product, Quote, QuoteLine
from .policies import VERSION, VAT, validate_selection

def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def price(inquiry: Inquiry, products: List[Product]) -> Quote:
    errors = validate_selection(inquiry, products)
    if not products:
        errors.append("No eligible products")
    if errors:
        raise ValueError("; ".join(errors))
    lines = [QuoteLine(product_id=p.id, description=p.name, quantity=inquiry.users if p.per_user else 1, unit_price=p.price, net=money(p.price * (inquiry.users if p.per_user else 1))) for p in products]
    subtotal = sum((line.net for line in lines), Decimal("0"))
    discount = money(subtotal * inquiry.discount / 100)
    net = subtotal - discount
    vat = money(net * VAT)
    content = inquiry.model_dump_json() + "|" + "|".join(p.model_dump_json() for p in products) + VERSION
    return Quote(id="quote-" + hashlib.sha256(content.encode()).hexdigest()[:24], policy_version=VERSION, lines=lines, subtotal=subtotal, discount_percent=inquiry.discount, discount_amount=discount, net=net, vat=vat, total=net+vat, delivery_days=sum(p.lead_days for p in products))
