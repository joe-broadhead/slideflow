import math
import decimal
import numpy as np
from typing import Any, List

from slideflow.utilities.exceptions import DataTransformError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)

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

def round_value(value: Any, ndigits: int = 2) -> float:
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
    value,
    currency_symbol = "€",
    symbol_position = "prefix",
    decimals = 2,
    negative_parens = False,
    thousands_sep = ",",
    decimal_sep = "."
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
    suffixes: List[tuple] = None,
    decimals: int = 2,
    thousands_sep: str = ",",
    decimal_sep: str = "."
) -> str:
    """
    Abbreviates a number (e.g., 1,200 → 1.2K) and adds a currency symbol.

    Args:
        value: Numeric input.
        currency_symbol (str): Symbol to add (default is '€').
        symbol_position (str): 'prefix' or 'suffix'. Defaults to 'prefix'.
        negative_parens (bool): Wrap negative values in parentheses if True.
        suffixes (List[tuple]): Custom suffix thresholds. Defaults to [(1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')].
        decimals (int): Decimal places for values < 1K. Defaults to 2.
        thousands_sep (str): Separator for thousands. Defaults to ','.
        decimal_sep (str): Separator for decimals. Defaults to '.'.

    Returns:
        str: Abbreviated and formatted value with currency.
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