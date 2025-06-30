from pathlib import Path
from rich.panel import Panel
from rich.console import Console

from slideflow.presentations.config import PresentationConfig

console = Console()

def print_validation_header(config_file: Path) -> None:
    """Print a formatted header for validation operations."""
    console.print(Panel.fit(
        f"[bold blue]Slideflow Configuration Validator[/bold blue]\n"
        f"Validating: [cyan]{config_file}[/cyan]",
        border_style="blue"
    ))

def print_config_summary(presentation_config: PresentationConfig) -> None:
    """Print a summary of the validated configuration."""
    presentation = presentation_config.presentation
    slides_count = len(presentation.slides)
    
    console.print(f"\n[cyan]Summary:[/cyan]")
    console.print(f"  📄 Presentation: {presentation.name}")
    console.print(f"  📊 Slides: {slides_count}")

    data_source_types = set()
    data_sources_count = 0
    
    if hasattr(presentation_config, 'data_sources') and presentation_config.data_sources:
        data_sources_count += len(presentation_config.data_sources)
        for ds_config in presentation_config.data_sources.values():
            data_source_types.add(ds_config.type)
    
    for slide in presentation.slides:
        for replacement_spec in slide.replacements:
            # replacement_spec.config is a dict that may contain data_source
            if isinstance(replacement_spec.config, dict) and 'data_source' in replacement_spec.config:
                ds_config = replacement_spec.config['data_source']
                if ds_config and isinstance(ds_config, dict) and 'type' in ds_config:
                    data_sources_count += 1
                    data_source_types.add(ds_config['type'])
        
        for chart_spec in slide.charts:
            # chart_spec.config is a dict that may contain data_source
            if isinstance(chart_spec.config, dict) and 'data_source' in chart_spec.config:
                ds_config = chart_spec.config['data_source']
                if ds_config and isinstance(ds_config, dict) and 'type' in ds_config:
                    data_sources_count += 1
                    data_source_types.add(ds_config['type'])
    
    if data_sources_count > 0:
        console.print(f"  🗃️  Data sources: {data_sources_count}")
        if data_source_types:
            types_str = ", ".join(sorted(data_source_types))
            console.print(f"     Types: {types_str}")
    
    total_replacements = sum(len(slide.replacements) for slide in presentation.slides)
    total_charts = sum(len(slide.charts) for slide in presentation.slides)
    
    if total_replacements:
        console.print(f"  🔄 Replacements: {total_replacements}")
    if total_charts:
        console.print(f"  📈 Charts: {total_charts}")


def handle_validation_error(error: Exception, verbose: bool = False) -> None:
    """Handle and display validation errors consistently."""
    console.print(f"[red]❌ Validation failed:[/red]")
    if verbose:
        console.print(f"[red]{str(error)}[/red]")
    else:
        # Show first line of error only
        error_msg = str(error).split('\n')[0]
        console.print(f"[red]{error_msg}[/red]")
