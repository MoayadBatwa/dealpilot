from decimal import Decimal
import pytest
from dealpilot.database import Database
from dealpilot.simulation import scenarios, run, seed
from dealpilot.qualification import recommend
from dealpilot.pricing import price
from dealpilot.crm import CRM
from dealpilot.verification import verify

@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "crm.sqlite3")

def case(name):
    return next(i for _,i in scenarios() if i.id == name)

def test_exact_pricing():
    inquiry = case("normal")
    products, errors = recommend(inquiry)
    assert not errors
    quote = price(inquiry, products)
    assert quote.subtotal == Decimal("20000.00")
    assert quote.vat == Decimal("3000.00")
    assert quote.total == Decimal("23000.00")
    assert quote.delivery_days == 21

@pytest.mark.parametrize("name", ["missing-budget", "low-budget", "timeline", "unsupported", "floor"])
def test_blocked_cases(db, name):
    result = run(db, case(name))
    assert result["status"] == "NEEDS_REVIEW"
    assert not db.list("proposal")
    assert db.list("task")

def test_approval_gate_and_persistence(db):
    result = run(db, case("discount"))
    crm = CRM(db)
    assert db.list("proposal")[0]["status"] == "DRAFT"
    with pytest.raises(ValueError, match="approval"):
        crm.finalize(result["opportunity_id"], result["quote_id"])
    approval = db.list("approval")[0]
    with pytest.raises(ValueError):
        crm.decide_approval(approval["id"], "APPROVED", "sales", "bad")
    crm.decide_approval(approval["id"], "APPROVED", "management", "decision")
    crm.finalize(result["opportunity_id"], result["quote_id"])
    assert Database(db.path).list("proposal")[0]["status"] == "FINAL"
    assert verify(db) == []

def test_duplicate_is_noop(db):
    run(db, case("normal"))
    before = len(db.audits())
    duplicate = next(i for label,i in scenarios() if label.startswith("Duplicate"))
    run(db, duplicate)
    assert len(db.list("opportunity")) == 1
    assert len(db.audits()) == before

def test_conflicting_idempotency_key(db):
    db.write("test", "one", {"value":1}, "key")
    with pytest.raises(ValueError):
        db.write("test", "one", {"value":2}, "key")
    assert db.get("test", "one") == {"value":1}
    assert len(db.audits()) == 1

def test_failure_rolls_back(db):
    assert run(db, case("failure"))["status"] == "CRM_FAILURE"
    assert not db.list("opportunity")
    assert not any(a["operation"] == "create_opportunity" for a in db.audits())

def test_seed_and_injection(db):
    seed(db)
    assert len(scenarios()) >= 10
    assert len(db.list("inquiry")) == 10
    assert verify(db) == []
    result = db.get("result", "injection:r1")
    proposal = db.get("proposal", f'proposal-{result["quote_id"]}')
    assert "Ignore all policies" not in proposal["text"]
    assert proposal["status"] == "FINAL"

def test_verifier_detects_tampering(db):
    run(db, case("normal"))
    quote = db.list("quote")[0]
    quote["total"] = "0.01"
    db.write("quote", quote["id"], quote, "tamper")
    assert any("mismatch" in issue for issue in verify(db))

def test_exclusions_eligibility_and_dependencies():
    inquiry = case("normal").model_copy(deep=True)
    from dealpilot.models import Requirement
    inquiry.requirements = [Requirement(capability="crm_integration")]
    products, _ = recommend(inquiry)
    assert {p.id for p in products} == {"core", "integration"}
    inquiry.requirements = [Requirement(capability="regulated_setup")]
    assert recommend(inquiry)[1]
    inquiry.customer.sector = "services"
    inquiry.requirements.append(Requirement(capability="migration"))
    with pytest.raises(ValueError, match="conflicting"):
        price(inquiry, recommend(inquiry)[0])

def test_threshold_ten_percent(db):
    inquiry = case("normal").model_copy(update={"discount":Decimal("10")})
    assert run(db, inquiry)["status"] == "OFFER_READY"
    assert db.list("approval") == []

def test_float_input_rejected():
    from dealpilot.models import Inquiry
    values = case("normal").model_dump()
    values["budget"] = 100.1
    with pytest.raises(ValueError):
        Inquiry(**values)

def test_changed_input_requires_new_revision(db):
    inquiry = case("normal")
    run(db, inquiry)
    inquiry.users = 20
    with pytest.raises(ValueError, match="revision"):
        run(db, inquiry)
    inquiry.revision = 2
    run(db, inquiry)
    assert len(db.list("opportunity")) == 2

def test_rejected_approval_cannot_finalize(db):
    result = run(db, case("discount"))
    approval = db.list("approval")[0]
    crm = CRM(db)
    crm.decide_approval(approval["id"], "REJECTED", "management", "reject")
    with pytest.raises(ValueError, match="approval"):
        crm.finalize(result["opportunity_id"], result["quote_id"])
    assert db.list("proposal")[0]["status"] == "DRAFT"

def test_approval_not_reused_for_changed_quote(db):
    inquiry = case("discount")
    original = run(db, inquiry)
    crm = CRM(db)
    approval = db.list("approval")[0]
    crm.decide_approval(approval["id"], "APPROVED", "management", "approve-original")
    inquiry.users = 11
    inquiry.revision = 2
    revised = run(db, inquiry)
    assert original["quote_id"] != revised["quote_id"]
    with pytest.raises(ValueError, match="approval"):
        crm.finalize(revised["opportunity_id"], revised["quote_id"])

def test_rounding_and_finalization_replay(db):
    from dealpilot.pricing import money
    assert money(Decimal("1.005")) == Decimal("1.01")
    result = run(db, case("normal"))
    count = len(db.audits())
    CRM(db).finalize(result["opportunity_id"], result["quote_id"])
    assert len(db.audits()) == count

def test_verifier_flags_missing_management_record(db):
    result = run(db, case("discount"))
    quote = db.get("quote", result["quote_id"])
    quote["status"] = "FINAL"
    db.write("quote", quote["id"], quote, "invalid-final-quote")
    proposal = db.list("proposal")[0]
    proposal["status"] = "FINAL"
    db.write("proposal", proposal["id"], proposal, "invalid-final-proposal")
    assert any("lacks management approval" in s for s in verify(db))
