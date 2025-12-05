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

import typer
from slideflow.utilities.logging import setup_logging
from slideflow.cli.commands import validate_command, build_command
from slideflow.cli.theme import print_slideflow_banner, print_help_footer

app = typer.Typer(
    name = "slideflow",
    help = "🚀 Slideflow CLI - Generate beautiful presentations from your data",
    rich_markup_mode = "rich",
    no_args_is_help = False
)

@app.callback(invoke_without_command = True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help = "Enable verbose logging"),
    debug: bool = typer.Option(False, "--debug", help = "Enable debug logging"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help = "Suppress most output")
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
    
    setup_logging(level = log_level, enable_debug = debug)
    
    if ctx.invoked_subcommand is None:
        print_slideflow_banner()
        print_help_footer()
        return

app.command("validate")(validate_command)
app.command("build")(build_command)

if __name__ == "__main__":
    app()
