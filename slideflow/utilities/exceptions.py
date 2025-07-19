"""Custom exception hierarchy for Slideflow.

This module defines a comprehensive exception hierarchy that provides structured
error handling throughout the Slideflow system. The hierarchy is designed to
enable specific error handling while maintaining clear inheritance relationships
for broader exception catching.

Exception Hierarchy:
    SlideFlowError (base)
    ├── ConfigurationError
    │   ├── TemplateError
    ├── DataSourceError
    ├── DataTransformError
    │   ├── DataValidationError
    ├── ProviderError
    │   ├── APIError
    │   │   ├── APIRateLimitError
    │   │   └── APIAuthenticationError
    ├── RenderingError
    │   ├── ChartGenerationError
    │   └── ReplacementError
    ├── AuthenticationError
    │   └── APIAuthenticationError
    └── ConcurrencyError

Design Principles:
    - Specific exceptions for targeted error handling
    - Inheritance allows catching at appropriate levels
    - Clear naming that indicates the error domain
    - Separation of concerns across system components

Example:
    Using the exception hierarchy for error handling:
    
    >>> from slideflow.utilities.exceptions import (
    ...     SlideFlowError, ConfigurationError, DataSourceError,
    ...     ChartGenerationError, APIRateLimitError
    ... )
    >>> 
    >>> try:
    ...     # Some Slideflow operation
    ...     result = presentation.render()
    ... except APIRateLimitError as e:
    ...     # Handle rate limiting specifically
    ...     print(f"Rate limited, retry after: {e}")
    ... except ChartGenerationError as e:
    ...     # Handle chart generation issues
    ...     print(f"Chart generation failed: {e}")
    ... except RenderingError as e:
    ...     # Handle other rendering issues
    ...     print(f"Rendering failed: {e}")
    ... except SlideFlowError as e:
    ...     # Handle any other Slideflow error
    ...     print(f"Slideflow operation failed: {e}")
    ... except Exception as e:
    ...     # Handle unexpected errors
    ...     print(f"Unexpected error: {e}")
"""

class SlideFlowError(Exception):
    """Base exception for all Slideflow errors.
    
    This is the root exception class that all Slideflow-specific exceptions
    inherit from. It allows for catching any Slideflow-related error while
    distinguishing them from system or library exceptions.
    
    Use this as a catch-all for any Slideflow operation that might fail,
    or as a base class when creating new custom exceptions for Slideflow.
    
    Example:
        >>> try:
        ...     slideflow_operation()
        ... except SlideFlowError as e:
        ...     logger.error(f"Slideflow operation failed: {e}")
        ...     # Handle Slideflow-specific error
        ... except Exception as e:
        ...     logger.error(f"Unexpected error: {e}")
        ...     # Handle other errors
    """
    pass

class ConfigurationError(SlideFlowError):
    """Raised when configuration loading, parsing, or validation fails.
    
    This exception covers errors in:
    - YAML configuration file parsing
    - Configuration validation and schema errors
    - Function registry loading issues
    - Parameter substitution failures
    - Invalid configuration values or structure
    
    Example:
        >>> try:
        ...     config = ConfigLoader(yaml_path=Path("invalid.yaml"))
        ... except ConfigurationError as e:
        ...     print(f"Configuration error: {e}")
    """
    pass

class DataSourceError(SlideFlowError):
    """Raised when data source operations fail.
    
    This exception covers errors in:
    - Database connection failures
    - File reading errors (CSV, JSON, etc.)
    - API data fetching issues
    - Data source authentication problems
    - Network connectivity issues for remote data sources
    
    Example:
        >>> try:
        ...     data = csv_source.fetch_data()
        ... except DataSourceError as e:
        ...     print(f"Failed to fetch data: {e}")
    """
    pass

class DataTransformError(SlideFlowError):
    """Raised when data transformation operations fail.
    
    This exception covers errors in:
    - Data transformation function execution
    - Data validation failures
    - Column or data type mismatches
    - Aggregation or calculation errors
    - Custom transformation function failures
    
    Example:
        >>> try:
        ...     result = apply_data_transforms(transforms, df)
        ... except DataTransformError as e:
        ...     print(f"Data transformation failed: {e}")
    """
    pass

class ProviderError(SlideFlowError):
    """Raised when provider operations fail.
    
    This exception covers errors in:
    - AI provider initialization or configuration
    - External service provider failures
    - Provider-specific operational errors
    - Service unavailability or downtime
    
    This is a base class for more specific provider errors.
    
    Example:
        >>> try:
        ...     result = ai_provider.generate_text(prompt)
        ... except ProviderError as e:
        ...     print(f"Provider operation failed: {e}")
    """
    pass

class RenderingError(SlideFlowError):
    """Raised when presentation rendering operations fail.
    
    This exception covers errors in:
    - Presentation creation or modification
    - Slide rendering and content generation
    - Template processing failures
    - Output format conversion errors
    - General presentation generation issues
    
    This is a base class for more specific rendering errors.
    
    Example:
        >>> try:
        ...     result = presentation.render()
        ... except RenderingError as e:
        ...     print(f"Presentation rendering failed: {e}")
    """
    pass

class AuthenticationError(SlideFlowError):
    """Raised when authentication with external services fails.
    
    This exception covers errors in:
    - Invalid API keys or credentials
    - OAuth token issues
    - Service account authentication failures
    - Permission or authorization errors
    - Expired credentials
    
    Example:
        >>> try:
        ...     provider = GoogleSlidesProvider(config)
        ... except AuthenticationError as e:
        ...     print(f"Authentication failed: {e}")
    """
    pass

class ChartGenerationError(RenderingError):
    """Raised when chart generation fails.
    
    This exception covers errors in:
    - Chart data processing issues
    - Visualization library errors
    - Chart configuration problems
    - Image generation or formatting failures
    - Chart positioning or sizing errors
    
    Example:
        >>> try:
        ...     chart_image = chart.generate_chart_image(df)
        ... except ChartGenerationError as e:
        ...     print(f"Chart generation failed: {e}")
    """
    pass

class ReplacementError(RenderingError):
    """Raised when text or content replacement fails.
    
    This exception covers errors in:
    - Text replacement function execution
    - AI text generation failures
    - Template placeholder resolution issues
    - Content formatting or conversion errors
    - Replacement validation failures
    
    Example:
        >>> try:
        ...     content = replacement.get_replacement()
        ... except ReplacementError as e:
        ...     print(f"Content replacement failed: {e}")
    """
    pass

class APIError(ProviderError):
    """Raised when external API operations fail.
    
    This exception covers errors in:
    - HTTP request failures
    - API response parsing errors
    - Service-specific error responses
    - Network connectivity issues
    - API endpoint unavailability
    
    This is a base class for more specific API errors.
    
    Example:
        >>> try:
        ...     response = api_client.make_request(endpoint, data)
        ... except APIError as e:
        ...     print(f"API request failed: {e}")
    """
    pass

class APIRateLimitError(APIError):
    """Raised when API rate limits are exceeded.
    
    This exception is raised when external APIs return rate limiting
    responses, indicating that the request frequency has exceeded
    the allowed limits. It often includes retry timing information.
    
    Example:
        >>> try:
        ...     result = api_client.generate_text(prompt)
        ... except APIRateLimitError as e:
        ...     print(f"Rate limited: {e}")
        ...     # Implement retry logic with backoff
    """
    pass

class APIAuthenticationError(AuthenticationError):
    """Raised when API authentication fails.
    
    This exception is raised when API requests fail due to authentication
    issues such as invalid API keys, expired tokens, or insufficient
    permissions for the requested operation.
    
    Example:
        >>> try:
        ...     client = OpenAIProvider(api_key="invalid_key")
        ...     result = client.generate_text(prompt)
        ... except APIAuthenticationError as e:
        ...     print(f"API authentication failed: {e}")
    """
    pass

class DataValidationError(DataTransformError):
    """Raised when data validation fails.
    
    This exception is raised when data doesn't meet expected validation
    criteria such as required columns, data types, value ranges, or
    business rules during transformation or processing.
    
    Example:
        >>> try:
        ...     validated_df = validate_data_schema(df, schema)
        ... except DataValidationError as e:
        ...     print(f"Data validation failed: {e}")
    """
    pass

class TemplateError(ConfigurationError):
    """Raised when template processing fails.
    
    This exception is raised when template engines (Jinja2, etc.) fail
    to process templates due to syntax errors, missing variables,
    or template rendering issues during configuration processing.
    
    Example:
        >>> try:
        ...     rendered = template_engine.render(template, context)
        ... except TemplateError as e:
        ...     print(f"Template processing failed: {e}")
    """
    pass

class ConcurrencyError(SlideFlowError):
    """Raised when concurrent operations fail.
    
    This exception is raised when errors occur in concurrent or parallel
    processing scenarios such as thread pool execution failures,
    concurrent data fetching issues, or resource contention problems.
    
    Example:
        >>> try:
        ...     results = executor.execute_concurrent_tasks(tasks)
        ... except ConcurrencyError as e:
        ...     print(f"Concurrent execution failed: {e}")
    """
    pass
