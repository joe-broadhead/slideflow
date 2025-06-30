"""
SlideFlow Builtins Registry

Pre-built function registry containing common data transformations and utilities.
Users can import this registry and extend it with their custom functions.

Usage:
    from slideflow.builtins.registry import builtin_function_registry
    
    # Use the registry directly
    func = builtin_function_registry.get('create_dynamic_colors')
    
    # Or get all functions as a dict for backward compatibility
    builtin_registry = builtin_function_registry.items()
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

# Create the standardized function registry
builtin_function_registry = create_function_registry("builtin_functions")

# Register all built-in functions
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
    """Get a built-in function by name."""
    return builtin_function_registry.get(name)


def register_builtin_function(name: str, func, overwrite: bool = False) -> None:
    """Register a new built-in function."""
    builtin_function_registry.register_function(name, func, overwrite)


def list_builtin_functions() -> list[str]:
    """Get list of available built-in function names."""
    return builtin_function_registry.list_available()