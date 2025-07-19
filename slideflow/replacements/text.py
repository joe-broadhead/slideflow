"""Text replacement implementation for static and computed text content.

This module provides the TextReplacement class for handling simple text
substitutions in presentations. It supports both static text replacements
and dynamic text generation using data sources and custom functions.

The TextReplacement class is designed for:
    - Static text substitutions (e.g., company names, dates)
    - Computed text from data sources (e.g., calculated metrics)
    - Function-based text generation with custom logic
    - Template variable replacement with data integration

Example:
    Static text replacement:
    
    >>> from slideflow.replacements.text import TextReplacement
    >>> 
    >>> replacement = TextReplacement(
    ...     type="text",
    ...     placeholder="{{COMPANY_NAME}}",
    ...     replacement="Acme Corporation"
    ... )
    >>> content = replacement.get_replacement()
    >>> # Result: "Acme Corporation"
    
    Data-driven text with custom function:
    
    >>> def calculate_growth(df, period="Q1"):
    ...     current = df[df['period'] == period]['revenue'].sum()
    ...     previous = df[df['period'] == 'Q4']['revenue'].sum()
    ...     growth = ((current - previous) / previous) * 100
    ...     return f"{growth:.1f}% growth in {period}"
    >>> 
    >>> replacement = TextReplacement(
    ...     type="text",
    ...     placeholder="{{GROWTH_RATE}}",
    ...     data_source=revenue_data_source,
    ...     value_fn=calculate_growth,
    ...     value_fn_args={"period": "Q2"}
    ... )
    >>> content = replacement.get_replacement()
    >>> # Result: "15.3% growth in Q2"
"""

import pandas as pd
from pydantic import Field, field_validator, ConfigDict
from typing import Annotated, Optional, Callable, Literal, Dict, Any

from slideflow.replacements.base import BaseReplacement
from slideflow.data.connectors.connect import DataSourceConfig

class TextReplacement(BaseReplacement):
    """Text replacement for static or computed content in presentations.
    
    This class handles simple text substitutions where a placeholder in the
    presentation template is replaced with either static text or dynamically
    generated content. It supports data source integration for computed
    replacements and custom functions for complex text generation logic.
    
    The replacement process follows this priority:
    1. If value_fn is provided, call it with data and arguments
    2. Otherwise, use the static replacement value
    3. Return empty string if neither is available
    
    Data Integration:
        When a data_source is configured, the replacement can fetch data
        and apply transformations before passing it to the value function.
        This enables dynamic content generation based on current data.
    
    Attributes:
        type: Always "text" for this replacement type.
        placeholder: Template placeholder to replace (e.g., "{{REVENUE}}").
        replacement: Static text to use when no value_fn is provided.
        data_source: Optional data source configuration for dynamic content.
        value_fn: Optional function to compute replacement from data.
        value_fn_args: Keyword arguments passed to value_fn.
        
    Example:
        Static text replacement:
        
        >>> replacement = TextReplacement(
        ...     type="text",
        ...     placeholder="{{QUARTER}}",
        ...     replacement="Q3 2024"
        ... )
        >>> result = replacement.get_replacement()
        >>> # Returns: "Q3 2024"
        
        Computed replacement with data:
        
        >>> def format_revenue(df, currency="USD"):
        ...     total = df['revenue'].sum()
        ...     return f"{currency} {total:,.2f}M"
        >>> 
        >>> replacement = TextReplacement(
        ...     type="text",
        ...     placeholder="{{TOTAL_REVENUE}}",
        ...     data_source=revenue_source,
        ...     value_fn=format_revenue,
        ...     value_fn_args={"currency": "EUR"}
        ... )
        >>> result = replacement.get_replacement()
        >>> # Returns: "EUR 125.50M"
        
        Function without data source:
        
        >>> def current_date(format="%Y-%m-%d"):
        ...     from datetime import datetime
        ...     return datetime.now().strftime(format)
        >>> 
        >>> replacement = TextReplacement(
        ...     type="text",
        ...     placeholder="{{REPORT_DATE}}",
        ...     value_fn=current_date,
        ...     value_fn_args={"format": "%B %d, %Y"}
        ... )
        >>> result = replacement.get_replacement()
        >>> # Returns: "March 15, 2024"
    """
    type: Annotated[Literal["text"], Field("text", description = "Discriminator for text replacement")]
    placeholder: Annotated[str, Field(..., description = "Placeholder to replace (e.g. '{{STORE_CODE}}')")]
    replacement: Annotated[Optional[str], Field(default = None, description = "Static text to use if no `value_fn` is provided")]
    data_source: Annotated[Optional[DataSourceConfig], Field(default = None, description = "Optional data source for computing the replacement")]
    value_fn: Annotated[Optional[Callable[..., str]], Field(default = None, description = "Function to compute the replacement text from data")]
    value_fn_args: Annotated[Dict[str, Any], Field(default_factory = dict, description = "Keyword arguments passed to `value_fn`; string values will be formatted")]

    model_config = ConfigDict(
        extra = "forbid",
        arbitrary_types_allowed = True
    )

    @field_validator("replacement", mode = "before")
    @classmethod
    def _ensure_str(cls, v: Any) -> Optional[str]:
        """Convert replacement values to strings for consistency.
        
        Ensures that any non-None replacement value is converted to a string
        representation. This allows numeric, boolean, or other types to be
        used as replacement values while maintaining string output.
        
        Args:
            v: The replacement value to validate and convert.
            
        Returns:
            String representation of the value, or None if input was None.
            
        Example:
            >>> TextReplacement._ensure_str(42)
            "42"
            >>> TextReplacement._ensure_str(True)
            "True"
            >>> TextReplacement._ensure_str(None)
            None
        """
        return None if v is None else str(v)

    def fetch_data(self) -> Optional[pd.DataFrame]:
        """Fetch data from the configured data source for dynamic content.
        
        If a data_source is configured, this method delegates to the data
        source's fetch_data method to retrieve the underlying data. The data
        can then be used by value_fn to generate dynamic replacement text.
        
        Returns:
            DataFrame containing the fetched data if a data source is configured,
            None if no data source is set (for static or function-only replacements).
            
        Example:
            >>> replacement = TextReplacement(
            ...     type="text",
            ...     placeholder="{{METRIC}}",
            ...     data_source=database_source
            ... )
            >>> data = replacement.fetch_data()
            >>> # Returns DataFrame from database_source
        """
        if self.data_source:
            return self.data_source.fetch_data()
        return None

    def get_replacement(self) -> str:
        """Generate the final replacement text content.
        
        This is the main method that produces the text content to replace
        the placeholder. The method follows a priority system:
        
        1. If value_fn is configured:
           a. Fetch data from data_source if available
           b. Apply data transformations if data was fetched
           c. Call value_fn with data and/or arguments
           d. Convert result to string
        
        2. If no value_fn is configured:
           a. Return the static replacement value
           b. Return empty string if no replacement is set
        
        The method ensures that the result is always a string, making it
        safe for use in text substitution operations.
        
        Returns:
            String content to replace the placeholder. Never returns None.
            
        Raises:
            Any exception raised by value_fn during execution will propagate.
            
        Example:
            Static replacement:
            
            >>> replacement = TextReplacement(
            ...     type="text",
            ...     placeholder="{{NAME}}",
            ...     replacement="John Doe"
            ... )
            >>> result = replacement.get_replacement()
            >>> # Returns: "John Doe"
            
            Function-based replacement:
            
            >>> def summarize_data(df):
            ...     return f"Dataset contains {len(df)} records"
            >>> 
            >>> replacement = TextReplacement(
            ...     type="text",
            ...     placeholder="{{SUMMARY}}",
            ...     data_source=source,
            ...     value_fn=summarize_data
            ... )
            >>> result = replacement.get_replacement()
            >>> # Returns: "Dataset contains 150 records"
            
            Function without data:
            
            >>> def get_timestamp():
            ...     import time
            ...     return time.strftime("%Y-%m-%d %H:%M:%S")
            >>> 
            >>> replacement = TextReplacement(
            ...     type="text",
            ...     placeholder="{{TIMESTAMP}}",
            ...     value_fn=get_timestamp
            ... )
            >>> result = replacement.get_replacement()
            >>> # Returns: "2024-03-15 14:30:25"
        """
        if self.value_fn:
            data = self.fetch_data()
            if data is not None:
                # Apply data transformations before processing
                transformed_data = self.apply_data_transforms(data)
                return str(self.value_fn(transformed_data, **(self.value_fn_args or {})))
            return str(self.value_fn(**(self.value_fn_args or {})))
        return self.replacement or ''
