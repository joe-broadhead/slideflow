"""CLI commands module."""

from slideflow.cli.commands.validate import validate_command
from slideflow.cli.commands.build import build_command

__all__ = ['validate_command', 'build_command']