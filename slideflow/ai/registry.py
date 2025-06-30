"""AI Provider registry for resolving provider strings to classes."""
from typing import Type
from slideflow.ai.providers import AIProvider, OpenAIProvider, GeminiProvider
from slideflow.core.registry import create_provider_registry

# Create the standardized AI provider registry
ai_provider_registry = create_provider_registry("ai_providers", AIProvider)

# Register built-in providers
ai_provider_registry.register_class("openai", OpenAIProvider)
ai_provider_registry.register_class("gemini", GeminiProvider)


def get_provider_class(provider_name: str) -> Type[AIProvider]:
    """Get provider class by name.
    
    Args:
        provider_name: Name of the provider (e.g. "openai", "gemini")
        
    Returns:
        Provider class
        
    Raises:
        ProviderError: If provider name is not found
    """
    return ai_provider_registry.get_provider_class(provider_name)


def register_provider(name: str, provider_class: Type[AIProvider], overwrite: bool = False) -> None:
    """Register a new AI provider.
    
    Args:
        name: Provider name
        provider_class: Provider class that implements AIProvider protocol
        overwrite: Whether to overwrite existing provider
    """
    ai_provider_registry.register_class(name, provider_class, overwrite)


def list_available_providers() -> list[str]:
    """Get list of available AI provider names."""
    return ai_provider_registry.list_available()


def create_provider(provider_name: str, *args, **kwargs) -> AIProvider:
    """Create an AI provider instance.
    
    Args:
        provider_name: Name of the provider
        *args: Constructor arguments
        **kwargs: Constructor keyword arguments
        
    Returns:
        Provider instance
    """
    return ai_provider_registry.create_provider(provider_name, *args, **kwargs)