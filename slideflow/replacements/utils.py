"""Utility functions for replacement processing and data conversion.

This module provides helper functions for converting data between different
formats used in the replacement system. The primary focus is on converting
structured data (DataFrames) into the placeholder-value dictionaries used
by the table replacement system.

Example:
    Converting DataFrame to replacements:
    
    >>> import pandas as pd
    >>> from slideflow.replacements.utils import dataframe_to_replacement_object
    >>> 
    >>> df = pd.DataFrame({
    ...     'Product': ['Widget', 'Gadget'],
    ...     'Sales': [125.5, 89.2],
    ...     'Growth': [15.3, -5.1]
    ... })
    >>> replacements = dataframe_to_replacement_object(df, 'PRODUCTS_')
    >>> # Returns:
    >>> # {
    >>> #     '{{PRODUCTS_1,1}}': 'Product',
    >>> #     '{{PRODUCTS_1,2}}': 'Sales', 
    >>> #     '{{PRODUCTS_1,3}}': 'Growth',
    >>> #     '{{PRODUCTS_2,1}}': 'Widget',
    >>> #     '{{PRODUCTS_2,2}}': 125.5,
    >>> #     '{{PRODUCTS_2,3}}': 15.3,
    >>> #     '{{PRODUCTS_3,1}}': 'Gadget',
    >>> #     '{{PRODUCTS_3,2}}': 89.2,
    >>> #     '{{PRODUCTS_3,3}}': -5.1
    >>> # }
"""

import pandas as pd

def dataframe_to_replacement_object(df: pd.DataFrame, prefix: str = '') -> dict:
    """Convert a DataFrame to a dictionary of coordinate-based placeholders.

    This function transforms tabular data into a flat dictionary where each
    cell value is mapped to a coordinate-based placeholder key. The resulting
    dictionary can be used for systematic text replacement in templates.

    The placeholder format follows the pattern {{prefix[row],[col]}} where:
    - prefix: Optional namespace string to group related replacements
    - row: 1-based row index (includes column headers as row 1)
    - col: 1-based column index

    This coordinate system allows templates to reference specific table
    positions without needing to know the actual data structure in advance.

    Args:
        df: Input DataFrame containing the tabular data to convert.
            Column names become the first row of replacements.
        prefix: Optional string prefix for placeholder keys. Useful for
            namespacing when multiple tables are used in the same template.
            Should typically end with an underscore for readability.

    Returns:
        Dictionary mapping placeholder strings to cell values. Keys are
        formatted as "{{prefix[row],[col]}}" and values preserve their
        original DataFrame types.

    Example:
        Basic DataFrame conversion:
        
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'Quarter': ['Q1', 'Q2', 'Q3'],
        ...     'Revenue': [100, 120, 135],
        ...     'Growth': [5.2, 8.1, 12.5]
        ... })
        >>> result = dataframe_to_replacement_object(df, 'SALES_')
        >>> 
        >>> # Generated placeholders:
        >>> # {{SALES_1,1}} = 'Quarter'  (column header)
        >>> # {{SALES_1,2}} = 'Revenue'  (column header)
        >>> # {{SALES_1,3}} = 'Growth'   (column header)
        >>> # {{SALES_2,1}} = 'Q1'       (first data row)
        >>> # {{SALES_2,2}} = 100        (first data row)
        >>> # {{SALES_2,3}} = 5.2        (first data row)
        >>> # ... and so on
        
        Template usage:
        
        >>> # In presentation template:
        >>> # "In {{SALES_2,1}}, revenue was ${{SALES_2,2}}M with {{SALES_2,3}}% growth"
        >>> # Becomes: "In Q1, revenue was $100M with 5.2% growth"
        
        Without prefix:
        
        >>> df = pd.DataFrame({'Name': ['Alice'], 'Age': [30]})
        >>> result = dataframe_to_replacement_object(df)
        >>> # Returns: {'{{1,1}}': 'Name', '{{1,2}}': 'Age', '{{2,1}}': 'Alice', '{{2,2}}': 30}
        
        Empty DataFrame handling:
        
        >>> empty_df = pd.DataFrame()
        >>> result = dataframe_to_replacement_object(empty_df, 'EMPTY_')
        >>> # Returns: {} (empty dictionary)
    """
    return {
        f"{{{{{prefix}{row_index + 1},{col_index + 1}}}}}": value
        for row_index, row in enumerate(df.values)
        for col_index, value in enumerate(row)
    }
