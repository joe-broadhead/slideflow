"""Table-based text replacement for data-driven content generation.

This module provides table replacement functionality for generating multiple
text replacements from tabular data. It converts DataFrames into sets of
placeholder-value pairs, enabling dynamic population of tables, metrics,
and structured content in presentations.

The table replacement system supports:
    - Data-driven placeholder generation from DataFrames
    - Custom column formatting with configurable functions
    - Static replacement dictionaries for predefined content
    - Prefix-based placeholder organization for namespace management
    - Integration with data transformation pipeline

Key Features:
    - Automatic placeholder generation with coordinate-based naming
    - Per-column custom formatting functions
    - Static and dynamic content modes
    - Data transformation integration
    - Type-safe configuration with Pydantic validation

Example:
    Basic table replacement from data:
    
    >>> from slideflow.replacements.table import TableReplacement
    >>> import pandas as pd
    >>> 
    >>> # Data source returns DataFrame with metrics
    >>> replacement = TableReplacement(
    ...     type="table",
    ...     prefix="METRICS_",
    ...     data_source=metrics_data_source
    ... )
    >>> replacements = replacement.get_replacement()
    >>> # Returns: {"{{METRICS_1,1}}": "Revenue", "{{METRICS_1,2}}": "$125M", ...}
    
    Table with custom formatting:
    
    >>> def format_currency(value, symbol="$"):
    ...     return f"{symbol}{value:,.2f}M"
    >>> 
    >>> def format_percentage(value):
    ...     return f"{value:.1f}%"
    >>> 
    >>> replacement = TableReplacement(
    ...     type="table",
    ...     prefix="FINANCIAL_",
    ...     data_source=financial_data,
    ...     formatting=TableFormattingOptions(custom_formatters={
    ...         "revenue": TableColumnFormatter(
    ...             format_fn=format_currency,
    ...             format_fn_args={"symbol": "€"}
    ...         ),
    ...         "growth_rate": TableColumnFormatter(
    ...             format_fn=format_percentage
    ...         )
    ...     })
    ... )
    
    Static replacement table:
    
    >>> replacement = TableReplacement(
    ...     type="table",
    ...     prefix="STATUS_",
    ...     replacements={
    ...         "{{STATUS_CURRENT}}": "Active",
    ...         "{{STATUS_NEXT}}": "Pending",
    ...         "{{STATUS_COUNT}}": "150"
    ...     }
    ... )
"""

import pandas as pd
from pydantic import BaseModel, Field, ConfigDict
from typing import Annotated, Any, Callable, Dict, Optional, Literal

from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.connect import DataSourceConfig
from slideflow.replacements.utils import dataframe_to_replacement_object

class TableColumnFormatter(BaseModel):
    """Configuration for custom formatting of table column values.
    
    This class defines how individual columns in a table should be formatted
    when converting DataFrame data to text replacements. It allows for
    sophisticated formatting logic such as currency formatting, percentage
    display, date formatting, or any custom transformation.
    
    The formatter consists of a formatting function and optional arguments
    that will be passed to that function along with each cell value.
    
    Attributes:
        format_fn: Function that takes a cell value and returns formatted string.
        format_fn_args: Additional keyword arguments passed to format_fn.
        
    Example:
        Currency formatting:
        
        >>> def format_currency(value, currency="USD", precision=2):
        ...     return f"{currency} {value:,.{precision}f}"
        >>> 
        >>> formatter = TableColumnFormatter(
        ...     format_fn=format_currency,
        ...     format_fn_args={"currency": "EUR", "precision": 1}
        ... )
        >>> # When applied: format_currency(125000, currency="EUR", precision=1)
        >>> # Result: "EUR 125,000.0"
        
        Date formatting:
        
        >>> from datetime import datetime
        >>> def format_date(value, format_str="%Y-%m-%d"):
        ...     if isinstance(value, str):
        ...         value = datetime.strptime(value, "%Y-%m-%d")
        ...     return value.strftime(format_str)
        >>> 
        >>> formatter = TableColumnFormatter(
        ...     format_fn=format_date,
        ...     format_fn_args={"format_str": "%B %d, %Y"}
        ... )
    """
    format_fn: Annotated[Callable[[Any], str], Field(..., description = "Function to format a cell's value")]
    format_fn_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Additional kwargs for `format_fn`")]

    model_config = ConfigDict(
        extra = "forbid"
    )

class TableFormattingOptions(BaseModel):
    """Container for column-specific formatting configurations.
    
    This class manages the mapping of column names to their respective
    formatting configurations. It allows different columns in the same
    table to use different formatting functions, enabling rich and
    contextually appropriate display of tabular data.
    
    Attributes:
        custom_formatters: Dictionary mapping column names to TableColumnFormatter
            instances. Only columns specified here will have custom formatting
            applied; others will use default string conversion.
            
    Example:
        Multi-column formatting:
        
        >>> def format_money(value, prefix="$"):
        ...     return f"{prefix}{value:,.2f}"
        >>> 
        >>> def format_percent(value):
        ...     return f"{value:.1f}%"
        >>> 
        >>> def format_large_number(value):
        ...     if value >= 1_000_000:
        ...         return f"{value/1_000_000:.1f}M"
        ...     elif value >= 1_000:
        ...         return f"{value/1_000:.1f}K"
        ...     return str(value)
        >>> 
        >>> formatting = TableFormattingOptions(
        ...     custom_formatters={
        ...         "revenue": TableColumnFormatter(
        ...             format_fn=format_money,
        ...             format_fn_args={"prefix": "$"}
        ...         ),
        ...         "growth_rate": TableColumnFormatter(
        ...             format_fn=format_percent
        ...         ),
        ...         "customer_count": TableColumnFormatter(
        ...             format_fn=format_large_number
        ...         )
        ...     }
        ... )
    """
    custom_formatters: Annotated[Dict[str, TableColumnFormatter], Field(default_factory = dict, description = "Map column name → formatter")]

    model_config = ConfigDict(
        extra = "forbid"
    )

class TableReplacement(BaseReplacement):
    """Table-based replacement for generating multiple text substitutions from data.
    
    This class converts tabular data (DataFrames) or static dictionaries into
    sets of text replacements. It's designed for populating tables, metrics
    displays, and other structured content in presentations where multiple
    related values need to be replaced.
    
    The replacement process can operate in two modes:
    
    1. Data-driven mode: Fetches data from a configured data source,
       applies transformations and formatting, then converts to replacements
       using coordinate-based placeholder naming.
    
    2. Static mode: Uses a predefined dictionary of placeholder-value pairs,
       bypassing data fetching and processing.
    
    Placeholder Generation:
        In data-driven mode, placeholders are generated using the pattern:
        {{prefix[row],[col]}} where row and col are 1-based indices.
        This allows systematic population of table structures in templates.
    
    Custom Formatting:
        Individual columns can have custom formatting functions applied
        before conversion to text. This enables proper display of currencies,
        percentages, dates, and other specialized data types.
    
    Attributes:
        type: Always "table" for this replacement type.
        prefix: String prefix for generated placeholders (e.g., "METRICS_").
        data_source: Optional data source configuration for dynamic content.
        formatting: Column-specific formatting options.
        replacements: Static placeholder-value dictionary (overrides data_source).
        
    Example:
        Data-driven table replacement:
        
        >>> import pandas as pd
        >>> 
        >>> # Assume data_source returns DataFrame:
        >>> # | metric     | q1_value | q2_value |
        >>> # | Revenue    | 125.5    | 138.2    |
        >>> # | Growth     | 15.3     | 22.1     |
        >>> 
        >>> replacement = TableReplacement(
        ...     type="table",
        ...     prefix="QUARTERLY_",
        ...     data_source=quarterly_data_source
        ... )
        >>> result = replacement.get_replacement()
        >>> # Returns:
        >>> # {
        >>> #     "{{QUARTERLY_1,1}}": "Revenue",
        >>> #     "{{QUARTERLY_1,2}}": "125.5",
        >>> #     "{{QUARTERLY_1,3}}": "138.2",
        >>> #     "{{QUARTERLY_2,1}}": "Growth",
        >>> #     "{{QUARTERLY_2,2}}": "15.3",
        >>> #     "{{QUARTERLY_2,3}}": "22.1"
        >>> # }
        
        With custom formatting:
        
        >>> def format_currency(value, symbol="$"):
        ...     return f"{symbol}{float(value):,.1f}M"
        >>> 
        >>> def format_percentage(value):
        ...     return f"{float(value):.1f}%"
        >>> 
        >>> replacement = TableReplacement(
        ...     type="table",
        ...     prefix="FORMATTED_",
        ...     data_source=financial_data,
        ...     formatting=TableFormattingOptions(
        ...         custom_formatters={
        ...             "q1_value": TableColumnFormatter(
        ...                 format_fn=format_currency,
        ...                 format_fn_args={"symbol": "€"}
        ...             ),
        ...             "q2_value": TableColumnFormatter(
        ...                 format_fn=format_percentage
        ...             )
        ...         }
        ...     )
        ... )
        >>> # q1_value column formatted as "€125.5M"
        >>> # q2_value column formatted as "138.2%"
        
        Static replacement table:
        
        >>> replacement = TableReplacement(
        ...     type="table",
        ...     prefix="STATUS_",
        ...     replacements={
        ...         "{{STATUS_CURRENT}}": "Active",
        ...         "{{STATUS_PENDING}}": "15",
        ...         "{{STATUS_COMPLETED}}": "142"
        ...     }
        ... )
        >>> result = replacement.get_replacement()
        >>> # Returns the static replacements dictionary as-is
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
        """Fetch tabular data from the configured data source.
        
        This method retrieves the underlying data that will be converted into
        table replacements. The data is typically structured as a DataFrame
        with rows and columns that map to the coordinate-based placeholder system.
        
        Returns:
            DataFrame containing the table data if a data source is configured,
            None if no data source is set (will use static replacements instead).
            
        Example:
            >>> replacement = TableReplacement(
            ...     type="table",
            ...     prefix="SALES_",
            ...     data_source=sales_table_source
            ... )
            >>> data = replacement.fetch_data()
            >>> # Returns DataFrame with sales table structure
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None

    def get_replacement(self) -> Dict[str, Any]:
        """Generate the complete set of placeholder-value mappings.
        
        This method produces the final dictionary of placeholder keys to
        replacement values. The process depends on the configuration mode:
        
        Static Mode (replacements provided):
            Returns the static replacements dictionary as-is.
        
        Data-Driven Mode (data_source configured):
            1. Fetch data from the data source
            2. Apply configured data transformations
            3. Apply custom column formatting where specified
            4. Convert DataFrame to coordinate-based placeholders
            5. Return the resulting placeholder-value dictionary
        
        Placeholder Format:
            Generated placeholders follow the pattern {{prefix[row],[col]}}
            where row and col are 1-based indices into the DataFrame.
        
        Column Formatting:
            Custom formatters are applied before placeholder generation,
            allowing for proper display formatting of different data types.
        
        Returns:
            Dictionary mapping placeholder strings to their replacement values.
            Keys are formatted as "{{prefix[row],[col]}}" for data-driven mode
            or as specified in the static replacements dictionary.
            
        Example:
            Data-driven replacement generation:
            
            >>> # DataFrame:
            >>> # | Product | Sales | Growth |
            >>> # | Widget  | 125.5 | 15.3   |
            >>> # | Gadget  | 89.2  | -5.1   |
            >>> 
            >>> replacement = TableReplacement(
            ...     type="table",
            ...     prefix="PRODUCTS_",
            ...     data_source=products_source,
            ...     formatting=TableFormattingOptions(
            ...         custom_formatters={
            ...             "Sales": TableColumnFormatter(
            ...                 format_fn=lambda x: f"${x}M"
            ...             ),
            ...             "Growth": TableColumnFormatter(
            ...                 format_fn=lambda x: f"{x}%"
            ...             )
            ...         }
            ...     )
            ... )
            >>> result = replacement.get_replacement()
            >>> # Returns:
            >>> # {
            >>> #     "{{PRODUCTS_1,1}}": "Product",
            >>> #     "{{PRODUCTS_1,2}}": "Sales",
            >>> #     "{{PRODUCTS_1,3}}": "Growth",
            >>> #     "{{PRODUCTS_2,1}}": "Widget",
            >>> #     "{{PRODUCTS_2,2}}": "$125.5M",
            >>> #     "{{PRODUCTS_2,3}}": "15.3%",
            >>> #     "{{PRODUCTS_3,1}}": "Gadget",
            >>> #     "{{PRODUCTS_3,2}}": "$89.2M",
            >>> #     "{{PRODUCTS_3,3}}": "-5.1%"
            >>> # }
            
            Static replacement mode:
            
            >>> replacement = TableReplacement(
            ...     type="table",
            ...     prefix="SUMMARY_",
            ...     replacements={
            ...         "{{SUMMARY_TOTAL}}": "$1,250,000",
            ...         "{{SUMMARY_COUNT}}": "150",
            ...         "{{SUMMARY_AVERAGE}}": "$8,333"
            ...     }
            ... )
            >>> result = replacement.get_replacement()
            >>> # Returns the static dictionary unchanged
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
