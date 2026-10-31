"""Live OpenAI-compatible providers. No fallback or simulated responses."""
import os
from typing import Any, Dict, Mapping, Optional, Protocol, Type
from pathlib import Path
from pydantic import BaseModel


class ProviderUnavailable(RuntimeError):
    pass


class ProviderFailure(RuntimeError):
    pass


class StructuredProvider(Protocol):
    def status(self) -> Dict[str, Any]: ...
    def generate(self, node: str, instructions: str, payload: Dict[str, Any], schema: Type[BaseModel]) -> Dict[str, Any]: ...


class OpenAIProvider:
    name = "OpenAI"
    key_variable = "OPENAI_API_KEY"
    model_variable = "OPENAI_MODEL"
    default_model = "gpt-4o-mini"
    base_url = "https://api.openai.com/v1"

    def __init__(self, settings: Optional[Mapping[str, str]] = None):
        self.settings = settings if settings is not None else os.environ

    def status(self) -> Dict[str, Any]:
        configured = bool(self.settings.get(self.key_variable, "").strip())
        return {"name": self.name, "model": self.settings.get(self.model_variable) or self.default_model,
                "available": configured, "live": True,
                "message": "Configured; connectivity and model access are checked on execution." if configured else f"AI mode unavailable: set {self.key_variable}. Deterministic simulation remains available."}

    def generate(self, node: str, instructions: str, payload: Dict[str, Any], schema: Type[BaseModel]) -> Dict[str, Any]:
        if not self.status()["available"]:
            raise ProviderUnavailable(f"AI mode unavailable: {self.key_variable} is missing")
        import json
        from openai import OpenAI, OpenAIError
        # No shared clients/secrets in graph state, UI session, SQLite or trace.
        try:
            with OpenAI(api_key=self.settings.get(self.key_variable), base_url=self.base_url, timeout=30.0, max_retries=0) as client:
                response = client.chat.completions.parse(
                    model=self.status()["model"],
                    messages=[{"role": "system", "content": instructions},
                              {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                    response_format=schema,
                    max_completion_tokens=2500,
                )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise ProviderFailure("Model refused or returned no structured output")
            return parsed.model_dump(mode="json")
        except OpenAIError as exc:
            # SDK exception strings may contain response/request data: do not persist them.
            raise ProviderFailure(f"{self.name} request failed ({type(exc).__name__}); check credentials, model access, quota and connectivity") from None


class GroqProvider(OpenAIProvider):
    name = "Groq"
    key_variable = "GROQ_API_KEY"
    model_variable = "GROQ_MODEL"
    default_model = "openai/gpt-oss-120b"
    base_url = "https://api.groq.com/openai/v1"


def get_provider(load_local_env: bool = False) -> StructuredProvider:
    """Environment overrides .env; configuration loading never mutates os.environ."""
    settings = {}
    if load_local_env:
        from dotenv import dotenv_values
        path = os.environ.get("DEALPILOT_ENV_FILE", str(Path(__file__).resolve().parents[2] / ".env"))
        settings.update({k:v for k,v in dotenv_values(path, interpolate=False).items() if v is not None})
    settings.update(os.environ)
    selected = settings.get("DEALPILOT_LLM_PROVIDER", "").strip().lower()
    if not selected:
        selected = "groq" if settings.get("GROQ_API_KEY", "").strip() else "openai"
    if selected not in ("openai", "groq"):
        raise ValueError("DEALPILOT_LLM_PROVIDER must be groq or openai")
    return GroqProvider(settings) if selected == "groq" else OpenAIProvider(settings)
