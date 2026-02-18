import sys
import types

import pytest

import slideflow.ai.providers as providers_module
from slideflow.utilities.exceptions import APIAuthenticationError, APIError, APIRateLimitError


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


def test_openai_authentication_error_maps_to_api_authentication_error(monkeypatch):
    fake_openai = types.ModuleType("openai")

    class APIError(Exception):
        pass

    class RateLimitError(APIError):
        pass

    class AuthenticationError(APIError):
        pass

    class _Completions:
        def create(self, *args, **kwargs):
            raise AuthenticationError("bad key")

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
    with pytest.raises(APIAuthenticationError):
        provider.generate_text("hello")


def test_openai_success_trims_response_content(monkeypatch):
    fake_openai = types.ModuleType("openai")
    captured = {}

    class APIError(Exception):
        pass

    class RateLimitError(APIError):
        pass

    class AuthenticationError(APIError):
        pass

    class _Message:
        content = "  response text  "

    class _Choice:
        message = _Message()

    class _Completions:
        def create(self, *args, **kwargs):
            captured["kwargs"] = kwargs
            return types.SimpleNamespace(choices=[_Choice()])

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

    provider = providers_module.OpenAIProvider(model="gpt-test", temperature=0.1)
    text = provider.generate_text("hello", top_p=0.8)
    assert text == "response text"
    assert captured["kwargs"]["model"] == "gpt-test"
    assert captured["kwargs"]["temperature"] == 0.1
    assert captured["kwargs"]["top_p"] == 0.8


def test_gemini_non_vertex_missing_api_key_raises_auth_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    provider = providers_module.GeminiProvider(model="gemini-test")
    with pytest.raises(APIAuthenticationError):
        provider.generate_text("hello")


def test_gemini_vertex_requires_project_and_location(monkeypatch):
    provider = providers_module.GeminiProvider(
        model="gemini-test",
        vertex=True,
        project=None,
        location="us-central1",
        credentials="{}",
    )

    with pytest.raises(APIAuthenticationError):
        provider.generate_text("hello")


def test_gemini_non_vertex_rate_limit_error_is_mapped(monkeypatch):
    google_mod = sys.modules.get("google")
    if google_mod is None:
        google_mod = types.ModuleType("google")
        google_mod.__path__ = []
        sys.modules["google"] = google_mod

    genai_mod = types.ModuleType("google.genai")
    genai_types_mod = types.ModuleType("google.genai.types")

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Client:
        def __init__(self, api_key=None, **kwargs):
            self.models = self

        def generate_content(self, *args, **kwargs):
            raise RuntimeError("rate limit exceeded")

    genai_types_mod.GenerateContentConfig = GenerateContentConfig
    genai_mod.Client = Client
    genai_mod.types = genai_types_mod

    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types_mod)
    setattr(google_mod, "genai", genai_mod)

    monkeypatch.setenv("GOOGLE_API_KEY", "abc123")
    provider = providers_module.GeminiProvider(model="gemini-test")

    with pytest.raises(APIRateLimitError):
        provider.generate_text("hello")


def test_gemini_import_error_maps_to_api_error(monkeypatch):
    google_mod = sys.modules.get("google")
    if google_mod is None:
        google_mod = types.ModuleType("google")
        google_mod.__path__ = []
        sys.modules["google"] = google_mod

    genai_mod = types.ModuleType("google.genai")
    genai_types_mod = types.ModuleType("google.genai.types")

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Client:
        def __init__(self, *args, **kwargs):
            raise ImportError("missing dependency")

    genai_types_mod.GenerateContentConfig = GenerateContentConfig
    genai_mod.Client = Client
    genai_mod.types = genai_types_mod

    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types_mod)
    setattr(google_mod, "genai", genai_mod)
    monkeypatch.setenv("GOOGLE_API_KEY", "abc123")

    provider = providers_module.GeminiProvider(model="gemini-test")
    with pytest.raises(APIError, match="Missing Gemini dependencies"):
        provider.generate_text("hello")
