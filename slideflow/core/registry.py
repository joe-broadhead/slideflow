"""Standardized registry system for extensible component management.

This module provides a comprehensive registry system that enables plugin-style
architecture throughout Slideflow. The registry system allows for type-safe
registration and discovery of functions, classes, and providers, enabling
users to extend Slideflow with custom functionality.

The registry system is built around three main concepts:
    - BaseRegistry: Generic foundation for all registry types
    - Specialized registries: Function, Class, and Provider registries
    - Factory functions: Convenient creation of common registry types

Key Features:
    - Type safety with generic type parameters
    - Consistent error handling and logging
    - Overwrite protection with explicit control
    - Inspection and introspection capabilities
    - Module-level function registration
    - Provider-specific error handling

Architecture:
    The registry system uses a hierarchical design where BaseRegistry provides
    the core functionality, and specialized registries add domain-specific
    features and validation.

Example:
    Basic registry usage::
    
        from slideflow.core.registry import create_function_registry
        
        # Create a custom transformation registry
        transforms = create_function_registry("data_transforms")
        
        # Register functions
        transforms.register_function("uppercase", str.upper)
        transforms.register_function("reverse", lambda x: x[::-1])
        
        # Use registered functions
        func = transforms.get("uppercase")
        result = func("hello")  # "HELLO"
        
        # Call directly
        result = transforms.call("reverse", "hello")  # "olleh"
        
    Provider registration::
    
        from slideflow.core.registry import create_provider_registry
        
        # Create provider registry with base class validation
        providers = create_provider_registry("ai_providers", AIProvider)
        
        # Register provider classes
        providers.register_class("openai", OpenAIProvider)
        providers.register_class("gemini", GeminiProvider)
        
        # Create instances
        openai = providers.create_provider("openai", api_key="...")
"""

import inspect
from abc import ABC
from typing import Dict, Generic, TypeVar, Type, List, Optional, Any, Callable

from slideflow.utilities.logging import get_logger
from slideflow.utilities.exceptions import ProviderError

logger = get_logger(__name__)

T = TypeVar('T')
K = TypeVar('K')  # Key type
V = TypeVar('V')  # Value type

class BaseRegistry(Generic[K, V], ABC):
    """Abstract base class for all registry implementations.
    
    Provides a consistent, type-safe interface for registering and retrieving
    items of any type. This class serves as the foundation for all specialized
    registries in Slideflow, ensuring consistent behavior and error handling.
    
    The registry is generic over key type K and value type V, allowing for
    different key-value combinations while maintaining type safety.
    
    Features:
        - Type-safe operations with generic parameters
        - Overwrite protection with explicit control
        - Comprehensive error handling with helpful messages
        - Logging integration for debugging and monitoring
        - Dictionary-like interface with additional safety
        - Introspection capabilities
    
    Type Parameters:
        K: Type of keys used to identify registry items
        V: Type of values stored in the registry
        
    Example:
        >>> # Create a simple string-to-function registry
        >>> class MyRegistry(BaseRegistry[str, Callable]):
        ...     pass
        >>> 
        >>> registry = MyRegistry("my_functions")
        >>> registry.register("add", lambda x, y: x + y)
        >>> func = registry.get("add")
        >>> result = func(2, 3)  # 5
    """
    
    def __init__(self, name: str = "registry"):
        """Initialize a new registry instance.
        
        Args:
            name: Human-readable name for this registry. Used in error messages
                and logging to help identify which registry is being used.
                Defaults to "registry".
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
    """Registry specialized for managing callable functions and methods.
    
    Extends BaseRegistry with function-specific validation, direct calling
    capabilities, and module-level registration utilities. This registry
    ensures that only callable objects are stored and provides convenient
    methods for function execution.
    
    Key Features:
        - Callable validation on registration
        - Direct function invocation with error handling
        - Bulk registration from modules
        - Function signature preservation
        - Enhanced error reporting for function calls
        
    Example:
        >>> registry = FunctionRegistry("transforms")
        >>> 
        >>> # Register individual functions
        >>> registry.register_function("upper", str.upper)
        >>> registry.register_function("reverse", lambda s: s[::-1])
        >>> 
        >>> # Call functions directly
        >>> result = registry.call("upper", "hello")  # "HELLO"
        >>> 
        >>> # Register all functions from a module
        >>> import math
        >>> registry.register_module_functions(math, prefix="math_")
        >>> result = registry.call("math_sqrt", 16)  # 4.0
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
    """Registry specialized for managing class types with factory capabilities.
    
    Extends BaseRegistry to provide type-safe class registration and instance
    creation. This registry can optionally enforce inheritance from a base
    class, providing compile-time and runtime type safety.
    
    Key Features:
        - Class type validation on registration
        - Optional base class inheritance checking
        - Factory method for instance creation
        - Type-safe class retrieval
        - Enhanced error handling for instantiation
        
    Type Parameters:
        T: Base type that registered classes must inherit from (optional)
        
    Example:
        >>> # Registry for any class type
        >>> registry = ClassRegistry[Any]("processors")
        >>> registry.register_class("list", list)
        >>> registry.register_class("dict", dict)
        >>> 
        >>> # Create instances
        >>> my_list = registry.create_instance("list", [1, 2, 3])
        >>> my_dict = registry.create_instance("dict", {"a": 1})
        >>> 
        >>> # Registry with base class validation
        >>> class DataProcessor:
        ...     pass
        >>> 
        >>> class CSVProcessor(DataProcessor):
        ...     def __init__(self, delimiter=","):
        ...         self.delimiter = delimiter
        >>> 
        >>> processors = ClassRegistry("processors", DataProcessor)
        >>> processors.register_class("csv", CSVProcessor)
        >>> csv_proc = processors.create_instance("csv", delimiter=";")
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
    """Registry specialized for provider pattern implementations.
    
    Extends ClassRegistry with provider-specific error handling and naming
    conventions. This registry is designed for managing pluggable provider
    implementations (like AI providers, presentation providers, etc.) with
    enhanced error reporting using ProviderError exceptions.
    
    Key Features:
        - Provider-specific error handling with ProviderError
        - Descriptive error messages listing available providers
        - Consistent naming conventions for provider operations
        - Enhanced exception context for troubleshooting
        
    Example:
        >>> from slideflow.ai.providers import AIProvider
        >>> 
        >>> # Create provider registry with base class validation
        >>> providers = ProviderRegistry("ai_providers", AIProvider)
        >>> 
        >>> # Register provider classes
        >>> providers.register_class("openai", OpenAIProvider)
        >>> providers.register_class("gemini", GeminiProvider)
        >>> 
        >>> # Get provider class
        >>> provider_cls = providers.get_provider_class("openai")
        >>> 
        >>> # Create provider instance
        >>> provider = providers.create_provider("openai", api_key="sk-...")
        >>> 
        >>> # Error handling shows available providers
        >>> try:
        ...     providers.get_provider_class("unknown")
        ... except ProviderError as e:
        ...     print(e)  # "Unknown provider: unknown. Available: openai, gemini"
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

# Factory functions for creating common registry types

def create_function_registry(name: str = "functions") -> FunctionRegistry:
    """Create a new function registry with the specified name.
    
    Convenience factory function for creating FunctionRegistry instances
    with a descriptive name for logging and error reporting.
    
    Args:
        name: Human-readable name for the registry. Used in error messages
            and logging. Defaults to "functions".
            
    Returns:
        New FunctionRegistry instance ready for function registration.
        
    Example:
        >>> transforms = create_function_registry("data_transforms")
        >>> transforms.register_function("normalize", lambda x: x.lower())
    """
    return FunctionRegistry(name)

def create_class_registry(name: str = "classes", base_class: Optional[Type[T]] = None) -> ClassRegistry[T]:
    """Create a new class registry with optional base class validation.
    
    Convenience factory function for creating ClassRegistry instances
    with optional type safety through base class inheritance checking.
    
    Args:
        name: Human-readable name for the registry. Used in error messages
            and logging. Defaults to "classes".
        base_class: Optional base class that all registered classes must
            inherit from. Provides compile-time and runtime type safety.
            
    Returns:
        New ClassRegistry instance ready for class registration.
        
    Example:
        >>> # Registry for any class
        >>> processors = create_class_registry("processors")
        >>> 
        >>> # Registry with base class validation
        >>> from slideflow.data.connectors import DataConnector
        >>> connectors = create_class_registry("connectors", DataConnector)
    """
    return ClassRegistry(name, base_class)

def create_provider_registry(name: str = "providers", base_class: Optional[Type] = None) -> ProviderRegistry:
    """Create a new provider registry with enhanced error handling.
    
    Convenience factory function for creating ProviderRegistry instances
    designed for the provider pattern with specialized error reporting.
    
    Args:
        name: Human-readable name for the registry. Used in error messages
            and logging. Defaults to "providers".
        base_class: Optional base class that all registered provider classes
            must inherit from. Provides compile-time and runtime type safety.
            
    Returns:
        New ProviderRegistry instance ready for provider registration.
        
    Example:
        >>> from slideflow.ai.providers import AIProvider
        >>> ai_providers = create_provider_registry("ai_providers", AIProvider)
        >>> ai_providers.register_class("openai", OpenAIProvider)
    """
    return ProviderRegistry(name, base_class)
