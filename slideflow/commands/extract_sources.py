import yaml
import typer
import pandas as pd
from rich import print
from pathlib import Path
from rich.console import Console
from pydantic import TypeAdapter, ValidationError
from typing import Optional, Dict, Any, Literal, Callable

from slideflow.data.connectors.base import DataSourceConfig, get_data_connector
from slideflow.commands.utils import print_banner, print_error_panel, print_success_message

app = typer.Typer()
console = Console()

@app.command()
def run(
    config_path: Path = typer.Argument(..., help = 'Path to your YAML slide config'),
    output_dir: Optional[Path] = typer.Option(None, '--output-dir', '-o', help = 'Directory to save output files'),
    format: str = typer.Option('csv', '--format', '-f', help = 'csv, json, or parquet', case_sensitive = False),
    source: Optional[str] = typer.Option(None, '--source', '-s', help = 'Only extract one specific data source by name'),
) -> None:
    """
    Extracts all unique data sources from the slide config, or just one if --source is specified.
    """
    print_banner(console)
    
    if not config_path.exists():
        msg = f'Config file not found: {config_path}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    try:
        with config_path.open('r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        msg = f'Failed to parse YAML: {e}'
        print_error_panel(console, msg)
        raise typer.Exit(code = 1)

    sources: Dict[str, DataSourceConfig] = {}

    for slide in config.get('slides', []):
        for chart in slide.get('charts', []):
            maybe_add_source(chart.get('data_source'), sources)
        for replacement in slide.get('replacements', []):
            maybe_add_source(replacement.get('data_source'), sources)

    if source:
        if source not in sources:
            msg = f"Source '{source}' not found in config"
            print_error_panel(console, msg)
            raise typer.Exit(code = 1)
        sources = {source: sources[source]}

    print(f'[bold blue]🔍 Found {len(sources)} data source(s)[/bold blue]')

    for name, config in sources.items():
        print(f'[bold blue]📊 Fetching:[/bold blue] {name}')
        try:
            df = get_data_connector(config).fetch_data()
        except Exception as e:
            msg = f"⚠️  Failed to fetch '{name}': {e}"
            print_error_panel(console, msg)
            continue

        if output_dir:
            output_dir.mkdir(parents = True, exist_ok = True)
            file_path = output_dir / f'{name}.{format.lower()}'
            try:
                save_dataframe(df, file_path, format)
                msg = f'Saved {len(df)} rows to: {file_path}'
                print_success_message(console, msg)
            except Exception as e:
                msg = f"Failed to save '{name}': {e}"
                print_error_panel(console, msg)
        else:
            print(df.head(5).to_markdown())


def maybe_add_source(source_dict: Optional[Dict[str, Any]], sources: Dict[str, DataSourceConfig]) -> None:
    if not source_dict:
        return
    name = source_dict.get('name')
    if not name or name in sources:
        return
    try:
        sources[name] = TypeAdapter(DataSourceConfig).validate_python(source_dict)
    except ValidationError as e:
        msg = f"Invalid source config for '{name}': {e}"
        print_error_panel(console, msg)

def save_dataframe(
    df: pd.DataFrame,
    path: Path,
    fmt: Literal['csv', 'json', 'parquet']
) -> None:
    """
    Saves a DataFrame to a file in the given format.

    Args:
        df: The DataFrame to save.
        path: Full path to the output file (including extension).
        fmt: Output format: 'csv', 'json', or 'parquet'.

    Raises:
        ValueError: If the provided format is not supported.
    """

    save_funcs: dict[str, Callable[[], None]] = {
        'csv': lambda: df.to_csv(path, index = False),
        'json': lambda: df.to_json(path, orient = 'records', lines = True),
        'parquet': lambda: df.to_parquet(path, index = False),
    }

    fmt = fmt.lower()
    if fmt not in save_funcs:
        raise ValueError(
            f"Unsupported format: '{fmt}'. Supported formats are: {', '.join(save_funcs.keys())}"
        )

    path.parent.mkdir(parents = True, exist_ok = True)

    save_funcs[fmt]()
