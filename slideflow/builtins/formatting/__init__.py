"""Built-in formatting functions for Slideflow presentations.

This module provides a collection of formatting utilities for transforming
data values into presentation-ready formats. It includes functions for
number formatting, currency display, color coding, and text abbreviation.

The formatting functions are designed to be used in:
    - YAML configuration files via the function registry
    - Direct Python code for custom transformations
    - Text replacements and table formatting

Functions:
    Color formatting:
        - green_or_red: Apply color based on positive/negative values
    
    Number formatting:
        - abbreviate: Shorten large numbers (1.2M, 3.4K)
        - format_currency: Format numbers as currency
        - percentage: Format decimals as percentages

Example:
    Using in YAML configuration::
    
        replacements:
          - type: text
            placeholder: "{{REVENUE}}"
            value_fn: format_currency
            
          - type: text  
            placeholder: "{{GROWTH}}"
            value_fn: green_or_red
            
    Using in Python code::
    
        from slideflow.builtins.formatting import format_currency, percentage
        
        revenue = format_currency(1234567.89)  # "$1,234,568"
        growth = percentage(0.125)  # "12.5%"
"""

from slideflow.builtins.formatting.color import green_or_red
from slideflow.builtins.formatting.format import abbreviate, format_currency, percentage

__all__ = [
    # Color functions
    'green_or_red',
    
    # Format functions
    'abbreviate',
    'format_currency', 
    'percentage',
]
