from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from typing import Optional, Any

console = Console(force_terminal = True, color_system = "truecolor")

def print_slideflow_banner() -> None:
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
    console.print("[bold blue]\nValidation Complete ✅[/bold blue]")
    console.print("[bold blue]━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]")

def print_config_summary(presentation_config: Any) -> None:  
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
    progress_bar = "█" * step + "░" * (total_steps - step)
    percentage = int((step / total_steps) * 100)
    
    console.print(f"[magenta]⚡[/magenta] [bold blue]{message}[/bold blue]")
    console.print(f"[magenta]▪[/magenta] [magenta][{progress_bar}][/magenta] [bold blue]{percentage}%[/bold blue]")


def print_build_success(presentation_url: Optional[str] = None) -> None:
    console.print("\n[bold blue]🎉 Build Complete[/bold blue]")
    console.print("[magenta]━━━━━━━━━━━━━━━━━━━━━━━[/magenta]")
    
    if presentation_url:
        console.print(f"\n[bold blue]📡 Presentation URL:[/bold blue]")
        console.print(f"[bold magenta]\n{presentation_url}[/bold magenta]")
    
    console.print("\n[magenta]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/magenta]")
    console.print("[bold blue]🚀 Build Complete[/bold blue] [magenta]✨ Ready for presentation ✨\n[/magenta]")


def print_build_error(error_msg: Any, verbose: bool = False) -> None:
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
    console.print("""
[dim cyan]⚡ Need help? Check the docs or run with --verbose for more details ⚡[/dim cyan]
[bold magenta]🌐 slideflow.dev | 📧 support@slideflow.dev[/bold magenta]
""")
