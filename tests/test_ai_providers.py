import sys
import types

import pytest

import slideflow.ai.providers as providers_module
from slideflow.utilities.exceptions import APIRateLimitError


def test_openai_rate_limit_error_maps_to_api_rate_limit_error(monkeypatch):
    fake_openai = types.ModuleType("openai")

    class APIError(Exception):
        pass

    class RateLimitError(APIError):
        pass

    class AuthenticationError(APIError):
        pass

    class _Completions:
        def create(self, *args, **kwargs):
            raise RateLimitError("too many requests")

    class _Chat:
        completions = _Completions()

    class OpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = _Chat()

    fake_openai.APIError = APIError
    fake_openai.RateLimitError = RateLimitError
    fake_openai.AuthenticationError = AuthenticationError
    fake_openai.OpenAI = OpenAI

    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    provider = providers_module.OpenAIProvider(model="gpt-test")

    with pytest.raises(APIRateLimitError):
        provider.generate_text("hello")


def test_gemini_non_vertex_uses_google_genai_client_api(monkeypatch):
    captured = {}

    google_mod = sys.modules.get("google")
    if google_mod is None:
        google_mod = types.ModuleType("google")
        google_mod.__path__ = []
        sys.modules["google"] = google_mod

    genai_mod = types.ModuleType("google.genai")
    genai_types_mod = types.ModuleType("google.genai.types")

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            captured["config_kwargs"] = kwargs

    class Client:
        def __init__(self, api_key=None, **kwargs):
            captured["api_key"] = api_key
            self.models = self

        def generate_content(self, model, contents, config=None):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return types.SimpleNamespace(text="gemini-ok")

    genai_types_mod.GenerateContentConfig = GenerateContentConfig
    genai_mod.Client = Client
    genai_mod.types = genai_types_mod

    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types_mod)
    setattr(google_mod, "genai", genai_mod)

    monkeypatch.setenv("GOOGLE_API_KEY", "abc123")

    provider = providers_module.GeminiProvider(
        model="gemini-test",
        max_tokens=128,
        temperature=0.25,
    )

    response = provider.generate_text("Summarize", top_p=0.7)

    assert response == "gemini-ok"
    assert captured["api_key"] == "abc123"
    assert captured["model"] == "gemini-test"
    assert captured["contents"] == "Summarize"
    assert captured["config_kwargs"]["max_output_tokens"] == 128
    assert captured["config_kwargs"]["temperature"] == 0.25
    assert captured["config_kwargs"]["top_p"] == 0.7
