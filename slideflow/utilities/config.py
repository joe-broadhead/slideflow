"""Configuration loading and template resolution system for Slideflow.

This module provides the ConfigLoader class and supporting functions for loading
YAML configuration files with advanced features including parameter substitution,
function registry resolution, and automatic package discovery of function registries.

The configuration system supports:
    - YAML file loading with validation
    - Parameter substitution using {param} syntax
    - Function registry loading from Python modules
    - Automatic discovery of function registries in packages
    - Template resolution with nested structures
    - Cached configuration parsing for performance

Key Features:
    - Recursive parameter substitution in nested structures
    - Function registry merging from multiple sources
    - Automatic package scanning for function registries
    - Safe YAML loading with error handling
    - Cached property for efficient repeated access

Example:
    Basic configuration loading:
    
    >>> from slideflow.utilities.config import ConfigLoader
    >>> from pathlib import Path
    >>> 
    >>> # config.yaml:
    >>> # name: "Report for {quarter}"
    >>> # data_source:
    >>> #   query: !func get_quarterly_data
    >>> #   params:
    >>> #     quarter: "{quarter}"
    >>> 
    >>> loader = ConfigLoader(
    ...     yaml_path=Path("config.yaml"),
    ...     registry_paths=[Path("functions.py")],
    ...     params={"quarter": "Q3"}
    ... )
    >>> config = loader.config
    >>> # Results in resolved configuration with functions and parameters
    
    Function registry usage:
    
    >>> # functions.py:
    >>> # def get_quarterly_data(quarter):
    >>> #     return f"SELECT * FROM sales WHERE quarter = '{quarter}'"
    >>> # 
    >>> # function_registry = {
    >>> #     "get_quarterly_data": get_quarterly_data
    >>> # }
"""

import re
import sys
import yaml
import pkgutil
import importlib.util
from pathlib import Path
from functools import cached_property
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, List, Mapping, Callable, Sequence

from slideflow.utilities.exceptions import ConfigurationError

def render_params(obj: Any, params: Mapping[str, str]) -> Any:
    """Recursively substitute parameters in nested data structures.
    
    This function traverses nested dictionaries, lists, and strings to perform
    parameter substitution using Python's str.format() method. It preserves
    double-brace syntax ({{...}}) for template engines while substituting
    single-brace parameters ({param}).
    
    The function handles:
    - Nested dictionaries and lists recursively
    - String formatting with parameter substitution
    - Preservation of template syntax (double braces)
    - Safe handling of missing parameters
    
    Args:
        obj: The data structure to process. Can be dict, list, string, or any value.
        params: Dictionary of parameter names to replacement values.
        
    Returns:
        Copy of the input object with parameter substitutions applied.
        
    Example:
        Basic parameter substitution:
        
        >>> data = {
        ...     "title": "Report for {quarter}",
        ...     "filters": [
        ...         {"column": "date", "value": "{start_date}"},
        ...         {"column": "region", "value": "{region}"}
        ...     ],
        ...     "template": "{{PLACEHOLDER}}"  # Preserved
        ... }
        >>> params = {"quarter": "Q3", "start_date": "2024-01-01", "region": "US"}
        >>> result = render_params(data, params)
        >>> # Result:
        >>> # {
        >>> #     "title": "Report for Q3",
        >>> #     "filters": [
        >>> #         {"column": "date", "value": "2024-01-01"},
        >>> #         {"column": "region", "value": "US"}
        >>> #     ],
        >>> #     "template": "{{PLACEHOLDER}}"  # Unchanged
        >>> # }
        
        Missing parameter handling:
        
        >>> data = {"title": "Report for {quarter}", "subtitle": "Data for {missing}"}
        >>> params = {"quarter": "Q3"}
        >>> result = render_params(data, params)
        >>> # Result: {"title": "Report for Q3", "subtitle": "Data for {missing}"}
        >>> # Missing parameters are left unchanged
    """
    if isinstance(obj, Mapping):
        return {k: render_params(v, params) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        return [render_params(v, params) for v in obj]
    if isinstance(obj, str):
        _DOUBLE_BRACE_RE = re.compile(r"{{.*?}}")
        if _DOUBLE_BRACE_RE.search(obj):
            return obj
        try:
            return obj.format(**params)
        except KeyError:
            return obj
    return obj

def load_registry_from_path(registry_path: Path) -> dict[str, Callable]:
    """Load a function registry from a Python file.
    
    This function dynamically imports a Python module and extracts its
    function_registry dictionary. The registry should contain mappings
    of string names to callable functions that can be used in YAML
    configuration files.
    
    The function handles:
    - Dynamic module loading from file paths
    - Proper module naming and package structure
    - Validation of registry format and content
    - Error handling for missing files or invalid registries
    
    Args:
        registry_path: Path to Python file containing function_registry.
            The file must define a module-level variable named
            'function_registry' of type dict[str, Callable].
            
    Returns:
        Dictionary mapping function names to callable objects.
        
    Raises:
        ConfigurationError: If the file doesn't exist, can't be imported,
            or doesn't contain a valid function_registry.
            
    Example:
        Registry file structure:
        
        >>> # functions.py:
        >>> def calculate_growth(current, previous):
        ...     return ((current - previous) / previous) * 100
        >>> 
        >>> def format_currency(amount, symbol="$"):
        ...     return f"{symbol}{amount:,.2f}"
        >>> 
        >>> function_registry = {
        ...     "calculate_growth": calculate_growth,
        ...     "format_currency": format_currency
        ... }
        
        Loading the registry:
        
        >>> from pathlib import Path
        >>> registry = load_registry_from_path(Path("functions.py"))
        >>> growth_func = registry["calculate_growth"]
        >>> result = growth_func(120, 100)  # Returns 20.0
    """
    path = registry_path.resolve()
    if not path.exists():
        raise ConfigurationError(f"Registry file not found: {path}")

    module_name = path.stem
    package = path.parent.name
    full_name = f"{package}.{module_name}"
    sys.path.insert(0, str(path.parent.parent))

    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = package
    spec.loader.exec_module(module)  # type: ignore

    registry = getattr(module, "function_registry", None)
    if not isinstance(registry, dict):
        raise ConfigurationError(f"`function_registry` must be a dict in {path}")
    return registry

def resolve_functions(obj: Any, registry: dict[str, Callable]) -> Any:
    """Recursively resolve function references in nested data structures.
    
    This function traverses nested dictionaries, lists, and values to replace
    string function names with actual callable objects from the registry.
    It's typically used after parameter substitution to resolve function
    references in YAML configurations.
    
    The function handles:
    - Nested dictionaries and lists recursively
    - String-to-function resolution using registry lookup
    - Preservation of non-function values
    - Safe handling of unknown function names
    
    Args:
        obj: The data structure to process. Can be dict, list, string, or any value.
        registry: Dictionary mapping function names to callable objects.
        
    Returns:
        Copy of the input object with function name strings replaced by
        actual callable objects where matches are found in the registry.
        
    Example:
        Function resolution in configuration:
        
        >>> def my_transform(df):
        ...     return df * 2
        >>> 
        >>> registry = {"my_transform": my_transform}
        >>> data = {
        ...     "charts": [
        ...         {
        ...             "type": "custom",
        ...             "chart_fn": "my_transform",  # Will be resolved
        ...             "title": "My Chart"          # Will remain string
        ...         }
        ...     ]
        ... }
        >>> result = resolve_functions(data, registry)
        >>> # result["charts"][0]["chart_fn"] is now the actual function
        >>> assert callable(result["charts"][0]["chart_fn"])
        
        Non-matching strings remain unchanged:
        
        >>> data = {"function": "unknown_function", "value": 42}
        >>> result = resolve_functions(data, {})
        >>> # Result: {"function": "unknown_function", "value": 42}
    """
    if isinstance(obj, Mapping):
        return {k: resolve_functions(v, registry) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, str):
        return [resolve_functions(v, registry) for v in obj]
    if isinstance(obj, str) and obj in registry:
        return registry[obj]
    return obj

def search_registries_in_package() -> dict[str, Callable]:
    """Automatically discover and merge function registries from package modules.
    
    This function performs automatic discovery of function registries by walking
    through all modules in the current package hierarchy. It imports each module
    and checks for a 'function_registry' variable, merging all found registries
    into a single dictionary.
    
    The discovery process:
    1. Determines the root package name from the current module
    2. Walks through all submodules using pkgutil.walk_packages
    3. Imports each module and looks for function_registry
    4. Merges all registries, with later discoveries overriding earlier ones
    
    This enables automatic registration of functions without explicit imports,
    supporting a plugin-like architecture where modules can contribute functions
    simply by defining a function_registry variable.
    
    Returns:
        Merged dictionary of all function registries found in the package.
        Returns empty dict if no registries are found or package detection fails.
        
    Example:
        Package structure with auto-discovery:
        
        >>> # slideflow/transforms/math.py:
        >>> def add_constant(df, value=1):
        ...     return df + value
        >>> 
        >>> function_registry = {"add_constant": add_constant}
        >>> 
        >>> # slideflow/transforms/text.py:
        >>> def uppercase_column(df, column):
        ...     df[column] = df[column].str.upper()
        ...     return df
        >>> 
        >>> function_registry = {"uppercase_column": uppercase_column}
        >>> 
        >>> # Usage:
        >>> merged_registry = search_registries_in_package()
        >>> # merged_registry contains both add_constant and uppercase_column
        
        Registry collision handling:
        
        >>> # If multiple modules define the same function name,
        >>> # the last one discovered wins (based on import order)
    """
    merged: dict[str, Callable] = {}

    pkg_name = __package__.split(".")[0] if __package__ else None
    if not pkg_name:
        return merged

    pkg = importlib.import_module(pkg_name)
    for finder, mod_name, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        reg = getattr(mod, "function_registry", None)
        if isinstance(reg, dict):
            merged.update(reg)
    return merged

class ConfigLoader(BaseModel):
    """Advanced configuration loader with template resolution and function registry support.
    
    This class provides a comprehensive configuration loading system that combines
    YAML parsing, parameter substitution, and function registry resolution into
    a single, cached interface. It's designed to handle complex configuration
    scenarios common in data processing and presentation generation.
    
    Key Features:
    - YAML file loading with safe parsing
    - Parameter substitution using {param} syntax
    - Function registry loading from multiple Python files
    - Automatic package discovery of function registries
    - Cached configuration parsing for performance
    - Recursive resolution of nested structures
    
    The configuration loading process follows these steps:
    1. Load raw YAML content from file
    2. Apply parameter substitution throughout the structure
    3. Discover and merge function registries from package and files
    4. Resolve function references in the configuration
    5. Cache the final result for subsequent access
    
    Attributes:
        yaml_path: Path to the YAML configuration file to load.
        registry_paths: List of Python files containing function registries.
        params: Dictionary of parameters for template substitution.
        
    Example:
        Complete configuration loading workflow:
        
        >>> from slideflow.utilities.config import ConfigLoader
        >>> from pathlib import Path
        >>> 
        >>> # config.yaml:
        >>> # name: "Report for {quarter} {year}"
        >>> # data_transforms:
        >>> #   - transform_fn: !func calculate_growth
        >>> #     transform_args:
        >>> #       baseline_quarter: "{baseline}"
        >>> # charts:
        >>> #   - type: custom
        >>> #     chart_fn: !func create_trend_chart
        >>> 
        >>> loader = ConfigLoader(
        ...     yaml_path=Path("config.yaml"),
        ...     registry_paths=[Path("custom_functions.py")],
        ...     params={
        ...         "quarter": "Q3",
        ...         "year": "2024",
        ...         "baseline": "Q2"
        ...     }
        ... )
        >>> 
        >>> # Access resolved configuration (cached after first access)
        >>> config = loader.config
        >>> # config now contains:
        >>> # - Substituted parameters
        >>> # - Resolved function references
        >>> # - All nested structures processed
        
        Performance considerations:
        
        >>> # First access parses and caches
        >>> config1 = loader.config  # YAML parsed, functions resolved
        >>> 
        >>> # Subsequent accesses use cache
        >>> config2 = loader.config  # Returns cached result
        >>> assert config1 is config2  # Same object reference
    """
    yaml_path: Path = Field(..., description = "YAML file to load")
    registry_paths: List[Path] = Field(
        ..., description = "One or more Python files defining `function_registry`"
    )
    params: Mapping[str, str] = Field(
        default_factory = dict,
        description = "Values for {param} substitution"
    )

    model_config = ConfigDict(
        arbitrary_types_allowed = True
    )

    @cached_property
    def config(self) -> Any:
        """Load and process the complete configuration with caching.
        
        This property orchestrates the entire configuration loading pipeline:
        1. Loads raw YAML content from the specified file
        2. Applies parameter substitution using the provided params
        3. Discovers function registries from the package
        4. Loads additional registries from specified registry_paths
        5. Resolves function references in the configuration
        6. Caches the result for subsequent access
        
        The processing is performed only once due to the @cached_property
        decorator, making repeated access efficient.
        
        Returns:
            Fully processed configuration object with parameters substituted
            and function references resolved. The return type depends on the
            YAML content structure.
            
        Raises:
            ConfigurationError: If YAML file cannot be read, contains invalid
                syntax, or function registries cannot be loaded.
            FileNotFoundError: If yaml_path or any registry_path doesn't exist.
            
        Example:
            Accessing the processed configuration:
            
            >>> loader = ConfigLoader(
            ...     yaml_path=Path("presentation.yaml"),
            ...     registry_paths=[Path("functions.py")],
            ...     params={"environment": "production"}
            ... )
            >>> 
            >>> # First access triggers full processing
            >>> config = loader.config
            >>> 
            >>> # Access configuration elements
            >>> presentation_name = config["presentation"]["name"]
            >>> chart_function = config["charts"][0]["chart_fn"]
            >>> 
            >>> # Function references are now callable
            >>> assert callable(chart_function)
        """
        raw = yaml.safe_load(self.yaml_path.read_text(encoding = "utf-8"))
        rendered = render_params(raw, self.params)

        merged_registry = search_registries_in_package()
        for path in self.registry_paths:
            reg = load_registry_from_path(path)
            merged_registry.update(reg)
        return resolve_functions(rendered, merged_registry)
