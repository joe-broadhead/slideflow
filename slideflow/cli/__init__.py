"""Command-line interface for Slideflow.

This module provides the main entry point for the Slideflow CLI application,
which offers commands for building and validating presentations from YAML
configurations. The CLI is built using Typer and provides a user-friendly
interface with rich formatting, progress tracking, and comprehensive error
reporting.

The CLI includes:
    - build: Generate presentations from YAML configurations
    - validate: Validate configurations without building
    - Comprehensive help system and error reporting
    - Rich terminal output with colors and formatting
    - Progress tracking for long-running operations

Example:
    The CLI can be used directly from the command line:
    
    $ slideflow --help
    $ slideflow build config.yaml
    $ slideflow validate config.yaml --registry custom.py
    
    Or programmatically:
    
    >>> from slideflow.cli import app
    >>> # Use app as Typer application in other contexts

Attributes:
    app: The main Typer application instance for the CLI.
"""

from slideflow.cli.main import app

__all__ = ['app']
