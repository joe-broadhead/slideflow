"""Built-in utilities and functions for Slideflow presentations.

This module provides a comprehensive collection of utility functions and common
patterns that enhance Slideflow presentations. It includes data transformation
utilities, formatting functions, color mapping tools, and table enhancement
features that can be used directly or imported into custom registries.

The builtins module is organized into several categories:
    - Formatting: Number, currency, and percentage formatting
    - Color utilities: Dynamic color assignment based on data values
    - Column utilities: Batch operations on DataFrame columns
    - Table utilities: Enhanced table formatting and styling
    - Template engine: Jinja2-based template processing

Key Features:
    - Ready-to-use functions for common presentation tasks
    - Extensible design allowing custom implementations
    - Integration with the function registry system
    - Support for both YAML configuration and direct Python usage

Example:
    Using builtins in YAML configuration::
    
        data_transforms:
          - function: abbreviate_number_columns
            columns: [revenue, costs, profit]
            
        replacements:
          - type: text
            value_fn: format_currency
            
    Using builtins in Python code::
    
        from slideflow.builtins import (
            create_dynamic_colors,
            abbreviate_currency_columns
        )
        
        # Apply dynamic colors to a DataFrame
        df_styled = create_dynamic_colors(df, 'category')
        
        # Format currency columns
        df_formatted = abbreviate_currency_columns(
            df, 
            ['revenue', 'costs'],
            currency_symbol='$'
        )

Modules:
    formatting: Number and text formatting functions
    table_utils: Table styling and color mapping
    column_utils: DataFrame column operations
    template_engine: Jinja2 template processing
    registry: Function registry for builtins
"""

from slideflow.builtins.table_utils import create_dynamic_colors, create_growth_colors
from slideflow.builtins.formatting import abbreviate, format_currency, percentage, green_or_red
from slideflow.builtins.column_utils import abbreviate_number_columns, abbreviate_currency_columns

__all__ = [
    'create_dynamic_colors',
    'create_growth_colors',
    'abbreviate_number_columns', 
    'abbreviate_currency_columns',
    'abbreviate',
    'format_currency',
    'percentage',
    'green_or_red'
]
