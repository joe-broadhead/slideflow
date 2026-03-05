"""AI provider implementations for text generation.

This module contains implementations of AI providers that can generate text
content for presentations. It includes support for OpenAI and Google Gemini,
with a protocol-based interface for adding new providers.

The module provides:
    - AIProvider protocol defining the provider interface
    - OpenAIProvider for OpenAI's GPT models
    - DatabricksProvider for Databricks Serving Endpoints
    - GeminiProvider for Google's Gemini models (both regular and Vertex AI)
"""

import os
import time
from typing import Any, ClassVar, Optional, Protocol, runtime_checkable

from google.oauth2 import service_account

from slideflow.constants import Defaults, Environment
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.exceptions import (
    APIAuthenticationError,
    APIError,
    APIRateLimitError,
)
from slideflow.utilities.logging import get_logger, log_api_operation

logger = get_logger(__name__)


def _apply_slideflow_extra_headers(
    headers: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Merge caller headers with a Slideflow user-agent identifier."""
    merged: dict[str, Any] = dict(headers or {})
    user_agent_key = next(
        (key for key in merged.keys() if key.lower() == "user-agent"), None
    )
    if user_agent_key is None:
        merged["User-Agent"] = Defaults.CLIENT_USER_AGENT
        return merged

    existing = str(merged.get(user_agent_key, "")).strip()
    if Defaults.CLIENT_USER_AGENT.lower() not in existing.lower():
        merged[user_agent_key] = (
            f"{existing} {Defaults.CLIENT_USER_AGENT}".strip()
            if existing
            else Defaults.CLIENT_USER_AGENT
        )
    return merged


@runtime_checkable
class AIProvider(Protocol):
    """Protocol for AI text generation providers.

    This protocol defines the interface that all AI providers must implement.
    It ensures consistency across different AI backends and enables easy
    addition of new providers.
    """

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Generate text based on the provided prompt.

        Args:
            prompt: The input prompt for text generation.
            **kwargs: Additional provider-specific parameters such as
                temperature, max_tokens, top_p, etc.

        Returns:
            Generated text response from the AI model.

        Raises:
            APIError: For general API errors.
            APIRateLimitError: When rate limits are exceeded.
            APIAuthenticationError: For authentication failures.
        """
        raise NotImplementedError


class OpenAIProvider:
    """OpenAI ChatCompletion provider for text generation.

    This provider uses OpenAI's Chat Completion API to generate text content.
    It supports all OpenAI chat models and handles authentication, rate
    limiting, and error cases appropriately.

    Requires OPENAI_API_KEY environment variable to be set.

    Attributes:
        provider_name: Class-level identifier for this provider type.
        model: The OpenAI model to use for generation.
        defaults: Default parameters to apply to all generation requests.

    Example:
        >>> provider = OpenAIProvider(model="gpt-4", temperature=0.7)
        >>> text = provider.generate_text("Summarize Q3 performance")
    """

    provider_name: ClassVar[str] = "openai"

    def __init__(self, model: str = Defaults.OPENAI_MODEL, **defaults: Any) -> None:
        """Initialize OpenAI provider with model and default parameters.

        Args:
            model: OpenAI model identifier (e.g., 'gpt-4', 'gpt-3.5-turbo').
                Defaults to the value specified in constants.
            **defaults: Default parameters for all requests. Common options:
                temperature (float): Controls randomness (0-2).
                max_tokens (int): Maximum tokens to generate.
                top_p (float): Nucleus sampling parameter.
                frequency_penalty (float): Reduce repetition (-2 to 2).
                presence_penalty (float): Encourage new topics (-2 to 2).
        """
        self.model = model
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using OpenAI's Chat Completion API.

        Args:
            prompt: The input prompt for text generation.
            **kwargs: Additional parameters to override defaults:
                temperature (float): Controls randomness (0-2).
                max_tokens (int): Maximum tokens to generate.
                top_p (float): Nucleus sampling parameter.
                frequency_penalty (float): Reduce repetition (-2 to 2).
                presence_penalty (float): Encourage new topics (-2 to 2).
                stop (list): Stop sequences.
                n (int): Number of completions to generate.

        Returns:
            Generated text with leading/trailing whitespace removed.

        Raises:
            APIError: For general OpenAI API errors or empty responses.
            APIRateLimitError: When OpenAI rate limits are exceeded.
            APIAuthenticationError: When OpenAI API key is invalid or missing.
        """
        try:
            import openai
        except ImportError as e:
            raise APIError(f"Missing OpenAI dependencies: {e}") from e

        start_time = time.time()
        try:
            client = openai.OpenAI()
            params = {**self.defaults, **kwargs}
            params["extra_headers"] = _apply_slideflow_extra_headers(
                params.get("extra_headers")
            )
            messages: Any = [{"role": "user", "content": prompt}]

            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                **params,
            )

            content = resp.choices[0].message.content
            if content is None:
                raise APIError("OpenAI API returned empty response")

            duration = time.time() - start_time
            log_api_operation(
                "openai",
                "generate_text",
                True,
                duration,
                model=self.model,
                chars_generated=len(content),
            )
            return content.strip()

        except openai.RateLimitError as e:
            duration = time.time() - start_time
            log_api_operation(
                "openai", "generate_text", False, duration, error="rate_limit"
            )
            raise APIRateLimitError(f"OpenAI rate limit exceeded: {e}") from e
        except openai.AuthenticationError as e:
            duration = time.time() - start_time
            log_api_operation(
                "openai", "generate_text", False, duration, error="auth_failed"
            )
            raise APIAuthenticationError(f"OpenAI authentication failed: {e}") from e
        except openai.APIError as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error=str(e))
            raise APIError(f"OpenAI API error: {e}") from e
        except Exception as e:
            duration = time.time() - start_time
            log_api_operation(
                "openai", "generate_text", False, duration, error="unexpected"
            )
            raise APIError(f"Unexpected OpenAI error: {e}") from e


class DatabricksProvider:
    """Databricks Serving Endpoints provider for text generation.

    This provider targets Databricks OpenAI-compatible Serving Endpoints via
    the `openai` SDK and is focused on text generation for SlideFlow
    `ai_text` replacements.
    """

    provider_name: ClassVar[str] = "databricks"
    _BLOCKED_TEXT_MODE_PARAMS: ClassVar[set[str]] = {
        "tools",
        "tool_choice",
        "stream",
        "n",
        "logprobs",
        "top_logprobs",
    }

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        **defaults: Any,
    ) -> None:
        """Initialize Databricks provider with endpoint and defaults.

        Args:
            model: Databricks serving endpoint name.
            base_url: OpenAI-compatible Databricks base URL. Defaults to
                `DATABRICKS_SERVING_BASE_URL`.
            api_key: Databricks token. Defaults to `DATABRICKS_TOKEN`.
            **defaults: Default generation parameters for requests.
        """
        self.model = model.strip() if model else ""
        self.base_url = base_url
        self.api_key = api_key
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using Databricks chat completions."""
        if not self.model:
            raise APIAuthenticationError(
                "Databricks provider requires a non-empty model endpoint name"
            )

        resolved_base_url = self.base_url or os.getenv(
            Environment.DATABRICKS_SERVING_BASE_URL
        )
        if not resolved_base_url:
            raise APIAuthenticationError(
                f"Databricks provider requires base_url or {Environment.DATABRICKS_SERVING_BASE_URL}"
            )

        resolved_api_key = self.api_key or os.getenv(Environment.DATABRICKS_TOKEN)
        if not resolved_api_key:
            raise APIAuthenticationError(
                f"Databricks provider requires api_key or {Environment.DATABRICKS_TOKEN}"
            )

        params = {**self.defaults, **kwargs}
        params["extra_headers"] = _apply_slideflow_extra_headers(
            params.get("extra_headers")
        )
        blocked = sorted(key for key in params if key in self._BLOCKED_TEXT_MODE_PARAMS)
        if blocked:
            raise APIError(
                "Databricks text mode does not support arguments: " + ", ".join(blocked)
            )

        try:
            import openai
        except ImportError as e:
            raise APIError(f"Missing Databricks dependencies: {e}") from e

        start_time = time.time()
        try:
            client = openai.OpenAI(
                api_key=resolved_api_key,
                base_url=resolved_base_url,
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                **params,
            )
            content = response.choices[0].message.content
            if content is None:
                raise APIError("Databricks API returned empty response")

            text = content.strip() if isinstance(content, str) else str(content).strip()
            if not text:
                raise APIError("Databricks API returned empty response")

            duration = time.time() - start_time
            log_api_operation(
                "databricks",
                "generate_text",
                True,
                duration,
                model=self.model,
                chars_generated=len(text),
            )
            return text

        except openai.RateLimitError as e:
            duration = time.time() - start_time
            log_api_operation(
                "databricks", "generate_text", False, duration, error="rate_limit"
            )
            raise APIRateLimitError(f"Databricks rate limit exceeded: {e}") from e
        except openai.AuthenticationError as e:
            duration = time.time() - start_time
            log_api_operation(
                "databricks", "generate_text", False, duration, error="auth_failed"
            )
            raise APIAuthenticationError(
                f"Databricks authentication failed: {e}"
            ) from e
        except openai.APIError as e:
            duration = time.time() - start_time
            log_api_operation(
                "databricks", "generate_text", False, duration, error=str(e)
            )
            raise APIError(f"Databricks API error: {e}") from e
        except Exception as e:
            duration = time.time() - start_time
            log_api_operation(
                "databricks", "generate_text", False, duration, error="unexpected"
            )
            raise APIError(f"Unexpected Databricks error: {e}") from e


class GeminiProvider:
    """Google Generative AI (Gemini) provider for text generation.

    This provider supports both the standard Gemini API and Vertex AI.
    It handles authentication, parameter mapping, and error handling for both
    API variants.

    Attributes:
        provider_name (str): Class-level identifier for this provider type.
        model (str): The Gemini model to use for generation.
        vertex (bool): Whether to use Vertex AI instead of standard Gemini API.
        project (Optional[str]): GCP project ID (required for Vertex AI).
        location (Optional[str]): GCP location/region (required for Vertex AI).
        credentials (Optional[str]): Path to the service account JSON file.
        defaults (dict): Default generation parameters (e.g., temperature).
    """

    provider_name: ClassVar[str] = "gemini"

    def __init__(
        self,
        model: str = Defaults.GEMINI_MODEL,
        *,
        vertex: bool = False,
        project: Optional[str] = None,
        location: Optional[str] = None,
        credentials: Optional[str] = None,
        **defaults: Any,
    ) -> None:
        """Initializes the GeminiProvider instance.

        Args:
            model: Gemini model identifier (e.g., 'gemini-pro').
            vertex: If True, use Vertex AI instead of Gemini API.
            project: GCP project ID (required for Vertex AI).
            location: GCP location/region (required for Vertex AI).
            credentials: Path to service account key file or a JSON string of the credentials (optional).
            **defaults: Default parameters for all generation requests.
        """
        self.model = model
        self.vertex = vertex
        self.project = project
        self.location = location
        self.credentials = credentials
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        """Generates text using Gemini API or Vertex AI.

        Args:
            prompt: The input prompt to generate text from.
            **kwargs: Additional generation parameters (e.g., temperature, top_k).

        Returns:
            str: The generated text response.

        Raises:
            APIAuthenticationError: If authentication fails.
            APIRateLimitError: If request is rate-limited.
            APIError: For all other errors.
        """
        params = {**self.defaults, **kwargs}
        invalid_params = {"model", "vertex", "project", "location", "credentials"}
        generation_config = {}
        valid_generation_params = {"max_output_tokens", "temperature", "top_p", "top_k"}

        for k, v in params.items():
            if k not in invalid_params:
                if k == "max_tokens":
                    generation_config["max_output_tokens"] = v
                elif k in valid_generation_params:
                    generation_config[k] = v

        try:
            if self.vertex:
                from google import genai
                from google.genai import types

                if not self.project or not self.location:
                    raise APIAuthenticationError(
                        "Vertex AI requires project and location"
                    )

                loaded_credentials = handle_google_credentials(self.credentials)
                credentials = None
                scopes_definition = ["https://www.googleapis.com/auth/cloud-platform"]

                # Initialize Google API services
                try:
                    credentials = service_account.Credentials.from_service_account_info(
                        loaded_credentials, scopes=scopes_definition
                    )
                except Exception as auth_error:
                    raise APIAuthenticationError(
                        f"Credentials authentication failed: {auth_error}"
                    )

                client = genai.Client(
                    vertexai=True,
                    project=self.project,
                    location=self.location,
                    credentials=credentials,
                    http_options={
                        "headers": {"User-Agent": Defaults.CLIENT_USER_AGENT}
                    },
                )

                config = (
                    types.GenerateContentConfig(**generation_config)
                    if generation_config
                    else None
                )

                response = client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )

                text_content = getattr(response, "text", None)
                if not text_content:
                    raise APIError("Gemini Vertex AI returned empty response")

                return text_content

            else:
                # Use standard Gemini API
                from google import genai
                from google.genai import types

                api_key = os.getenv(Environment.GOOGLE_API_KEY) or os.getenv(
                    Environment.GEMINI_API_KEY
                )
                if not api_key:
                    raise APIAuthenticationError(
                        f"Gemini API requires {Environment.GOOGLE_API_KEY} or {Environment.GEMINI_API_KEY} environment variable"
                    )

                client = genai.Client(
                    api_key=api_key,
                    http_options={
                        "headers": {"User-Agent": Defaults.CLIENT_USER_AGENT}
                    },
                )
                config = (
                    types.GenerateContentConfig(**generation_config)
                    if generation_config
                    else None
                )
                response = client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )

                text_content = getattr(response, "text", None)
                if not text_content:
                    raise APIError("Gemini API returned empty response")

                return text_content

        except ImportError as e:
            raise APIError(f"Missing Gemini dependencies: {e}") from e
        except (APIAuthenticationError, APIRateLimitError, APIError):
            raise
        except Exception as e:
            lowered_error = str(e).lower()
            if (
                "authentication" in lowered_error
                or "credential" in lowered_error
                or "unauthorized" in lowered_error
            ):
                raise APIAuthenticationError(f"Gemini authentication error: {e}") from e
            elif (
                "quota" in lowered_error
                or "rate limit" in lowered_error
                or "limit exceeded" in lowered_error
            ):
                raise APIRateLimitError(f"Gemini rate limit exceeded: {e}") from e
            else:
                raise APIError(f"Unexpected Gemini error: {e}") from e
