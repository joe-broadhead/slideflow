"""Text replacement system for dynamic content generation in presentations.

This module provides a comprehensive replacement system for dynamically generating
content in presentations. The system supports multiple types of replacements
including static text, AI-generated content, and data-driven table replacements,
all with a unified interface and type-safe configuration.

The replacement system integrates with:
    - Data sources for fetching replacement data
    - AI providers for generating intelligent content
    - Data transformation pipeline for preprocessing
    - Presentation builders for seamless integration

Key Features:
    - Type-safe replacement definitions with Pydantic validation
    - Multiple replacement types with discriminated unions
    - Data source integration for dynamic content
    - AI-powered text generation with multiple providers
    - Table-based replacements with custom formatting
    - Data transformation pipeline integration
    - Extensible architecture for custom replacement types

Replacement Types:
    - TextReplacement: Static or computed text replacements
    - AITextReplacement: AI-generated content using various providers
    - TableReplacement: Data-driven table content with formatting

Example:
    Creating different types of replacements:
    
    >>> from slideflow.replacements import (
    ...     TextReplacement, AITextReplacement, TableReplacement
    ... )
    >>> 
    >>> # Static text replacement
    >>> text_replacement = TextReplacement(
    ...     type="text",
    ...     placeholder="{{COMPANY_NAME}}",
    ...     replacement="Acme Corporation"
    ... )
    >>> 
    >>> # AI-generated content
    >>> ai_replacement = AITextReplacement(
    ...     type="ai_text",
    ...     placeholder="{{EXECUTIVE_SUMMARY}}",
    ...     prompt="Generate a 3-sentence executive summary",
    ...     provider="openai",
    ...     data_source=sales_data_source
    ... )
    >>> 
    >>> # Table-based replacement
    >>> table_replacement = TableReplacement(
    ...     type="table",
    ...     prefix="METRICS_",
    ...     data_source=metrics_data_source
    ... )
    >>> 
    >>> # Use replacements
    >>> content = text_replacement.get_replacement()
    >>> summary = ai_replacement.get_replacement()
    >>> metrics = table_replacement.get_replacement()

Architecture:
    The replacement system follows a plugin architecture where each replacement
    type implements the BaseReplacement interface. The ReplacementUnion provides
    type-safe discrimination for automatic instantiation of the correct
    replacement class based on configuration.
"""

from pydantic import Field
from typing import Union, Annotated

from slideflow.replacements.base import BaseReplacement
from slideflow.replacements.text import TextReplacement
from slideflow.replacements.table import TableReplacement
from slideflow.replacements.ai_text import AITextReplacement
from slideflow.replacements.utils import dataframe_to_replacement_object

# Discriminated union for all replacement types
ReplacementUnion = Annotated[
    Union[TextReplacement, AITextReplacement, TableReplacement],
    Field(discriminator = "type")
]
"""Union type for all available replacement types with discriminated validation.

This type alias enables Pydantic to automatically select and validate the
correct replacement type based on the 'type' field in the configuration.
Supports:

- TextReplacement: For static or computed text with 'type': 'text'
- AITextReplacement: For AI-generated content with 'type': 'ai_text'  
- TableReplacement: For table-based data with 'type': 'table'

Example:
    >>> from pydantic import TypeAdapter
    >>> 
    >>> # Automatically creates TextReplacement instance
    >>> replacement_config = {
    ...     "type": "text",
    ...     "placeholder": "{{NAME}}",
    ...     "replacement": "John Doe"
    ... }
    >>> adapter = TypeAdapter(ReplacementUnion)
    >>> replacement = adapter.validate_python(replacement_config)
"""

__all__ = [
    'BaseReplacement',
    'TextReplacement',
    'TableReplacement', 
    'AITextReplacement',
    'ReplacementUnion',
    'dataframe_to_replacement_object',
]
