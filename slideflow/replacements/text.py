import pandas as pd
from pydantic import Field, field_validator
from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.base import DataSourceConfig
from typing import Optional, Callable, Literal, Dict, Any, Annotated

class TextReplacement(BaseReplacement):
    """
    Represents a text placeholder replacement in a slide.

    Replaces a single text placeholder with either a static value or a
    dynamically computed one based on a data source and transformation function.

    Attributes:
        type (Literal['text']): Discriminator for Pydantic model selection.
        placeholder (str): The placeholder string to be replaced (e.g. "{{STORE_CODE}}").
        replacement (Optional[str]): A static value to replace the placeholder.
        data_source (Optional[DataSourceConfig]): Data source used for computing the replacement if `value_fn` is provided.
        value_fn (Optional[Callable[..., str]]): Function used to compute the replacement from the data source.
        value_fn_args (Dict[str, Any]): Keyword arguments passed to `value_fn`. Can include placeholders to be formatted with `params`.
    """
    type: Literal['text'] = Field('text', description = 'The text replacement type')
    placeholder: Annotated[str, Field(description = 'Placeholder text to be replaced')]
    replacement: Annotated[Optional[str], Field(default = None, description = 'Static text replacement value')]
    data_source: Annotated[Optional[DataSourceConfig], Field(default = None, description = 'Data source for computing the replacement')]
    value_fn: Annotated[Optional[Callable[..., str]], Field(default = None, description = 'Function to compute the replacement text from data')]
    value_fn_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = 'Extra keyword arguments for the value function')]

    @field_validator('replacement', mode = 'before')
    @staticmethod
    def ensure_str(value):
        """Ensures the replacement value is a string."""
        return str(value) if value is not None else None

    def resolve_args(self, params: dict[str, str]) -> None:
        """
        Format string arguments in `value_fn_args` using the provided parameters.
        """
        if self.value_fn_args:
            self.value_fn_args = {
                key: value.format(**params) if isinstance(value, str) else value
                for key, value in self.value_fn_args.items()
            }

    def get_replacement(self, data: Optional[pd.DataFrame] = None) -> str:
        """
        Computes the final replacement string for the placeholder.

        Args:
            data (Optional[pd.DataFrame]): Optional data used as input to `value_fn`.

        Returns:
            str: The final replacement string.
        """
        if self.value_fn:
            if data is not None:
                return str(self.value_fn(data, **(self.value_fn_args or {})))
            return str(self.value_fn(**(self.value_fn_args or {})))
        return self.replacement or ''
