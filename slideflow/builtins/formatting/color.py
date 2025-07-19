"""Color formatting utilities for data visualization in presentations.

This module provides functions that map data values to colors, enabling
visual distinction based on data characteristics. These functions are
particularly useful for highlighting positive/negative trends, performance
indicators, and other data-driven color coding in presentations.

The color functions can be used in:
    - Table cell formatting to highlight values
    - Text replacements with color coding
    - Custom visualizations requiring dynamic colors

Functions:
    green_or_red: Maps positive/negative values to corresponding colors
"""

import decimal
from typing import Union

def green_or_red(value: Union[int, float, decimal.Decimal, str, None]) -> str:
    """Return a color name based on the sign of a numeric value.
    
    This function is commonly used to apply color coding to financial metrics,
    growth rates, and other values where positive/negative distinction is
    meaningful. It provides a simple way to visually highlight performance
    indicators in presentations. Zero is considered positive and returns 'green'.
    Non-numeric values return 'black' as a neutral color.

    Args:
        value: A numeric value to evaluate. Can be:
            - int: Integer values
            - float: Floating-point values
            - decimal.Decimal: High-precision decimal values
            - str: String representations of numbers (will return 'black')
            - None or other types: Non-numeric values (will return 'black')

    Returns:
        Color name as a string:
            - 'green': Value is greater than or equal to 0
            - 'red': Value is less than 0
            - 'black': Value is not a valid number
            
    Example:
        >>> green_or_red(42.5)
        'green'
        
        >>> green_or_red(-10)
        'red'
        
        >>> green_or_red(0)
        'green'
        
        >>> green_or_red("N/A")
        'black'
        
        >>> from decimal import Decimal
        >>> green_or_red(Decimal('15.75'))
        'green'
        
    Note:
        - Zero is considered positive and returns 'green'
        - Decimal values are converted to float for comparison
        - Non-numeric values return 'black' as a neutral color
        - This function does not raise exceptions for invalid inputs
    """
    if isinstance(value, decimal.Decimal):
        value = float(value)
        
    if isinstance(value, (int, float)):
        return "green" if value >= 0 else "red"
    return "black"

function_registry = {
    "green_or_red": green_or_red
}
