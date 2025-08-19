"""Number and currency formatting utilities for presentations.

This module provides comprehensive formatting functions for numeric values,
including abbreviation, percentage conversion, currency formatting, and
rounding. These functions handle various edge cases and data types to ensure
robust formatting in presentation contexts.

The formatting functions support:
    - Large number abbreviation (K, M, B, T suffixes)
    - Percentage formatting with customizable precision
    - Currency formatting with international symbol support
    - Safe handling of invalid inputs and edge cases
    - NumPy and Decimal type compatibility

Functions:
    abbreviate: Shorten large numbers with suffixes
    percentage: Format numbers as percentages
    round_value: Round numbers to specified precision
    format_currency: Format numbers as currency values
    abbreviate_currency: Combine abbreviation with currency formatting
"""

import math
import decimal
import numpy as np
from typing import Any, List, Tuple, Union, Optional

from slideflow.utilities.logging import get_logger
from slideflow.utilities.exceptions import DataTransformError

logger = get_logger(__name__)

def abbreviate(value: Any, suffixes: Optional[List[Tuple[float, str]]] = None) -> str:
    """Abbreviate large numeric values using standard suffixes.

    Converts large numbers into shorter, more readable strings by applying
    appropriate suffixes (K for thousands, M for millions, etc.). This is
    particularly useful for financial data, statistics, and metrics in
    presentations where space is limited.

    Args:
        value: The numeric value to abbreviate. Accepts:
            - int, float: Standard numeric types
            - numpy numeric types: np.integer, np.floating
            - decimal.Decimal: High-precision decimals
            - Any other type: Returned as string without modification
        suffixes: Custom suffix thresholds as (threshold, suffix) tuples.
            If None, uses default: [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")].
            Order matters - should be from largest to smallest threshold.

    Returns:
        Abbreviated string representation:
            - Numbers >= 1,000: Formatted with suffix (e.g., "1.2K", "3.4M")
            - Numbers < 1,000: Formatted with 2 decimal places and commas
            - Non-numeric values: Converted to string without modification
            
    Example:
        >>> abbreviate(1234)
        '1.2K'
        
        >>> abbreviate(1234567)
        '1.2M'
        
        >>> abbreviate(1234567890)
        '1.2B'
        
        >>> abbreviate(42.75)
        '42.75'
        
        >>> abbreviate(1234, [(1e3, "k"), (1e6, "m")])
        '1.2k'
        
        >>> abbreviate("N/A")
        'N/A'
        
    Note:
        - Maintains sign for negative numbers
        - Boolean values are treated as non-numeric
        - Handles edge cases gracefully without raising exceptions
    """
    try:
        if isinstance(value, decimal.Decimal):
            value = float(value)

        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            abs_val = abs(value)
            suffixes = suffixes or [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]
            for threshold, suffix in suffixes:
                if abs_val >= threshold:
                    return f"{value / threshold:.1f}{suffix}"
            return f"{value:,.2f}"
        return str(value)
    except (TypeError, ValueError, decimal.InvalidOperation, AttributeError) as e:
        logger.warning(f"Formatting failed for value {value}: {e}")
        return str(value)
    except Exception as e:
        logger.error(f"Unexpected error formatting {value}: {e}")
        raise DataTransformError(f"Critical formatting error: {e}") from e

def percentage(value: Any, ndigits: int = 2, from_ratio: bool = True) -> str:
    """Format a numeric value as a percentage string.

    Converts numbers to percentage format with customizable precision.
    Particularly useful for displaying rates, proportions, and growth
    figures in presentations.

    Args:
        value: The numeric value to convert to percentage. Accepts:
            - int, float: Standard numeric types
            - numpy numeric types: np.integer, np.floating
            - decimal.Decimal: High-precision decimals
            - Any other type: Returned as string without modification
        ndigits: Number of decimal places in the output. Defaults to 2.
            Must be non-negative. Higher values provide more precision.
        from_ratio: If True, multiplies value by 100 (treats input as ratio).
            If False, treats input as already in percentage form.
            Defaults to True.

    Returns:
        Formatted percentage string:
            - Valid numbers: Formatted as "XX.XX%" with specified precision
            - NaN values: Returns "NaN%"
            - Non-numeric values: Converted to string without modification
            
    Example:
        >>> percentage(0.1234)
        '12.34%'
        
        >>> percentage(0.1234, ndigits=1)
        '12.3%'
        
        >>> percentage(25.5, from_ratio=False)
        '25.50%'
        
        >>> percentage(0.05, ndigits=0)
        '5%'
        
        >>> percentage(float('nan'))
        'NaN%'
        
        >>> percentage("TBD")
        'TBD'
        
    Note:
        - Handles negative percentages correctly
        - Boolean values are treated as non-numeric
        - Special handling for NaN values
    """
    if value is None:
        return str(value)
    try:
        if isinstance(value, decimal.Decimal):
            value = float(value)

        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            if math.isnan(value):
                return "NaN%"
            val = value * 100 if from_ratio else value
            return f"{val:.{ndigits}f}%"
        return str(value)
    except (TypeError, ValueError, decimal.InvalidOperation) as e:
        logger.warning(f"Percentage formatting failed for value {value}: {e}")
        return str(value)
    except Exception as e:
        logger.error(f"Unexpected error in percentage formatting {value}: {e}")
        raise DataTransformError(f"Critical percentage formatting error: {e}") from e

def round_value(value: Any, ndigits: int = 2) -> Union[float, Any]:
    """Round a numeric value to specified decimal places.

    Provides consistent rounding behavior across different numeric types,
    useful for standardizing precision in presentations and reports.

    Args:
        value: The value to round. Accepts:
            - int, float: Standard numeric types
            - numpy numeric types: np.integer, np.floating
            - decimal.Decimal: Converted to float then rounded
            - Any other type: Returned unchanged
        ndigits: Number of decimal places to round to. Defaults to 2.
            Can be negative to round to tens, hundreds, etc.

    Returns:
        Rounded value:
            - Numeric inputs: Float rounded to specified precision
            - Non-numeric inputs: Original value unchanged
            
    Example:
        >>> round_value(3.14159)
        3.14
        
        >>> round_value(3.14159, ndigits=4)
        3.1416
        
        >>> round_value(1234.5, ndigits=-2)
        1200.0
        
        >>> round_value(decimal.Decimal('3.14159'), ndigits=3)
        3.142
        
        >>> round_value("N/A")
        'N/A'
        
    Note:
        - Uses Python's built-in round() function
        - Decimal values are converted to float before rounding
        - Boolean values are treated as non-numeric
        - Returns original value for invalid inputs rather than raising
    """
    try:
        if isinstance(value, decimal.Decimal):
            value = float(value)

        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            return round(float(value), ndigits)
        return value
    except (TypeError, ValueError, decimal.InvalidOperation) as e:
        logger.warning(f"Rounding failed for value {value}: {e}")
        return value
    except Exception as e:
        logger.error(f"Unexpected error rounding {value}: {e}")
        raise DataTransformError(f"Critical rounding error: {e}") from e

def format_currency(
    value: Any,
    currency_symbol: str = "€",
    symbol_position: str = "prefix",
    decimals: int = 2,
    negative_parens: bool = False,
    thousands_sep: str = ",",
    decimal_sep: str = "."
) -> str:
    """Format a numeric value as a currency string.

    Provides comprehensive currency formatting with support for various
    international conventions, including symbol placement, separators,
    and negative value representation.

    Args:
        value: The numeric value to format. Must be convertible to float.
            Non-numeric values are returned as strings.
        currency_symbol: Currency symbol to use. Defaults to "€".
            Common options: "$", "£", "¥", "€".
        symbol_position: Where to place the symbol:
            - "prefix": Before the number (e.g., "$100")
            - "suffix": After the number (e.g., "100 €")
            Defaults to "prefix".
        decimals: Number of decimal places to show. Defaults to 2.
            Use 0 for whole currency units only.
        negative_parens: How to display negative values:
            - True: Use parentheses, e.g., "($100.00)"
            - False: Use minus sign, e.g., "-$100.00"
            Defaults to False.
        thousands_sep: Character for thousands separation. Defaults to ",".
            Use "" for no separator, "." for European style.
        decimal_sep: Character for decimal separation. Defaults to ".".
            Use "," for European style.

    Returns:
        Formatted currency string. Non-numeric inputs return string representation.
        
    Example:
        >>> format_currency(1234.56)
        '€1,234.56'
        
        >>> format_currency(1234.56, currency_symbol="$", symbol_position="prefix")
        '$1,234.56'
        
        >>> format_currency(-500, negative_parens=True)
        '(€500.00)'
        
        >>> format_currency(1234.5, thousands_sep=".", decimal_sep=",")
        '€1.234,50'
        
        >>> format_currency(42, decimals=0)
        '€42'
        
        >>> format_currency("N/A")
        'N/A'
        
    Note:
        - Always shows the specified number of decimal places
        - Handles negative zero correctly
        - Preserves non-numeric inputs without raising exceptions
    """
    if value is None:
        return str(value)
    try:
        numeric_value = float(value)
        if math.isnan(numeric_value) or math.isinf(numeric_value):
            return str(value)
    except (TypeError, ValueError) as e:
        logger.warning(f"Currency formatting failed for non-numeric value {value}: {e}")
        return str(value)
    except Exception as e:
        logger.error(f"Unexpected error converting {value} to float: {e}")
        raise DataTransformError(f"Critical currency formatting error: {e}") from e

    formatted = f"{abs(numeric_value):,.{decimals}f}"

    if thousands_sep != "," or decimal_sep != ".":
        formatted = formatted.replace(",", "TEMP").replace(".", decimal_sep)
        formatted = formatted.replace("TEMP", thousands_sep)

    if symbol_position == "prefix":
        formatted = f"{currency_symbol}{formatted}"
    else:
        formatted = f"{formatted} {currency_symbol}"

    if numeric_value < 0:
        if negative_parens:
            formatted = f"({formatted})"
        else:
            formatted = f"-{formatted}"

    return formatted

def abbreviate_currency(
    value: Any,
    currency_symbol: str = "€",
    symbol_position: str = "prefix",
    negative_parens: bool = False,
    suffixes: Optional[List[Tuple[float, str]]] = None,
    decimals: int = 2,
    thousands_sep: str = ",",
    decimal_sep: str = "."
) -> str:
    """Combine number abbreviation with currency formatting.

    Formats large monetary values in a compact, readable form by combining
    abbreviation (K, M, B suffixes) with currency symbols. Ideal for
    dashboards, executive summaries, and space-constrained presentations.

    Args:
        value: Numeric value to format. Accepts:
            - int, float: Standard numeric types
            - numpy numeric types: np.integer, np.floating
            - decimal.Decimal: High-precision decimals
            - Any other type: Returned as string
        currency_symbol: Currency symbol to use. Defaults to "€".
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
        Formatted string combining currency symbol and abbreviated value.
        Non-numeric inputs return string representation.
        
    Example:
        >>> abbreviate_currency(1234567)
        '€1.2M'
        
        >>> abbreviate_currency(1234567, currency_symbol="$")
        '$1.2M'
        
        >>> abbreviate_currency(999)
        '€999.00'
        
        >>> abbreviate_currency(-5000000, negative_parens=True)
        '(€5.0M)'
        
        >>> abbreviate_currency(1500, suffixes=[(1e3, "k")])
        '€1.5k'
        
        >>> abbreviate_currency(1234567890)
        '€1.2B'
        
        >>> abbreviate_currency("N/A")
        'N/A'
        
    Note:
        - Values >= 1,000 are abbreviated with 1 decimal place
        - Values < 1,000 use full currency formatting
        - Maintains sign for negative numbers
        - Handles edge cases gracefully
    """
    try:
        if isinstance(value, decimal.Decimal):
            value = float(value)

        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            numeric_value = float(value)
            abs_val = abs(numeric_value)
            suffixes = suffixes or [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]

            for threshold, suffix in suffixes:
                if abs_val >= threshold:
                    abbreviated = f"{numeric_value / threshold:.1f}{suffix}"
                    break
            else:
                formatted = f"{abs_val:,.{decimals}f}"
                if thousands_sep != "," or decimal_sep != ".":
                    formatted = formatted.replace(",", "TEMP").replace(".", decimal_sep).replace("TEMP", thousands_sep)
                abbreviated = formatted

            if symbol_position == "prefix":
                formatted = f"{currency_symbol}{abbreviated}"
            else:
                formatted = f"{abbreviated} {currency_symbol}"

            if numeric_value < 0:
                if negative_parens:
                    formatted = f"({formatted})"
                else:
                    formatted = f"-{formatted}"

            return formatted

        return str(value)
    except (TypeError, ValueError, decimal.InvalidOperation, ZeroDivisionError) as e:
        logger.warning(f"Currency abbreviation failed for value {value}: {e}")
        return str(value)
    except Exception as e:
        logger.error(f"Unexpected error in currency abbreviation {value}: {e}")
        raise DataTransformError(f"Critical currency abbreviation error: {e}") from e

function_registry = {
    "abbreviate": abbreviate,
    "percentage": percentage,
    "round_value": round_value,
    "format_currency": format_currency,
    "abbreviate_currency": abbreviate_currency,
}
