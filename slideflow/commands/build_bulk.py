import time
import yaml
import typer
import pandas as pd
from rich import print
from pathlib import Path
from typing import Optional
from rich.console import Console
from pydantic import TypeAdapter, ValidationError
from concurrent.futures import ThreadPoolExecutor, as_completed

from slideflow.data.data_manager import DataManager
from slideflow.presentation.presentation import Presentation
from slideflow.utils.registry_loader import load_function_registry
from slideflow.utils.config_loader import build_services, resolve_functions
from slideflow.commands.utils import (
    print_banner,
    print_error_panel,
    print_warning_panel,
    print_success_table,
    print_success_message,
    inject_params_into_model,
    create_drive_subfolder,
    move_file_to_folder_id
)

app = typer.Typer()
console = Console()

def build_one_presentation(context: dict, base: Presentation, data_manager: DataManager, run_folder_id: str) -> dict:
    """
    Builds a single Google Slides presentation using a template and a given context.

    This function:
    - Injects context parameters into a deep copy of the base presentation
    - Copies the presentation from a template
    - Renders charts and replacements for each slide
    - Shares the final presentation with specified users
    - Moves the presentation to the designated run folder

    Args:
        context (dict): Dictionary of context variables (e.g., store_code) to inject into the presentation.
        base (Presentation): The base presentation template to copy and customize.
        data_manager (DataManager): Manager that provides data for charts and replacements.
        run_folder_id (str): The designated drive folder id for the run

    Returns:
        dict: A dictionary with:
            - 'success' (bool): Whether the operation succeeded
            - 'name' (str, optional): Name of the presentation (on success)
            - 'url' (str, optional): URL to the built presentation (on success)
            - 'context' (dict, optional): The context used (on failure)
            - 'error' (str, optional): Error message (on failure)
    """
    try:
        presentation = inject_params_into_model(base.model_copy(deep = True), context)
        presentation.copy_presentation()
        presentation.process_slides(
            slides_service = presentation.slides_service,
            drive_service = presentation.drive_service,
            data_manager = data_manager
        )

        presentation.share_presentation()

        if run_folder_id:
            move_file_to_folder_id(presentation.drive_service, presentation.presentation_id, run_folder_id)
            msg = f'Presentation {presentation.name} moved to folder: https://drive.google.com/drive/folders/{run_folder_id}'
            print_success_message(console, msg)
        return {'success': True, 'name': presentation.name, 'url': f"https://docs.google.com/presentation/d/{presentation.presentation_id}"}
    except Exception as e:
        return {'success': False, 'context': context, 'error': str(e)}

@app.command()
def run(
    config_path: Path = typer.Argument(..., help = 'Path to the base YAML config file'),
    param_file: Optional[Path] = typer.Option(None, '--param-file', '-f', help = 'CSV file with parameter rows'),
    registry: Optional[str] = typer.Option('registry.py', '--registry', help = 'Module path exposing a function_registry'),
    max_workers: int = typer.Option(5, '--max-workers', '-w', help = 'Number of threads to run in parallel'),
    root_folder_id: str = typer.Option(None, '--root-folder-id', help = 'Optional root Drive folder id to move the presentation into.'),
    run_folder_name: str = typer.Option(None, '--run-folder-name', help = 'Optional run Drive folder name to create and then move the presentation into.')
) -> None:
    """
    Builds the bulk presentations and uploads them to Google Slides using threading.
    """
    print_banner(console)

    start_time = time.time()
    
    print(f'[bold blue]🛠 Building presentations from:[/bold blue] {config_path}')

    if not config_path.exists():
        msg = f'Config file not found: {config_path}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    if Path(registry).exists():
        try:
            function_registry = load_function_registry(registry)
        except Exception as e:
            print_error_panel(console, f"Failed to load registry '{registry}': {e}")
            raise typer.Exit(code = 1)
    else:
        function_registry = {}

    try:
        raw = yaml.safe_load(config_path.read_text())
        resolved = resolve_functions(raw, function_registry) | build_services()
        base_presentation = TypeAdapter(Presentation).validate_python(resolved)
    except ValidationError as e:
        msg = f'[bold red]Invalid config:[/bold red] {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)
    except Exception as e:
        msg = f'Failed to resolve config: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    if not param_file or not param_file.exists():
        msg = f'Must provide --param-file with valid CSV'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    try:
        param_df = pd.read_csv(param_file, dtype = str).fillna('')
    except Exception as e:
        msg = f'Failed to read parameter file: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    param_list = param_df.to_dict(orient = 'records')
    print(f'[bold blue]🔁 Building {len(param_list)} presentations using {max_workers} threads...[/bold blue]')

    shared_data_manager = DataManager()

    try:
        if root_folder_id:
            if run_folder_name:
                run_folder_id = create_drive_subfolder(base_presentation.drive_service, run_folder_name, root_folder_id)
            else:
                run_folder_id = root_folder_id
        else:
            run_folder_id = root_folder_id
    except Exception as e:
        msg = f'⚠️ Presentation built, but moving directories failed: {e}'
        print_warning_panel(console, msg)
        run_folder_id = root_folder_id

    successes = []
    failures = []

    with ThreadPoolExecutor(max_workers = max_workers) as executor:
        futures = [executor.submit(build_one_presentation, row, base_presentation, shared_data_manager, run_folder_id) for row in param_list]
        for future in as_completed(futures):
            result = future.result()
            if result['success']:
                successes.append(result)
            else:
                failures.append(result)

    if successes:
        print_success_table(console, successes)

    if failures:
        msg = f'{len(failures)} presentations failed to build'
        print_error_panel(console, msg)
        for fail in failures:
            print(f"[red]• {fail['context']}[/red]: {fail['error']}")

    end_time = time.time()
    duration = end_time - start_time
    formatted = f"{duration:.2f} seconds"
    
    success_msg = f'🎉 {len(successes)}/{len(param_list)} presentations built successfully in {formatted}!'
    print_success_message(console, success_msg)
