"""
Presentation Provider Factory

Factory for creating presentation provider instances based on configuration.
Supports multiple presentation platforms and maintains backward compatibility.
"""

from typing import Type
from slideflow.core.registry import create_class_registry
from slideflow.presentations.providers.base import PresentationProvider, PresentationProviderConfig
from slideflow.presentations.providers.google_slides import GoogleSlidesProvider, GoogleSlidesProviderConfig
from slideflow.presentations.config import ProviderConfig
from slideflow.utilities.exceptions import ConfigurationError


# Create registries for providers and their configurations
provider_registry = create_class_registry("presentation_providers", PresentationProvider)
config_registry = create_class_registry("provider_configs", PresentationProviderConfig)

# Register built-in providers
provider_registry.register_class("google_slides", GoogleSlidesProvider)
config_registry.register_class("google_slides", GoogleSlidesProviderConfig)


class ProviderFactory:
    """Factory for creating presentation provider instances."""
    
    @classmethod
    def register_provider(cls, 
                         provider_type: str, 
                         provider_class: Type[PresentationProvider],
                         config_class: Type[PresentationProviderConfig]) -> None:
        """Register a new presentation provider.
        
        Args:
            provider_type: Unique identifier for the provider
            provider_class: Provider implementation class
            config_class: Provider configuration class
        """
        provider_registry.register_class(provider_type, provider_class, overwrite=True)
        config_registry.register_class(provider_type, config_class, overwrite=True)
    
    @classmethod
    def create_provider(cls, config: ProviderConfig) -> PresentationProvider:
        """Create a presentation provider from configuration.
        
        Args:
            config: Provider configuration
            
        Returns:
            Instantiated presentation provider
            
        Raises:
            ConfigurationError: If provider type is not supported
        """
        provider_type = config.type
        
        if not provider_registry.has(provider_type):
            available = provider_registry.list_available()
            raise ConfigurationError(
                f"Unsupported provider type '{provider_type}'. "
                f"Available providers: {available}"
            )
        
        # Get the provider and config classes
        provider_class = provider_registry.get_class(provider_type)
        config_class = config_registry.get_class(provider_type)
        
        # Create provider-specific config
        provider_config = config_class(**config.config)
        
        # Instantiate and return provider
        return provider_class(provider_config)
    
    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available provider types.
        
        Returns:
            List of provider type strings
        """
        return provider_registry.list_available()
    
    @classmethod
    def get_provider_class(cls, provider_type: str) -> Type[PresentationProvider]:
        """Get a provider class by type.
        
        Args:
            provider_type: Provider type identifier
            
        Returns:
            Provider class
        """
        return provider_registry.get_class(provider_type)
    
    @classmethod
    def get_config_class(cls, provider_type: str) -> Type[PresentationProviderConfig]:
        """Get a provider config class by type.
        
        Args:
            provider_type: Provider type identifier
            
        Returns:
            Provider configuration class
        """
        return config_registry.get_class(provider_type)