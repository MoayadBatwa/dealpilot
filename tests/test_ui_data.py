"""Presentation joins must reconcile current persisted state without writes."""
from decimal import Decimal
from dealpilot.database import Database
from dealpilot.crm import CRM
from dealpilot.ui_data import load_deals, sar
from dealpilot.agents import AgentWorkflow
from test_agents import ScriptedProvider, TEXT, CUSTOMER, extraction, number


def test_join_deduplicates_run_and_crm_and_uses_current_offer(tmp_path):
    db = Database(tmp_path / "view.sqlite3")
    state = AgentWorkflow(db, ScriptedProvider(extracted=extraction(discount=number("15")))).start(TEXT.replace("Discount 0", "Discount 15"), CUSTOMER)
    assert len(load_deals(db)) == 1
    assert load_deals(db)[0]["status"] == "APPROVAL_PENDING"
    approval = db.list("approval")[0]
    CRM(db).decide_approval(approval["id"], "APPROVED", "management", "ui-approve")
    assert load_deals(db)[0]["status"] == "APPROVED_AWAITING_RESUME"
    # A manager may have finalized through another session; stale run state must not win.
    CRM(db).finalize(approval["opportunity_id"], approval["quote_id"])
    count = len(db.audits())
    deal = load_deals(db)[0]
    assert deal["status"] == "OFFER_READY"
    assert deal["quote"]["status"] == "FINAL"
    assert deal["run"]["status"] == "APPROVAL_PENDING"
    assert len(db.audits()) == count
    assert sar(Decimal("1234.50")) == "SAR 1,234.50"


def test_stopped_inquiry_without_opportunity_still_appears(tmp_path):
    db = Database(tmp_path / "stopped.sqlite3")
    AgentWorkflow(db, ScriptedProvider(extracted=extraction(users=None))).start(TEXT, CUSTOMER)
    deal = load_deals(db)[0]
    assert deal["status"] == "NEEDS_INFORMATION"
    assert deal["name"] == CUSTOMER.name
    assert deal["opportunity"] is None
