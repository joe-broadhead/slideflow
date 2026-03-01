"""Standard CLI error codes for automation-friendly failures."""

from typing import Dict, Type

from slideflow.utilities.exceptions import (
    AuthenticationError,
    ChartGenerationError,
    ConfigurationError,
    DataSourceError,
    RenderingError,
    SlideFlowError,
)


class CliErrorCode:
    """Stable error code strings used in command output."""

    BUILD_FAILED = "SLIDEFLOW_BUILD_FAILED"
    VALIDATE_FAILED = "SLIDEFLOW_VALIDATE_FAILED"
    DOCTOR_FAILED = "SLIDEFLOW_DOCTOR_FAILED"
    SHEETS_BUILD_FAILED = "SLIDEFLOW_SHEETS_BUILD_FAILED"
    SHEETS_VALIDATE_FAILED = "SLIDEFLOW_SHEETS_VALIDATE_FAILED"
    SHEETS_DOCTOR_FAILED = "SLIDEFLOW_SHEETS_DOCTOR_FAILED"

    CONFIGURATION = "SLIDEFLOW_CONFIG_ERROR"
    AUTHENTICATION = "SLIDEFLOW_AUTH_ERROR"
    DATA_SOURCE = "SLIDEFLOW_DATA_SOURCE_ERROR"
    RENDERING = "SLIDEFLOW_RENDER_ERROR"
    CHART_GENERATION = "SLIDEFLOW_CHART_ERROR"
    INTERNAL = "SLIDEFLOW_INTERNAL_ERROR"


_ERROR_CODE_BY_TYPE: Dict[Type[BaseException], str] = {
    ConfigurationError: CliErrorCode.CONFIGURATION,
    AuthenticationError: CliErrorCode.AUTHENTICATION,
    DataSourceError: CliErrorCode.DATA_SOURCE,
    ChartGenerationError: CliErrorCode.CHART_GENERATION,
    RenderingError: CliErrorCode.RENDERING,
    SlideFlowError: CliErrorCode.INTERNAL,
}


def resolve_cli_error_code(error: Exception, default: str) -> str:
    """Map an exception to the most specific CLI error code available."""
    for exception_type, error_code in _ERROR_CODE_BY_TYPE.items():
        if isinstance(error, exception_type):
            return error_code
    return default
