"""Custom exception hierarchy for SlideFlow."""

class SlideFlowError(Exception):
    """Base exception for all SlideFlow errors."""
    pass


class ConfigurationError(SlideFlowError):
    """Raised when there are configuration or validation errors."""
    pass


class DataSourceError(SlideFlowError):
    """Raised when data source operations fail."""
    pass


class DataTransformError(SlideFlowError):
    """Raised when data transformation operations fail."""
    pass


class ProviderError(SlideFlowError):
    """Raised when AI provider operations fail."""
    pass


class RenderingError(SlideFlowError):
    """Raised when presentation rendering operations fail."""
    pass


class AuthenticationError(SlideFlowError):
    """Raised when authentication with external services fails."""
    pass


class ChartGenerationError(RenderingError):
    """Raised when chart generation fails."""
    pass


class ReplacementError(RenderingError):
    """Raised when text/content replacement fails."""
    pass


class APIError(ProviderError):
    """Raised when external API operations fail."""
    pass


class APIRateLimitError(APIError):
    """Raised when API rate limits are exceeded."""
    pass


class APIAuthenticationError(AuthenticationError):
    """Raised when API authentication fails."""
    pass


class DataValidationError(DataTransformError):
    """Raised when data validation fails."""
    pass


class TemplateError(ConfigurationError):
    """Raised when template processing fails."""
    pass


class ConcurrencyError(SlideFlowError):
    """Raised when concurrent operations fail."""
    pass