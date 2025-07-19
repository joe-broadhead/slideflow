"""Core utilities and foundational patterns for Slideflow.

This module provides the fundamental abstractions and design patterns that
underpin the Slideflow architecture. It contains base classes, registry
systems, and common utilities that are used throughout the entire package
to ensure consistency and extensibility.

Key Components:
    - Registry system for plugins and extensions
    - Base classes for type-safe operations
    - Factory patterns for object creation
    - Common interfaces and protocols

The core module is designed to be:
    - Framework-agnostic: Can be used with different presentation providers
    - Extensible: Easy to add new functionality through registries
    - Type-safe: Comprehensive type annotations and validation
    - Consistent: Standardized patterns across all modules

Registry System:
    The registry system provides a standardized way to register and discover
    functions, classes, and providers. This enables a plugin architecture
    where users can extend Slideflow with custom functionality.

Example:
    Using the registry system::
    
        from slideflow.core.registry import create_function_registry
        
        # Create a custom registry
        my_registry = create_function_registry("transformations")
        
        # Register functions
        my_registry.register_function("capitalize", str.upper)
        
        # Use registered functions
        func = my_registry.get("capitalize")
        result = func("hello")  # "HELLO"

Attributes:
    BaseRegistry: Abstract base class for all registry implementations
    FunctionRegistry: Registry specialized for callable functions
    ClassRegistry: Registry specialized for class types and constructors
"""

from slideflow.core.registry import BaseRegistry, FunctionRegistry, ClassRegistry

__all__ = [
    "BaseRegistry",
    "FunctionRegistry", 
    "ClassRegistry",
]
