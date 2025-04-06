from typing import List
from rich.table import Table
from rich.panel import Panel
from rich.console import Console

from slideflow.presentation.presentation import Presentation

def inject_params_into_model(presentation: Presentation, params: dict[str, str]) -> Presentation:
    """
    Applies parameter values into the presentation model, updating placeholders, chart configs,
    and replacement function arguments.

    Args:
        presentation (Presentation): The presentation object to update.
        params (dict[str, str]): Parameters to inject.

    Returns:
        Presentation: Updated presentation with parameters applied.
    """
    presentation.name = presentation.name.format(**params)

    for slide in presentation.slides:
        slide.context = params

        for chart in slide.charts:
            if chart.chart_config and hasattr(chart.chart_config, 'resolve_args'):
                chart.chart_config.resolve_args(params)

        for replacement in slide.replacements:
            if hasattr(replacement, 'resolve_args'):
                replacement.resolve_args(params)

    return presentation

def print_banner(console: Console) -> None:
    console.print("""
[bold blue]
  ____  _ _     _       __ _                
 / ___|| (_) __| | ___ / _| | _____      __ 
 \___ \| | |/ _` |/ _ \ |_| |/ _ \ \ /\ / / 
  ___) | | | (_| |  __/  _| | (_) \ V  V /  
 |____/|_|_|\__,_|\___|_| |_|\___/ \_/\_/   
            
            🚀 Slideflow CLI            
        Build. Automate. Present.  
[/bold blue]""")

def print_section(console: Console, title: str) -> None:
    console.rule(f'[bold yellow]{title}[/bold yellow]')

def print_success_table(console: Console, presentations: List[dict]) -> None:
    table = Table(
        title = '📊 [bold magenta]Built Presentations[/bold magenta]',
        show_lines = True,
        header_style = 'bold magenta'
    )
    table.add_column('📄 Name', style = 'bold blue')
    table.add_column('🔗 URL', style = 'bold blue')

    for pres in presentations:
        table.add_row(pres['name'], f"[link={pres['url']}]" + pres['url'] + "[/link]")

    console.print(Panel.fit(table, border_style = 'magenta'))

def print_error_panel(console: Console, msg: str) -> None:
    console.print(Panel.fit(f"❌ {msg}", title = '[red]Error[/red]', border_style = 'red'))

def print_warning_panel(console: Console, msg: str) -> None:
    console.print(Panel.fit(f'⚠️ {msg}', title = '[yellow]Warning[/yellow]', border_style = 'yellow'))

def print_success_message(console: Console, msg: str) -> None:
    console.print(f'\n[green]✅ {msg}[/green]')
