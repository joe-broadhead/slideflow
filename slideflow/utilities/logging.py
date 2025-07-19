"""Centralized logging system for Slideflow with specialized operation tracking.

This module provides a comprehensive logging framework tailored for Slideflow's
needs, including performance monitoring, API operation tracking, data operation
logging, and consistent formatting across all components.

The logging system is designed to provide observability into Slideflow operations
while maintaining performance and structured output for monitoring and debugging.

Key Features:
    - Package-wide logging configuration with consistent formatting
    - Specialized loggers for different operation types (performance, data, API)
    - Structured logging with context information
    - Configurable log levels and output formatting
    - Integration with monitoring systems through structured messages

Logger Hierarchy:
    - slideflow.performance: Function execution times and performance metrics
    - slideflow.data: Data fetching, transformation, and caching operations
    - slideflow.api: External API calls and responses
    - slideflow.*: General application logging

Example:
    Basic logging setup and usage:
    
    >>> from slideflow.utilities.logging import setup_logging, get_logger
    >>> from slideflow.utilities.logging import log_performance, log_api_operation
    >>> 
    >>> # Configure logging for the application
    >>> setup_logging(level="INFO", enable_debug=True)
    >>> 
    >>> # Get a logger for your module
    >>> logger = get_logger(__name__)
    >>> logger.info("Starting data processing")
    >>> 
    >>> # Log performance metrics
    >>> import time
    >>> start_time = time.time()
    >>> # ... some operation ...
    >>> duration = time.time() - start_time
    >>> log_performance("data_processing", duration, records=1000)
    >>> 
    >>> # Log API operations
    >>> log_api_operation("openai", "generate_text", success=True, duration=2.5)

Integration:
    The logging system integrates with all Slideflow components:
    - Presentation rendering logs performance and API calls
    - Data transformation logs data operations and errors
    - Chart generation logs performance and rendering metrics
    - Provider operations log API calls and authentication events
"""
import sys
import logging
from typing import Optional, Any


def setup_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    enable_debug: bool = False,
    show_module_names: bool = True
) -> None:
    """Configure package-wide logging with consistent formatting and output handling.
    
    This function establishes the logging configuration for all Slideflow components,
    setting up consistent formatting, log levels, and output handlers. It configures
    both the root logger and Slideflow-specific loggers to ensure proper logging
    hierarchy and debug capabilities.
    
    The function supports customizable formatting and can enable debug-level logging
    specifically for Slideflow modules while maintaining different levels for other
    packages. This is useful for development and troubleshooting scenarios.
    
    Args:
        level: Log level for the root logger. Must be one of 'DEBUG', 'INFO', 
            'WARNING', 'ERROR', or 'CRITICAL'. Defaults to 'INFO'.
        format_string: Custom format string for log messages. If None, uses a
            default format that includes timestamp, logger name, level, and message.
            The format can include module names based on show_module_names parameter.
        enable_debug: If True, enables DEBUG level logging specifically for all
            slideflow.* loggers, regardless of the root level setting. Useful for
            detailed debugging of Slideflow operations without verbose output from
            other libraries.
        show_module_names: If True and format_string is None, includes the logger
            name (module name) in the default format. Set to False for cleaner
            output in production environments.
            
    Example:
        Basic logging setup for development:
        
        >>> setup_logging(level="DEBUG", enable_debug=True)
        >>> # Enables debug logging for all Slideflow components
        
        Production logging setup:
        
        >>> setup_logging(
        ...     level="INFO", 
        ...     show_module_names=False,
        ...     enable_debug=False
        ... )
        >>> # Clean production logging without module names
        
        Custom format string:
        
        >>> setup_logging(
        ...     level="INFO",
        ...     format_string="[%(levelname)s] %(asctime)s: %(message)s"
        ... )
        >>> # Uses custom format for all log messages
        
        Debugging specific operations:
        
        >>> setup_logging(level="WARNING", enable_debug=True)
        >>> # Only shows warnings/errors from external libraries
        >>> # but detailed debug info from Slideflow components
    """
    if format_string is None:
        if show_module_names:
            format_string = (
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        else:
            format_string = (
                "%(asctime)s - %(levelname)s - %(message)s"
            )

    logging.basicConfig(
        level = getattr(logging, level.upper()),
        format = format_string,
        handlers = [logging.StreamHandler(sys.stdout)],
        force = True  # Override any existing configuration
    )
    
    slideflow_logger = logging.getLogger("slideflow")
    if enable_debug:
        slideflow_logger.setLevel(logging.DEBUG)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with consistent configuration for the calling module.
    
    This function provides a standardized way to obtain logger instances across
    all Slideflow components. It ensures that all loggers follow the established
    hierarchy and inherit the appropriate configuration from the package-wide
    logging setup.
    
    The returned logger will automatically inherit the formatting, handlers, and
    log levels configured by setup_logging(), ensuring consistent output across
    all Slideflow modules.
    
    Args:
        name: The name for the logger, typically __name__ of the calling module.
            This creates a hierarchical logger name that helps with filtering
            and debugging. For example, passing 'slideflow.presentations.charts'
            creates a logger in the slideflow hierarchy.
            
    Returns:
        A configured Logger instance that inherits settings from the package
        logging configuration. The logger will respect the global log level
        and formatting settings established by setup_logging().
        
    Example:
        Standard usage in a module:
        
        >>> from slideflow.utilities.logging import get_logger
        >>> 
        >>> logger = get_logger(__name__)
        >>> logger.info("Module initialized successfully")
        >>> logger.debug("Detailed debugging information")
        >>> logger.error("An error occurred", exc_info=True)
        
        Custom logger naming:
        
        >>> logger = get_logger("slideflow.custom.component")
        >>> logger.warning("Custom component warning")
        
        Usage with exception handling:
        
        >>> logger = get_logger(__name__)
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     logger.error(f"Operation failed: {e}", exc_info=True)
        ...     raise
    """
    return logging.getLogger(name)

def log_performance(func_name: str, duration: float, **context: Any) -> None:
    """Log performance metrics for function execution with structured formatting.
    
    This function provides standardized performance logging across Slideflow
    components, making it easy to track execution times and identify performance
    bottlenecks. The logs are sent to the 'slideflow.performance' logger for
    easy filtering and monitoring.
    
    Performance logs include the function name, execution duration, and any
    additional context provided through keyword arguments. This enables
    detailed performance analysis and optimization efforts.
    
    Args:
        func_name: Name of the function or operation being measured. This should
            be descriptive enough to identify the specific operation, such as
            'render_presentation', 'generate_chart', or 'fetch_data'.
        duration: Execution time in seconds as a float. Typically obtained by
            measuring time before and after the operation using time.time() or
            similar timing mechanisms.
        **context: Additional context information to include in the log entry.
            Common context includes record counts, file sizes, API call counts,
            or other relevant metrics. These are formatted as key=value pairs
            in the log output.
            
    Example:
        Basic performance logging:
        
        >>> import time
        >>> from slideflow.utilities.logging import log_performance
        >>> 
        >>> start_time = time.time()
        >>> # ... perform some operation ...
        >>> duration = time.time() - start_time
        >>> log_performance("data_processing", duration)
        >>> # Output: "data_processing completed in 2.34s"
        
        Performance logging with context:
        
        >>> log_performance(
        ...     "chart_generation", 
        ...     1.25, 
        ...     chart_type="bar", 
        ...     data_points=1000
        ... )
        >>> # Output: "chart_generation completed in 1.25s (chart_type=bar, data_points=1000)"
        
        Integration with function decorators:
        
        >>> def timed_operation():
        ...     start = time.time()
        ...     try:
        ...         # ... operation logic ...
        ...         result = process_data()
        ...         return result
        ...     finally:
        ...         duration = time.time() - start
        ...         log_performance("process_data", duration, records=len(result))
    """
    logger = get_logger("slideflow.performance")
    
    context_str = ""
    if context:
        context_parts = [f"{k}={v}" for k, v in context.items()]
        context_str = f" ({', '.join(context_parts)})"
    
    logger.info(f"{func_name} completed in {duration:.2f}s{context_str}")

def log_data_operation(
    operation: str, 
    source_type: str, 
    record_count: Optional[int] = None,
    **context: Any
) -> None:
    """Log data operations with structured formatting and context information.
    
    This function provides standardized logging for data operations throughout
    Slideflow, including data fetching, transformation, caching, and validation.
    The logs are sent to the 'slideflow.data' logger for easy filtering and
    monitoring of data pipeline operations.
    
    Data operation logs include the operation type, data source type, record
    counts, and any additional context that helps with debugging and monitoring
    data flow through the system.
    
    Args:
        operation: Type of data operation being performed. Common values include
            'fetch', 'transform', 'cache', 'validate', 'aggregate', 'filter', or
            custom operation names. Should be descriptive of the actual operation.
        source_type: Type or identifier of the data source being operated on.
            Examples include 'csv', 'json', 'databricks', 'postgres', 'api', 
            'memory', or specific source identifiers like 'sales_database'.
        record_count: Number of records or rows processed in the operation.
            Used for tracking data volume and can help identify performance
            issues with large datasets. Pass None if record count is not
            applicable or unknown.
        **context: Additional context information relevant to the operation.
            Common context includes file paths, query parameters, transformation
            names, error counts, or execution metadata. These are formatted as
            key=value pairs in the log output.
            
    Example:
        Data fetching operations:
        
        >>> from slideflow.utilities.logging import log_data_operation
        >>> 
        >>> log_data_operation("fetch", "csv", record_count=1500)
        >>> # Output: "fetch from csv (1,500 records)"
        
        Data transformation with context:
        
        >>> log_data_operation(
        ...     "transform", 
        ...     "memory", 
        ...     record_count=1200, 
        ...     transform_name="filter_by_date",
        ...     filters_applied=3
        ... )
        >>> # Output: "transform from memory (1,200 records) [transform_name=filter_by_date, filters_applied=3]"
        
        Cache operations:
        
        >>> log_data_operation(
        ...     "cache", 
        ...     "redis", 
        ...     cache_key="sales_q3_2024",
        ...     ttl_seconds=3600
        ... )
        >>> # Output: "cache from redis [cache_key=sales_q3_2024, ttl_seconds=3600]"
        
        Error scenarios:
        
        >>> log_data_operation(
        ...     "fetch", 
        ...     "databricks", 
        ...     record_count=0,
        ...     query_failed=True,
        ...     error_type="connection_timeout"
        ... )
        >>> # Output: "fetch from databricks (0 records) [query_failed=True, error_type=connection_timeout]"
    """
    logger = get_logger("slideflow.data")
    
    message_parts = [f"{operation} from {source_type}"]
    
    if record_count is not None:
        message_parts.append(f"({record_count:,} records)")
    
    if context:
        context_parts = [f"{k}={v}" for k, v in context.items()]
        message_parts.append(f"[{', '.join(context_parts)}]")
    
    logger.info(" ".join(message_parts))

def log_api_operation(
    provider: str,
    operation: str,
    success: bool = True,
    duration: Optional[float] = None,
    **context: Any
) -> None:
    """Log external API operations with success status and performance metrics.
    
    This function provides standardized logging for all external API interactions
    in Slideflow, including AI providers, presentation platforms, data sources,
    and other external services. The logs are sent to the 'slideflow.api' logger
    for easy filtering and monitoring of external dependencies.
    
    API operation logs include the provider name, operation type, success status,
    execution duration, and any additional context. This enables monitoring of
    API performance, error rates, and debugging of external service issues.
    
    Args:
        provider: Name of the API provider or service being called. Common values
            include 'openai', 'anthropic', 'google_slides', 'databricks', or any
            external service identifier. Should be consistent across all calls
            to the same provider.
        operation: Type of operation being performed on the API. Examples include
            'generate_text', 'upload_image', 'create_presentation', 'execute_query',
            'authenticate', or other provider-specific operations.
        success: Whether the API operation completed successfully. Defaults to True.
            Set to False for failed operations to enable error rate monitoring
            and alerting on API failures.
        duration: Execution time for the API call in seconds as a float. Used for
            performance monitoring and identifying slow API operations. Pass None
            if timing information is not available.
        **context: Additional context information relevant to the API operation.
            Common context includes request IDs, response sizes, token usage,
            error codes, retry attempts, or provider-specific metadata. These
            are formatted as key=value pairs in the log output.
            
    Example:
        Successful API operations:
        
        >>> from slideflow.utilities.logging import log_api_operation
        >>> 
        >>> log_api_operation("openai", "generate_text", success=True, duration=2.1)
        >>> # Output: "✓ openai.generate_text (2.10s)"
        
        API operations with context:
        
        >>> log_api_operation(
        ...     "google_slides", 
        ...     "upload_image", 
        ...     success=True, 
        ...     duration=0.8,
        ...     image_size_kb=156,
        ...     slide_id="slide_123"
        ... )
        >>> # Output: "✓ google_slides.upload_image (0.80s) [image_size_kb=156, slide_id=slide_123]"
        
        Failed API operations:
        
        >>> log_api_operation(
        ...     "databricks", 
        ...     "execute_query", 
        ...     success=False,
        ...     duration=30.0,
        ...     error_code="TIMEOUT",
        ...     retry_attempt=2
        ... )
        >>> # Output: "✗ databricks.execute_query (30.00s) [error_code=TIMEOUT, retry_attempt=2]"
        
        Authentication operations:
        
        >>> log_api_operation(
        ...     "google_slides", 
        ...     "authenticate", 
        ...     success=True,
        ...     token_expires_in=3600
        ... )
        >>> # Output: "✓ google_slides.authenticate [token_expires_in=3600]"
        
        Monitoring token usage:
        
        >>> log_api_operation(
        ...     "openai", 
        ...     "generate_text", 
        ...     success=True, 
        ...     duration=1.5,
        ...     tokens_used=150,
        ...     model="gpt-4"
        ... )
        >>> # Output: "✓ openai.generate_text (1.50s) [tokens_used=150, model=gpt-4]"
    """
    logger = get_logger("slideflow.api")
    
    status = "✓" if success else "✗"
    message_parts = [f"{status} {provider}.{operation}"]
    
    if duration is not None:
        message_parts.append(f"({duration:.2f}s)")
    
    if context:
        context_parts = [f"{k}={v}" for k, v in context.items()]
        message_parts.append(f"[{', '.join(context_parts)}]")
    
    level = logging.INFO if success else logging.ERROR
    logger.log(level, " ".join(message_parts))

setup_logging()
