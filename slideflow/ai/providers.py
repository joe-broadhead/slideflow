from __future__ import annotations

from typing import Protocol, Any, Dict


class AIProvider(Protocol):
    """Protocol for AI text generation providers."""

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from a prompt."""
        ...


class OpenAIProvider:
    """OpenAI ChatCompletion provider."""

    def __init__(self, model: str = "gpt-3.5-turbo", **defaults: Any) -> None:
        self.model = model
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        import openai

        params: Dict[str, Any] = {**self.defaults, **kwargs}
        messages = [{"role": "user", "content": prompt}]
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=messages,
            **params,
        )
        return response["choices"][0]["message"]["content"].strip()


class GeminiProvider:
    """Google Generative AI (Gemini) provider."""

    def __init__(self, model: str = "gemini-pro", **defaults: Any) -> None:
        self.model = model
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        import google.generativeai as genai

        params: Dict[str, Any] = {**self.defaults, **kwargs}
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(prompt, **params)
        # google-generativeai response has .text attribute
        return getattr(response, "text", str(response))


AI_PROVIDERS: Dict[str, AIProvider] = {
    "openai": OpenAIProvider(),
    "gemini": GeminiProvider(),
}
