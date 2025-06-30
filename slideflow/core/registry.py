"""
Standardized registry patterns for the slideflow package.

This module provides base classes and utilities for consistent registry
implementations across all modules.
"""

import inspect
from abc import ABC
from typing import Dict, Generic, TypeVar, Type, List, Optional, Any, Callable

from slideflow.utilities.exceptions import ProviderError
from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')
K = TypeVar('K')  # Key type
V = TypeVar('V')  # Value type


class BaseRegistry(Generic[K, V], ABC):
    """
    Abstract base class for all registry implementations.
    
    Provides consistent interface and error handling for registries
    throughout the slideflow package.
    """
    
    def __init__(self, name: str = "registry"):
        """
        Initialize registry.
        
        Args:
            name: Human-readable name for this registry (used in error messages)
        """
        self._items: Dict[K, V] = {}
        self._name = name
        logger.debug(f"Initialized {name}")
    
    def register(self, key: K, item: V, overwrite: bool = False) -> None:
        """
        Register an item in the registry.
        
        Args:
            key: Unique identifier for the item
            item: Item to register
            overwrite: Whether to allow overwriting existing items
            
        Raises:
            ValueError: If key already exists and overwrite=False
        """
        if key in self._items and not overwrite:
            raise ValueError(
                f"Key '{key}' already registered in {self._name}. "
                f"Use overwrite=True to replace existing item."
            )
        
        self._items[key] = item
        logger.debug(f"Registered '{key}' in {self._name}")
    
    def get(self, key: K) -> V:
        """
        Get an item from the registry.
        
        Args:
            key: Key to look up
            
        Returns:
            The registered item
            
        Raises:
            KeyError: If key is not found
        """
        if key not in self._items:
            available = list(self._items.keys())
            raise KeyError(
                f"'{key}' not found in {self._name}. "
                f"Available: {available}"
            )
        return self._items[key]
    
    def get_optional(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """
        Get an item from the registry, returning default if not found.
        
        Args:
            key: Key to look up
            default: Default value if key not found
            
        Returns:
            The registered item or default
        """
        return self._items.get(key, default)
    
    def has(self, key: K) -> bool:
        """
        Check if a key exists in the registry.
        
        Args:
            key: Key to check
            
        Returns:
            True if key exists
        """
        return key in self._items
    
    def remove(self, key: K) -> V:
        """
        Remove an item from the registry.
        
        Args:
            key: Key to remove
            
        Returns:
            The removed item
            
        Raises:
            KeyError: If key is not found
        """
        if key not in self._items:
            raise KeyError(f"'{key}' not found in {self._name}")
        
        item = self._items.pop(key)
        logger.debug(f"Removed '{key}' from {self._name}")
        return item
    
    def list_available(self) -> List[K]:
        """
        Get list of all available keys.
        
        Returns:
            List of registered keys
        """
        return list(self._items.keys())
    
    def size(self) -> int:
        """
        Get number of registered items.
        
        Returns:
            Number of items in registry
        """
        return len(self._items)
    
    def clear(self) -> None:
        """Clear all items from the registry."""
        count = len(self._items)
        self._items.clear()
        logger.debug(f"Cleared {count} items from {self._name}")
    
    def items(self) -> Dict[K, V]:
        """
        Get a copy of all registered items.
        
        Returns:
            Dictionary of all registered items
        """
        return self._items.copy()
    
    def __contains__(self, key: K) -> bool:
        """Support 'in' operator."""
        return key in self._items
    
    def __len__(self) -> int:
        """Support len() function."""
        return len(self._items)
    
    def __repr__(self) -> str:
        """String representation of registry."""
        return f"{self.__class__.__name__}(name='{self._name}', size={len(self._items)})"


class FunctionRegistry(BaseRegistry[str, Callable]):
    """
    Registry for functions and callables.
    
    Specialized registry for managing function registrations with
    validation and helper methods for function-specific operations.
    """
    
    def __init__(self, name: str = "function_registry"):
        super().__init__(name)
    
    def register_function(self, name: str, func: Callable, overwrite: bool = False) -> None:
        """
        Register a function with validation.
        
        Args:
            name: Function name
            func: Callable to register
            overwrite: Whether to allow overwriting
            
        Raises:
            TypeError: If func is not callable
            ValueError: If name already exists and overwrite=False
        """
        if not callable(func):
            raise TypeError(f"Item '{name}' must be callable, got {type(func)}")
        
        self.register(name, func, overwrite)
    
    def call(self, name: str, *args, **kwargs) -> Any:
        """
        Call a registered function.
        
        Args:
            name: Function name
            *args: Positional arguments to pass to function
            **kwargs: Keyword arguments to pass to function
            
        Returns:
            Function result
        """
        func = self.get(name)
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error calling function '{name}': {e}")
            raise
    
    def register_module_functions(self, module, prefix: str = "", overwrite: bool = False) -> None:
        """
        Register all functions from a module.
        
        Args:
            module: Module to import functions from
            prefix: Optional prefix to add to function names
            overwrite: Whether to allow overwriting existing functions
        """
        
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith('_'):  # Skip private functions
                full_name = f"{prefix}{name}" if prefix else name
                self.register_function(full_name, obj, overwrite)
                
        logger.debug(f"Registered functions from module {module.__name__}")


class ClassRegistry(BaseRegistry[str, Type[T]]):
    """
    Registry for classes with factory capabilities.
    
    Specialized registry for managing class registrations with
    factory methods and instance creation helpers.
    """
    
    def __init__(self, name: str = "class_registry", base_class: Optional[Type[T]] = None):
        """
        Initialize class registry.
        
        Args:
            name: Registry name
            base_class: Optional base class for type validation
        """
        super().__init__(name)
        self._base_class = base_class
    
    def register_class(self, name: str, cls: Type[T], overwrite: bool = False) -> None:
        """
        Register a class with validation.
        
        Args:
            name: Class name/identifier
            cls: Class to register
            overwrite: Whether to allow overwriting
            
        Raises:
            TypeError: If cls is not a class or doesn't inherit from base_class
            ValueError: If name already exists and overwrite=False
        """
        if not isinstance(cls, type):
            raise TypeError(f"Item '{name}' must be a class, got {type(cls)}")
        
        if self._base_class and not issubclass(cls, self._base_class):
            raise TypeError(
                f"Class '{name}' must inherit from {self._base_class.__name__}, "
                f"got {cls.__name__}"
            )
        
        self.register(name, cls, overwrite)
    
    def create_instance(self, name: str, *args, **kwargs) -> T:
        """
        Create an instance of a registered class.
        
        Args:
            name: Class name
            *args: Positional arguments for class constructor
            **kwargs: Keyword arguments for class constructor
            
        Returns:
            Instance of the registered class
        """
        cls = self.get(name)
        try:
            return cls(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating instance of '{name}': {e}")
            raise
    
    def get_class(self, name: str) -> Type[T]:
        """
        Get a registered class (alias for get() with better naming).
        
        Args:
            name: Class name
            
        Returns:
            The registered class
        """
        return self.get(name)


class ProviderRegistry(ClassRegistry):
    """
    Specialized registry for provider classes.
    
    Extends ClassRegistry with provider-specific error handling
    and convenience methods.
    """
    
    def __init__(self, name: str = "provider_registry", base_class: Optional[Type] = None):
        super().__init__(name, base_class)
    
    def get_provider_class(self, provider_name: str) -> Type:
        """
        Get provider class by name with provider-specific error handling.
        
        Args:
            provider_name: Name of the provider
            
        Returns:
            Provider class
            
        Raises:
            ProviderError: If provider name is not found
        """
        try:
            return self.get(provider_name)
        except KeyError:
            available = ", ".join(self.list_available())
            raise ProviderError(
                f"Unknown provider: {provider_name}. Available: {available}"
            )
    
    def create_provider(self, provider_name: str, *args, **kwargs) -> Any:
        """
        Create a provider instance.
        
        Args:
            provider_name: Name of the provider
            *args: Constructor arguments
            **kwargs: Constructor keyword arguments
            
        Returns:
            Provider instance
            
        Raises:
            ProviderError: If provider creation fails
        """
        try:
            return self.create_instance(provider_name, *args, **kwargs)
        except Exception as e:
            raise ProviderError(f"Failed to create provider '{provider_name}': {e}") from e


# Utility functions for creating common registry types
def create_function_registry(name: str = "functions") -> FunctionRegistry:
    """Create a new function registry."""
    return FunctionRegistry(name)


def create_class_registry(name: str = "classes", base_class: Optional[Type[T]] = None) -> ClassRegistry[T]:
    """Create a new class registry."""
    return ClassRegistry(name, base_class)


def create_provider_registry(name: str = "providers", base_class: Optional[Type] = None) -> ProviderRegistry:
    """Create a new provider registry."""
    return ProviderRegistry(name, base_class)