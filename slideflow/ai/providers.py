from __future__ import annotations
from typing import Protocol, Any, Dict, runtime_checkable

@runtime_checkable
class AIProvider(Protocol):
    """Protocol for AI text generation providers."""

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from a prompt."""
        ...


class OpenAIProvider:
    """OpenAI ChatCompletion provider."""

    def __init__(self, model: str = "gpt-4o", **defaults: Any) -> None:
        self.model = model
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        import openai

        client = openai.OpenAI()
        params: Dict[str, Any] = {**self.defaults, **kwargs}
        print(params, self.model)
        messages = [{"role": "user", "content": prompt}]
        response = client.chat.completions.create(
            model = self.model,
            messages = messages,
            **params,
        )
        print(response)
        return response.choices[0].message.content.strip()


class GeminiProvider:
    """Google Generative AI (Gemini) provider.

    Parameters
    ----------
    model:
        Name of the model to use.
    vertex:
        If ``True`` use Vertex AI endpoints when available.
    project:
        Google Cloud project ID for Vertex AI.
    location:
        Google Cloud region for Vertex AI.
    defaults:
        Additional keyword arguments passed to ``generate_content``.
    """

    def __init__(
        self,
        model: str = "gemini-pro",
        *,
        vertex: bool = False,
        project: str | None = None,
        location: str | None = None,
        **defaults: Any,
    ) -> None:
        self.model = model
        self.vertex = vertex
        self.project = project
        self.location = location
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        import os
        import google.generativeai as genai

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key = api_key)

        params: Dict[str, Any] = {**self.defaults, **kwargs}
        
        # Filter out provider initialization parameters and prepare generation config
        invalid_params = {"model", "vertex", "project", "location"}
        
        # Build generation config from parameters
        generation_config = {}
        valid_generation_params = {"max_output_tokens", "temperature", "top_p", "top_k"}
        
        for k, v in params.items():
            if k not in invalid_params:
                if k == "max_tokens":
                    generation_config["max_output_tokens"] = v
                elif k in valid_generation_params:
                    generation_config[k] = v

        # Prepare generation config if any parameters are set
        config = genai.GenerationConfig(**generation_config) if generation_config else None

        if self.vertex and hasattr(genai, "Client"):
            client = genai.Client(
                vertexai = True,
                project = self.project,
                location = self.location,
            )

            response = client.models.generate_content(
                model = self.model,
                contents = prompt,
                generation_config = config,
            )
        else:
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(
                prompt, 
                generation_config=config
            )

        return getattr(response, "text", str(response))

AI_PROVIDERS: Dict[str, AIProvider] = {
    "openai": OpenAIProvider(),
    "gemini": GeminiProvider(),
}
