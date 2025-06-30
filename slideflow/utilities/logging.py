"""
Centralized logging configuration for the slideflow package.
"""
import logging
import sys
from typing import Optional, Any


def setup_logging(
    level: str = "INFO",
    format_string: Optional[str] = None,
    enable_debug: bool = False,
    show_module_names: bool = True
) -> None:
    """
    Configure package-wide logging with consistent formatting.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format_string: Custom format string, uses default if None
        enable_debug: Enable debug logging for slideflow modules
        show_module_names: Include module names in log output
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
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True  # Override any existing configuration
    )
    
    # Set slideflow package logger level
    slideflow_logger = logging.getLogger("slideflow")
    if enable_debug:
        slideflow_logger.setLevel(logging.DEBUG)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with consistent configuration.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_performance(func_name: str, duration: float, **context: Any) -> None:
    """
    Log performance information with consistent formatting.
    
    Args:
        func_name: Name of the function/operation
        duration: Duration in seconds
        **context: Additional context to include in log
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
    """
    Log data operations with consistent formatting.
    
    Args:
        operation: Type of operation (fetch, transform, cache)
        source_type: Type of data source (csv, json, databricks, etc.)
        record_count: Number of records processed
        **context: Additional context
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
    """
    Log API operations with consistent formatting.
    
    Args:
        provider: API provider (openai, gemini, google_slides, etc.)
        operation: Type of operation (generate_text, upload_image, etc.)
        success: Whether operation succeeded
        duration: Duration in seconds
        **context: Additional context
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


# Default setup for when package is imported
setup_logging()