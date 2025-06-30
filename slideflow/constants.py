"""
Constants and magic numbers used throughout the slideflow package.
"""

# Google Slides dimensions and conversions
class GoogleSlides:
    """Constants for Google Slides operations."""
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
    """Common MIME types used in the application."""
    PNG = "image/png"
    PDF = "application/pdf"
    CSV = "text/csv"
    JSON = "application/json"
    YAML = "application/x-yaml"


class FileExtensions:
    """Common file extensions."""
    PNG = ".png"
    PDF = ".pdf"
    CSV = ".csv"
    JSON = ".json"
    YAML = ".yaml"
    YML = ".yml"


# Default values for various operations
class Defaults:
    """Default values used across the application."""
    
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


# Chart configuration
class Charts:
    """Constants for chart generation."""
    
    # Plotly figure defaults
    DEFAULT_DPI = 150
    DEFAULT_WIDTH_PX = 960   # 720 * 1.33
    DEFAULT_HEIGHT_PX = 720  # 540 * 1.33
    
    # Chart types
    TYPE_PLOTLY_GO = "plotly_go"
    TYPE_CUSTOM = "custom"
    
    # Common column reference prefix
    COLUMN_REFERENCE_PREFIX = "$"


# Registry and configuration
class Registry:
    """Constants for function and provider registries."""
    FUNCTION_REGISTRY_KEY = "function_registry"
    REGISTRY_FILENAME = "registry.py"
    
    # Built-in function categories
    FORMATTING_FUNCTIONS = "formatting"
    TABLE_FUNCTIONS = "table"
    COLUMN_FUNCTIONS = "column"


# Logging configuration
class Logging:
    """Constants for logging configuration."""
    DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    SIMPLE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
    
    # Logger names
    LOGGER_DATA = "slideflow.data"
    LOGGER_API = "slideflow.api"
    LOGGER_PERFORMANCE = "slideflow.performance"
    LOGGER_SLIDEFLOW = "slideflow"


# Template and configuration patterns
class Templates:
    """Constants for template processing."""
    PARAM_START_DELIMITER = "{"
    PARAM_END_DELIMITER = "}"
    EXCLUDED_PATTERN = "{{"  # Patterns to exclude from substitution
    
    # Column reference patterns
    COLUMN_PREFIX = "$"


# Error messages and codes
class ErrorMessages:
    """Standard error messages."""
    MISSING_DEPENDENCY = "{package} is required for {feature}. Install: pip install {package}"
    API_AUTH_FAILED = "Authentication failed for {provider}: {error}"
    FILE_NOT_FOUND = "File not found: {file_path}"
    INVALID_CONFIG = "Invalid configuration: {error}"
    DATA_TRANSFORM_FAILED = "Data transform '{transform}' failed: {error}"
    
    # API specific
    OPENAI_EMPTY_RESPONSE = "OpenAI API returned empty response"
    RATE_LIMIT_EXCEEDED = "Rate limit exceeded for {provider}"


# Cache keys and patterns
class Cache:
    """Constants for caching operations."""
    KEY_SEPARATOR = "|"
    HASH_ALGORITHM = "md5"  # Could be upgraded to sha256
    
    # Cache operation types
    OPERATION_HIT = "hit"
    OPERATION_MISS = "miss"
    OPERATION_SET = "set"
    OPERATION_CLEAR = "clear"


# Concurrent processing
class Concurrency:
    """Constants for concurrent operations."""
    DEFAULT_TIMEOUT_SECONDS = 30
    MAX_WORKERS_DEFAULT = 10
    THREAD_NAME_PREFIX = "slideflow-worker"


# Data validation
class Validation:
    """Constants for data validation."""
    MIN_DATAFRAME_ROWS = 1
    MAX_RECOMMENDED_ROWS = 100000  # Performance warning threshold
    
    # Email validation (if needed)
    EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'


# Environment variables
class Environment:
    """Environment variable names."""
    
    # OpenAI
    OPENAI_API_KEY = "OPENAI_API_KEY"
    
    # Google/Gemini
    GOOGLE_API_KEY = "GOOGLE_API_KEY"
    GEMINI_API_KEY = "GEMINI_API_KEY"
    
    # Databricks
    DATABRICKS_HOST = "DATABRICKS_HOST"
    DATABRICKS_HTTP_PATH = "DATABRICKS_HTTP_PATH"
    DATABRICKS_ACCESS_TOKEN = "DATABRICKS_ACCESS_TOKEN"
    
    # General
    DEBUG = "DEBUG"
    LOG_LEVEL = "LOG_LEVEL"


# Status and success indicators
class Status:
    """Status indicators for operations."""
    SUCCESS_SYMBOL = "✓"
    FAILURE_SYMBOL = "✗"
    
    # Operation states
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"