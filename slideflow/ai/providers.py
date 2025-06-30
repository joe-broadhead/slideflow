import time
from typing import Any, ClassVar, Optional, Protocol, runtime_checkable

from slideflow.utilities.exceptions import APIError, APIRateLimitError, APIAuthenticationError
from slideflow.utilities.logging import log_api_operation
from slideflow.constants import Defaults, Environment

@runtime_checkable
class AIProvider(Protocol):
    """
    Protocol for AI text‐generation providers.
    """
    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        ...

class OpenAIProvider:
    """
    OpenAI ChatCompletion provider.
    """
    provider_name: ClassVar[str] = "openai"

    def __init__(self, model: str = Defaults.OPENAI_MODEL, **defaults: Any) -> None:
        self.model = model
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
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
                            model=self.model, chars_generated=len(content))
            return content.strip()
            
        except openai.APIError as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error=str(e))
            raise APIError(f"OpenAI API error: {e}") from e
        except openai.RateLimitError as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error="rate_limit")
            raise APIRateLimitError(f"OpenAI rate limit exceeded: {e}") from e
        except openai.AuthenticationError as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error="auth_failed")
            raise APIAuthenticationError(f"OpenAI authentication failed: {e}") from e
        except Exception as e:
            duration = time.time() - start_time
            log_api_operation("openai", "generate_text", False, duration, error="unexpected")
            raise APIError(f"Unexpected OpenAI error: {e}") from e

class GeminiProvider:
    """
    Google Generative AI (Gemini) provider.
    """
    provider_name: ClassVar[str] = "gemini"

    def __init__(
        self,
        model: str = Defaults.GEMINI_MODEL,
        *,
        vertex: bool = False,
        project: Optional[str] = None,
        location: Optional[str] = None,
        **defaults: Any,
    ) -> None:
        self.model = model
        self.vertex = vertex
        self.project = project
        self.location = location
        self.defaults = defaults

    def generate_text(self, prompt: str, **kwargs: Any) -> str:
        params = {**self.defaults, **kwargs}

        invalid_params = {'model', 'vertex', 'project', 'location'}
        
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
                # Use Google Gen AI SDK with Vertex AI
                from google import genai
                from google.genai.types import GenerateContentConfig
                
                if not self.project or not self.location:
                    raise APIAuthenticationError("Vertex AI requires project and location to be configured")
                
                # Create Vertex AI client
                client = genai.Client(
                    vertexai=True,
                    project=self.project,
                    location=self.location
                )
                
                # Generate content with optional config
                config = GenerateContentConfig(**generation_config) if generation_config else None
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                
                if not hasattr(response, 'text') or not response.text:
                    raise APIError("Gemini Vertex AI returned empty response")
                
                return response.text
            else:
                # Use regular Gemini API
                import os
                import google.generativeai as genai
                
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
            # Handle various Google API exceptions
            error_msg = str(e).lower()
            if 'authentication' in error_msg or 'credential' in error_msg or 'unauthorized' in error_msg:
                raise APIAuthenticationError(f"Gemini authentication error: {e}") from e
            elif 'quota' in error_msg or 'rate limit' in error_msg or 'limit exceeded' in error_msg:
                raise APIRateLimitError(f"Gemini rate limit exceeded: {e}") from e
            else:
                raise APIError(f"Unexpected Gemini error: {e}") from e
