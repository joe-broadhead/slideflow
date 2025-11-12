"""AI provider implementations for text generation.

This module contains implementations of AI providers that can generate text
content for presentations. It includes support for OpenAI and Google Gemini,
with a protocol-based interface for adding new providers.

The module provides:
    - AIProvider protocol defining the provider interface
    - OpenAIProvider for OpenAI's GPT models
    - GeminiProvider for Google's Gemini models (both regular and Vertex AI)
"""
import os
import time
import json
from pathlib import Path
from google.oauth2 import service_account
from typing import Any, ClassVar, Optional, Protocol, runtime_checkable

from slideflow.constants import Defaults, Environment
from slideflow.utilities.auth import handle_google_credentials
from slideflow.utilities.logging import log_api_operation
from slideflow.utilities.exceptions import APIError, APIRateLimitError, APIAuthenticationError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)

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
        ...

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
        import openai
        
        start_time = time.time()
        try:
            client = openai.OpenAI()
            params = {**self.defaults, **kwargs}
            messages = [{"role": "user", "content": prompt}]
            
            resp = client.chat.completions.create(
                model = self.model,
                messages = messages,
                **params,
            )
            
            content = resp.choices[0].message.content
            if content is None:
                raise APIError("OpenAI API returned empty response")
            
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", True, duration, 
                            model = self.model, chars_generated = len(content))
            return content.strip()
            
        except openai.APIError as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error = str(e))
            raise APIError(f"OpenAI API error: {e}") from e
        except openai.RateLimitError as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error = "rate_limit")
            raise APIRateLimitError(f"OpenAI rate limit exceeded: {e}") from e
        except openai.AuthenticationError as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error = "auth_failed")
            raise APIAuthenticationError(f"OpenAI authentication failed: {e}") from e
        except Exception as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error = "unexpected")
            raise APIError(f"Unexpected OpenAI error: {e}") from e

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
        invalid_params = {'model', 'vertex', 'project', 'location', 'credentials'}
        generation_config = {}
        valid_generation_params = {'max_output_tokens', 'temperature', 'top_p', 'top_k'}

        for k, v in params.items():
            if k not in invalid_params:
                if k == 'max_tokens':
                    generation_config['max_output_tokens'] = v
                elif k in valid_generation_params:
                    generation_config[k] = v

        try:
            if self.vertex:
                from google import genai
                from google.genai import types

                if not self.project or not self.location:
                    raise APIAuthenticationError("Vertex AI requires project and location")

                loaded_credentials = handle_google_credentials(self.credentials)
                credentials = None
                scopes_definition = ["https://www.googleapis.com/auth/cloud-platform"]

                # Initialize Google API services
                try:
                    credentials = service_account.Credentials.from_service_account_info(
                        loaded_credentials,
                        scopes = scopes_definition
                    )
                except Exception as error_msg:
                    raise APIAuthenticationError(f"Credentials authentication failed: {error_msg}")

                client = genai.Client(
                    vertexai = True,
                    project = self.project,
                    location = self.location,
                    credentials = credentials
                )

                config = types.GenerateContentConfig(**generation_config) if generation_config else None

                response = client.models.generate_content(
                    model = self.model,
                    contents = prompt,
                    config = config
                )

                text_content = getattr(response, "text", None)
                if not text_content:
                    raise APIError("Gemini Vertex AI returned empty response")

                return text_content

            else:
                # Use standard Gemini API
                from google import genai
                from google.genai import types

                api_key = os.getenv(Environment.GOOGLE_API_KEY) or os.getenv(Environment.GEMINI_API_KEY)
                if not api_key:
                    raise APIAuthenticationError(f"Gemini API requires {Environment.GOOGLE_API_KEY} or {Environment.GEMINI_API_KEY} environment variable")
                
                genai.configure(api_key = api_key)
                
                config = genai.GenerationConfig(**generation_config) if generation_config else None
                model = genai.GenerativeModel(self.model)
                response = model.generate_content(
                    prompt,
                    generation_config=config
                )

                text_content = getattr(response, 'text', None)
                if not text_content:
                    raise APIError("Gemini API returned empty response")

                return text_content

        except ImportError as e:
            raise APIError(f"Missing Gemini dependencies: {e}") from e
        except Exception as e:
            error_msg = str(e).lower()
            if 'authentication' in error_msg or 'credential' in error_msg or 'unauthorized' in error_msg:
                raise APIAuthenticationError(f"Gemini authentication error: {e}") from e
            elif 'quota' in error_msg or 'rate limit' in error_msg or 'limit exceeded' in error_msg:
                raise APIRateLimitError(f"Gemini rate limit exceeded: {e}") from e
            else:
                raise APIError(f"Unexpected Gemini error: {e}") from e
