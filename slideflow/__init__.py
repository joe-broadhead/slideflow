"""Slideflow - Dynamic Presentation Generation Framework.

Slideflow is a comprehensive Python framework for creating dynamic, data-driven
presentations across multiple platforms. It provides a unified interface for
data integration, content generation, chart creation, and presentation rendering
with support for various data sources and AI-powered content generation.

The framework is designed around a modular architecture that enables:
    - Data integration from multiple sources (CSV, JSON, databases, APIs)
    - AI-powered content generation with multiple provider support
    - Dynamic chart creation using various visualization libraries
    - Multi-platform presentation rendering (Google Slides, PowerPoint, etc.)
    - Extensible plugin system for custom functionality

Key Components:
    - Data Sources: Connect to CSV, JSON, Databricks, and other data sources
    - AI Providers: Integration with OpenAI, Google Gemini, and other AI services
    - Presentations: Framework for creating and managing presentations with charts
    - Replacements: Text and content replacement system with AI capabilities
    - Utilities: Configuration management, data transformation, and logging
    - Registry System: Extensible function and provider registration

Example:
    Basic Slideflow usage for creating a presentation:
    
    >>> import slideflow as sf
    >>> from pathlib import Path
    >>> 
    >>> # Load configuration
    >>> config_loader = sf.ConfigLoader(
    ...     yaml_path=Path("presentation_config.yaml"),
    ...     registry_paths=[Path("custom_functions.py")],
    ...     params={"quarter": "Q3", "year": "2024"}
    ... )
    >>> 
    >>> # Build presentation
    >>> builder = sf.PresentationBuilder(config_loader.config)
    >>> presentation = builder.build()
    >>> 
    >>> # Render presentation
    >>> result = presentation.render()
    >>> print(f"Presentation created: {result.presentation_id}")
    
    Working with data sources:
    
    >>> # Configure data source
    >>> csv_config = sf.CSVSourceConfig(file_path="sales_data.csv")
    >>> connector = sf.CSVConnector(csv_config)
    >>> 
    >>> # Get cached data
    >>> cache = sf.get_data_cache()
    >>> data = cache.get_data(connector)
    >>> 
    >>> # Apply transformations
    >>> transforms = [{"transform_fn": filter_current_quarter}]
    >>> processed_data = sf.apply_data_transforms(transforms, data)
    
    AI-powered content generation:
    
    >>> # Configure AI provider
    >>> ai_provider = sf.OpenAIProvider()
    >>> 
    >>> # Create AI text replacement
    >>> ai_replacement = sf.AITextReplacement(
    ...     prompt="Summarize the key insights from this sales data",
    ...     ai_provider=ai_provider,
    ...     data_context=processed_data
    ... )
    >>> 
    >>> # Generate content
    >>> summary = ai_replacement.get_replacement()

Architecture Overview:
    The Slideflow framework follows a layered architecture:
    
    1. Data Layer: Connectors and caches for various data sources
    2. Processing Layer: Data transformations and AI content generation
    3. Presentation Layer: Chart generation and slide management
    4. Rendering Layer: Platform-specific presentation rendering
    5. Utility Layer: Configuration, logging, and registry systems

Integration Features:
    - Built-in formatters for common data presentations
    - Registry system for custom functions and providers
    - Configuration-driven presentation generation
    - Caching for improved performance
    - Comprehensive error handling and logging
    - CLI interface for automation and scripting
"""

__version__ = "0.0.0"

# Core data functionality
from slideflow.data import (
    DataSourceCache, get_data_cache, DataSourceConfig,
    DataConnector, BaseSourceConfig,
    CSVConnector, CSVSourceConfig,
    JSONConnector, JSONSourceConfig,
    DatabricksConnector, DatabricksSourceConfig,
    DBTDatabricksConnector, DBTDatabricksSourceConfig
)

# Replacement functionality  
from slideflow.replacements import (
    BaseReplacement, TextReplacement, 
    TableReplacement, AITextReplacement,
    ReplacementUnion, dataframe_to_replacement_object
)

# AI providers
from slideflow.ai import (
    AIProvider, OpenAIProvider, GeminiProvider
)

# Presentation functionality
from slideflow.presentations import (
    PresentationBuilder, BaseChart, PlotlyGraphObjects, 
    CustomChart, TemplateChart, ChartUnion
)

# Utilities
from slideflow.utilities import ConfigLoader
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.builtins.formatting import (
    green_or_red, abbreviate, 
    format_currency, percentage
)

# Core registry utilities for extensibility
from slideflow.core.registry import (
    BaseRegistry, FunctionRegistry, ClassRegistry, ProviderRegistry,
    create_function_registry, create_class_registry, create_provider_registry
)

# CLI
from slideflow.cli import app as cli_app

# Exceptions
from slideflow.utilities.exceptions import (
    SlideFlowError, ConfigurationError, DataSourceError, DataTransformError,
    ProviderError, RenderingError, AuthenticationError, ChartGenerationError,
    ReplacementError
)

__all__ = [
    # Version
    '__version__',
    
    # Data
    'DataSourceCache', 'get_data_cache', 'DataSourceConfig',
    'DataConnector', 'BaseSourceConfig',
    'CSVConnector', 'CSVSourceConfig',
    'JSONConnector', 'JSONSourceConfig', 
    'DatabricksConnector', 'DatabricksSourceConfig',
    'DBTDatabricksConnector', 'DBTDatabricksSourceConfig',
    
    # Replacements
    'BaseReplacement', 'TextReplacement',
    'TableReplacement', 'AITextReplacement',
    'ReplacementUnion', 'dataframe_to_replacement_object',
    
    # AI
    'AIProvider', 'OpenAIProvider', 'GeminiProvider',
    
    # Presentations
    'PresentationBuilder', 'BaseChart', 'PlotlyGraphObjects',
    'CustomChart', 'TemplateChart', 'ChartUnion',
    
    # Utilities
    'ConfigLoader', 'apply_data_transforms',
    'green_or_red', 'abbreviate', 'format_currency', 'percentage',
    
    # Core registry utilities
    'BaseRegistry', 'FunctionRegistry', 'ClassRegistry', 'ProviderRegistry',
    'create_function_registry', 'create_class_registry', 'create_provider_registry',
    
    # CLI
    'cli_app',
    
    # Exceptions
    'SlideFlowError', 'ConfigurationError', 'DataSourceError', 'DataTransformError',
    'ProviderError', 'RenderingError', 'AuthenticationError', 'ChartGenerationError',
    'ReplacementError',
]