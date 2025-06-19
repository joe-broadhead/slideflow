from __future__ import annotations

from typing import Callable, Any, Dict, Union, Literal, Annotated

from pydantic import Field, field_validator

from slideflow.replacements.base import BaseReplacement
from slideflow.ai import AIProvider, AI_PROVIDERS
from slideflow.data.connectors.base import DataSourceConfig


class AITextReplacement(BaseReplacement):
    """Replacement that generates text via an AI provider."""

    type: Literal['ai_text'] = Field(
        'ai_text', description='AI text replacement type'
    )
    placeholder: Annotated[
        str, Field(description='Placeholder text to replace')
    ]
    prompt: Annotated[
        str, Field(description='Prompt sent to the provider')
    ]
    provider: Annotated[
        Union[str, Any, Callable[..., str]],
        Field(default='openai', description='Provider name or callable')
    ]
    provider_args: Annotated[Dict[str, Any], Field(
        default_factory=dict,
        description='Extra arguments for the provider'
    )]
    data_source: Annotated[
        DataSourceConfig | None,
        Field(
            default=None,
            description='Optional data source passed to the provider'
        )
    ]

    model_config = {
        'discriminator': 'type',
        'arbitrary_types_allowed': True
    }

    @field_validator('provider', mode='before')
    @classmethod
    def resolve_provider(cls, value):
        if isinstance(value, str):
            if value not in AI_PROVIDERS:
                raise ValueError(f'Unknown AI provider: {value}')
            # Return the provider class name, we'll instantiate it later with args
            return value
        return value

    def resolve_args(self, params: dict[str, str]) -> None:
        if self.prompt:
            self.prompt = self.prompt.format(**params)
        if self.provider_args:
            self.provider_args = {
                k: v.format(**params) if isinstance(v, str) else v
                for k, v in self.provider_args.items()
            }

    def get_replacement(self, data_manager, context: dict[str, str]) -> str:
        data = None
        if self.data_source:
            df = data_manager.get_data(self.data_source)
            data = df.to_dict(orient="records")

        prompt = self.prompt.format(**context)
        
        # Include data in the prompt if available
        if data:
            prompt += f"\n\nData:\n{data}"

        # Instantiate provider with custom args if provider is a string
        if isinstance(self.provider, str):
            from slideflow.ai.providers import OpenAIProvider, GeminiProvider
            
            provider_classes = {
                "openai": OpenAIProvider,
                "gemini": GeminiProvider,
            }
            
            provider_class = provider_classes[self.provider]
            
            # Extract initialization args from provider_args
            init_args = {}
            call_args = {}
            
            if self.provider == "gemini":
                gemini_init_params = {"model", "vertex", "project", "location"}
                for k, v in self.provider_args.items():
                    if k in gemini_init_params:
                        init_args[k] = v
                    else:
                        call_args[k] = v
            elif self.provider == "openai":
                openai_init_params = {"model"}
                for k, v in self.provider_args.items():
                    if k in openai_init_params:
                        init_args[k] = v
                    else:
                        call_args[k] = v
            
            provider_instance = provider_class(**init_args)
            provider_fn = provider_instance.generate_text
            provider_call_args = call_args
        elif isinstance(self.provider, AIProvider) or hasattr(
            self.provider, "generate_text"
        ):
            provider_fn = self.provider.generate_text
            provider_call_args = self.provider_args
        else:
            provider_fn = self.provider
            provider_call_args = self.provider_args

        return provider_fn(prompt, **provider_call_args)
