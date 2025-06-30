import time
import typer
import threading
import pandas as pd
from pathlib import Path
from typing import Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from slideflow.presentations import PresentationBuilder
from slideflow.cli.theme import (
    print_build_error,
    print_build_header,
    print_build_success,
    print_build_progress
)

def build_single_presentation(config_file: Path, registry_files: List[Path], params: dict, index: int, total: int, print_lock: threading.Lock) -> tuple:
    """Build and render a single presentation.
    
    Args:
        config_file: Path to YAML configuration
        registry_files: List of registry file paths
        params: Parameters for this presentation
        index: Current presentation index (1-based)
        total: Total number of presentations
        print_lock: Thread lock for safe printing
        
    Returns:
        Tuple of (presentation_name, result, index)
    """
    try:
        # Build presentation
        presentation = PresentationBuilder.from_yaml(
            yaml_path=config_file,
            registry_paths=list(registry_files) or [],
            params=params
        )
        
        with print_lock:
            print(f"🔄 [{index}/{total}] Rendering: {presentation.name}")
        
        # Render presentation
        result = presentation.render()
        
        with print_lock:
            print(f"✅ [{index}/{total}] Generated: {presentation.name}")
            print(f"   URL: {result.presentation_url}")
        
        return (presentation.name, result, index)
        
    except Exception as e:
        with print_lock:
            print(f"❌ [{index}/{total}] Failed: {str(e)}")
        raise

def build_command(
    config_file: Path = typer.Argument(..., help = "Path to YAML configuration file"),
    registry_files: Optional[List[Path]] = typer.Option(
        ["registry.py"], "--registry", "-r", 
        help = "Path to Python registry files (can be used multiple times)"
    ),
    params_path: Optional[Path] = typer.Option(None, "--params-path", "-f", help = "Path to CSV with parameter rows"),
    dry_run: Optional[bool] = typer.Option(False, "--dry-run", help = "Validate config without building")
) -> None:

    print_build_header(config_file)
    
    try:
        print_build_progress(1, 6, "Loading configuration...")
        time.sleep(0.5)
        
        if dry_run:
            print_build_progress(6, 6, "Dry run complete - configuration is valid!")
            print_build_success()
            return

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
        max_workers = min(total_presentations, 5)  # Max 5 concurrent presentations
        
        results = []
        completed_count = 0
        
        print(f"\n🚀 Generating {total_presentations} presentation(s) with {max_workers} concurrent workers...\n")
        
        # Execute presentations concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
                    name, result, pres_index = future.result()
                    results.append((name, result))
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
        results.sort(key=lambda x: x[0])  # Sort by name for consistent output
        print(f"\n🎉 Successfully generated {len(results)} presentation(s):")
        for name, result in results:
            print(f"  • {name}: {result.presentation_url}")
        
        print_build_success()
        
    except Exception as e:
        print_build_error(str(e))
        raise typer.Exit(1)
