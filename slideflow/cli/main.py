"""Main CLI application setup and configuration.

This module configures the primary Typer application for Slideflow's command-line
interface. It sets up global options, logging configuration, and registers all
available commands. The CLI provides a consistent interface for all Slideflow
operations with proper error handling and user feedback.

The main function serves as a callback that:
    - Configures logging based on user preferences
    - Displays the banner and help when run without commands
    - Sets up the global application context

Commands are registered from the commands module to maintain separation of
concerns and modularity.

Example:
    This module is typically used as an entry point::

        $ python -m slideflow.cli.main
        $ slideflow build config.yaml
        $ slideflow --verbose validate config.yaml
"""

import warnings

# Suppress known noisy dependency warnings globally before any other imports happen.
# We use string-based filtering to catch them even if triggered during import.
warnings.filterwarnings("ignore", message=".*urllib3.*match a supported version.*")
warnings.filterwarnings("ignore", message=".*RequestsDependencyWarning.*")

import typer

from slideflow.cli.commands import (
    build_command,
    doctor_command,
    sheets_app,
    sheets_build_command,
    sheets_doctor_command,
    sheets_validate_command,
    validate_command,
)
from slideflow.cli.commands.templates import (
    templates_app,
    templates_info,
    templates_list,
)
from slideflow.cli.theme import print_help_footer, print_slideflow_banner
from slideflow.utilities.logging import setup_logging

app = typer.Typer(
    name="slideflow",
    help="🚀 Slideflow CLI - Generate beautiful presentations from your data",
    rich_markup_mode="rich",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose logging"
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress most output"),
):
    """Main CLI callback function for global configuration and help display.

    This callback function is executed before any subcommand and handles global
    CLI options that affect the entire application. It configures logging based
    on user preferences and displays the application banner when no specific
    command is provided.

    The function implements a logging hierarchy where debug takes precedence
    over verbose, and quiet suppresses most output except errors.

    Args:
        ctx: Typer context object containing command execution information.
            Used to determine if a subcommand was invoked.
        verbose: Enable verbose logging (INFO level). Shows detailed operational
            information including configuration loading and processing steps.
        debug: Enable debug logging (DEBUG level). Shows detailed internal
            information including API calls, data transformations, and
            detailed execution traces.
        quiet: Enable quiet mode (ERROR level only). Suppresses all output
            except critical errors. Useful for automated scripts and CI/CD.

    Raises:
        typer.Exit: Exits gracefully when no subcommand is provided after
            displaying the banner and help information.

    Example:
        Global options can be used with any command::

            $ slideflow --verbose build config.yaml
            $ slideflow --debug validate config.yaml
            $ slideflow --quiet build batch.yaml

    Note:
        - Logging configuration affects all subsequent operations
        - Debug mode provides the most detailed output for troubleshooting
        - Quiet mode is recommended for production automation
        - The banner is only shown when no subcommand is specified
    """
    # Configure logging based on options
    if quiet:
        log_level = "ERROR"
    elif debug:
        log_level = "DEBUG"
    elif verbose:
        log_level = "INFO"
    else:
        log_level = "WARNING"

    setup_logging(level=log_level, enable_debug=debug)

    if ctx.invoked_subcommand is None:
        print_slideflow_banner()
        print_help_footer()
        return


app.command("validate")(validate_command)
app.command("build")(build_command)
app.command("doctor")(doctor_command)
if hasattr(app, "add_typer"):
    app.add_typer(sheets_app, name="sheets")
    app.add_typer(templates_app, name="templates")
else:
    # Compatibility fallback for minimal Typer stubs used in tests.
    app.command("sheets-validate")(sheets_validate_command)
    app.command("sheets-build")(sheets_build_command)
    app.command("sheets-doctor")(sheets_doctor_command)
    app.command("templates-list")(templates_list)
    app.command("templates-info")(templates_info)

if __name__ == "__main__":
    app()
