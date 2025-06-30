import typer
from pathlib import Path
from typing import Optional, List

from slideflow.utilities import ConfigLoader
from slideflow.cli.theme import (
    print_validation_header,
    print_success,
    print_config_summary,
    print_error
)
from slideflow.presentations.config import PresentationConfig

def validate_command(
    config_file: Path = typer.Argument(..., help = "Path to YAML configuration file"),
    registry_paths: Optional[List[Path]] = typer.Option(
        ["registry.py"], "--registry", "-r", 
        help = "Path to Python registry files (can be used multiple times)"
    )
) -> None:

    print_validation_header(config_file)
    
    try:
        loader = ConfigLoader(
            yaml_path = config_file,
            registry_paths = list(registry_paths) if registry_paths else []
        )
    
        presentation_config = PresentationConfig(**loader.config)

        print_success()

        print_config_summary(presentation_config)
        
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)
