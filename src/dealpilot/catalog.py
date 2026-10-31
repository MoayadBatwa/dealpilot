from decimal import Decimal
from .models import Product, ProductCapability

def product(id, name, caps, price, floor, days, deps=(), exclusions=(), per_user=False, sectors=("retail", "manufacturing", "services"), max_users=10000):
    return Product(id=id, name=name, capabilities=[ProductCapability(code=c, description=d) for c,d in caps], price=Decimal(price), minimum_price=Decimal(floor), lead_days=days, dependencies=list(deps), exclusions=list(exclusions), per_user=per_user, eligible_sectors=list(sectors), max_users=max_users)

CATALOG = {p.id:p for p in [
    product("core", "Nakhla CRM Annual", [("crm", "Contacts, accounts and opportunity tracking")], "1200", "840", 7, per_user=True),
    product("integration", "Wasl CRM Integration", [("crm_integration", "One documented REST connector to the simulated CRM")], "8000", "6000", 14, deps=("core",)),
    product("bilingual", "Lisan Arabic / English", [("bilingual", "Arabic and English interface and templates")], "3000", "2100", 3, deps=("core",)),
    product("analytics", "Basira Analytics", [("analytics", "Daily refreshed sales dashboards")], "6000", "4500", 10, deps=("core",)),
    product("service", "Khidma Service Desk", [("customer_service", "Case routing and business hours support")], "900", "630", 7, deps=("core",), per_user=True),
    product("migration", "Intiqal Data Migration", [("migration", "One CSV import up to 50,000 records")], "5000", "4000", 7, deps=("core",), exclusions=("regulated",)),
    product("regulated", "Aman Regulated Setup", [("regulated_setup", "Configuration workshop for regulated workflows; no certification")], "12000", "10000", 21, deps=("core",), exclusions=("migration",), sectors=("services",), max_users=200),
]}
