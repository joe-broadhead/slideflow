import pandas as pd
from pydantic import Field
from typing import Optional, Callable, Literal, Dict, Any, Union, Annotated

from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.base import DataSourceConfig
from slideflow.replacements.utils import dataframe_to_replacement_object

class TableReplacement(BaseReplacement):
    """
    Represents a table replacement in a slide.

    Replaces a group of text placeholders in a table based on data from
    a data source or a transformed DataFrame.

    Attributes:
        type (Literal['table']): Discriminator for Pydantic model selection.
        prefix (str): Prefix used for matching table placeholders.
        data_source (Optional[Union[str, DataSourceConfig]]): The name or config of the data source providing replacement values.
        value_fn (Optional[Callable[[pd.DataFrame], pd.DataFrame]]): Optional transformation function applied to the source data before replacement.
        value_fn_args (Dict[str, Any]): Optional keyword arguments passed to `value_fn`.
        replacements (Optional[Dict[str, Any]]): Static replacements if not using a data source.
    """
    type: Literal['table'] = Field('table', description = 'The table replacement type')
    prefix: Annotated[str, Field(description = 'Prefix for placeholders in the table')]
    data_source: Annotated[Optional[Union[str, DataSourceConfig]], Field(default = None, description = 'Data source for the table replacement')]
    value_fn: Annotated[Optional[Callable[[pd.DataFrame], pd.DataFrame]], Field(default = None, description = 'Function to transform the data before replacement')]
    value_fn_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = 'Extra keyword arguments for the table transformation function')]
    replacements: Annotated[Optional[Dict[str, Any]], Field(default = None, description = 'Static mapping of placeholder to new text')]

    def resolve_args(self, params: dict[str, str]) -> None:
        """
        Formats any string arguments in `value_fn_args` using the provided parameters.

        Args:
            params (dict): Parameters used to format strings in `value_fn_args`.
        """
        if self.value_fn_args:
            self.value_fn_args = {
                key: value.format(**params) if isinstance(value, str) else value
                for key, value in self.value_fn_args.items()
            }

    def get_table_replacements(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Generates table text replacements from a DataFrame or static config.

        Args:
            data (pd.DataFrame): The source data for the replacements.

        Returns:
            Dict[str, Any]: A dictionary mapping placeholders to replacement values.
        """
        if self.replacements is not None:
            return self.replacements
        elif self.value_fn:
            result_df = self.value_fn(data, **(self.value_fn_args or {}))
            return dataframe_to_replacement_object(result_df, self.prefix)
        else:
            return dataframe_to_replacement_object(data, self.prefix)
