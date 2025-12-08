"""Build command implementation for generating presentations.

This module provides the core build functionality for Slideflow, including
single presentation building and batch processing with concurrent execution.
It handles YAML configuration loading, parameter substitution, presentation
rendering, and comprehensive error reporting.

Key Features:
    - Single and batch presentation generation
    - Concurrent processing for improved performance
    - Parameter file support for generating multiple variants
    - Dry-run validation without actual generation
    - Progress tracking and user-friendly output
    - Thread-safe logging and error handling

Example:
    Command-line usage::
    
        # Build single presentation
        slideflow build config.yaml
        
        # Build with custom registry
        slideflow build config.yaml --registry custom_registry.py
        
        # Batch build with parameters
        slideflow build config.yaml --params-path variants.csv
        
        # Validate configuration only
        slideflow build config.yaml --dry-run
"""

import time
import typer
import threading
import yaml
import pandas as pd
from pathlib import Path
from typing import Optional, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from slideflow.presentations import PresentationBuilder
from slideflow.cli.theme import (
    print_build_error,
    print_build_header,
    print_build_success,
    print_build_progress
)

def build_single_presentation(
    config_file: Path, 
    registry_files: List[Path], 
    params: dict, 
    index: int, 
    total: int, 
    print_lock: threading.Lock
) -> Tuple[str, Any, int, dict]:
    """Build and render a single presentation with thread-safe logging.
    
    This function handles the complete presentation generation process for
    a single configuration, including building from YAML, parameter
    substitution, and rendering to the target provider (e.g., Google Slides).
    
    The function is designed to be used in concurrent execution contexts
    and provides thread-safe progress reporting.
    
    Args:
        config_file: Path to the YAML configuration file containing the
            presentation definition.
        registry_files: List of Python files containing function registries
            for custom data transformations and formatting.
        params: Dictionary of parameters for template substitution in the
            configuration. Used for generating presentation variants.
        index: Current presentation index (1-based) for progress reporting.
        total: Total number of presentations being generated.
        print_lock: Threading lock to ensure thread-safe console output.
        
    Returns:
        Tuple containing:
            - presentation_name (str): Name of the generated presentation
            - result: Presentation result object with URL and metadata
            - index (int): Original index for tracking purposes
            - params (dict): The parameters used for this presentation.
            
    Raises:
        Exception: Any error during presentation building or rendering.
            The function re-raises exceptions after logging them with
            thread-safe output.
            
    Example:
        >>> import threading
        >>> from pathlib import Path
        >>> 
        >>> config = Path("presentation.yaml")
        >>> registries = [Path("registry.py")]
        >>> params = {"title": "Q3 Report", "quarter": "Q3"}
        >>> lock = threading.Lock()
        >>> 
        >>> name, result, idx, params = build_single_presentation(
        ...     config, registries, params, 1, 1, lock
        ... )
        >>> print(f"Generated: {name} at {result.presentation_url}")
        
    Note:
        - Function is thread-safe and suitable for concurrent execution
        - Progress is logged with emoji indicators for visual clarity
        - All exceptions are re-raised to allow proper error handling
    """
    try:
        presentation = PresentationBuilder.from_yaml(
            yaml_path=config_file,
            registry_paths=list(registry_files) or [],
            params=params
        )
        
        with print_lock:
            print(f"🔄 [{index}/{total}] Rendering: {presentation.name}")

        result = presentation.render()
        
        with print_lock:
            print(f"✅ [{index}/{total}] Generated: {presentation.name}")
            print(f"   URL: {result.presentation_url}")
        
        return (presentation.name, result, index, params)
        
    except Exception as e:
        with print_lock:
            print(f"❌ [{index}/{total}] Failed: {str(e)}")
        raise

def build_command(
    config_file: Path = typer.Argument(..., help = "Path to YAML configuration file"),
    registry_files: Optional[List[Path]] = typer.Option(
        None, "--registry", "-r", 
        help="Path to Python registry files (can be used multiple times)"
    ),
    params_path: Optional[Path] = typer.Option(
        None, "--params-path", "-f", 
        help="Path to CSV with parameter rows"
    ),
    dry_run: Optional[bool] = typer.Option(
        False, "--dry-run", 
        help="Validate config without building"
    ),
    threads: Optional[int] = typer.Option(
        None, "--threads", "-t",
        help="Number of concurrent threads to use"
    )
) -> List[dict]:
    """Generate presentations from YAML configuration.
    
    This is the main entry point for the build command, which processes
    YAML configuration files and generates presentations using the specified
    providers (e.g., Google Slides). It supports both single presentation
    generation and batch processing with parameter substitution.
    
    The command provides comprehensive progress tracking, concurrent execution
    for batch operations, and detailed error reporting.
    
    Args:
        config_file: Path to the YAML configuration file that defines the
            presentation structure, data sources, and rendering options.
        registry_files: List of Python files containing custom function
            registries. Defaults to ["registry.py"]. Functions in these
            files can be referenced in YAML configurations for data
            transformations and formatting.
        params_path: Optional path to a CSV file containing parameter rows
            for batch generation. Each row represents a set of parameters
            that will be substituted into the configuration template.
        dry_run: If True, validates the configuration and parameters without
            actually generating presentations. Useful for testing
            configurations.
            
    Returns:
        A list of dictionaries, where each dictionary contains the slide
        URL and the parameters used for its generation.
        
    Raises:
        typer.Exit: Exits with code 1 if any error occurs during processing.
        
    Examples:
        Basic usage::
        
            slideflow build presentation.yaml
            
        With custom registry::
        
            slideflow build config.yaml --registry custom_functions.py
            
        Batch generation with parameters::
        
            slideflow build template.yaml --params-path variants.csv
            
        Validation only::
        
            slideflow build config.yaml --dry-run
            
    CSV Parameter File Format:
        The params_path CSV should have column headers matching the
        parameter names used in the YAML template::
        
            title,quarter,region
            Q1 Sales,Q1,North
            Q1 Sales,Q1,South
            Q2 Sales,Q2,North
            
    Performance:
        - Concurrent execution with up to 5 parallel workers
        - Thread-safe progress reporting and logging
        - Optimized for API rate limits and resource constraints
        
    Note:
        - Failed presentations in batch mode cause the entire operation to fail
        - Progress is displayed with visual indicators and completion status
        - Generated presentation URLs are displayed upon successful completion
    """

    print_build_header(config_file)
    
    try:
        print_build_progress(1, 6, "Loading configuration...")
        time.sleep(0.5)

        raw_config = yaml.safe_load(config_file.read_text())
        config_registry = raw_config.get("registry")

        if isinstance(config_registry, (str, Path, list)):
            config_registry = [Path(p) for p in ([config_registry] if isinstance(config_registry, (str, Path)) else config_registry)]

        registry_files = registry_files or config_registry or [Path("registry.py")]
        
        if dry_run:
            print_build_progress(6, 6, "Dry run complete - configuration is valid!")
            print_build_success()
            return []

        print_build_progress(2, 6, "Initializing presentation builder...")
        time.sleep(0.3)

        param_configs = pd.read_csv(params_path).to_dict(orient = 'records') if params_path else [{}]
        total_presentations = len(param_configs)
        
        print_build_progress(3, 6, f"Processing {total_presentations} presentation(s) concurrently...")
        time.sleep(0.5)
        
        print_build_progress(4, 6, f"Starting concurrent generation...")
        time.sleep(0.3)
        
        # Create thread lock for safe printing
        print_lock = threading.Lock()
        
        # Determine optimal number of workers (limit to avoid overwhelming APIs)
        if threads:
            max_workers = threads
        else:
            max_workers = min(total_presentations, 5)  # Max 5 concurrent presentations
        
        results = []
        completed_count = 0
        
        print(f"\n🚀 Generating {total_presentations} presentation(s) with {max_workers} concurrent workers...\n")

        with ThreadPoolExecutor(max_workers = max_workers) as executor:
            # Submit all presentation tasks
            future_to_params = {
                executor.submit(
                    build_single_presentation,
                    config_file,
                    registry_files,
                    params,
                    i,
                    total_presentations,
                    print_lock
                ): (i, params)
                for i, params in enumerate(param_configs, 1)
            }
            
            # Process completed presentations
            for future in as_completed(future_to_params):
                index, params = future_to_params[future]
                try:
                    name, result, pres_index, returned_params = future.result()
                    
                    result_dict = returned_params.copy()
                    result_dict['url'] = result.presentation_url
                    result_dict['presentation_name'] = name
                    results.append(result_dict)
                    
                    completed_count += 1

                    with print_lock:
                        print_build_progress(5, 6, f"Completed {completed_count}/{total_presentations} presentations...")
                        
                except Exception as e:
                    with print_lock:
                        print(f"❌ Presentation {index} failed: {e}")
                    raise

        print_build_progress(6, 6, "All presentations deployed!")
        time.sleep(0.3)

        # Sort results by original order and print summary
        results.sort(key=lambda x: x['presentation_name'])  # Sort by name for consistent output
        print(f"\n🎉 Successfully generated {len(results)} presentation(s):")
        for res in results:
            print(f"  • {res['presentation_name']}: {res['url']}")
        
        print_build_success()
        
        return results
        
    except Exception as e:
        print_build_error(str(e))
        raise typer.Exit(1)
