import logging
from typing import List, Any
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from googleapiclient.errors import HttpError

from slideflow.presentation.presentation import Presentation

logger = logging.getLogger(__name__)

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

            if chart.data_source:
                if hasattr(chart.data_source, 'vars') and isinstance(chart.data_source.vars, dict):
                    chart.data_source.vars = replace_params(chart.data_source.vars, params)

        for replacement in slide.replacements:
            if hasattr(replacement, 'resolve_args'):
                replacement.resolve_args(params)
            
            if replacement.data_source:
                if hasattr(replacement.data_source, 'vars') and isinstance(replacement.data_source.vars, dict):
                    replacement.data_source.vars = replace_params(replacement.data_source.vars, params)

    return presentation

def replace_params(obj, params):
    if isinstance(obj, str):
        try:
            return obj.format(**params)
        except KeyError as e:
            print(f'⚠️ Missing parameter for string: {obj} — {e}')
    elif isinstance(obj, dict):
        return {k: replace_params(v, params) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_params(item, params) for item in obj]
    else:
        return obj

def print_banner(console: Console) -> None:
    console.print(r"""
[bold blue]
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

def create_drive_subfolder(
    drive_service: Any,
    name: str,
    parent_id: str
) -> str:
    """
    Creates a new folder with the specified name inside the given parent folder.

    Args:
        drive_service (Any): Authenticated Google Drive service instance.
        name (str): Name of the new folder to create.
        parent_id (str): ID of the parent folder.

    Returns:
        str: The ID of the newly created folder.

    Raises:
        HttpError: If an API call to Drive fails.
    """
    try:
        logger.info(f"Creating subfolder '{name}' under parent '{parent_id}'")

        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id],
        }
        file = drive_service.files().create(body = file_metadata, fields = 'id').execute()
        folder_id = file['id']

        logger.info(f"Created folder '{name}' with ID '{folder_id}'")
        return folder_id

    except HttpError as e:
        logger.error(f"Failed to create folder '{name}' under parent '{parent_id}': {e}")
        raise

def move_file_to_folder_id(
    drive_service: Any,
    file_id: str,
    folder_id: str
) -> None:
    try:
        file = drive_service.files().get(fileId = file_id, fields = 'parents').execute()
        previous_parents = ','.join(file.get('parents', []))

        drive_service.files().update(
            fileId = file_id,
            addParents = folder_id,
            removeParents = previous_parents,
            fields = 'id, parents'
        ).execute()

        logger.info(f"Moved file '{file_id}' into folder '{folder_id}'")

    except HttpError as e:
        logger.error(f"Error moving file '{file_id}' to folder '{folder_id}': {e}")
        raise
