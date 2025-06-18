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
        Union[str, AIProvider, Callable[..., str]],
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

    @field_validator('provider', mode='before')
    @classmethod
    def resolve_provider(cls, value):
        if isinstance(value, str):
            if value not in AI_PROVIDERS:
                raise ValueError(f'Unknown AI provider: {value}')
            return AI_PROVIDERS[value]
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

        if isinstance(self.provider, AIProvider) or hasattr(
            self.provider, "generate_text"
        ):
            provider_fn = self.provider.generate_text
        else:
            provider_fn = self.provider

        return provider_fn(prompt, data=data, **self.provider_args)
