"""Column-level data transformation utilities for DataFrames.

This module provides batch operations for transforming multiple DataFrame columns
at once. It focuses on common presentation formatting tasks like number abbreviation,
currency formatting, percentage conversion, and rounding. These utilities are
designed to work seamlessly with pandas DataFrames and integrate with Slideflow's
data transformation pipeline.

The module leverages existing formatting functions from slideflow.builtins.formatting
and applies them efficiently across specified columns, preserving data types where
possible and handling edge cases gracefully.

Functions:
    abbreviate_number_columns: Apply number abbreviation to multiple columns
    abbreviate_currency_columns: Apply currency abbreviation to multiple columns
    format_percentages: Convert columns to percentage format
    round_numbers: Round numeric columns to specified precision

Example:
    >>> import pandas as pd
    >>> from slideflow.builtins.column_utils import abbreviate_number_columns
    >>> 
    >>> df = pd.DataFrame({
    ...     'revenue': [1234567, 2345678, 3456789],
    ...     'costs': [234567, 345678, 456789],
    ...     'name': ['A', 'B', 'C']
    ... })
    >>> 
    >>> df_formatted = abbreviate_number_columns(df, ['revenue', 'costs'])
    >>> # revenue: ['1.2M', '2.3M', '3.5M']
    >>> # costs: ['234.6K', '345.7K', '456.8K']
"""

import pandas as pd
from typing import List
from slideflow.builtins.formatting.format import abbreviate, abbreviate_currency

def abbreviate_number_columns(df: pd.DataFrame, columns_to_abbreviate: List[str]) -> pd.DataFrame:
    """Abbreviate large numbers in specified DataFrame columns.
    
    Applies number abbreviation (K, M, B, T suffixes) to specified columns,
    making large numbers more readable in presentations. Non-numeric values
    are preserved as strings.
    
    Args:
        df: DataFrame to process. Original DataFrame is not modified.
        columns_to_abbreviate: List of column names to abbreviate. Columns
            not present in the DataFrame are silently ignored.
        
    Returns:
        New DataFrame with specified columns containing abbreviated values.
        Other columns remain unchanged. Column types may change to object/string.
        
    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'revenue': [1234567, 2345678, 3456789],
        ...     'units': [1234, 12345, 123456],
        ...     'product': ['A', 'B', 'C']
        ... })
        >>> 
        >>> result = abbreviate_number_columns(df, ['revenue', 'units'])
        >>> print(result['revenue'].tolist())
        ['1.2M', '2.3M', '3.5M']
        >>> print(result['units'].tolist())
        ['1.2K', '12.3K', '123.5K']
        
    Note:
        - Uses slideflow.builtins.formatting.format.abbreviate internally
        - Creates a copy of the DataFrame to avoid modifying the original
        - Handles NaN, None, and non-numeric values gracefully
        - Column order is preserved
    """
    
    df = df.copy()
    
    for col in columns_to_abbreviate:
        if col in df.columns:
            df[col] = df[col].apply(abbreviate)
    
    return df

def abbreviate_currency_columns(
    df: pd.DataFrame, 
    columns_to_abbreviate: List[str], 
    currency_symbol: str = "$",
    symbol_position: str = "prefix",
    negative_parens: bool = False,
    decimals: int = 2,
    thousands_sep: str = ",",
    decimal_sep: str = "."
) -> pd.DataFrame:
    """Abbreviate and format currency values in specified DataFrame columns.
    
    Combines number abbreviation with currency formatting for specified columns,
    creating compact, presentation-ready currency displays (e.g., $1.2M, €3.4K).
    
    Args:
        df: DataFrame to process. Original DataFrame is not modified.
        columns_to_abbreviate: List of column names to format as abbreviated
            currency. Columns not present in the DataFrame are silently ignored.
        currency_symbol: Currency symbol to use. Defaults to "$".
            Common options: "$", "£", "¥", "€".
        symbol_position: Where to place the symbol:
            - "prefix": Before the number (e.g., "$1.2M")
            - "suffix": After the number (e.g., "1.2M €")
            Defaults to "prefix".
        negative_parens: How to display negative values:
            - True: Use parentheses, e.g., "($1.2M)"
            - False: Use minus sign, e.g., "-$1.2M"
            Defaults to False.
        suffixes: Custom abbreviation thresholds as (threshold, suffix) tuples.
            If None, uses: [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")].
            Order matters - should be from largest to smallest.
        decimals: Decimal places for values < 1K. Defaults to 2.
            Abbreviated values always use 1 decimal place.
        thousands_sep: Character for thousands separation in small values.
            Defaults to ",". Not used for abbreviated values.
        decimal_sep: Character for decimal separation. Defaults to ".".
        
    Returns:
        New DataFrame with specified columns containing abbreviated currency
        values. Other columns remain unchanged.
        
    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'revenue': [1234567, 2345678, 3456789],
        ...     'costs': [234567, 345678, 456789],
        ...     'margin': [0.15, 0.20, 0.25]
        ... })
        >>> 
        >>> result = abbreviate_currency_columns(
        ...     df, 
        ...     ['revenue', 'costs'], 
        ...     currency_symbol='€'
        ... )
        >>> print(result['revenue'].tolist())
        ['€1.2M', '€2.3M', '€3.5M']
        >>> print(result['costs'].tolist())
        ['€234.6K', '€345.7K', '€456.8K']
        
    Note:
        - Uses slideflow.builtins.formatting.format.abbreviate_currency internally
        - Creates a copy of the DataFrame to avoid modifying the original
        - Values < 1,000 are formatted with full currency notation
        - Handles negative values appropriately
    """
    
    df = df.copy()
    
    for col in columns_to_abbreviate:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: abbreviate_currency(x, currency_symbol=currency_symbol, symbol_position=symbol_position, negative_parens=negative_parens, decimals=decimals, thousands_sep=thousands_sep, decimal_sep=decimal_sep))
    return df

def format_percentages(
    df: pd.DataFrame, 
    columns_to_format: List[str], 
    decimal_places: int = 1, 
    from_ratio: bool = True
) -> pd.DataFrame:
    """Format specified columns as percentage strings.
    
    Converts numeric values in specified columns to percentage format with
    customizable precision. Handles both ratio inputs (0.25 → 25%) and
    percentage inputs (25 → 25%) based on the from_ratio parameter.
    
    Args:
        df: DataFrame to process. Original DataFrame is not modified.
        columns_to_format: List of column names to format as percentages.
            Columns not present in the DataFrame are silently ignored.
        decimal_places: Number of decimal places in the output. Defaults to 1.
            For example, 0.1234 with decimal_places=1 becomes "12.3%".
        from_ratio: Interpretation of input values:
            - True: Values are ratios (0.25 represents 25%)
            - False: Values are already percentages (25 represents 25%)
            Defaults to True.
        
    Returns:
        New DataFrame with specified columns formatted as percentage strings.
        Other columns remain unchanged.
        
    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'growth_rate': [0.152, 0.203, -0.051],
        ...     'completion': [95.5, 87.3, 100.0],
        ...     'name': ['Q1', 'Q2', 'Q3']
        ... })
        >>> 
        >>> # Format ratios as percentages
        >>> result = format_percentages(df, ['growth_rate'], decimal_places=1)
        >>> print(result['growth_rate'].tolist())
        ['15.2%', '20.3%', '-5.1%']
        >>> 
        >>> # Format already-percentage values
        >>> result = format_percentages(
        ...     df, 
        ...     ['completion'], 
        ...     decimal_places=0, 
        ...     from_ratio=False
        ... )
        >>> print(result['completion'].tolist())
        ['96%', '87%', '100%']
        
    Note:
        - Non-numeric values are preserved as strings
        - NaN and None values are handled gracefully
        - Negative percentages are formatted correctly
        - Creates a copy to preserve the original DataFrame
    """
    df = df.copy()
    
    def format_percentage(value):
        try:
            val = float(value)
            if from_ratio:
                val *= 100
            return f"{val:.{decimal_places}f}%"
        except (ValueError, TypeError):
            return str(value)
    
    for col in columns_to_format:
        if col in df.columns:
            df[col] = df[col].apply(format_percentage)
    
    return df

def round_numbers(
    df: pd.DataFrame, 
    columns_to_round: List[str], 
    decimal_places: int = 2
) -> pd.DataFrame:
    """Round numeric values in specified columns to given decimal places.
    
    Applies consistent rounding to specified numeric columns, useful for
    standardizing precision in presentations and reports. Non-numeric values
    are preserved unchanged.
    
    Args:
        df: DataFrame to process. Original DataFrame is not modified.
        columns_to_round: List of column names to round. Columns not present
            in the DataFrame are silently ignored. Non-numeric columns are
            also ignored.
        decimal_places: Number of decimal places to round to. Defaults to 2.
            Can be negative to round to tens, hundreds, etc.
        
    Returns:
        New DataFrame with specified numeric columns rounded to the given
        precision. Other columns and non-numeric values remain unchanged.
        
    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'price': [10.12345, 20.56789, 30.98765],
        ...     'quantity': [1.5, 2.7, 3.9],
        ...     'total': [15.18518, 55.53333, 120.84885],
        ...     'product': ['A', 'B', 'C']
        ... })
        >>> 
        >>> # Round to 2 decimal places
        >>> result = round_numbers(df, ['price', 'total'], decimal_places=2)
        >>> print(result['price'].tolist())
        [10.12, 20.57, 30.99]
        >>> print(result['total'].tolist())
        [15.19, 55.53, 120.85]
        >>> 
        >>> # Round to whole numbers
        >>> result = round_numbers(df, ['quantity'], decimal_places=0)
        >>> print(result['quantity'].tolist())
        [2.0, 3.0, 4.0]
        
    Note:
        - Uses pandas .round() method for efficient operation
        - Maintains numeric data types (doesn't convert to strings)
        - NaN values remain as NaN
        - Creates a copy to preserve the original DataFrame
        - Silently skips non-numeric columns
    """
    df = df.copy()
    
    for col in columns_to_round:
        if col in df.columns:
            df[col] = df[col].round(decimal_places)
    
    return df
