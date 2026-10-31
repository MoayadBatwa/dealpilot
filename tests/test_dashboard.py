from streamlit.testing.v1 import AppTest

def test_dashboard_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("DEALPILOT_DB", str(tmp_path / "dashboard.sqlite3"))
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert app.title[0].value == "◈ DealPilot AI"
    assert len(app.metric) == 4
    assert app.success

def test_dashboard_management_workflow(tmp_path, monkeypatch):
    from dealpilot.database import Database
    from dealpilot.verification import verify
    path = tmp_path / "interactive.sqlite3"
    monkeypatch.setenv("DEALPILOT_DB", str(path))
    app = AppTest.from_file("app.py").run(timeout=30)
    next(s for s in app.selectbox if s.label == "Simulated role").select("management").run()
    next(b for b in app.button if b.label == "Approved").click().run()
    assert not app.exception
    next(b for b in app.button if b.label == "Validate and finalize simulated offer").click().run()
    assert not app.exception
    db = Database(path)
    approved = db.list("approval")[0]
    assert approved["status"] == "APPROVED"
    assert db.get("quote", approved["quote_id"])["status"] == "FINAL"
    assert verify(db) == []

def test_ai_mode_without_key_is_unavailable_and_simulation_works(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("DEALPILOT_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("DEALPILOT_DB", str(tmp_path / "no-key.sqlite3"))
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert "AI Agent Workspace" in [tab.label for tab in app.tabs]
    assert next(b for b in app.button if b.label == "Run AI Agents").disabled
    assert any("AI mode unavailable" in item.value for item in app.warning)
    assert app.metric[0].value == "9"
    from dealpilot.database import Database
    db = Database(tmp_path / "no-key.sqlite3")
    assert db.list("quote")
    assert not db.list("agent_run")

def test_dashboard_uses_local_groq_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("DEALPILOT_LLM_PROVIDER", raising=False)
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=dummy-local-ui-test-key\nGROQ_MODEL=openai/gpt-oss-120b\n")
    monkeypatch.setenv("DEALPILOT_ENV_FILE", str(env))
    monkeypatch.setenv("DEALPILOT_DB", str(tmp_path / "groq-ui.sqlite3"))
    app = AppTest.from_file("app.py").run(timeout=30)
    assert not app.exception
    assert not next(b for b in app.button if b.label == "Run AI Agents").disabled
    assert any("sent to Groq" in item.value for item in app.info)
    assert not any("dummy-local-ui-test-key" in item.value for item in app.info)
