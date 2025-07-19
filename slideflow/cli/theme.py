"""Rich terminal theme and formatting for Slideflow CLI.

This module provides a comprehensive theming system for the Slideflow CLI using
the Rich library. It offers consistent, visually appealing output with color
coding, progress indicators, and structured displays for validation results,
build progress, and error reporting.

The theme system includes:
    - ASCII art banner with brand colors
    - Structured panels for different operation types
    - Progress bars with visual indicators
    - Color-coded status messages and errors
    - Formatted tables for configuration summaries
    - Consistent styling across all CLI output

All functions use the Rich library for terminal output with support for:
    - True color terminals
    - Fallback color schemes
    - Screen reader compatibility
    - Proper text formatting and alignment

Example:
    The theme functions are used throughout the CLI:
    
    >>> from slideflow.cli.theme import print_slideflow_banner
    >>> print_slideflow_banner()
    # Displays ASCII art banner
    
    >>> print_build_progress(3, 5, "Processing data...")
    # Shows progress bar at 60%
"""

from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from typing import Optional, Any

console = Console(force_terminal = True, color_system = "truecolor")

def print_slideflow_banner() -> None:
    """Display the Slideflow ASCII art banner with brand colors.
    
    Prints a stylized ASCII art logo with the Slideflow branding and tagline.
    Uses Rich markup for color styling with blue primary color and magenta
    accent color. The banner is displayed at the start of CLI operations
    to provide visual branding and user feedback.
    
    Example:
        >>> print_slideflow_banner()
        # Displays:
        #   ____  _ _     _       __ _                
        #  / ___|| (_) __| | ___ / _| | _____      __ 
        #  \___ \| | |/ _` |/ _ \ |_| |/ _ \ \ /\ / / 
        #   ___) | | | (_| |  __/  _| | (_) \ V  V /  
        #  |____/|_|_|\__,_|\___|_| |_|\___/ \_/\_/   
        #           Generate
        #       Beautiful slides.
        #         Direct from your data.
    
    Note:
        - Uses raw string to preserve ASCII art formatting
        - Colors automatically fallback on terminals with limited support
        - Banner is consistent across all CLI operations
    """
    console.print(r"""[bold blue]
  ____  _ _     _       __ _                
 / ___|| (_) __| | ___ / _| | _____      __ 
 \___ \| | |/ _` |/ _ \ |_| |/ _ \ \ /\ / / 
  ___) | | | (_| |  __/  _| | (_) \ V  V /  
 |____/|_|_|\__,_|\___|_| |_|\___/ \_/\_/   
[/bold blue][bold magenta]
         Generate
     Beautiful slides.
       Direct from your data.[/bold magenta]
""")

def print_validation_header(config_file: str) -> None:
    """Display validation operation header with file information.
    
    Shows the Slideflow banner followed by a styled panel indicating
    the start of a validation operation. The panel displays the target
    configuration file in a visually appealing format.
    
    Args:
        config_file: Path to the configuration file being validated.
            Can be absolute or relative path as a string.
            
    Example:
        >>> print_validation_header("config.yaml")
        # Displays banner and validation panel with file path
    """
    print_slideflow_banner()

    content = Text()
    content.append("🔍 Analyzing Config\n", style = "bold blue")
    content.append("━" * 40 + "\n", style = "magenta")
    content.append("File: ", style = "white")
    content.append(f"{config_file}", style = "bold blue")
    
    panel = Panel(
        content,
        title = "[bold magenta]⚡ SlideFlow Validator ⚡[/bold magenta]",
        border_style = "bold blue",
        padding = (1, 2)
    )
    
    console.print(panel)

def print_success() -> None:
    """Display validation success message.
    
    Shows a styled success message indicating that validation
    has completed successfully. Uses green checkmark and blue
    styling for positive visual feedback.
    """
    console.print("[bold blue]\nValidation Complete ✅[/bold blue]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")

def print_config_summary(presentation_config: Any) -> None:
    """Display detailed summary of validated configuration.
    
    Analyzes the presentation configuration and displays a comprehensive
    summary table showing slides, data sources, replacements, and charts.
    Provides visual confirmation of what will be built.
    
    Args:
        presentation_config: Validated PresentationConfig object containing
            the complete presentation structure and metadata.
            
    Example:
        >>> print_config_summary(config)
        # Displays formatted table with configuration details
    """
    presentation = presentation_config.presentation
    slides_count = len(presentation.slides)

    table = Table(
        title = "[bold magenta]📊 Overview[/bold magenta]",
        border_style = "bold blue",
        header_style = "bold blue"
    )
    
    table.add_column("Component", style = "white", no_wrap = True)
    table.add_column("Value", style = "bold magenta", justify = "right")
    table.add_column("Status", style = "green", justify = "center")

    table.add_row("📄 Presentation", presentation.name, "🟢 READY")
    table.add_row("📊 Slides", str(slides_count), "🟢 LOADED")

    data_source_types = set()
    data_sources_count = 0

    if hasattr(presentation_config, 'data_sources') and presentation_config.data_sources:
        data_sources_count += len(presentation_config.data_sources)
        for ds_config in presentation_config.data_sources.values():
            data_source_types.add(ds_config.type)
    
    for slide in presentation.slides:
        for replacement_spec in slide.replacements:
            if isinstance(replacement_spec.config, dict) and 'data_source' in replacement_spec.config:
                ds_config = replacement_spec.config['data_source']
                if ds_config and isinstance(ds_config, dict) and 'type' in ds_config:
                    data_sources_count += 1
                    data_source_types.add(ds_config['type'])
        
        for chart_spec in slide.charts:
            if isinstance(chart_spec.config, dict) and 'data_source' in chart_spec.config:
                ds_config = chart_spec.config['data_source']
                if ds_config and isinstance(ds_config, dict) and 'type' in ds_config:
                    data_sources_count += 1
                    data_source_types.add(ds_config['type'])
    
    if data_sources_count > 0:
        types_str = ", ".join(sorted(data_source_types)).upper()
        table.add_row("🗃️  Data Sources", str(data_sources_count), "🟢 Linked")
        table.add_row("   └─ Types", types_str, "🔗 Active")

    total_replacements = sum(len(slide.replacements) for slide in presentation.slides)
    total_charts = sum(len(slide.charts) for slide in presentation.slides)
    
    if total_replacements:
        table.add_row("🔄 Replacements", str(total_replacements), "⚡ Powered")
    if total_charts:
        table.add_row("📈 Charts", str(total_charts), "🎨 Rendered")
    
    console.print(table)

    console.print("[magenta]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/magenta]")
    console.print("[bold blue]🚀 Ready To Build![/bold blue] [magenta]✨ Config is Valid ✨[/magenta]")

def print_error(error_msg: Any, verbose: bool = False) -> None:
    console.print("[bold red]❌ Validation Faliled[/bold red]")
    console.print("[red]━━━━━━━━━━━━━━━━━━━━━━━[/red]")
    console.print("[bold yellow]🚨 Error Detected:[/bold yellow]")
    
    if verbose:
        console.print(f"[red]{error_msg}[/red]")
    else:
        first_line = str(error_msg).split('\n')[0]
        console.print(f"[red]{first_line}[/red]")
    
    console.print("[red]━━━━━━━━━━━━━━━━━━━━━━━[/red]")

def print_build_header(config_file: str) -> None:
    print_slideflow_banner()

    content = Text()
    content.append("🚀 Initiating Build\n", style = "bold blue")
    content.append("━" * 40 + "\n", style = "magenta")
    content.append("File: ", style = "white")
    content.append(f"{config_file}", style = "bold blue")
    
    panel = Panel(
        content,
        title = "[bold magenta]⚡ SlideFlow Builder ⚡[/bold magenta]",
        border_style = "bold blue",
        padding = (1, 2)
    )
    
    console.print(panel)

def print_build_progress(step: int, total_steps: int, message: str) -> None:
    """Display build progress with visual progress bar.
    
    Shows the current step in a multi-step build process with a visual
    progress bar and percentage completion. Uses block characters to
    create an ASCII progress bar that works in all terminals.
    
    Args:
        step: Current step number (1-based).
        total_steps: Total number of steps in the process.
        message: Descriptive message for the current step.
        
    Example:
        >>> print_build_progress(3, 5, "Processing data...")
        # Displays: ⚡ Processing data...
        #          ▪ [███░░] 60%
    """
    progress_bar = "█" * step + "░" * (total_steps - step)
    percentage = int((step / total_steps) * 100)
    
    console.print(f"[magenta]⚡[/magenta] [bold blue]{message}[/bold blue]")
    console.print(f"[magenta]▪[/magenta] [magenta][{progress_bar}][/magenta] [bold blue]{percentage}%[/bold blue]")

def print_build_success(presentation_url: Optional[str] = None) -> None:
    """Display build completion success message.
    
    Shows a celebratory message indicating successful completion of the
    build process. Optionally displays the presentation URL if provided.
    
    Args:
        presentation_url: Optional URL to the generated presentation.
            If provided, displays the URL prominently for easy access.
            
    Example:
        >>> print_build_success("https://docs.google.com/presentation/d/abc123")
        # Displays success message with URL
        
        >>> print_build_success()
        # Displays success message without URL
    """
    
    if presentation_url:
        console.print(f"\n[bold blue]📡 Presentation URL:[/bold blue]")
        console.print(f"[bold magenta]\n{presentation_url}[/bold magenta]")
    
    console.print("\n[magenta]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/magenta]")
    console.print("[bold blue]🚀 Build Complete[/bold blue] [magenta]✨ Ready for presentation ✨\n[/magenta]")

def print_build_error(error_msg: Any, verbose: bool = False) -> None:
    """Display build failure error message.
    
    Shows a styled error message when build operations fail. Can display
    either the full error message or just the first line depending on
    the verbose setting.
    
    Args:
        error_msg: Error message or exception to display. Can be string
            or any object that converts to string.
        verbose: If True, displays the complete error message including
            stack traces. If False, shows only the first line for brevity.
            
    Example:
        >>> print_build_error("Configuration file not found")
        # Displays concise error message
        
        >>> print_build_error(exception, verbose=True)
        # Displays full error details
    """
    console.print("[bold red]💥 Build Failed[/bold red]")
    console.print("[red]━━━━━━━━━━━━━━━━━━━━━━━[/red]")
    console.print("[bold yellow]🚨 Error Detected:[/bold yellow]")
    
    if verbose:
        console.print(f"[red]{error_msg}[/red]")
    else:
        # Show first line only
        first_line = str(error_msg).split('\n')[0]
        console.print(f"[red]{first_line}[/red]")
    
    console.print("[red]━━━━━━━━━━━━━━━━━━━━━━━[/red]")

def print_help_footer() -> None:
    """Display help footer with support information.
    
    Shows styled footer with links to documentation and support resources.
    Displayed when users run the CLI without specific commands to provide
    guidance on getting help.
    
    Example:
        >>> print_help_footer()
        # Displays:
        # ⚡ Need help? Check the docs or run with --verbose for more details ⚡
        # 🌐 slideflow.dev | 📧 support@slideflow.dev
    """
    console.print("""
[dim cyan]⚡ Need help? Check the docs ⚡[/dim cyan]
""")
