import yaml
import typer
from rich import print
from pathlib import Path
from rich.console import Console
from pydantic import ValidationError, TypeAdapter

from slideflow.presentation.presentation import Presentation
from slideflow.utils.config_loader import build_services, resolve_functions
from slideflow.commands.utils import print_banner, print_error_panel, print_success_message
from slideflow.utils.registry_loader import load_function_registry, load_registry_from_entry_point

app = typer.Typer()
console = Console()

@app.callback()
def main(
    config_path: Path,
    registry: str = typer.Option(
        None,
        '--registry',
        help = 'Optional module path to a function registry (e.g. myproject.registry)'
    )
) -> None:
    """
    Validates the config file for correctness and structure.
    """
    print_banner(console)

    if not config_path.exists():
        msg = f'Config file not found: {config_path}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    if registry:
        try:
            function_registry = load_function_registry(registry)
        except Exception as e:
            msg = f"Failed to load registry '{registry}': {e}"
            print_error_panel(console, msg)
            raise typer.Exit(code = 1)
    else:
        try:
            function_registry = load_registry_from_entry_point('default')
        except Exception as e:
            msg = f'No --registry provided and failed to load default entry point: {e}'
            print_error_panel(console, msg)
            raise typer.Exit(code = 1)

    try:
        raw_config = yaml.safe_load(config_path.read_text())
        resolved_config = resolve_functions(raw_config, function_registry) | build_services()
        TypeAdapter(Presentation).validate_python(resolved_config)
    except ValidationError as e:
        msg = f'Validation failed with {len(e.errors())} error(s):'
        print_error_panel(console, msg)
        for err in e.errors():
            loc = ' → '.join(map(str, err['loc']))
            msg = err['msg']
            print(f'• [red]{loc}[/red]: {msg}')
        raise typer.Exit(code = 1)
    except Exception as e:
        msg = f'Failed to parse or resolve config: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    msg = f'Config is valid!'
    print_success_message(console, msg)
