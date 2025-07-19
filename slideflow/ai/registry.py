"""AI Provider registry for managing and resolving AI providers.

This module provides a registry system for AI providers, allowing dynamic
registration and discovery of text generation providers. It includes functions
for registering new providers, retrieving provider classes, and creating
provider instances.

The registry supports:
    - Registration of built-in providers (OpenAI, Gemini)
    - Dynamic registration of custom providers
    - Provider discovery and listing
    - Factory functions for provider instantiation

Example:
    Registering and using a custom provider::
    
        from slideflow.ai import register_provider, create_provider
        
        class CustomProvider:
            def generate_text(self, prompt: str, **kwargs) -> str:
                return f"Custom response to: {prompt}"
        
        # Register the provider
        register_provider("custom", CustomProvider)
        
        # Create and use
        provider = create_provider("custom")
        text = provider.generate_text("Hello")

Attributes:
    ai_provider_registry: The global registry instance for AI providers.
"""

from typing import Type
from slideflow.core.registry import create_provider_registry
from slideflow.ai.providers import AIProvider, OpenAIProvider, GeminiProvider

ai_provider_registry = create_provider_registry("ai_providers", AIProvider)

ai_provider_registry.register_class("openai", OpenAIProvider)
ai_provider_registry.register_class("gemini", GeminiProvider)

def get_provider_class(provider_name: str) -> Type[AIProvider]:
    """Get provider class by name from the registry.
    
    This function retrieves the class associated with a registered provider name.
    It's useful when you need the class itself rather than an instance.
    
    Args:
        provider_name: Name of the provider (e.g., "openai", "gemini", or custom names).
            Case-insensitive.
        
    Returns:
        The provider class that implements the AIProvider protocol.
        
    Raises:
        ProviderError: If the provider name is not found in the registry.
        
    Example:
        >>> from slideflow.ai import get_provider_class
        >>> OpenAIProvider = get_provider_class("openai")
        >>> provider = OpenAIProvider(model="gpt-4")
    """
    return ai_provider_registry.get_provider_class(provider_name)

def register_provider(name: str, provider_class: Type[AIProvider], overwrite: bool = False) -> None:
    """Register a new AI provider in the global registry.
    
    This function allows registration of custom AI providers that implement
    the AIProvider protocol. Once registered, providers can be instantiated
    using create_provider() or retrieved using get_provider_class().
    
    Args:
        name: Unique identifier for the provider. This name will be used
            to retrieve the provider later. Case-insensitive.
        provider_class: The provider class that implements the AIProvider protocol.
            Must have a generate_text method.
        overwrite: If True, allows overwriting an existing provider with the same name.
            If False (default), raises an error when attempting to register
            a duplicate name.
            
    Raises:
        ValueError: If a provider with the same name already exists and overwrite=False.
        TypeError: If the provider_class doesn't implement the AIProvider protocol.
        
    Example:
        >>> from slideflow.ai import register_provider
        >>> 
        >>> class AnthropicProvider:
        >>>     def generate_text(self, prompt: str, **kwargs) -> str:
        >>>         # Implementation here
        >>>         return "Generated text"
        >>> 
        >>> register_provider("anthropic", AnthropicProvider)
    """
    ai_provider_registry.register_class(name, provider_class, overwrite)

def list_available_providers() -> list[str]:
    """Get list of all registered AI provider names.
    
    This function returns the names of all providers currently registered
    in the global AI provider registry, including both built-in providers
    and any custom providers that have been registered.
    
    Returns:
        List of provider names (strings) that can be used with create_provider()
        or get_provider_class(). The list includes built-in providers like
        'openai' and 'gemini', plus any custom registered providers.
        
    Example:
        >>> from slideflow.ai import list_available_providers
        >>> providers = list_available_providers()
        >>> print(providers)
        ['openai', 'gemini', 'custom']
    """
    return ai_provider_registry.list_available()

def create_provider(provider_name: str, *args, **kwargs) -> AIProvider:
    """Create an AI provider instance from a registered provider name.
    
    This is the primary factory function for creating AI provider instances.
    It looks up the provider class in the registry and instantiates it with
    the provided arguments.
    
    Args:
        provider_name: Name of the registered provider (e.g., "openai", "gemini").
            Case-insensitive.
        *args: Positional arguments to pass to the provider's constructor.
        **kwargs: Keyword arguments to pass to the provider's constructor.
            Common kwargs include:
            - model: The AI model to use
            - temperature: Controls randomness
            - max_tokens: Maximum tokens to generate
            - For Gemini with Vertex AI: vertex=True, project="...", location="..."
        
    Returns:
        An instance of the requested provider that implements the AIProvider protocol.
        
    Raises:
        ProviderError: If the provider name is not found in the registry.
        TypeError: If the provider constructor arguments are invalid.
        
    Example:
        >>> from slideflow.ai import create_provider
        >>> 
        >>> # Create OpenAI provider
        >>> openai = create_provider("openai", model="gpt-4", temperature=0.7)
        >>> 
        >>> # Create Gemini provider with Vertex AI
        >>> gemini = create_provider(
        >>>     "gemini",
        >>>     model="gemini-pro",
        >>>     vertex=True,
        >>>     project="my-project",
        >>>     location="us-central1"
        >>> )
    """
    return ai_provider_registry.create_provider(provider_name, *args, **kwargs)
