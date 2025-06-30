"""
Formatting utility functions for slideflow

Functions for number abbreviation, currency formatting, and other common data transformations.
"""

from typing import List
from slideflow.builtins.formatting.format import abbreviate, abbreviate_currency

def abbreviate_number_columns(df, columns_to_abbreviate: List[str]):
    """
    Abbreviate large numbers in specified columns using existing slideflow utilities.
    
    Args:
        df: DataFrame to process
        columns_to_abbreviate: List of column names to abbreviate
        
    Returns:
        DataFrame with abbreviated number columns
        
    Example:
        df = abbreviate_number_columns(df, ['count', 'volume'])
        # Uses slideflow.utilities.formatting.format.abbreviate
    """
    
    df = df.copy()
    
    for col in columns_to_abbreviate:
        if col in df.columns:
            df[col] = df[col].apply(abbreviate)
    
    return df


def abbreviate_currency_columns(df, columns_to_abbreviate: List[str], currency_symbol: str = "$"):
    """
    Abbreviate large currency values in specified columns using existing slideflow utilities.
    
    Args:
        df: DataFrame to process
        columns_to_abbreviate: List of column names to abbreviate
        currency_symbol: Currency symbol to prepend (default '$')
        
    Returns:
        DataFrame with abbreviated currency columns
        
    Example:
        df = abbreviate_currency_columns(df, ['amount'], currency_symbol='€')
        # Uses slideflow.utilities.formatting.format.abbreviate_currency
    """
    
    df = df.copy()
    
    for col in columns_to_abbreviate:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: abbreviate_currency(x, currency_symbol=currency_symbol))
    
    return df


def format_percentages(df, columns_to_format: List[str], decimal_places: int = 1, from_ratio: bool = True):
    """
    Format columns as percentages.
    
    Args:
        df: DataFrame to process
        columns_to_format: List of column names to format as percentages
        decimal_places: Number of decimal places (default 1)
        from_ratio: Whether input is a ratio (0.25 -> 25%) or percentage (25 -> 25%)
        
    Returns:
        DataFrame with percentage formatted columns
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


def round_numbers(df, columns_to_round: List[str], decimal_places: int = 2):
    """
    Round numbers in specified columns to given decimal places.
    
    Args:
        df: DataFrame to process
        columns_to_round: List of column names to round
        decimal_places: Number of decimal places (default 2)
        
    Returns:
        DataFrame with rounded columns
    """
    df = df.copy()
    
    for col in columns_to_round:
        if col in df.columns:
            df[col] = df[col].round(decimal_places)
    
    return df