"""Timeline regression tests: fixed Saudi-time references, no live model calls."""
from datetime import datetime, timezone
import pytest
from dealpilot.durations import normalize_timeline
from dealpilot.agents import AgentWorkflow
from dealpilot.models import Customer
from dealpilot.database import Database
from dealpilot.ui_data import load_deals
from dealpilot.deal_insights import business_status
from test_agents import ScriptedProvider, extraction, number

REFERENCE = datetime(2026, 10, 31, 9, tzinfo=timezone.utc)  # Noon, Saudi Arabia.
CUSTOMER = Customer(id="riyadh-logistics", name="Riyadh Logistics Co.", sector="services")
INQUIRY = "We need CRM integration for 10 users. Our budget is SAR 180,000, and our target delivery is six weeks. We are requesting a 15% discount."


@pytest.mark.parametrize("phrase,days", [
    ("six weeks",42), ("6 weeks",42), ("six-weeks",42), ("within six weeks",42),
    ("42 days",42), ("forty-two days",42), ("1 week",7), ("within 3 weeks",21),
    ("2 months",61), ("two months",61), ("1 year",365), ("one year",365),
    ("خلال ٣ أسابيع",21), ("خلال ۳ أسابيع",21), ("خلال ستة أسابيع",42),
    ("خلال شهرين",61), ("خلال أسبوع",7), ("بعد سنة",365),
    ("by December 15, 2026",45), ("by 2026-12-15",45), ("2026-12-15",45),
    ("بحلول ١٥ ديسمبر ٢٠٢٦",45), ("next Friday",6), ("الجمعة القادمة",6),
    ("end of next month",30), ("نهاية الشهر القادم",30), ("no later than six weeks",42),
])
def test_supported_timeline_expressions(phrase, days):
    result = normalize_timeline(phrase, reference_at=REFERENCE)
    assert result.requested_days == days
    assert not result.clarifications
    assert result.original_text and result.source_phrase in phrase
    assert result.reference_at.utcoffset().total_seconds() == 10800


@pytest.mark.parametrize("phrase,precision", [("approximately six weeks","approximate"), ("approximately within six weeks","approximate"), ("ideally by December 15, 2026","tentative"), ("يفضل خلال ستة أسابيع","tentative")])
def test_soft_deadline_is_not_hardened(phrase, precision):
    result = normalize_timeline(phrase, reference_at=REFERENCE)
    assert result.precision == precision
    assert result.requested_days is None
    assert result.clarifications and not result.explicitly_confirmed


@pytest.mark.parametrize("phrase", ["ASAP", "as soon as possible", "في أسرع وقت", "عاجل"])
def test_urgency_has_no_invented_deadline(phrase):
    result = normalize_timeline(phrase, reference_at=REFERENCE)
    assert result.kind == "urgency"
    assert result.requested_days is None and result.deadline is None
    assert result.clarifications


def test_missing_and_non_delivery_dates_are_not_deadlines():
    for text in ("We need CRM. Budget SAR 180000.", "Our company was established on December 15, 2020.", "Subscription for 2 months. Budget confirmed."):
        result = normalize_timeline(text, reference_at=REFERENCE)
        assert result.requested_days is None
        assert result.clarifications


def test_calendar_months_and_years_are_not_fixed_approximations():
    jan = datetime(2027, 1, 31, 12, tzinfo=timezone.utc)
    assert normalize_timeline("2 months", reference_at=jan).requested_days == 59
    assert normalize_timeline("1 month", reference_at=jan).deadline.isoformat() == "2027-02-28"
    leap = datetime(2024, 2, 29, 12, tzinfo=timezone.utc)
    assert normalize_timeline("1 year", reference_at=leap).deadline.isoformat() == "2025-02-28"
    assert normalize_timeline("2 months").requested_days is None


def test_date_and_weekday_use_saudi_local_recorded_date():
    near_midnight = datetime(2026, 10, 31, 22, tzinfo=timezone.utc)  # Already Nov 1 in Riyadh.
    assert normalize_timeline("by December 15, 2026", reference_at=near_midnight).requested_days == 44
    friday = datetime(2026, 11, 6, 9, tzinfo=timezone.utc)
    assert normalize_timeline("next Friday", reference_at=friday).requested_days == 7
    assert normalize_timeline("next Friday").requested_days is None
    with pytest.raises(ValueError, match="timezone"):
        normalize_timeline("next Friday", reference_at=datetime(2026, 10, 31))


@pytest.mark.parametrize("phrase", ["6 weeks or 8 weeks", "within six weeks, but by December 15, 2026", "4 to 6 weeks", "6 business days", "by 2026-02-30", "by 2026-10-30", "by 1448-01-01 Hijri"])
def test_ambiguous_or_invalid_timeline_needs_clarification(phrase):
    result = normalize_timeline(phrase, reference_at=REFERENCE)
    assert result.requested_days is None
    assert result.clarifications


def test_valid_explicit_days_are_preserved_and_conflicts_flagged():
    good = normalize_timeline("42 days", 42, "42", REFERENCE)
    assert good.requested_days == 42 and not good.issues
    conflict = normalize_timeline("45 days and six weeks", 45, "45", REFERENCE)
    assert conflict.requested_days == 45
    assert conflict.issues
    assert normalize_timeline("six weeks and 42 days", reference_at=REFERENCE).requested_days == 42


def test_explicit_confirmation_is_not_invented():
    assert not normalize_timeline("Budget confirmed. Target delivery is six weeks", reference_at=REFERENCE).explicitly_confirmed
    assert normalize_timeline("Our confirmed delivery target is six weeks", reference_at=REFERENCE).explicitly_confirmed


def test_riyadh_logistics_null_model_timeline_is_normalized_and_persisted(tmp_path):
    provider = ScriptedProvider(extracted=extraction(budget={"value":"180000", "source":"180,000"}, discount=number("15"), requested_days=None))
    db = Database(tmp_path / "crm.sqlite3")
    workflow = AgentWorkflow(db, provider)
    state = workflow.start(INQUIRY, CUSTOMER, received_at=REFERENCE)
    assert state["status"] == "APPROVAL_PENDING"
    assert state["inquiry"]["requested_days"] == 42
    assert state["inquiry"]["budget"] == "180000" and state["inquiry"]["discount"] == "15"
    assert state["timeline"]["duration_value"] == 6 and state["timeline"]["unit"] == "week"
    assert state["timeline"]["source_phrase"] == "six weeks"
    key = f'{state["inquiry"]["id"]}:r1'
    assert db.get("inquiry", key)["requested_days"] == 42
    assert db.get("timeline", key)["reference_at"] == "2026-10-31T12:00:00+03:00"
    deal = load_deals(db)[0]
    assert deal["inquiry"]["requested_days"] == 42
    assert business_status(deal) == "Pending Approval"
    assert deal["quote"]["discount_percent"] == "15"
    assert db.list("approval")[0]["status"] == "PENDING"
    count = len(db.audits())
    assert workflow.start(INQUIRY, CUSTOMER, received_at=datetime(2027, 1, 1, tzinfo=timezone.utc)) == state
    assert len(db.audits()) == count and len(db.list("opportunity")) == 1


def test_revision_has_its_own_recorded_anchor_and_metadata(tmp_path):
    db = Database(tmp_path / "revision.sqlite3")
    provider = ScriptedProvider(extracted=extraction(budget={"value":"180000", "source":"180,000"}, discount=number("15"), requested_days=None))
    flow = AgentWorkflow(db, provider)
    first = flow.start(INQUIRY, CUSTOMER, received_at=REFERENCE)
    second = flow.start(INQUIRY.replace("six weeks", "2 months"), CUSTOMER, revision=2, received_at=REFERENCE)
    assert second["inquiry"]["requested_days"] == 61
    assert db.get("inquiry", f'{first["inquiry"]["id"]}:r1')["requested_days"] == 42
    assert db.get("inquiry", f'{second["inquiry"]["id"]}:r2')["requested_days"] == 61
    assert db.get("timeline", f'{second["inquiry"]["id"]}:r2')["unit"] == "month"


def test_conflicting_timeline_cannot_enter_crm_execution(tmp_path):
    provider = ScriptedProvider(extracted=extraction(requested_days=None))
    text = "CRM integration for 10 users. Budget 100000. Discount 0%. Delivery within six weeks or eight weeks."
    db = Database(tmp_path / "conflict.sqlite3")
    result = AgentWorkflow(db, provider).start(text, CUSTOMER, received_at=REFERENCE)
    assert result["status"] == "NEEDS_INFORMATION"
    assert any("Conflicting" in item for item in result["policy_findings"])
    assert not db.list("opportunity") and not db.list("quote")
    assert provider.calls == ["intake"]


def test_unrecognized_model_phrase_is_retained_without_inventing_days(tmp_path):
    provider = ScriptedProvider(extracted=extraction(requested_days=None, timeline_source="after the next holiday"))
    db = Database(tmp_path / "unknown.sqlite3")
    text = "CRM integration for 10 users. Budget 100000. Discount 0%. Deliver after the next holiday."
    result = AgentWorkflow(db, provider).start(text, CUSTOMER, received_at=REFERENCE)
    assert result["timeline"]["source_phrase"] == "after the next holiday"
    assert result["timeline"]["requested_days"] is None
    assert result["status"] == "NEEDS_INFORMATION"


def test_urgency_clarification_is_visible_in_existing_deal_insights(tmp_path):
    from dealpilot.deal_insights import decision_explanation
    provider = ScriptedProvider(extracted=extraction(requested_days=None, timeline_source="ASAP"))
    db = Database(tmp_path / "urgent.sqlite3")
    text = "CRM integration for 10 users. Budget 100000. Discount 0%. Please deliver ASAP."
    result = AgentWorkflow(db, provider).start(text, CUSTOMER, received_at=REFERENCE)
    assert result["status"] == "NEEDS_INFORMATION"
    deal = load_deals(db)[0]
    assert deal["timeline"]["kind"] == "urgency"
    assert any("What specific delivery date" in question for question in decision_explanation(deal)[1])
    assert not db.list("quote")


def test_trusted_structured_days_remain_valid_without_source_text():
    result = normalize_timeline("No extra narrative.", explicit_days=42, reference_at=REFERENCE)
    assert result.requested_days == 42
    assert not result.clarifications


def test_time_of_day_is_not_silently_dropped():
    result = normalize_timeline("by 2026-12-15T23:00:00Z", reference_at=REFERENCE)
    assert result.requested_days is None
    assert any("time-of-day" in q.lower() for q in result.clarifications)


def test_day_of_month_is_not_used_as_duration_by_model():
    result = normalize_timeline("by December 15, 2026", explicit_days=15, explicit_source="15", reference_at=REFERENCE)
    assert result.requested_days == 45
    assert result.clarifications


SIX_WEEK_PHRASES = [
    "within six weeks",
    "within a six-week period",
    "a six-week delivery timeline",
    "delivery in 6 weeks",
    "delivery within 6-week timeframe",
    "six weeks from now",
]


@pytest.mark.parametrize("phrase", SIX_WEEK_PHRASES)
def test_six_week_phrases_preserve_full_source_and_precision(phrase):
    parsed = normalize_timeline(phrase, reference_at=REFERENCE)
    assert parsed.requested_days == 42
    assert parsed.source_phrase == parsed.original_text == phrase
    assert parsed.precision == "exact"
    assert parsed.duration_value == 6 and parsed.unit == "week"
    assert not parsed.clarifications
    if "within" in phrase:
        assert parsed.constraint == "latest"


@pytest.mark.parametrize("phrase", SIX_WEEK_PHRASES)
@pytest.mark.parametrize("model_days", [None, "6", "42", "60"])
def test_six_week_phrases_through_full_graph_and_crm(tmp_path, phrase, model_days):
    # Real compiled AgentWorkflow, pricing and CRM; only provider output is a TEST DOUBLE.
    evidence = None if model_days is None else {"value":model_days, "source":phrase}
    provider = ScriptedProvider(extracted=extraction(discount=number("15"), requested_days=evidence, timeline_source=phrase))
    db = Database(tmp_path / "six-week.sqlite3")
    text = f"CRM integration for 10 users. Budget 100000. Discount 15%. Our target is {phrase}."
    flow = AgentWorkflow(db, provider)
    state = flow.start(text, CUSTOMER, received_at=REFERENCE)
    assert state["status"] == "APPROVAL_PENDING"
    assert state["inquiry"]["requested_days"] == 42
    key = f'{state["inquiry"]["id"]}:r1'
    assert db.get("inquiry", key)["requested_days"] == 42
    metadata = db.get("timeline", key)
    assert metadata["source_phrase"] == phrase
    assert metadata["precision"] == "exact" and not metadata["clarifications"]
    assert db.list("approval")[0]["status"] == "PENDING"
    assert db.list("quote")[0]["status"] == "DRAFT"
    assert load_deals(db)[0]["inquiry"]["requested_days"] == 42
    assert provider.calls == ["intake", "solution", "proposal"]
    count = len(db.audits())
    assert flow.start(text, CUSTOMER, received_at=REFERENCE) == state
    assert len(db.audits()) == count and len(db.list("opportunity")) == 1


@pytest.mark.parametrize("phrase", ["a six-week delivery timeline", "within a six-week period", "within six weeks"])
def test_delivery_scope_after_support_wording(phrase):
    result = normalize_timeline("We need CRM integration and bilingual support with " + phrase + ".", reference_at=REFERENCE)
    assert result.requested_days == 42
    assert not result.clarifications


def test_support_term_is_not_mistaken_for_delivery():
    assert normalize_timeline("Support for a six-week period.", reference_at=REFERENCE).requested_days is None
    assert normalize_timeline("Payment within six weeks.", reference_at=REFERENCE).requested_days is None


@pytest.mark.parametrize("phrase", ["approximately within a six-week period", "ideally a six-week delivery timeline", "six-week or eight-week delivery timeline"])
def test_model_cannot_remove_real_customer_ambiguity(tmp_path, phrase):
    provider = ScriptedProvider(extracted=extraction(requested_days={"value":"42", "source":"six-week"}, timeline_source=phrase))
    db = Database(tmp_path / "ambiguous.sqlite3")
    text = f"CRM integration for 10 users. Budget 100000. Discount 0%. We request {phrase}."
    state = AgentWorkflow(db, provider).start(text, CUSTOMER, received_at=REFERENCE)
    assert state["status"] == "NEEDS_INFORMATION"
    assert state["timeline"]["requested_days"] is None
    assert state["timeline"]["clarifications"]
    assert not db.list("opportunity") and not db.list("quote")


def test_null_or_paraphrased_model_hint_cannot_erase_clear_duration(tmp_path):
    provider = ScriptedProvider(extracted=extraction(requested_days=None, timeline_source="within six weeks"))
    db = Database(tmp_path / "hint.sqlite3")
    text = "CRM integration for 10 users. Budget 100000. Discount 0%. We require a six-week delivery timeline."
    state = AgentWorkflow(db, provider).start(text, CUSTOMER, received_at=REFERENCE)
    assert state["status"] == "OFFER_READY"
    assert state["inquiry"]["requested_days"] == 42
    assert state["timeline"]["source_phrase"] == "a six-week delivery timeline"
    assert not state["timeline"]["clarifications"]


def test_saved_failed_revision_is_not_silently_rewritten(tmp_path, monkeypatch):
    from dealpilot import durations
    original_scope = durations._scope
    db = Database(tmp_path / "cached.sqlite3")
    provider = ScriptedProvider(extracted=extraction(requested_days=None))
    flow = AgentWorkflow(db, provider)
    text = "CRM integration for 10 users. Budget 100000. Discount 0%. We need support with a six-week delivery timeline."
    # Reproduce the former scope rejection in an isolated historical revision.
    with monkeypatch.context() as patch:
        patch.setattr(durations, "_scope", lambda *args: False)
        prior = flow.start(text, CUSTOMER, received_at=REFERENCE)
    assert durations._scope is original_scope
    assert prior["status"] == "NEEDS_INFORMATION"
    calls, audits = len(provider.calls), len(db.audits())
    assert flow.start(text, CUSTOMER, received_at=REFERENCE) == prior
    assert len(provider.calls) == calls and len(db.audits()) == audits
    revised = flow.start(text, CUSTOMER, revision=2, received_at=REFERENCE)
    assert revised["inquiry"]["requested_days"] == 42
    assert db.get("agent_run", prior["run_id"]) == prior
    assert len(db.list("opportunity")) == 1
