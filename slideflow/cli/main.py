import typer
from slideflow.cli.commands import validate_command, build_command
from slideflow.cli.theme import print_slideflow_banner, print_help_footer
from slideflow.utilities.logging import setup_logging

app = typer.Typer(
    name = "slideflow",
    help = "🚀 Slideflow CLI - Generate beautiful presentations from your data",
    rich_markup_mode = "rich",
    no_args_is_help = False
)

@app.callback(invoke_without_command = True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress most output")
):
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
        raise typer.Exit()

app.command("validate")(validate_command)
app.command("build")(build_command)

if __name__ == "__main__":
    app()
