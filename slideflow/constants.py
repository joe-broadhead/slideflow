"""Constants and configuration values used throughout the Slideflow package.

This module centralizes all constants, default values, configuration parameters,
and magic numbers used across the Slideflow framework. It provides a single
source of truth for framework-wide settings, making configuration management
and maintenance easier.

The constants are organized into logical groups using nested classes, providing
namespace separation and making it easy to find and modify related values.
This approach improves code maintainability and reduces the risk of
configuration drift across the codebase.

Key Constant Categories:
    - GoogleSlides: Google Slides platform-specific constants and defaults
    - MimeTypes: Standard MIME type definitions for file operations
    - FileExtensions: Common file extension constants
    - Defaults: Default values for various operations and configurations
    - Charts: Chart generation and rendering constants
    - Registry: Function and provider registry configuration
    - Logging: Logging system configuration and format strings
    - Templates: Template processing and parameter substitution settings
    - ErrorMessages: Standardized error message templates
    - Cache: Caching system configuration and operation types
    - Concurrency: Concurrent processing settings and limits
    - Validation: Data validation thresholds and patterns
    - Environment: Environment variable names for external integrations
    - Status: Operation status indicators and state definitions

Example:
    Using constants throughout the application:
    
    >>> from slideflow.constants import GoogleSlides, Defaults, ErrorMessages
    >>> 
    >>> # Google Slides configuration
    >>> chart_width = GoogleSlides.DEFAULT_CHART_WIDTH
    >>> slide_width = GoogleSlides.STANDARD_WIDTH_POINTS
    >>> 
    >>> # Default AI model selection
    >>> model = Defaults.OPENAI_MODEL
    >>> max_workers = Defaults.DEFAULT_MAX_WORKERS
    >>> 
    >>> # Error message formatting
    >>> error_msg = ErrorMessages.API_AUTH_FAILED.format(
    ...     provider="OpenAI", 
    ...     error="Invalid API key"
    ... )
    
    Environment variable access:
    
    >>> from slideflow.constants import Environment
    >>> import os
    >>> 
    >>> api_key = os.getenv(Environment.OPENAI_API_KEY)
    >>> debug_mode = os.getenv(Environment.DEBUG, "false").lower() == "true"
    
    Chart configuration:
    
    >>> from slideflow.constants import Charts
    >>> 
    >>> # Set up chart rendering
    >>> dpi = Charts.DEFAULT_DPI
    >>> width = Charts.DEFAULT_WIDTH_PX
    >>> height = Charts.DEFAULT_HEIGHT_PX

Design Principles:
    - All magic numbers and hardcoded values should be defined here
    - Constants are grouped logically for easy discovery and maintenance
    - String templates use format() syntax for consistent parameter substitution
    - Environment variable names follow standard naming conventions
    - Default values are chosen to work well for most common use cases
    - Configuration is designed to be easily overridden when needed

Maintenance:
    When adding new constants:
    1. Choose the appropriate category or create a new one if needed
    2. Use descriptive names that clearly indicate the constant's purpose
    3. Add inline comments for complex or non-obvious values
    4. Follow existing naming conventions (UPPER_CASE for constants)
    5. Update this module docstring if adding a new category
"""

class GoogleSlides:
    """Constants for Google Slides platform operations and formatting.
    
    This class contains all constants related to Google Slides presentation
    creation, including dimension conversions, default positioning, and
    permission settings. These values are based on Google Slides API
    specifications and common presentation design standards.
    """
    STANDARD_WIDTH_POINTS = 720
    STANDARD_HEIGHT_POINTS = 540
    POINTS_TO_PIXELS_RATIO = 1.33
    
    # Standard permission roles
    PERMISSION_WRITER = "writer"
    PERMISSION_READER = "reader" 
    PERMISSION_COMMENTER = "commenter"
    
    # Chart positioning defaults
    DEFAULT_CHART_WIDTH = 480  # 2/3 of slide width
    DEFAULT_CHART_HEIGHT = 360  # 2/3 of slide height
    DEFAULT_CHART_X_OFFSET = 120  # Center horizontally
    DEFAULT_CHART_Y_OFFSET = 90   # Center vertically

# File formats and MIME types
class MimeTypes:
    """Standard MIME type definitions for file operations and content handling.
    
    This class provides centralized MIME type constants for consistent
    file type handling across the Slideflow framework. These are used
    for file uploads, content type validation, and API interactions.
    """
    PNG = "image/png"
    PDF = "application/pdf"
    CSV = "text/csv"
    JSON = "application/json"
    YAML = "application/x-yaml"

class FileExtensions:
    """Standard file extension constants for file handling and validation.
    
    This class provides consistent file extension definitions used throughout
    the framework for file type detection, validation, and processing.
    All extensions include the leading dot for direct usage in file operations.
    """
    PNG = ".png"
    PDF = ".pdf"
    CSV = ".csv"
    JSON = ".json"
    YAML = ".yaml"
    YML = ".yml"

class Defaults:
    """Default configuration values used across the Slideflow application.
    
    This class centralizes default values for various operations and configurations
    throughout the framework. These values are chosen to provide good out-of-box
    behavior while remaining easily configurable for specific use cases.
    """
    
    # Data source defaults
    JSON_ORIENT = "records"
    DBT_TARGET = "prod"
    DBT_COMPILE = True
    
    # AI provider defaults
    OPENAI_MODEL = "gpt-4o"
    GEMINI_MODEL = "gemini-pro"
    
    # Cache defaults
    CACHE_MAX_SIZE = 50
    CACHE_TTL_SECONDS = 3600  # 1 hour
    
    # Concurrent processing
    DEFAULT_MAX_WORKERS = 10
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 1
    RETRY_BACKOFF_MULTIPLIER = 2

class Charts:
    """Constants and configuration for chart generation and rendering.
    
    This class contains settings for chart creation, including default dimensions,
    supported chart types, and rendering parameters. These values ensure
    consistent chart appearance and behavior across different visualization backends.
    """
    
    # Plotly figure defaults
    DEFAULT_DPI = 150
    DEFAULT_WIDTH_PX = 960   # 720 * 1.33
    DEFAULT_HEIGHT_PX = 720  # 540 * 1.33
    
    # Chart types
    TYPE_PLOTLY_GO = "plotly_go"
    TYPE_CUSTOM = "custom"
    
    # Common column reference prefix
    COLUMN_REFERENCE_PREFIX = "$"

class Registry:
    """Constants for function and provider registry management.
    
    This class defines settings for the extensible registry system that allows
    custom functions and providers to be discovered and registered automatically
    throughout the Slideflow framework.
    """
    FUNCTION_REGISTRY_KEY = "function_registry"
    REGISTRY_FILENAME = "registry.py"
    
    # Built-in function categories
    FORMATTING_FUNCTIONS = "formatting"
    TABLE_FUNCTIONS = "table"
    COLUMN_FUNCTIONS = "column"

class Logging:
    """Constants for centralized logging system configuration.
    
    This class defines format strings, logger names, and other settings
    for the Slideflow logging system, ensuring consistent log formatting
    and categorization across all components.
    """
    DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    SIMPLE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Logger names
    LOGGER_DATA = "slideflow.data"
    LOGGER_API = "slideflow.api"
    LOGGER_PERFORMANCE = "slideflow.performance"
    LOGGER_SLIDEFLOW = "slideflow"

class Templates:
    """Constants for template processing and parameter substitution.
    
    This class defines delimiters, patterns, and other settings used in
    template processing and configuration parameter substitution throughout
    the Slideflow framework.
    """
    PARAM_START_DELIMITER = "{"
    PARAM_END_DELIMITER = "}"
    EXCLUDED_PATTERN = "{{"  # Patterns to exclude from substitution
    
    # Column reference patterns
    COLUMN_PREFIX = "$"

class ErrorMessages:
    """Standardized error message templates for consistent error reporting.
    
    This class provides formatted error message templates that can be used
    throughout the framework to ensure consistent error messaging and
    easier localization support in the future.
    """
    MISSING_DEPENDENCY = "{package} is required for {feature}. Install: pip install {package}"
    API_AUTH_FAILED = "Authentication failed for {provider}: {error}"
    FILE_NOT_FOUND = "File not found: {file_path}"
    INVALID_CONFIG = "Invalid configuration: {error}"
    DATA_TRANSFORM_FAILED = "Data transform '{transform}' failed: {error}"
    
    # API specific
    OPENAI_EMPTY_RESPONSE = "OpenAI API returned empty response"
    RATE_LIMIT_EXCEEDED = "Rate limit exceeded for {provider}"

class Cache:
    """Constants for caching system configuration and operations.
    
    This class defines settings for the caching layer, including key formatting,
    hash algorithms, and operation type identifiers used throughout the
    data caching system.
    """
    KEY_SEPARATOR = "|"
    HASH_ALGORITHM = "md5"  # Could be upgraded to sha256
    
    # Cache operation types
    OPERATION_HIT = "hit"
    OPERATION_MISS = "miss"
    OPERATION_SET = "set"
    OPERATION_CLEAR = "clear"

class Concurrency:
    """Constants for concurrent and parallel processing operations.
    
    This class defines limits, timeouts, and configuration for concurrent
    operations throughout the Slideflow framework, including thread pool
    management and async operation handling.
    """
    DEFAULT_TIMEOUT_SECONDS = 30
    MAX_WORKERS_DEFAULT = 10
    THREAD_NAME_PREFIX = "slideflow-worker"

class Validation:
    """Constants for data validation and quality checks.
    
    This class defines thresholds, patterns, and limits used in data validation
    throughout the framework, helping ensure data quality and system performance.
    """
    MIN_DATAFRAME_ROWS = 1
    MAX_RECOMMENDED_ROWS = 100000  # Performance warning threshold
    
    # Email validation (if needed)
    EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

class Environment:
    """Standard environment variable names for external service integration.
    
    This class centralizes environment variable names used throughout the
    framework for API keys, configuration, and external service authentication.
    Using constants ensures consistency and makes configuration management easier.
    """
    
    # OpenAI
    OPENAI_API_KEY = "OPENAI_API_KEY"
    
    # Google/Gemini
    GOOGLE_API_KEY = "GOOGLE_API_KEY"
    GEMINI_API_KEY = "GEMINI_API_KEY"
    GOOGLE_SLIDEFLOW_CREDENTIALS = "GOOGLE_SLIDEFLOW_CREDENTIALS"
    
    # Databricks
    DATABRICKS_HOST = "DATABRICKS_HOST"
    DATABRICKS_HTTP_PATH = "DATABRICKS_HTTP_PATH"
    DATABRICKS_ACCESS_TOKEN = "DATABRICKS_ACCESS_TOKEN"
    
    # General
    DEBUG = "DEBUG"
    LOG_LEVEL = "LOG_LEVEL"

class Status:
    """Status indicators and operation state definitions.
    
    This class provides standard status symbols and state constants used
    throughout the framework for operation tracking, logging, and user feedback.
    """
    SUCCESS_SYMBOL = "✓"
    FAILURE_SYMBOL = "✗"
    
    # Operation states
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
