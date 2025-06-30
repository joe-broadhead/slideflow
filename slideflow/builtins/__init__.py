"""
SlideFlow Builtins

This module provides high-order utility functions and common patterns for slideflow users.
Users can import these builtins into their custom registries for common data transformations,
chart formatting, and presentation enhancements.

Usage:
    from slideflow.builtins.table_utils import create_dynamic_colors
    from slideflow.builtins.formatting import abbreviate_number_columns
"""

from slideflow.builtins.table_utils import create_dynamic_colors, create_growth_colors
from slideflow.builtins.column_utils import abbreviate_number_columns, abbreviate_currency_columns
from slideflow.builtins.formatting import abbreviate, format_currency, percentage, green_or_red

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