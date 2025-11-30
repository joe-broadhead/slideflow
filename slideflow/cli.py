#!/usr/bin/env python3
"""Slideflow CLI entry point and command-line interface.

This module provides the main entry point for the Slideflow command-line interface,
enabling users to interact with Slideflow functionality through terminal commands.
The CLI provides access to presentation generation, data processing, and other
Slideflow operations through a command-line interface.

The CLI interface is built using a modular architecture that delegates actual
command implementations to the slideflow.cli.main module, keeping this entry
point simple and focused on bootstrapping the application.

Key Features:
    - Command-line access to all Slideflow functionality
    - Presentation generation from configuration files
    - Data source management and testing
    - Interactive configuration and setup
    - Batch processing capabilities
    - Integration with CI/CD pipelines

Usage:
    The CLI can be invoked directly as a Python module or through installed
    command-line tools. Common usage patterns include:
    
    Direct module execution:
    ```bash
    python -m slideflow.cli --help
    python -m slideflow.cli generate presentation.yaml
    python -m slideflow.cli test-data csv_source.json
    ```
    
    Installed command (if setuptools entry point is configured):
    ```bash
    slideflow --help
    slideflow generate presentation.yaml
    slideflow test-data csv_source.json
    ```

Architecture:
    This module serves as a thin wrapper around the main CLI application
    defined in slideflow.cli.main. The separation allows for:
    - Clean entry point definition
    - Easier testing and mocking of CLI functionality
    - Modular organization of CLI commands and features
    - Flexibility in CLI framework implementation

Example:
    Running the CLI programmatically:
    
    >>> from slideflow.cli import app
    >>> # Note: This would typically be called from command line
    >>> # app(['generate', 'config.yaml'])  # Example command
    
    The actual CLI commands and their implementations are defined in
    the slideflow.cli.main module and related submodules.
"""

from slideflow.cli.main import app

if __name__ == "__main__":
    try:
        app()
    except SystemExit as e:
        if e.code != 0:
            raise
