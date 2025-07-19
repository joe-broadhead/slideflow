"""Command-line interface commands for Slideflow.

This module provides the implementation of all CLI commands available through
the slideflow command-line tool. Commands are built using the Typer framework
and provide the primary interface for users to interact with Slideflow
functionality.

Available Commands:
    validate: Validate YAML configuration files and registry modules
    build: Generate presentations from configuration files

Each command is implemented as a separate module with comprehensive error
handling, progress reporting, and user-friendly output formatting.

Example:
    Commands are accessed through the main CLI:
    
    $ slideflow validate config.yaml
    $ slideflow build config.yaml --params-path data.csv
    $ slideflow build config.yaml --dry-run
    
Usage:
    Commands can also be imported and used programmatically:
    
    >>> from slideflow.cli.commands import build_command, validate_command
    >>> # Use in custom scripts or applications
"""

from slideflow.cli.commands.build import build_command
from slideflow.cli.commands.validate import validate_command

__all__ = ['validate_command', 'build_command']
