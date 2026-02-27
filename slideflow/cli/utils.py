"""Compatibility wrappers for CLI output helpers.

This module intentionally delegates to :mod:`slideflow.cli.theme` to keep a
single source of truth for CLI rendering behavior while preserving the legacy
`slideflow.cli.utils` import surface.
"""

from pathlib import Path

import slideflow.cli.theme as theme
from slideflow.presentations.config import PresentationConfig

# Backward-compatible alias for callers/tests that reference this module member.
console = theme.console


def print_validation_header(config_file: Path) -> None:
    """Render validation header via the shared theme implementation."""
    theme.print_validation_header(str(config_file))


def print_config_summary(presentation_config: PresentationConfig) -> None:
    """Render config summary via the shared theme implementation."""
    theme.print_config_summary(presentation_config)


def handle_validation_error(error: Exception, verbose: bool = False) -> None:
    """Render validation errors via the shared theme implementation."""
    theme.print_error(error, verbose=verbose)
