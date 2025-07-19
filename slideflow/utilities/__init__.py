"""Slideflow Utilities - Core infrastructure and helper functions.

This module provides essential utilities and infrastructure components that support
the Slideflow presentation generation system. It includes configuration management,
data transformation pipeline, exception hierarchy, and centralized logging facilities.

The utilities module is designed to be used across all other Slideflow components,
providing consistent interfaces for common operations like configuration loading,
data processing, error handling, and logging.

Key Components:
    - Configuration Management: YAML loading with template resolution and function registry
    - Data Transformation: Pipeline for preprocessing data before use in presentations
    - Exception Hierarchy: Structured error types for different failure scenarios
    - Logging System: Centralized logging with performance and API operation tracking

Example:
    Basic utility usage across Slideflow:
    
    >>> from slideflow.utilities import ConfigLoader, get_logger, apply_data_transforms
    >>> from pathlib import Path
    >>> 
    >>> # Load configuration with template resolution
    >>> loader = ConfigLoader(
    ...     yaml_path=Path("config.yaml"),
    ...     registry_paths=[Path("functions.py")],
    ...     params={"environment": "production"}
    ... )
    >>> config = loader.config
    >>> 
    >>> # Set up logging
    >>> from slideflow.utilities import setup_logging
    >>> setup_logging(level="INFO", enable_debug=True)
    >>> logger = get_logger(__name__)
    >>> 
    >>> # Apply data transformations
    >>> import pandas as pd
    >>> df = pd.DataFrame({"sales": [100, 200, 300]})
    >>> transforms = [{"transform_fn": lambda df: df * 1.1}]
    >>> transformed_df = apply_data_transforms(transforms, df)

Integration Points:
    - All Slideflow modules use utilities for consistent error handling
    - Configuration system supports all component types (charts, replacements, providers)
    - Data transformation pipeline is used by charts, replacements, and data sources
    - Logging system provides observability across all operations

Performance Features:
    - Cached configuration loading to avoid repeated YAML parsing
    - Efficient data transformation with pandas integration
    - Structured logging for performance monitoring and debugging
    - Exception context preservation for detailed error reporting
"""

from slideflow.utilities.config import ConfigLoader
from slideflow.utilities.data_transforms import apply_data_transforms
from slideflow.utilities.exceptions import (
    SlideFlowError,
    ConfigurationError,
    DataSourceError,
    DataTransformError,
    APIError,
    APIRateLimitError,
    ProviderError,
    RenderingError,
    AuthenticationError,
    ChartGenerationError,
    ReplacementError
)
from slideflow.utilities.logging import (
    setup_logging,
    get_logger,
    log_performance,
    log_data_operation,
    log_api_operation
)

__all__ = [
    'ConfigLoader',
    'apply_data_transforms',
    'SlideFlowError',
    'ConfigurationError', 
    'DataSourceError',
    'DataTransformError',
    'APIError',
    'APIRateLimitError',
    'ProviderError',
    'RenderingError',
    'AuthenticationError',
    'ChartGenerationError',
    'ReplacementError',
    'setup_logging',
    'get_logger',
    'log_performance',
    'log_data_operation',
    'log_api_operation',
]
