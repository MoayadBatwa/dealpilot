"""Truthful business projections and approval safety; all providers here are TEST DOUBLES."""
from copy import deepcopy
import pytest
from dealpilot.database import Database
from dealpilot.agents import AgentWorkflow
from dealpilot.crm import CRM
from dealpilot.ui_data import load_deals
from dealpilot.deal_insights import business_status, workflow_timeline, product_reasons, decision_explanation
from dealpilot.simulation import run, scenarios
from dealpilot.verification import save_verification, verify
from test_agents import ScriptedProvider, TEXT, CUSTOMER, extraction, number


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "brief.sqlite3")


def ai_run(db, **kwargs):
    text = kwargs.pop("text", TEXT)
    provider = kwargs.pop("provider", ScriptedProvider())
    return AgentWorkflow(db, provider).start(text, CUSTOMER)


def restricted(db):
    return ai_run(db, text=TEXT.replace("Discount 0", "Discount 15"), provider=ScriptedProvider(extracted=extraction(discount=number("15"))))


def stage(deal, key):
    return next(s for s in workflow_timeline(deal) if s["key"] == key)


@pytest.mark.parametrize("raw,business", [
    ("NEEDS_INFORMATION", "Needs Information"), ("RUNNING", "Analyzing"), ("QUALIFYING", "Analyzing"),
    ("DRAFT", "Ready for Review"), ("REJECTED", "Rejected"), ("PROVIDER_UNAVAILABLE", "Blocked"),
    ("UNSUPPORTED_REQUIREMENTS", "Blocked"), ("INFEASIBLE_TIMELINE", "Blocked"), ("OUTSIDE_BUDGET", "Blocked"),
    ("POLICY_BLOCKED", "Blocked"), ("VALIDATION_ERROR", "Blocked"), ("PROVIDER_ERROR", "Failed"),
    ("CRM_FAILURE", "Failed"), ("TOOL_ERROR", "Failed"), ("VERIFICATION_FAILED", "Failed"),
])
def test_business_status_mapping(raw, business):
    assert business_status({"status":raw, "inquiry":{}, "integrity_findings":[]}) == business


def test_normal_completion_has_saved_evidence_and_skips_approval(db):
    state = ai_run(db)
    deal = load_deals(db)[0]
    assert business_status(deal) == "Completed"
    assert deal["verification_current"] and deal["verification"]["status"] == "PASSED"
    assert stage(deal, "verified")["state"] == "Completed"
    assert stage(deal, "approval")["state"] == "Skipped"
    assert all(s["state"] == "Completed" for s in workflow_timeline(deal) if s["key"] != "approval")
    # Semantic stage ordering must not fabricate timestamps for trace-only steps.
    assert stage(deal, "solution")["timestamp"] is None
    assert stage(deal, "verified")["timestamp"]
    assert state["status"] == "OFFER_READY"


def test_pending_approved_resume_are_distinct_and_idempotent(db):
    state = restricted(db)
    assert business_status(load_deals(db)[0]) == "Pending Approval"
    assert stage(load_deals(db)[0], "approval")["state"] == "Completed"
    assert "pending" in stage(load_deals(db)[0], "approval")["detail"]
    approval = db.list("approval")[0]
    CRM(db).decide_approval(approval["id"], "APPROVED", "management", "approve")
    approved = load_deals(db)[0]
    assert business_status(approved) == "Approved"
    assert approved["quote"]["status"] == "DRAFT"
    # The decision changed the fingerprint; a previous check is not current.
    assert stage(approved, "verified")["state"] != "Completed"
    resumed = AgentWorkflow(Database(db.path)).resume(state["run_id"])
    assert business_status(load_deals(db)[0]) == "Completed"
    assert [e["node"] for e in resumed["trace"][len(state["trace"]):]] == ["supervisor", "resume", "supervisor", "verification", "supervisor"]
    before = len(db.audits())
    AgentWorkflow(Database(db.path)).resume(state["run_id"])
    assert len(db.audits()) == before
    assert len(db.list("opportunity")) == 1
    assert len(db.list("quote")) == 1


def test_missing_budget_does_not_complete_solution_or_quote(db):
    ai_run(db, provider=ScriptedProvider(extracted=extraction(budget=None)))
    deal = load_deals(db)[0]
    assert business_status(deal) == "Needs Information"
    assert stage(deal, "requirements")["state"] == "Completed"
    assert stage(deal, "solution")["state"] == "Blocked"
    assert stage(deal, "quote")["state"] == "Blocked"
    assert stage(deal, "proposal")["state"] == "Blocked"


def test_unsupported_node_success_is_not_a_successful_match(db):
    ai_run(db, text=TEXT + " telepathy", provider=ScriptedProvider(extracted=extraction(requirements=[{"capability":"unsupported:telepathy", "source":"telepathy"}])))
    deal = load_deals(db)[0]
    assert business_status(deal) == "Blocked"
    assert stage(deal, "solution")["state"] == "Blocked"
    assert stage(deal, "proposal")["state"] != "Completed"
    assert any("telepathy" in r for r in decision_explanation(deal)[1])


def test_outside_budget_has_calculation_but_not_validated_offer(db):
    ai_run(db, text=TEXT.replace("100000", "1000"), provider=ScriptedProvider(extracted=extraction(budget=number("1000"))))
    deal = load_deals(db)[0]
    assert deal["quote"]
    assert stage(deal, "quote")["state"] == "Blocked"
    assert any("22,000.00" in r for r in decision_explanation(deal)[1])


def test_crm_failure_is_failed_even_with_a_prepared_proposal(db, monkeypatch):
    from dealpilot import agents
    monkeypatch.setattr(agents, "run", lambda *args: {"status":"CRM_FAILURE"})
    ai_run(db)
    deal = load_deals(db)[0]
    assert business_status(deal) == "Failed"
    assert stage(deal, "proposal")["state"] == "Completed"
    assert stage(deal, "crm")["state"] == "Failed"
    assert stage(deal, "verified")["state"] != "Completed"


def test_catalog_reason_distinguishes_match_from_dependency(db):
    ai_run(db)
    reasons = {p["name"]:p["reasons"] for p in product_reasons(load_deals(db)[0])}
    assert any("dependency" in r for r in reasons["Nakhla CRM Annual"])
    assert any("REST connector" in r for r in reasons["Wasl CRM Integration"])


@pytest.mark.parametrize("decision", ["APPROVED", "REJECTED"])
def test_decisions_revalidate_exact_quote_before_writing(db, decision):
    restricted(db)
    approval = db.list("approval")[0]
    quote = db.list("quote")[0]
    quote["total"] = "0.01"
    db.write("quote", quote["id"], quote, "tampered-total")
    count = len(db.audits())
    with pytest.raises(ValueError, match="pricing"):
        CRM(db).decide_approval(approval["id"], decision, "management", "unsafe-decision")
    assert db.get("approval", approval["id"])["status"] == "PENDING"
    assert len(db.audits()) == count
    assert business_status(load_deals(db)[0]) == "Blocked"


def test_forged_approval_quote_reference_cannot_finalize(db):
    state = restricted(db)
    approval = db.list("approval")[0]
    CRM(db).decide_approval(approval["id"], "APPROVED", "management", "approve")
    approval = db.get("approval", approval["id"])
    approval["quote_id"] = "another-quote"
    db.write("approval", approval["id"], approval, "tampered-link")
    with pytest.raises(ValueError, match="approval"):
        CRM(db).finalize(state["execution_results"]["opportunity_id"], state["execution_results"]["quote_id"])
    assert not load_deals(db)[0]["offer_final"]


def test_legacy_final_offer_requires_saved_verification_without_rewriting_data(db):
    inquiry = next(i for _,i in scenarios() if i.id == "normal")
    run(db, inquiry)
    deal = load_deals(db)[0]
    assert deal["offer_final"] and business_status(deal) == "Ready for Review"
    assert stage(deal, "verified")["state"] == "Pending"
    report = save_verification(db, deal["opportunity"]["id"], verify(db))
    assert report["status"] == "PASSED"
    assert business_status(load_deals(db)[0]) == "Completed"
    count = len(db.audits())
    save_verification(db, deal["opportunity"]["id"], verify(db))
    assert len(db.audits()) == count


def test_stale_check_cannot_hide_record_tampering(db):
    ai_run(db)
    deal = load_deals(db)[0]
    assert business_status(deal) == "Completed"
    quote = deepcopy(deal["quote"])
    quote["total"] = "0.01"
    db.write("quote", quote["id"], quote, "changed-after-check")
    deal = load_deals(db)[0]
    assert not deal["verification_current"]
    assert business_status(deal) == "Blocked"
    assert stage(deal, "quote")["state"] == "Blocked"
    assert stage(deal, "verified")["state"] != "Completed"


def test_completed_resume_does_not_return_success_after_approval_is_revoked(db):
    state = restricted(db)
    approval = db.list("approval")[0]
    CRM(db).decide_approval(approval["id"], "APPROVED", "management", "approve")
    AgentWorkflow(db).resume(state["run_id"])
    approval = db.get("approval", approval["id"])
    approval.update(status="PENDING", approver=None)
    db.write("approval", approval["id"], approval, "external-record-change")
    with pytest.raises(ValueError, match="approval"):
        AgentWorkflow(db).resume(state["run_id"])
    assert business_status(load_deals(db)[0]) == "Blocked"


def test_rejection_and_sales_role_cannot_produce_an_offer(db):
    state = restricted(db)
    approval = db.list("approval")[0]
    with pytest.raises(ValueError, match="Management"):
        CRM(db).decide_approval(approval["id"], "APPROVED", "sales", "unauthorized")
    CRM(db).decide_approval(approval["id"], "REJECTED", "management", "reject")
    assert business_status(load_deals(db)[0]) == "Rejected"
    with pytest.raises(ValueError, match="approval"):
        AgentWorkflow(db).resume(state["run_id"])
    assert db.list("quote")[0]["status"] == "DRAFT"


def test_failed_verification_is_not_completed_from_empty_trace_errors(db):
    ai_run(db)
    deal = load_deals(db)[0]
    save_verification(db, deal["opportunity"]["id"], ["Explicit record check discrepancy"])
    deal = load_deals(db)[0]
    assert business_status(deal) == "Failed"
    assert stage(deal, "verified")["state"] == "Failed"


def test_repaired_record_can_be_verified_again_without_stale_idempotency_replay(db):
    ai_run(db)
    deal = load_deals(db)[0]
    original = deepcopy(deal["quote"])
    bad = {**original, "total":"0.01"}
    db.write("quote", bad["id"], bad, "corrupt")
    save_verification(db, deal["opportunity"]["id"], verify(db))
    assert business_status(load_deals(db)[0]) == "Failed"
    db.write("quote", original["id"], original, "repair")
    report = save_verification(db, deal["opportunity"]["id"], verify(db))
    assert report["check_revision"] == 3
    deal = load_deals(db)[0]
    assert business_status(deal) == "Completed"
    verification_events = [a for a in db.audits() if a["operation"] == "verify_records"]
    assert stage(deal, "verified")["timestamp"] == verification_events[-1]["timestamp"]


def test_creating_an_opportunity_alone_does_not_prove_analysis(db):
    inquiry = next(i for _,i in scenarios() if i.id == "normal")
    db.write("inquiry", "normal:r1", inquiry.model_dump(mode="json"), "intake-only", "receive_inquiry")
    CRM(db).create_opportunity(inquiry)
    deal = load_deals(db)[0]
    assert stage(deal, "inquiry")["state"] == "Completed"
    assert stage(deal, "requirements")["state"] == "Pending"
    assert stage(deal, "solution")["state"] == "Pending"
    assert stage(deal, "crm")["state"] == "Pending"
    assert stage(deal, "verified")["state"] == "Pending"


def test_failed_final_verification_can_resume_without_model_or_crm_replay(db, monkeypatch):
    from dealpilot import agents
    original_verify = agents.verify
    monkeypatch.setattr(agents, "verify", lambda db: ["Temporary reconciliation discrepancy"])
    provider = ScriptedProvider()
    state = ai_run(db, provider=provider)
    assert state["status"] == "VERIFICATION_FAILED"
    before_crm = [a for a in db.audits() if a["operation"] in ("create_opportunity", "finalize_quote", "finalize_proposal")]
    monkeypatch.setattr(agents, "verify", original_verify)
    recovered = AgentWorkflow(db).resume(state["run_id"])
    assert recovered["status"] == "OFFER_READY"
    assert business_status(load_deals(db)[0]) == "Completed"
    assert [e["node"] for e in recovered["trace"][len(state["trace"]):]] == ["supervisor", "verification", "supervisor"]
    assert [a for a in db.audits() if a["operation"] in ("create_opportunity", "finalize_quote", "finalize_proposal")] == before_crm
    assert provider.calls == ["intake", "solution", "proposal"]


def test_non_management_approval_record_is_not_presented_as_approved(db):
    restricted(db)
    approval = db.list("approval")[0]
    approval.update(status="APPROVED", approver="sales")
    db.write("approval", approval["id"], approval, "invalid-approver")
    deal = load_deals(db)[0]
    assert business_status(deal) == "Blocked"
    assert any("management authorization" in message for message in deal["integrity_findings"])
    with pytest.raises(ValueError, match="approval"):
        CRM(db).finalize(approval["opportunity_id"], approval["quote_id"])
