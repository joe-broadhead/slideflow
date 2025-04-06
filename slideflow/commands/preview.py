import yaml
import typer
import pandas as pd
from rich import print
from pathlib import Path
from typing import Optional
from rich.panel import Panel
from rich.table import Table
from rich.console import Console
from pydantic import ValidationError, TypeAdapter

from slideflow.presentation.presentation import Presentation
from slideflow.utils.config_loader import build_services, resolve_functions
from slideflow.utils.registry_loader import load_function_registry, load_registry_from_entry_point
from slideflow.commands.utils import print_banner, print_error_panel, print_success_message, inject_params_into_model

app = typer.Typer()
console = Console()

@app.command()
def main(
    config_path: Path = typer.Argument(..., help = 'Path to the base config file'),
    registry: Optional[str] = typer.Option(None, '--registry', help = 'Optional registry module path'),
    param_file: Optional[Path] = typer.Option(None, '--param-file', '-p', help = 'CSV of parameter rows'),
    limit: Optional[int] = typer.Option(None, '--limit', '-n', help = 'Limit number of previews')
) -> None:
    """
    Preview a single or multiple presentations from config.
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
        raw = yaml.safe_load(config_path.read_text())
        resolved = resolve_functions(raw, function_registry) | build_services()
        base_presentation = TypeAdapter(Presentation).validate_python(resolved)
    except ValidationError as e:
        msg = f'Invalid config: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)
    except Exception as e:
        msg = f'Error loading config: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    if param_file:
        if not param_file.exists():
            msg = f'Param file not found: {param_file}'
            print_error_panel(console, msg)
            raise typer.Exit(code = 1)

        try:
            df = pd.read_csv(param_file, dtype = str).fillna('')
        except Exception as e:
            msg = f'Failed to load param file: {e}'
            print_error_panel(console, msg)
            raise typer.Exit(code = 1)

        if limit:
            df = df.head(limit)

        print(f'[blue]🔍 Previewing {len(df)} presentations...[/blue]')
        for i, row in df.iterrows():
            params = row.to_dict()
            pres = inject_params_into_model(base_presentation.model_copy(deep = True), params)
            _preview_single(pres, title = f'📊 Preview {i+1}: {params}')
    else:
        _preview_single(base_presentation)

def _preview_single(presentation: Presentation, title: Optional[str] = None):
    print(Panel.fit(
        f'[bold blue]{presentation.name}[/bold blue]\n'
        f'[dim]Template ID:[/dim] {presentation.template_id}\n'
        f'[dim]Slides:[/dim] {len(presentation.slides)}',
        title = title or '📊 Presentation Preview'
    ))

    for i, slide in enumerate(presentation.slides, start=1):
        table = Table(show_header = True, header_style = 'bold blue')
        table.title = f'Slide {i}: {slide.slide_id}'
        table.add_column('Type', style = 'dim', width = 12)
        table.add_column('Name / Placeholder', style = 'bold')
        table.add_column('Source', style = 'bold')

        for chart in slide.charts:
            table.add_row('Chart', chart.name, chart.data_source.name)

        for replacement in slide.replacements:
            rtype = getattr(replacement, 'type', 'text')
            label = getattr(replacement, 'placeholder', '[unknown]') if rtype == 'text' else f'Table: {replacement.prefix}'
            source = replacement.data_source.name if replacement.data_source else '-'
            table.add_row(rtype.capitalize(), label, source)

        print(table)

    msg = f'Preview complete: {presentation.name}'
    print_success_message(console, msg)
