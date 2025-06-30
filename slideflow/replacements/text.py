import pandas as pd
from pydantic import Field, field_validator, ConfigDict
from typing import Annotated, Optional, Callable, Literal, Dict, Any

from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.connect import DataSourceConfig

class TextReplacement(BaseReplacement):
    """
    Represents a text placeholder replacement in a slide.

    Replaces a single text placeholder with either a static value or a
    dynamically computed one based on a data source and transformation function.
    """
    type: Annotated[Literal["text"], Field("text", description = "Discriminator for text replacement")]
    placeholder: Annotated[str, Field(..., description = "Placeholder to replace (e.g. '{{STORE_CODE}}')")]
    replacement: Annotated[Optional[str], Field(default = None, description = "Static text to use if no `value_fn` is provided")]
    data_source: Annotated[Optional[DataSourceConfig], Field(default = None, description = "Optional data source for computing the replacement")]
    value_fn: Annotated[Optional[Callable[..., str]], Field(default = None, description = "Function to compute the replacement text from data")]
    value_fn_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Keyword arguments passed to `value_fn`; string values will be formatted")]

    model_config = ConfigDict(
        extra = "forbid",
        arbitrary_types_allowed = True
    )

    @field_validator("replacement", mode = "before")
    @classmethod
    def _ensure_str(cls, v: Any) -> Optional[str]:
        """Coerce non-None replacement values to string."""
        return None if v is None else str(v)

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch data from the configured data source if available.
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None

    def get_replacement(self) -> str:
        """
        Compute the final replacement text.

        If `value_fn` is set, calls it with data from `data_source` if available,
        otherwise calls it with just `value_fn_args`.
        Returns the static `replacement` if no `value_fn` is provided.
        """
        if self.value_fn:
            data = self.fetch_data()
            if data is not None:
                # Apply data transformations before processing
                transformed_data = self.apply_data_transforms(data)
                return str(self.value_fn(transformed_data, **(self.value_fn_args or {})))
            return str(self.value_fn(**(self.value_fn_args or {})))
        return self.replacement or ''
