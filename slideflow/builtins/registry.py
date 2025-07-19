"""Registry for built-in Slideflow functions.

This module provides a centralized registry for all built-in functions that can be
used in Slideflow configurations and custom code. It leverages the standardized
registry system from slideflow.core.registry to provide consistent function
discovery, registration, and access patterns.

The registry includes functions for:
    - Table formatting and color mapping
    - Column-level data transformations
    - Number and currency formatting
    - Percentage and rounding operations

Key Features:
    - Automatic function discovery from builtins modules
    - Dynamic registration of custom functions
    - Integration with YAML configuration system
    - Type-safe function retrieval

Example:
    Using the registry in Python::
    
        from slideflow.builtins.registry import (
            builtin_function_registry,
            get_builtin_function,
            list_builtin_functions
        )
        
        # List available functions
        functions = list_builtin_functions()
        print(f"Available: {functions}")
        
        # Get a specific function
        color_func = get_builtin_function('create_dynamic_colors')
        styled_df = color_func(df, 'category')
        
        # Register a custom function
        def custom_transform(df):
            return df.transform(lambda x: x * 2)
            
        register_builtin_function('double_values', custom_transform)
        
    Using in YAML configuration::
    
        data_transforms:
          - function: abbreviate_number_columns
            columns: ['revenue', 'costs']
          - function: create_dynamic_colors
            column: 'category'

Attributes:
    builtin_function_registry: The global registry instance containing all
        built-in functions.
"""

from slideflow.core.registry import create_function_registry
from slideflow.builtins.table_utils import (
    create_dynamic_colors,
    create_growth_colors, 
    create_performance_colors,
    growth_color_function,
    performance_color_function,
    create_traffic_light_colors
)

from slideflow.builtins.column_utils import (
    abbreviate_number_columns,
    abbreviate_currency_columns,
    format_percentages,
    round_numbers
)

builtin_function_registry = create_function_registry("builtin_functions")

builtin_function_registry.register_function('create_dynamic_colors', create_dynamic_colors)
builtin_function_registry.register_function('create_growth_colors', create_growth_colors)
builtin_function_registry.register_function('create_performance_colors', create_performance_colors)
builtin_function_registry.register_function('growth_color_function', growth_color_function)
builtin_function_registry.register_function('performance_color_function', performance_color_function)
builtin_function_registry.register_function('create_traffic_light_colors', create_traffic_light_colors)
builtin_function_registry.register_function('abbreviate_number_columns', abbreviate_number_columns)
builtin_function_registry.register_function('abbreviate_currency_columns', abbreviate_currency_columns)
builtin_function_registry.register_function('format_percentages', format_percentages)
builtin_function_registry.register_function('round_numbers', round_numbers)

def get_builtin_function(name: str):
    """Retrieve a built-in function by its registered name.
    
    This function provides a convenient way to access built-in functions
    from the registry using their string identifiers. It's particularly
    useful when functions need to be selected dynamically based on
    configuration or user input.
    
    Args:
        name: The registered name of the function to retrieve.
            Case-sensitive. Must match the exact registration name.
            
    Returns:
        The callable function object if found, None if the function
        name is not registered.
        
    Example:
        >>> # Get the dynamic colors function
        >>> color_func = get_builtin_function('create_dynamic_colors')
        >>> if color_func:
        ...     styled_df = color_func(df, 'category_column')
        >>> 
        >>> # Get abbreviation function
        >>> abbrev_func = get_builtin_function('abbreviate_number_columns')
        >>> if abbrev_func:
        ...     df = abbrev_func(df, ['revenue', 'costs'])
        
    Note:
        - Returns None rather than raising an exception for missing functions
        - Function names are case-sensitive
        - Use list_builtin_functions() to see all available function names
    """
    return builtin_function_registry.get(name)

def register_builtin_function(name: str, func, overwrite: bool = False) -> None:
    """Register a new function in the built-in registry.
    
    Allows dynamic registration of custom functions to the built-in registry,
    making them available for use in YAML configurations and throughout the
    Slideflow system. This is useful for extending Slideflow with
    project-specific utilities.
    
    Args:
        name: Unique identifier for the function. This name will be used
            to retrieve the function later. Should be descriptive and
            follow naming conventions (lowercase_with_underscores).
        func: The callable function to register. Should be a pure function
            that accepts appropriate arguments for its intended use.
        overwrite: If True, allows replacing an existing function with the
            same name. If False (default), raises an error when attempting
            to register a duplicate name.
            
    Raises:
        ValueError: If a function with the same name already exists and
            overwrite=False.
        TypeError: If func is not callable.
        
    Example:
        >>> # Register a custom formatting function
        >>> def format_with_prefix(value, prefix="Value: "):
        ...     return f"{prefix}{value}"
        >>> 
        >>> register_builtin_function('format_with_prefix', format_with_prefix)
        >>> 
        >>> # Register a DataFrame transformation
        >>> def add_computed_column(df, source_col, target_col, multiplier=1.0):
        ...     df[target_col] = df[source_col] * multiplier
        ...     return df
        >>> 
        >>> register_builtin_function('add_computed_column', add_computed_column)
        >>> 
        >>> # Override an existing function
        >>> def custom_abbreviate(value):
        ...     return f"{value:,.0f}"
        >>> 
        >>> register_builtin_function(
        ...     'abbreviate_number_columns', 
        ...     custom_abbreviate, 
        ...     overwrite=True
        ... )
        
    Note:
        - Registered functions become immediately available in the registry
        - Functions should be stateless and side-effect free when possible
        - Consider namespacing custom functions to avoid conflicts
    """
    builtin_function_registry.register_function(name, func, overwrite)

def list_builtin_functions() -> list[str]:
    """Get a list of all registered built-in function names.
    
    Returns all function names currently available in the built-in registry.
    This includes both the default built-in functions and any custom functions
    that have been registered during runtime.
    
    Returns:
        Sorted list of function names (strings) that can be used with
        get_builtin_function() or in YAML configurations.
        
    Example:
        >>> # List all available functions
        >>> functions = list_builtin_functions()
        >>> print(f"Total functions: {len(functions)}")
        >>> for func_name in functions:
        ...     print(f"  - {func_name}")
        >>> 
        >>> # Check if a specific function is available
        >>> if 'create_dynamic_colors' in list_builtin_functions():
        ...     color_func = get_builtin_function('create_dynamic_colors')
        >>> 
        >>> # Filter functions by prefix
        >>> color_functions = [
        ...     f for f in list_builtin_functions() 
        ...     if 'color' in f
        ... ]
        >>> print(f"Color functions: {color_functions}")
        
    Note:
        - The list is sorted alphabetically for consistent ordering
        - Includes both default and dynamically registered functions
        - Function names reflect their registration keys, not the actual
          function object names
    """
    return builtin_function_registry.list_available()
