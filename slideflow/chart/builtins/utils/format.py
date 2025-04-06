import math
import numpy as np
from typing import Any, List

def abbreviate(value: Any, suffixes: List[tuple] = None) -> str:
    """
    Abbreviates a numeric value using standard suffixes (K, M, B, T).

    Converts large numbers into shorter human-readable strings, e.g.:
    1,200 → "1.2K", 3,400,000 → "3.4M".

    If the value is not numeric or an error occurs during formatting, the original
    value is returned as a string.

    Args:
        value (Any): The value to abbreviate.
        suffixes (List[tuple], optional): Custom suffix thresholds, 
            each as a (threshold, suffix) tuple. Defaults to common financial units.

    Returns:
        str: A string with the abbreviated value, or the original value as a string if not numeric.
    """
    try:
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            abs_val = abs(value)
            suffixes = suffixes or [(1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')]
            for threshold, suffix in suffixes:
                if abs_val >= threshold:
                    return f'{value / threshold:.1f}{suffix}'
            return f'{value:,.2f}'
        return str(value)
    except Exception:
        return str(value)

def percentage(value: Any, ndigits: int = 2, from_ratio: bool = True) -> str:
    """
    Formats a numeric value as a percentage string.

    Converts a number to a percentage string with the specified number of decimal places.
    Optionally assumes the input is a ratio (e.g., 0.25 → "25.00%").

    Args:
        value (Any): The value to convert to a percentage.
        ndigits (int): Number of decimal places to include. Defaults to 2.
        from_ratio (bool): Whether to multiply the input by 100. Defaults to True.

    Returns:
        str: The formatted percentage string. If the input is invalid, returns the original value as a string.
    """
    try:
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            if math.isnan(value):
                return 'NaN%'
            val = value * 100 if from_ratio else value
            return f'{val:.{ndigits}f}%'
        return str(value)
    except Exception:
        return str(value)

def round(value: Any, ndigits: int = 2) -> float:
    """
    Rounds a numeric value to the specified number of decimal places.

    If the input is a numeric type (int, float, numpy number), it is rounded to `ndigits`.
    If the input is not a valid numeric type, it is returned unchanged.

    Args:
        value (Any): The value to round.
        ndigits (int): The number of decimal places to round to. Defaults to 2.

    Returns:
        float: The rounded number if valid, otherwise the original input.
    """
    try:
        if isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool):
            return round(float(value), ndigits)
        return value
    except Exception:
        return value

def format_currency(
    value,
    currency_symbol = '€',
    decimals = 2,
    negative_parens = False,
    thousands_sep = ',',
    decimal_sep = '.'
):
    """
    Formats a numeric value as a currency string.

    Converts a number into a currency-formatted string with options for symbol, decimal precision,
    thousands separator, decimal separator, and handling of negative values.

    Args:
        value: The numeric value to format. Can be int, float, or convertible to float.
        currency_symbol (str): Symbol to prepend to the formatted value. Defaults to "€".
        decimals (int): Number of decimal places. Defaults to 2.
        negative_parens (bool): If True, wraps negative values in parentheses. Defaults to False.
        thousands_sep (str): Separator for thousands. Defaults to ",".
        decimal_sep (str): Separator for decimals. Defaults to ".".

    Returns:
        str: The formatted currency string. If `value` is not numeric, it is returned as-is.
    """
    try:
        numeric_value = float(value)
    except Exception:
        return str(value)

    formatted = f'{abs(numeric_value):,.{decimals}f}'

    if thousands_sep != ',' or decimal_sep != '.':
        formatted = formatted.replace(',', 'TEMP').replace('.', decimal_sep)
        formatted = formatted.replace('TEMP', thousands_sep)

    if numeric_value < 0:
        if negative_parens:
            formatted = f'({currency_symbol}{formatted})'
        else:
            formatted = f'-{currency_symbol}{formatted}'
    else:
        formatted = f'{currency_symbol}{formatted}'

    return formatted

BUILTIN_FORMAT_FUNCTIONS = {
    'abbreviate': abbreviate,
    'percentage': percentage,
    'round': round,
    'format_currency': format_currency,
}