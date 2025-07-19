"""CLI utility functions for Slideflow.

This module provides utility functions used by the CLI commands for common
operations like displaying validation headers, configuration summaries, and
error handling. These utilities complement the main theme module with simpler,
more focused functionality.

The utilities focus on:
    - Simple text output and formatting
    - Error handling and display
    - Configuration summary generation
    - Consistent message formatting

Note:
    This module appears to contain duplicate functionality with theme.py.
    The functions here may be legacy implementations that could be consolidated
    with the main theme system for consistency.

Example:
    >>> from slideflow.cli.utils import print_config_summary
    >>> print_config_summary(presentation_config)
"""

from pathlib import Path
from rich.panel import Panel
from rich.console import Console

from slideflow.presentations.config import PresentationConfig

console = Console()

def print_validation_header(config_file: Path) -> None:
    """Print a formatted header for validation operations.
    
    Displays a simple panel with the validation header and target file.
    This is an alternative to the main theme's validation header with
    a more minimal design.
    
    Args:
        config_file: Path to the configuration file being validated.
        
    Example:
        >>> print_validation_header(Path("config.yaml"))
        # Displays simple validation header panel
        
    Note:
        This function duplicates functionality in theme.py and may be
        consolidated in future versions.
    """
    console.print(Panel.fit(
        f"[bold blue]Slideflow Configuration Validator[/bold blue]\n"
        f"Validating: [cyan]{config_file}[/cyan]",
        border_style = "blue"
    ))

def print_config_summary(presentation_config: PresentationConfig) -> None:
    """Print a summary of the validated configuration.
    
    Displays a text-based summary of the presentation configuration including
    slide count, data sources, replacements, and charts. This provides a
    simpler alternative to the table-based summary in theme.py.
    
    Args:
        presentation_config: Validated PresentationConfig object containing
            the complete presentation structure and metadata.
            
    Example:
        >>> print_config_summary(config)
        # Displays:
        # Summary:
        #   📄 Presentation: Q3 Report
        #   📊 Slides: 5
        #   🗃️ Data sources: 3
        #      Types: csv, databricks
        #   🔄 Replacements: 12
        #   📈 Charts: 4
        
    Note:
        This function duplicates functionality in theme.py with a different
        format. Consider consolidating for consistency.
    """
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
    """Handle and display validation errors consistently.
    
    Provides standardized error formatting for validation failures.
    Can display either brief or detailed error information based on
    the verbose setting.
    
    Args:
        error: Exception that occurred during validation.
        verbose: If True, displays the complete error message including
            stack traces. If False, shows only the first line for brevity.
            
    Example:
        >>> try:
        ...     validate_config(config)
        ... except Exception as e:
        ...     handle_validation_error(e, verbose=True)
        
    Note:
        This function provides similar functionality to print_error in
        theme.py but with a different interface. Consider consolidating.
    """
    console.print(f"[red]❌ Validation failed:[/red]")
    if verbose:
        console.print(f"[red]{str(error)}[/red]")
    else:
        # Show first line of error only
        error_msg = str(error).split('\n')[0]
        console.print(f"[red]{error_msg}[/red]")
