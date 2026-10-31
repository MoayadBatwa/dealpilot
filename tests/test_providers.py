"""Offline provider checks: mocked transport is not live inference."""
import json
import os
import httpx
import pytest
from dealpilot.llm import GroqProvider, OpenAIProvider, get_provider, ProviderUnavailable
from dealpilot.agent_models import SolutionSelection


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for key in ("OPENAI_API_KEY", "GROQ_API_KEY", "OPENAI_MODEL", "GROQ_MODEL", "DEALPILOT_LLM_PROVIDER"):
        monkeypatch.delenv(key, raising=False)


def test_groq_key_selects_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy-groq-test-key")
    assert isinstance(get_provider(), GroqProvider)
    assert get_provider().status()["model"] == "openai/gpt-oss-120b"
    assert "dummy-groq" not in json.dumps(get_provider().status())


def test_explicit_openai_has_no_automatic_fallback(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy-test-key")
    monkeypatch.setenv("DEALPILOT_LLM_PROVIDER", "openai")
    provider = get_provider()
    assert type(provider) is OpenAIProvider
    assert not provider.status()["available"]


def test_local_dotenv_is_loaded_without_mutating_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=local-test-key\nGROQ_MODEL=openai/gpt-oss-120b\n")
    monkeypatch.setenv("DEALPILOT_ENV_FILE", str(env))
    provider = get_provider(load_local_env=True)
    assert provider.status()["name"] == "Groq"
    assert provider.status()["available"]
    assert "GROQ_API_KEY" not in os.environ
    monkeypatch.setenv("GROQ_MODEL", "shell-model")
    assert get_provider(load_local_env=True).status()["model"] == "shell-model"


def test_invalid_provider_is_explicit(monkeypatch):
    monkeypatch.setenv("DEALPILOT_LLM_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="groq or openai"):
        get_provider()


def test_missing_groq_key_has_explicit_status():
    provider = GroqProvider({})
    assert not provider.status()["available"]
    with pytest.raises(ProviderUnavailable, match="GROQ_API_KEY"):
        provider.generate("test", "instructions", {}, SolutionSelection)


def test_groq_sdk_uses_groq_host_and_strict_schema(monkeypatch):
    import openai
    client_type = openai.OpenAI
    observed = []
    expected = {"product_ids":["core"], "matches":[{"capability":"crm", "product_id":"core"}]}
    def respond(request):
        observed.append((request.url.host, json.loads(request.content)))
        return httpx.Response(200, json={"id":"groq-mock", "object":"chat.completion", "created":0, "model":"test-only",
            "choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":json.dumps(expected)}}]})
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client_type(http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs))
    provider = GroqProvider({"GROQ_API_KEY":"dummy-test-key", "GROQ_MODEL":"openai/gpt-oss-120b"})
    assert provider.generate("solution", "test instructions", {}, SolutionSelection) == expected
    host, body = observed[0]
    assert host == "api.groq.com"
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["response_format"]["json_schema"]["strict"] is True
