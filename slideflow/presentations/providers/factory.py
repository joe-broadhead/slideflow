"""Factory functions and registry for creating presentation providers in Slideflow.

This module provides factory functions and a registry system for instantiating
presentation providers with type safety and consistent error handling. The factory
pattern allows for dynamic provider creation based on configuration while
maintaining compile-time type safety and extensibility.

The factory system provides:
    - Registry-based provider management using core registry system
    - Type-safe provider instantiation with configuration validation
    - Centralized provider registration for extensibility
    - Consistent error handling for unknown providers
    - Configuration parameter validation and transformation

Example:
    Using the factory to create providers:
    
    >>> from slideflow.presentations.providers.factory import ProviderFactory
    >>> from slideflow.presentations.config import ProviderConfig
    >>> 
    >>> # Create a configuration
    >>> config = ProviderConfig(
    ...     type="google_slides",
    ...     config={"credentials": "/path/to/creds.json"}
    ... )
    >>> 
    >>> # Create provider using factory
    >>> provider = ProviderFactory.create_provider(config)
    >>> 
    >>> # Use the provider
    >>> presentation_id = provider.create_presentation("Monthly Report")
"""

from typing import Type
from slideflow.presentations.config import ProviderConfig
from slideflow.core.registry import create_class_registry
from slideflow.utilities.exceptions import ConfigurationError
from slideflow.presentations.providers.base import PresentationProvider, PresentationProviderConfig
from slideflow.presentations.providers.google_slides import GoogleSlidesProvider, GoogleSlidesProviderConfig

provider_registry = create_class_registry("presentation_providers", PresentationProvider)
config_registry = create_class_registry("provider_configs", PresentationProviderConfig)

provider_registry.register_class("google_slides", GoogleSlidesProvider)
config_registry.register_class("google_slides", GoogleSlidesProviderConfig)

class ProviderFactory:
    """Factory for creating and managing presentation provider instances.
    
    This factory class provides a centralized registry system for presentation
    providers, enabling dynamic provider creation, registration, and management.
    It uses the core registry system to maintain type safety and extensibility.
    
    The factory maintains separate registries for provider classes and their
    corresponding configuration classes, ensuring that providers can be
    instantiated with properly validated configurations.
    
    Example:
        Registering a custom provider:
        
        >>> class MyProvider(PresentationProvider):
        ...     pass
        >>> 
        >>> class MyProviderConfig(PresentationProviderConfig):
        ...     provider_type: str = "my_provider"
        >>> 
        >>> ProviderFactory.register_provider(
        ...     "my_provider",
        ...     MyProvider,
        ...     MyProviderConfig
        ... )
    """
    
    @classmethod
    def register_provider(
        cls, 
        provider_type: str, 
        provider_class: Type[PresentationProvider],
        config_class: Type[PresentationProviderConfig]
    ) -> None:
        """Register a new presentation provider with the factory.
        
        Adds a provider implementation and its configuration class to the factory
        registries, making it available for instantiation via create_provider().
        
        Args:
            provider_type: Unique string identifier for the provider type.
                This will be used in configurations to specify which provider to use.
            provider_class: The provider implementation class that inherits from
                PresentationProvider and implements all required abstract methods.
            config_class: The configuration class that inherits from
                PresentationProviderConfig and defines provider-specific settings.
                
        Example:
            >>> ProviderFactory.register_provider(
            ...     "my_platform",
            ...     MyPlatformProvider,
            ...     MyPlatformConfig
            ... )
            >>> # Now "my_platform" can be used in configurations
        """
        provider_registry.register_class(provider_type, provider_class, overwrite = True)
        config_registry.register_class(provider_type, config_class, overwrite = True)

    @classmethod
    def create_provider(cls, config: ProviderConfig) -> PresentationProvider:
        """Create a presentation provider instance from configuration.
        
        Creates and configures a presentation provider based on the provided
        configuration. This method handles the lookup of the appropriate provider
        class, configuration validation, and provider instantiation.
        
        Args:
            config: ProviderConfig object containing the provider type and
                provider-specific configuration parameters.
            
        Returns:
            Fully configured and instantiated presentation provider ready for use.
            The returned provider will be properly typed as PresentationProvider
            but will be the specific implementation requested.
            
        Raises:
            ConfigurationError: If the specified provider type is not registered
                or if the configuration parameters are invalid.
            ValidationError: If the provider-specific configuration fails validation.
            
        Example:
            >>> from slideflow.presentations.config import ProviderConfig
            >>> 
            >>> # Create configuration
            >>> config = ProviderConfig(
            ...     type="google_slides",
            ...     config={
            ...         "credentials_path": "/path/to/service_account.json",
            ...         "template_id": "template_123"
            ...     }
            ... )
            >>> 
            >>> # Create provider
            >>> provider = ProviderFactory.create_provider(config)
            >>> 
            >>> # Use provider
            >>> presentation_id = provider.create_presentation("My Report")
        """
        provider_type = config.type
        
        if not provider_registry.has(provider_type):
            available = provider_registry.list_available()
            raise ConfigurationError(
                f"Unsupported provider type '{provider_type}'. "
                f"Available providers: {available}"
            )

        provider_class = provider_registry.get_class(provider_type)
        config_class = config_registry.get_class(provider_type)

        provider_config = config_class(**config.config)

        return provider_class(provider_config)
    
    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of all registered provider types.
        
        Returns a list of provider type identifiers that are currently registered
        with the factory and available for use in configurations.
        
        Returns:
            List of provider type strings that can be used in ProviderConfig.type.
            
        Example:
            >>> available = ProviderFactory.get_available_providers()
            >>> print(f"Available providers: {available}")
            >>> # Output: ['google_slides', 'my_custom_provider']
        """
        return provider_registry.list_available()
    
    @classmethod
    def get_provider_class(cls, provider_type: str) -> Type[PresentationProvider]:
        """Get a registered provider class by type identifier.
        
        Retrieves the provider implementation class for the specified provider type.
        This is useful for advanced scenarios where direct class access is needed.
        
        Args:
            provider_type: Provider type identifier that was used during registration.
            
        Returns:
            The provider implementation class (not an instance).
            
        Raises:
            KeyError: If the provider type is not registered.
            
        Example:
            >>> provider_class = ProviderFactory.get_provider_class("google_slides")
            >>> print(provider_class.__name__)  # "GoogleSlidesProvider"
        """
        return provider_registry.get_class(provider_type)
    
    @classmethod
    def get_config_class(cls, provider_type: str) -> Type[PresentationProviderConfig]:
        """Get a registered provider configuration class by type identifier.
        
        Retrieves the configuration class for the specified provider type.
        This is useful for creating configurations programmatically or for
        validation purposes.
        
        Args:
            provider_type: Provider type identifier that was used during registration.
            
        Returns:
            The provider configuration class (not an instance).
            
        Raises:
            KeyError: If the provider type is not registered.
            
        Example:
            >>> config_class = ProviderFactory.get_config_class("google_slides")
            >>> print(config_class.__name__)  # "GoogleSlidesProviderConfig"
            >>> 
            >>> # Create configuration instance
            >>> config = config_class(
            ...     provider_type="google_slides",
            ...     credentials_path="/path/to/creds.json"
            ... )
        """
        return config_registry.get_class(provider_type)
