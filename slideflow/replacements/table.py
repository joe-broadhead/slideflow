import pandas as pd
from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated, Any, Callable, Dict, Optional, Literal

from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.connect import DataSourceConfig
from slideflow.replacements.utils import dataframe_to_replacement_object

class TableColumnFormatter(BaseModel):
    """
    Configuration for formatting individual columns in a table.
    """
    format_fn: Annotated[Callable[[Any], str], Field(..., description = "Function to format a cell's value")]
    format_fn_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Additional kwargs for `format_fn`")]

    model_config = ConfigDict(
        extra = "forbid"
    )

class TableFormattingOptions(BaseModel):
    """
    Holds per-column formatters for a table replacement.
    """
    custom_formatters: Annotated[Dict[str, TableColumnFormatter], Field(default_factory = dict, description = "Map column name → formatter")]

    model_config = ConfigDict(
        extra = "forbid"
    )

class TableReplacement(BaseReplacement):
    """
    Replaces a placeholder table by pulling data from a DataFrame or static map.
    """
    type: Annotated[Literal["table"], Field("table", description = "Discriminator for table replacements")]
    prefix: Annotated[str, Field(..., description = "Prefix for table placeholders (e.g. 'REPORT_')")]
    data_source: Annotated[Optional[DataSourceConfig], Field(default = None, description = "Config of the data source")]
    formatting: Annotated[TableFormattingOptions, Field(default_factory = TableFormattingOptions, description = "Column formatters")]
    replacements: Annotated[Optional[Dict[str, Any]], Field(default = None, description = "Static placeholder→value map (skips data source)")]

    model_config = ConfigDict(
        extra = "forbid"
    )

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """
        Fetch data from the configured data source if available.
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None

    def get_replacement(self) -> Dict[str, Any]:
        """
        Generate the final placeholder→text map, applying preprocessing
        and per-column formatting.
        """

        if self.replacements is not None:
            return self.replacements

        df = self.fetch_data()

        if df is not None:
            df = self.apply_data_transforms(df)

        for col, fmt in self.formatting.custom_formatters.items():
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda v, f = fmt: f.format_fn(v, **f.format_fn_args)
                )

        return dataframe_to_replacement_object(df, self.prefix)
