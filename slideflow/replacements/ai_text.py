import inspect
import pandas as pd
from pydantic import Field, ConfigDict
from typing import (
    Any,
    Type,
    Dict,
    Union,
    Literal,
    Callable,
    Annotated,
    Optional
)

from slideflow.ai.providers import AIProvider
from slideflow.ai.registry import get_provider_class
from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.connect import DataSourceConfig
from slideflow.utilities.exceptions import ReplacementError

class AITextReplacement(BaseReplacement):
    """
    Replacement that generates text via an AI provider.
    """
    type: Annotated[Literal["ai_text"], Field("ai_text", description = "Discriminator for AI-text replacements")]
    placeholder: Annotated[str, Field(..., description = "Placeholder to replace (e.g. '{{SUMMARY}}')")]
    prompt: Annotated[str, Field(..., description = "Prompt template for the AI provider")]
    provider: Annotated[Union[str, Type[AIProvider], AIProvider, Callable[..., str]], Field(default = "openai", description = "Provider name, class, instance, or plain callable")]
    provider_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Keyword args for provider init & call")]
    data_source: Annotated[Optional[DataSourceConfig], Field(default = None, description = "Optional data source to include")]

    model_config = ConfigDict(
        extra = "forbid",
        discriminator = "type",
        arbitrary_types_allowed = True
    )

    def _prepare_provider(self) -> tuple[Callable[..., str], dict[str, Any]]:
        """
        Instantiate or unwrap the provider, splitting args into init vs call.
        Returns (callable, call_args).
        """
        Prov = self.provider
        args = dict(self.provider_args)

        # Handle string provider names using registry
        if isinstance(Prov, str):
            Prov = get_provider_class(Prov)

        if inspect.isclass(Prov) and issubclass(Prov, AIProvider):
            sig = inspect.signature(Prov.__init__)
            init_params = {p for p in sig.parameters if p != "self"}
            init_args = {k: v for k, v in args.items() if k in init_params}
            call_args = {k: v for k, v in args.items() if k not in init_params}
            instance = Prov(**init_args)
            return instance.generate_text, call_args

        if isinstance(Prov, AIProvider):
            return Prov.generate_text, args

        if callable(Prov):
            return Prov, args

        raise ReplacementError(f"Invalid AI provider: {Prov!r}")

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch data from the configured data source if available.
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None

    def get_replacement(self) -> str:
        prompt = self.prompt

        df = self.fetch_data()
        if df is not None:
            df = self.apply_data_transforms(df)
            data = df.to_dict(orient = "records")
            prompt += f"\n\nData:\n{data}"

        fn, call_args = self._prepare_provider()
        return fn(prompt, **call_args)
