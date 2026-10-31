from decimal import Decimal
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

class Customer(Model):
    id: str
    name: str
    sector: str = "retail"
    country: Literal["SA"] = "SA"

class Requirement(Model):
    capability: str

class Inquiry(Model):
    id: str
    customer: Customer
    requirements: List[Requirement] = Field(min_length=1)
    users: int = Field(default=10, ge=1, le=10000)
    budget: Optional[Decimal] = Field(default=None, ge=0)
    requested_days: int = Field(default=60, ge=1)
    discount: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    notes: str = ""
    revision: int = Field(default=1, ge=1)
    simulate_crm_failure: bool = False

    @field_validator("budget", "discount", mode="before")
    @classmethod
    def no_float(cls, value):
        if isinstance(value, float):
            raise ValueError("Use Decimal or a decimal string for money and percentages")
        return value

class ProductCapability(Model):
    code: str
    description: str

class Product(Model):
    id: str
    name: str
    capabilities: List[ProductCapability]
    price: Decimal
    minimum_price: Decimal
    per_user: bool = False
    dependencies: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    lead_days: int
    eligible_sectors: List[str]
    max_users: int = 10000

class Opportunity(Model):
    id: str
    inquiry_id: str
    customer_id: str
    status: str
    revision: int

class QuoteLine(Model):
    product_id: str
    description: str
    quantity: int
    unit_price: Decimal
    net: Decimal

class Quote(Model):
    id: str
    currency: Literal["SAR"] = "SAR"
    policy_version: str
    lines: List[QuoteLine]
    subtotal: Decimal
    discount_percent: Decimal
    discount_amount: Decimal
    net: Decimal
    vat: Decimal
    total: Decimal
    delivery_days: int
    status: Literal["DRAFT", "FINAL"] = "DRAFT"

class Approval(Model):
    id: str
    opportunity_id: str
    quote_id: str
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    approver: Optional[str] = None

class Proposal(Model):
    id: str
    opportunity_id: str
    quote_id: str
    status: Literal["DRAFT", "FINAL"]
    text: str

class CRMTask(Model):
    id: str
    opportunity_id: str
    description: str

class AuditEvent(Model):
    id: str
    operation: str
    record_id: str
    idempotency_key: str
    timestamp: str
