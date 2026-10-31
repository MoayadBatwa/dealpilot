"""Business navigation smoke tests; no live provider calls in the UI suite."""
import pytest
from streamlit.testing.v1 import AppTest
from dealpilot.database import Database
from dealpilot.verification import verify


@pytest.fixture(autouse=True)
def offline_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("DEALPILOT_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("DEALPILOT_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("DEALPILOT_DB", str(tmp_path / "dashboard.sqlite3"))


def open_page(app, name):
    next(r for r in app.radio if r.label == "Navigation").set_value(name).run()
    assert not app.exception
    return app


def test_dashboard_renders():
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "Dashboard"
    assert len(app.metric) == 4
    assert app.metric[0].value == "9"
    assert next(r for r in app.radio if r.label == "Navigation").options == ["Dashboard", "New Opportunity", "Deals", "Approvals"]
    assert not app.tabs
    next(b for b in app.button if b.key == "dashboard_new").click().run()
    assert app.title[0].value == "New Opportunity"
    assert not app.exception


def test_dashboard_management_workflow(tmp_path):
    app = AppTest.from_file("app.py").run(timeout=30)
    open_page(app, "Approvals")
    assert next(b for b in app.button if b.label == "Approve").disabled
    next(s for s in app.selectbox if s.label == "Reviewing as").select("management").run()
    next(b for b in app.button if b.label == "Approve").click().run()
    assert not app.exception
    assert any("Approval alone does not finalize" in item.value for item in app.info)
    next(b for b in app.button if b.label == "Resume Workflow").click().run()
    assert not app.exception
    db = Database(tmp_path / "dashboard.sqlite3")
    approval = db.list("approval")[0]
    assert approval["status"] == "APPROVED"
    assert db.get("quote", approval["quote_id"])["status"] == "FINAL"
    assert verify(db) == []
    assert any("queue is clear" in item.value for item in app.success)


def test_ai_mode_without_key_is_unavailable_and_simulation_works(tmp_path):
    app = AppTest.from_file("app.py").run(timeout=30)
    open_page(app, "New Opportunity")
    assert next(b for b in app.button if b.label == "Analyze opportunity").disabled
    assert any("AI analysis is unavailable" in item.value for item in app.warning)
    assert len(app.text_input) == 1
    assert app.text_area[0].label == "What does the customer need?"
    db = Database(tmp_path / "dashboard.sqlite3")
    assert db.list("quote") and not db.list("agent_run")
    next(s for s in app.selectbox if s.label == "Tools").select("Test Scenarios").run()
    assert app.title[0].value == "Test Scenarios"
    assert not app.exception


def test_dashboard_uses_local_groq_configuration(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=dummy-local-ui-test-key\nGROQ_MODEL=openai/gpt-oss-120b\n")
    monkeypatch.setenv("DEALPILOT_ENV_FILE", str(env))
    app = AppTest.from_file("app.py").run(timeout=30)
    open_page(app, "New Opportunity")
    assert not next(b for b in app.button if b.label == "Analyze opportunity").disabled
    assert any("Groq" in item.value for item in app.caption)
    assert not any("dummy-local-ui-test-key" in item.value for item in app.caption)


def test_deals_are_readable_and_searchable():
    app = AppTest.from_file("app.py").run(timeout=30)
    open_page(app, "Deals")
    assert any(e.label == "Advanced Details" for e in app.expander)
    assert any(m.label == "Total including VAT" for m in app.metric) or app.info
    next(t for t in app.text_input if t.label == "Search companies").set_value("no matching customer").run()
    assert any("No deals match" in item.value for item in app.info)
    assert not app.exception


def test_persisted_ai_approval_state_and_resume(tmp_path):
    # Explicit TEST DOUBLE builds graph records offline; production UI still uses real providers.
    from test_agents import ScriptedProvider, extraction, number, TEXT, CUSTOMER
    from dealpilot.agents import AgentWorkflow
    db = Database(tmp_path / "dashboard.sqlite3")
    state = AgentWorkflow(db, ScriptedProvider(extracted=extraction(discount=number("15")))).start(TEXT.replace("Discount 0", "Discount 15"), CUSTOMER)
    app = AppTest.from_file("app.py").run(timeout=30)
    open_page(app, "Deals")
    next(s for s in app.selectbox if s.label == "Source").select("AI-assisted").run()
    assert any("proposal remains a draft" in x.value.lower() for x in app.warning)
    assert any("Actual workflow execution trace" in x.value for x in app.markdown)
    open_page(app, "Approvals")
    next(s for s in app.selectbox if s.label == "Reviewing as").select("management").run()
    approval = db.get("approval", state["pending_approval"])
    app.button(key=f'{approval["id"]}:APPROVED').click().run()
    app.button(key="resume_" + approval["id"]).click().run()
    assert not app.exception
    assert db.get("agent_run", state["run_id"])["status"] == "OFFER_READY"
    assert verify(db) == []

def test_primary_analysis_replay_and_revision(tmp_path, monkeypatch):
    """TEST DOUBLE drives the actual graph; no live inference is claimed."""
    from test_agents import ScriptedProvider, TEXT, extraction, number
    provider = ScriptedProvider()
    monkeypatch.setattr("dealpilot.agent_ui.get_provider", lambda **kwargs: provider)
    app = AppTest.from_file("app.py").run(timeout=30)
    open_page(app, "New Opportunity")
    app.text_input[0].set_value("Fictional UI Workflow Services")
    app.text_area[0].set_value(TEXT)
    next(b for b in app.button if b.label == "Analyze opportunity").click().run(timeout=30)
    assert not app.exception
    db = Database(tmp_path / "dashboard.sqlite3")
    original = db.list("agent_run")[0]
    assert original["status"] == "OFFER_READY"
    assert any("finalized demo offer" in x.value.lower() for x in app.success)
    calls, audits = len(provider.calls), len(db.audits())
    next(b for b in app.button if b.label == "Analyze opportunity").click().run(timeout=30)
    assert not app.exception
    assert len(provider.calls) == calls and len(db.audits()) == audits
    next(b for b in app.button if b.label == "Revise inquiry").click().run()
    assert not app.exception
    assert any("Current revision 1" in x.value for x in app.info)
    provider.extracted = extraction(users=number("11"))
    app.text_area[0].set_value(TEXT.replace("10 users", "11 users"))
    next(b for b in app.button if b.label == "Analyze opportunity").click().run(timeout=30)
    assert not app.exception
    assert sorted(r["request"]["revision"] for r in db.list("agent_run")) == [1, 2]
    next(b for b in app.button if b.label == "Revise inquiry").click().run()
    provider.extracted = extraction(users=number("12"))
    app.text_area[0].set_value(TEXT.replace("10 users", "12 users"))
    next(b for b in app.button if b.label == "Analyze opportunity").click().run(timeout=30)
    assert not app.exception
    assert sorted(r["request"]["revision"] for r in db.list("agent_run")) == [1, 2, 3]
    next(b for b in app.button if b.key == "sidebar_new").click().run()
    assert not app.exception
    assert app.text_input[0].value == "" and app.text_area[0].value == ""
    assert verify(db) == []
