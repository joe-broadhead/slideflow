import pandas as pd
from pydantic import Field, BaseModel, root_validator
from typing import Optional, Callable, Literal, Dict, Any, Union, Annotated, List

from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.base import DataSourceConfig
from slideflow.utils.formatting.format import BUILTIN_FORMAT_FUNCTIONS
from slideflow.replacements.utils import dataframe_to_replacement_object

BUILTIN_FUNCTIONS = BUILTIN_FORMAT_FUNCTIONS

class TableColumnFormatter(BaseModel):
    """
    Configuration for formatting individual columns in a table.

    This model allows users to specify a function for formatting the values in a column.

    Attributes:
        format_fn (Callable[[Any], str]): A function that formats a cell's value into a string.
        format_fn_args (Optional[Dict[str, Any]]): Additional keyword arguments passed to the formatting function.
    """
    format_fn: Callable[[Any], str]
    format_fn_args: Optional[Dict[str, Any]] = Field(default_factory = dict, description = 'Additional keyword arguments for the format function')
    
    @root_validator(pre = True)
    def resolve_function_names(cls, values):
        """
        Resolves any string references to functions in the format_fn
        using the BUILTIN_FUNCTIONS registry.

        Args:
            values (dict): The dictionary of field values.

        Returns:
            dict: The updated field values with resolved function references.

        Raises:
            ValueError: If a provided function name is not found in BUILTIN_FUNCTIONS.
        """
        for key in ['format_fn']:
            if isinstance(values.get(key), str):
                func_name = values[key]
                if func_name not in BUILTIN_FUNCTIONS:
                    raise ValueError(f'Unknown function: {func_name}')
                values[key] = BUILTIN_FUNCTIONS[func_name]
        return values

class TableFormattingOptions(BaseModel):
    custom_formatters: Dict[str, TableColumnFormatter] = Field(default_factory = dict)

class TableReplacement(BaseReplacement):
    """
    Represents a table replacement in a slide.

    Replaces a group of text placeholders in a table based on data from
    a data source or a transformed DataFrame.

    Attributes:
        type (Literal['table']): Discriminator for Pydantic model selection.
        prefix (str): Prefix used for matching table placeholders.
        data_source (Optional[Union[str, DataSourceConfig]]): The name or config of the data source providing replacement values.
        preprocess_functions (List[Dict[str, Any]]): A list of preprocessing steps to apply to the data before rendering. Each step includes a function reference and optional arguments, allowing for filtering, grouping, or transforming the data prior to display.
        replacements (Optional[Dict[str, Any]]): Static replacements if not using a data source.
        formatting (TableFormattingOptions): Formatting options for table data, including formatting functions
    """
    type: Literal['table'] = Field('table', description = 'The table replacement type')
    prefix: Annotated[str, Field(description = 'Prefix for placeholders in the table')]
    data_source: Annotated[Optional[Union[str, DataSourceConfig]], Field(default = None, description = 'Data source for the table replacement')]
    preprocess_functions: List[Dict[str, Any]] = Field(default_factory = list)
    replacements: Annotated[Optional[Dict[str, Any]], Field(default = None, description = 'Static mapping of placeholder to new text')]
    formatting: TableFormattingOptions = Field(default_factory = TableFormattingOptions)

    def resolve_args(self, params: dict[str, str]) -> None:
        """
        Updates all preprocess function args by formatting any string values with the provided params.

        Args:
            params (dict[str, str]): Parameters to use for string interpolation.
        """
        if hasattr(self, 'preprocess_functions'):
            for step in self.preprocess_functions:
                if 'args' in step:
                    for k, v in step['args'].items():
                        if isinstance(v, str):
                            step['args'][k] = v.format(**params)

    def get_table_replacements(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Generates table text replacements from a DataFrame or static config.

        Applies any preprocess_functions if provided, and optionally formats specific columns
        using user-defined functions before converting the result into a dictionary.

        Args:
            data (pd.DataFrame): The source data for the replacements.

        Returns:
            Dict[str, Any]: A dictionary mapping placeholders to replacement values.
        """
        if self.replacements is not None:
            return self.replacements

        df = data.copy()

        if self.preprocess_functions:
            for step in self.preprocess_functions:
                fn_name = step['function']
                args = step.get('args', {})
                df = fn_name(df, **args)

        for col_name, formatter in self.formatting.custom_formatters.items():
            if col_name in df.columns:
                df[col_name] = df[col_name].apply(
                    lambda val: formatter.format_fn(val, **formatter.format_fn_args)
                )

        return dataframe_to_replacement_object(df, self.prefix)
