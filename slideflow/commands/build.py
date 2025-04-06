import time
import yaml
import typer
from rich import print
from pathlib import Path
from rich.console import Console
from pydantic import ValidationError, TypeAdapter

from slideflow.presentation.presentation import Presentation
from slideflow.utils.config_loader import build_services, resolve_functions
from slideflow.utils.registry_loader import load_function_registry, load_registry_from_entry_point
from slideflow.commands.utils import print_banner, print_error_panel, print_warning_panel, print_success_message

app = typer.Typer()
console = Console()

@app.callback()
def main(
    config_path: Path,
    registry: str = typer.Option(
        None,
        '--registry',
        help = 'Optional module path to a custom function registry (e.g. myproject.registry)'
    )
) -> None:
    """
    Builds the full presentation and uploads it to Google Slides.
    """
    print_banner(console)

    start_time = time.time()
    
    print(f'[bold blue]🛠 Building presentation from:[/bold blue] {config_path}')

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
        raw = yaml.safe_load(config_path.read_text())
        resolved_config = resolve_functions(raw, function_registry) | build_services()
        presentation_data = TypeAdapter(Presentation).validate_python(resolved_config)
    except ValidationError as e:
        msg = f'Invalid config: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)
    except Exception as e:
        f'Error loading config: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    try:
        result = presentation_data.copy_presentation()
        msg = f"Presentation copied: https://docs.google.com/presentation/d/{result['id']}"
        print_success_message(console, msg)
    except Exception as e:
        msg = f'Failed to copy template: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    try:
        presentation_data.process_slides(
            slides_service = presentation_data.slides_service,
            drive_service = presentation_data.drive_service
        )
        msg = f'Charts and replacements inserted'
        print_success_message(console, msg)
    except Exception as e:
        msg = f'Failed to process slides: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    try:
        presentation_data.share_presentation()
        msg = f'Presentation shared with users'
        print_success_message(console, msg)
    except Exception as e:
        msg = f'⚠️ Presentation built, but sharing failed: {e}'
        print_warning_panel(console, msg)
    
    end_time = time.time()
    duration = end_time - start_time
    formatted = f"{duration:.2f} seconds"
    
    msg = f'🎉 Build complete in {formatted}!'
    print_success_message(console, msg)
