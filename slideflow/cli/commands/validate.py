"""Validate command implementation for configuration validation.

This module provides the validation functionality for Slideflow YAML
configurations and registry files. It performs comprehensive syntax
and semantic validation without executing any presentation generation,
making it ideal for configuration testing and development workflows.

Key Features:
    - YAML syntax and structure validation
    - Function registry resolution and validation
    - Pydantic model validation for presentation configurations
    - Parameter substitution testing
    - Detailed error reporting with helpful messages
    - Configuration summary display

The validation process includes:
    1. YAML file parsing and syntax checking
    2. Registry file loading and function resolution
    3. Parameter template validation
    4. Pydantic model validation for type safety
    5. Cross-reference validation between configuration sections

Example:
    Command-line usage::
    
        # Validate basic configuration
        slideflow validate config.yaml
        
        # Validate with custom registries
        slideflow validate config.yaml --registry custom.py
        
        # Validate with multiple registries
        slideflow validate config.yaml -r reg1.py -r reg2.py
"""

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
    """Validate YAML configuration and registry files.
    
    Performs comprehensive validation of Slideflow configuration files
    including YAML syntax, function registry resolution, and semantic
    validation using Pydantic models. This command helps identify
    configuration issues before attempting to build presentations.
    
    The validation process includes:
        1. YAML file existence and readability checks
        2. YAML syntax validation
        3. Registry file loading and function resolution
        4. Parameter template processing
        5. Pydantic model validation for type safety
        6. Configuration completeness verification
    
    Args:
        config_file: Path to the YAML configuration file to validate.
            Must be a readable file with valid YAML syntax.
        registry_paths: List of Python files containing function registries.
            Defaults to ["registry.py"]. These files are loaded to resolve
            function references in the configuration.
            
    Raises:
        typer.Exit: Exits with code 1 if validation fails at any stage.
        
    Examples:
        Basic validation::
        
            slideflow validate presentation.yaml
            
        With custom registry::
        
            slideflow validate config.yaml --registry custom_functions.py
            
        Multiple registries::
        
            slideflow validate config.yaml -r base.py -r custom.py
            
    Validation Checks:
        - File existence and permissions
        - YAML syntax correctness
        - Registry file validity and function availability
        - Parameter reference resolution
        - Data source configuration validity
        - Presentation structure completeness
        - Provider configuration correctness
        
    Output:
        On success, displays:
            - Validation success message
            - Configuration summary with key details
            - Slide count and structure information
            
        On failure, displays:
            - Detailed error message indicating the issue
            - File and line information when applicable
            - Suggestions for fixing common problems
            
    Note:
        - Validation does not perform actual data fetching or API calls
        - Registry functions are resolved but not executed
        - Template parameters are validated for syntax, not content
        - This command is safe to run in CI/CD pipelines
    """

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
